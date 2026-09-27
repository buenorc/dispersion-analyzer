# -*- coding: utf-8 -*-
"""
Leitura de arquivos de dados (datalogger do condutivímetro, CSV, TXT, XLSX).

O arquivo gravado pelo condutivímetro da Aula 07 tem o formato:

    data_hora   temp(C) tensao(V)   cond(uS/cm)
    30/09/2026 14:05:12 23.81   0.162   137.61

e o cabeçalho é regravado toda vez que o equipamento é religado. Este módulo
lida com isso, com separadores ( tab ; , espaço ), vírgula decimal e com
planilhas Excel. Também aceita séries em que o tempo já está em segundos.
"""
from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

TIME_KEYS = ("data_hora", "datahora", "datetime", "date", "data", "hora",
             "time", "tempo", "timestamp", "t(s)", "t_s", "seg")
EC_KEYS = ("cond", "ec", "us/cm", "µs", "us_cm", "condut", "spc", "sc")
CONC_KEYS = ("conc", "sal", "nacl", "kg/m", "g/l", "mg/l")
TEMP_KEYS = ("temp", "°c", "(c)")


# --------------------------------------------------------------------------
# leitura bruta
# --------------------------------------------------------------------------
def _sniff_sep(lines):
    sample = [l for l in lines[:50] if l.strip()]
    for sep in ("\t", ";", ","):
        counts = np.array([l.count(sep) for l in sample])
        if len(counts) and np.median(counts) >= 1 and \
                np.mean(counts == np.median(counts)) >= 0.8:
            return sep
    # separado por espaços: não separa "dd/mm/aaaa hh:mm:ss"
    return r"\s+(?!\d{1,2}:\d{2})"


def _is_number(s):
    try:
        float(str(s).replace(",", "."))
        return True
    except ValueError:
        return False


def _is_datetime_like(s):
    return bool(re.match(r"^\s*\d{1,4}[/\-.]\d{1,2}[/\-.]\d{1,4}", str(s))) or \
        bool(re.match(r"^\s*\d{1,2}:\d{2}(:\d{2})?", str(s)))


def read_table(path: str, sheet=None) -> pd.DataFrame:
    """Lê um arquivo tabular qualquer e devolve um DataFrame com cabeçalho.

    - .xlsx/.xls/.xlsm/.ods: pandas.read_excel (sheet = nome ou índice)
    - demais: texto; detecta separador, vírgula decimal e cabeçalhos repetidos.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls", ".xlsm", ".ods"):
        df = pd.read_excel(path, sheet_name=0 if sheet in (None, "") else sheet)
        df = df.dropna(how="all").dropna(axis=1, how="all")
        return _clean_df(df)

    raw = None
    for enc in ("utf-8-sig", "latin-1", "cp1252"):
        try:
            with open(path, "r", encoding=enc) as f:
                raw = f.read()
            break
        except UnicodeDecodeError:
            continue
    if raw is None:
        raise IOError(f"Não foi possível ler {path}")
    lines = [l.rstrip("\r\n") for l in raw.splitlines() if l.strip()]
    if not lines:
        raise ValueError(f"Arquivo vazio: {path}")

    sep = _sniff_sep(lines)
    split = (lambda l: re.split(sep, l.strip())) if len(sep) > 2 else (lambda l: l.split(sep))

    # cabeçalho = primeira linha cujo primeiro campo não é número/data
    first = split(lines[0])
    has_header = not (_is_number(first[0]) or _is_datetime_like(first[0]))
    if has_header:
        header = [h.strip() for h in first]
        body = lines[1:]
    else:
        header = [f"col{i+1}" for i in range(len(first))]
        body = lines

    rows = []
    for l in body:
        parts = [p.strip() for p in split(l)]
        # cabeçalho repetido (equipamento religado) ou linhas de mensagens
        if not parts or not (_is_number(parts[0]) or _is_datetime_like(parts[0])):
            continue
        if len(parts) < len(header):
            parts += [""] * (len(header) - len(parts))
        rows.append(parts[:len(header)])
    df = pd.DataFrame(rows, columns=header)
    return _clean_df(df)


def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    for c in df.columns:
        if df[c].dtype == object:
            s = df[c].astype(str).str.strip()
            # separa data/hora de números: só converte colunas numéricas
            num = pd.to_numeric(s.str.replace(",", ".", regex=False), errors="coerce")
            if num.notna().mean() > 0.9 and not s.head(20).map(_is_datetime_like).any():
                df[c] = num
    return df


# --------------------------------------------------------------------------
# identificação de colunas
# --------------------------------------------------------------------------
def _match(col, keys):
    c = str(col).lower()
    return any(k in c for k in keys)


def guess_columns(df: pd.DataFrame):
    """Devolve (col_tempo, col_valor, tipo) com tipo = 'ec' ou 'conc'."""
    cols = list(df.columns)
    tcol = next((c for c in cols if _match(c, TIME_KEYS)), None)
    if tcol is None:
        # primeira coluna com cara de data ou crescente
        for c in cols:
            s = df[c]
            if s.dtype == object and s.head(10).map(_is_datetime_like).all():
                tcol = c
                break
        if tcol is None:
            tcol = cols[0]
    vcol, kind = None, "ec"
    for c in cols:
        if c == tcol:
            continue
        if _match(c, EC_KEYS) and not _is_temp(c):
            vcol, kind = c, "ec"
            break
    if vcol is None:
        for c in cols:
            if c != tcol and _match(c, CONC_KEYS):
                vcol, kind = c, "conc"
                break
    if vcol is None:
        numeric = [c for c in cols if c != tcol and pd.api.types.is_numeric_dtype(df[c])]
        vcol = numeric[-1] if numeric else cols[-1]
    return tcol, vcol, kind


def _is_temp(col):
    c = str(col).lower()
    return bool(re.search(r"temp(?!o)|°c|\(c\)|wtemp", c))


def guess_temp_column(df):
    return next((c for c in df.columns if _is_temp(c)), None)


# --------------------------------------------------------------------------
# conversão para série temporal
# --------------------------------------------------------------------------
@dataclass
class RawSeries:
    t: np.ndarray             # tempo (s) relativo ao lançamento (ou ao 1º dado)
    value: np.ndarray         # condutividade (µS/cm) ou concentração (kg/m³)
    temp: np.ndarray | None   # temperatura da água (°C), se houver
    t_abs: pd.DatetimeIndex | None  # data/hora absoluta, se houver
    relative_to_injection: bool


def parse_time(series: pd.Series, dayfirst=True):
    """Converte a coluna de tempo. Devolve (segundos, datetimes|None)."""
    s = series
    if pd.api.types.is_numeric_dtype(s):
        return s.to_numpy(float), None
    if pd.api.types.is_datetime64_any_dtype(s):
        dt = pd.to_datetime(s)
    else:
        st = s.astype(str).str.strip()
        if st.map(_is_number).all():
            return pd.to_numeric(st.str.replace(",", "."), errors="coerce").to_numpy(float), None
        # somente hora (hh:mm:ss)
        if st.str.match(r"^\d{1,2}:\d{2}(:\d{2}(\.\d+)?)?$").all():
            td = pd.to_timedelta(st.where(st.str.count(":") == 2, st + ":00"))
            return td.dt.total_seconds().to_numpy(float), None
        dt = pd.to_datetime(st, dayfirst=dayfirst, errors="coerce")
    ok = dt.notna()
    secs = np.full(len(dt), np.nan)
    if ok.any():
        secs[ok.to_numpy()] = (dt[ok] - dt[ok].iloc[0]).dt.total_seconds().to_numpy()
    return secs, pd.DatetimeIndex(dt)


def to_series(df: pd.DataFrame, time_col, value_col, temp_col=None,
              injection_time: str | None = None, time_offset: float = 0.0,
              time_is_relative: bool = True, dayfirst=True) -> RawSeries:
    """Monta a série t (s) x valor.

    injection_time : 'dd/mm/aaaa hh:mm:ss' (ou 'hh:mm:ss') do lançamento do sal.
        Se informado e a coluna de tempo for data/hora, t = hora - lançamento.
    time_is_relative : se a coluna de tempo já é "segundos desde o lançamento".
    time_offset : correção (s) somada ao tempo (ex.: relógio atrasado).
    """
    secs, dt = parse_time(df[time_col], dayfirst=dayfirst)
    val = pd.to_numeric(df[value_col].astype(str).str.replace(",", "."),
                        errors="coerce").to_numpy(float) \
        if not pd.api.types.is_numeric_dtype(df[value_col]) else df[value_col].to_numpy(float)
    temp = None
    if temp_col and temp_col in df.columns:
        temp = pd.to_numeric(df[temp_col], errors="coerce").to_numpy(float)

    relative = time_is_relative
    if injection_time:
        t_inj = _parse_injection(injection_time, dt, dayfirst)
        if dt is not None and t_inj is not None:
            secs = (dt - t_inj).total_seconds().to_numpy(float)
            relative = True
        elif dt is None and t_inj is not None and isinstance(t_inj, float):
            secs = secs - t_inj  # lançamento dado em segundos
            relative = True
    elif dt is not None:
        relative = False  # só sabemos o tempo relativo ao 1º dado

    secs = secs + float(time_offset or 0.0)
    ok = np.isfinite(secs) & np.isfinite(val)
    secs, val = secs[ok], val[ok]
    temp = temp[ok] if temp is not None else None
    dt = dt[ok] if dt is not None else None
    order = np.argsort(secs, kind="stable")
    secs, val = secs[order], val[order]
    temp = temp[order] if temp is not None else None
    dt = dt[order] if dt is not None else None
    # remove tempos duplicados (média)
    if len(secs) and np.any(np.diff(secs) <= 0):
        u, inv = np.unique(secs, return_inverse=True)
        val = np.bincount(inv, val) / np.bincount(inv)
        if temp is not None:
            temp = np.bincount(inv, np.nan_to_num(temp)) / np.bincount(inv)
        if dt is not None:
            dt = pd.DatetimeIndex(pd.Series(dt).groupby(inv).first().to_numpy())
        secs = u
    return RawSeries(secs, val, temp, dt, relative)


def _parse_injection(text, dt, dayfirst):
    text = str(text).strip()
    if not text:
        return None
    if _is_number(text):
        return float(text.replace(",", "."))
    if re.match(r"^\d{1,2}:\d{2}(:\d{2})?$", text) and dt is not None:
        day = dt[0].normalize()
        return day + pd.to_timedelta(text if text.count(":") == 2 else text + ":00")
    return pd.to_datetime(text, dayfirst=dayfirst)


def read_xy_text(text: str):
    """Converte texto colado (duas ou mais colunas) em lista de listas de float."""
    rows = []
    for line in io.StringIO(text):
        parts = [p for p in re.split(r"[\t;]|\s+", line.strip()) if p]
        if not parts:
            continue
        try:
            rows.append([float(p.replace(",", ".")) for p in parts])
        except ValueError:
            continue  # cabeçalho
    return rows
