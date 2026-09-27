# -*- coding: utf-8 -*-
"""
Rotina principal: lê os dados do projeto, processa as curvas e aplica todos
os métodos. Não depende da interface gráfica (pode ser usada em scripts).
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import methods as mt
from .io_utils import read_table, guess_columns, to_series
from .processing import process_curve, section_mean_curve, Curve
from .project import Project


@dataclass
class Results:
    project: Project
    raw: dict = field(default_factory=dict)            # ponto -> RawSeries
    curves: dict = field(default_factory=dict)         # ponto -> Curve
    section_curves: dict = field(default_factory=dict)  # seção -> Curve (média)
    single: dict = field(default_factory=dict)         # alvo -> {método: dict}
    pairs: dict = field(default_factory=dict)          # (s1, s2) -> {método: dict}
    hydraulics: dict = field(default_factory=dict)     # seção -> dict
    tables: dict = field(default_factory=dict)         # nome -> DataFrame
    warnings: list = field(default_factory=list)
    log: list = field(default_factory=list)
    figures: dict = field(default_factory=dict)

    def warn(self, msg):
        self.warnings.append(msg)
        self.log.append("AVISO: " + msg)


def _fmt(v, nd=4):
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return v


def load_point_series(project: Project, p, cache=None):
    path = project.resolve(p.file)
    key = (path, p.sheet)
    if cache is not None and key in cache:
        df = cache[key]
    else:
        df = read_table(path, p.sheet or None)
        if cache is not None:
            cache[key] = df
    tcol, vcol, kind = guess_columns(df)
    tcol = p.time_col or tcol
    vcol = p.value_col or vcol
    for c in (tcol, vcol):
        if c not in df.columns:
            raise KeyError(f"Ponto '{p.name}': coluna '{c}' não existe em {p.file}. "
                           f"Colunas: {list(df.columns)}")
    raw = to_series(df, tcol, vcol, p.temp_col or None,
                    injection_time=project.injection_time or None,
                    time_offset=p.time_offset, time_is_relative=project.time_is_relative,
                    dayfirst=project.dayfirst)
    return raw


def run_analysis(project: Project, progress=None) -> Results:
    R = Results(project)
    opt = project.analysis
    say = (lambda m: (R.log.append(m), progress and progress(m)))

    # ------------------------------------------------------------ calibração
    for cal in project.calibrations:
        try:
            cal.fit()
            if cal.mode in ("poly", "ref") and len(cal.ec) >= 2:
                say(f"Calibração '{cal.name}': {cal.equation()}  (R² = {cal.r2:.4f})")
        except Exception as e:
            R.warn(f"Calibração '{cal.name}': {e}")
    try:
        project.link_calibrations()
    except ValueError as e:
        R.warn(str(e))

    project.ensure_sections()
    points = [p for p in project.points if p.enabled]
    if not points:
        raise ValueError("Nenhum ponto de monitoramento habilitado.")

    # ------------------------------------------------------------ leitura
    cache = {}
    for p in points:
        say(f"Lendo '{p.name}' ({p.file})")
        raw = load_point_series(project, p, cache)
        R.raw[p.name] = raw
        cal = project.calibration(p.calibration) if p.kind == "ec" else None
        cv = process_curve(p.name, raw.t, raw.value, p.kind, cal, p.options)
        R.curves[p.name] = cv
        for w in cv.warnings:
            R.warn(f"{p.name}: {w}")
        if not raw.relative_to_injection:
            R.warn(f"{p.name}: instante do lançamento desconhecido. Tempo contado a partir "
                   f"do 1º registro. Métodos de um só ponto não serão aplicados a ele.")

    # ------------------------------------------------------------ seções
    by_sec = {}
    for p in points:
        by_sec.setdefault(p.section, []).append(p)
    sec_order = sorted(by_sec, key=lambda s: project.section(s).x)
    lateral_rows = []
    for s in sec_order:
        pts = by_sec[s]
        cvs = [R.curves[p.name] for p in pts]
        if len(pts) == 1:
            R.section_curves[s] = cvs[0]
        else:
            R.section_curves[s] = section_mean_curve(f"{s} (média)", cvs, [p.weight for p in pts])
            m0 = np.array([mt.temporal_moments(*c.analysis_curve(opt.use_tail))["M0"] for c in cvs])
            tb = np.array([mt.temporal_moments(*c.analysis_curve(opt.use_tail))["t_mean"] for c in cvs])
            cv_m0 = np.std(m0, ddof=1) / np.mean(m0)
            lateral_rows.append(dict(
                Seção=s, Pontos=", ".join(p.name for p in pts),
                **{"Coeficiente de variação (CV) da integral da concentração (%)": 100 * cv_m0,
                   "Desvio máximo da integral da concentração (%)": 100 * np.max(np.abs(m0 / m0.mean() - 1)),
                   "Diferença do tempo médio de passagem entre sondas (s)": np.ptp(tb),
                   "Mistura lateral considerada": "Completa (CV ≤ 10 %)" if cv_m0 <= 0.10 else
                   "Incompleta (CV > 10 %)"}))
            if cv_m0 > 0.10:
                R.warn(f"Seção '{s}': as curvas dos pontos diferem "
                       f"(coeficiente de variação da integral da concentração = {100*cv_m0:.0f} %). "
                       f"Mistura lateral incompleta, a curva média depende dos pesos informados.")

    # ------------------------------------------------------------ hidráulica
    all_secs = [s.name for s in sorted(project.sections, key=lambda s: s.x)]
    for s in all_secs:
        sec = project.section(s)
        h = mt.section_hydraulics(sec.width, sec.depth, sec.area, sec.float_dist,
                                  sec.float_times, project.float_coef, sec.velocity,
                                  sec.Q, project.slope)
        R.hydraulics[s] = h

    # ------------------------------------------------------------ um ponto
    targets = []
    if opt.analyze_points_individually or all(len(v) == 1 for v in by_sec.values()):
        for p in points:
            targets.append((p.name, p.section, project.section(p.section).x, R.curves[p.name],
                            R.raw[p.name].relative_to_injection))
    for s in sec_order:
        if len(by_sec[s]) > 1:
            rel = all(R.raw[p.name].relative_to_injection for p in by_sec[s])
            targets.append((f"{s} (média)", s, project.section(s).x, R.section_curves[s], rel))

    point_rows, method_rows = [], []
    for name, s, x, cv, rel in targets:
        t, c = cv.analysis_curve(opt.use_tail)
        mo = mt.temporal_moments(t, c)
        de = mt.curve_descriptors(t, c)
        res = {}
        hyd = R.hydraulics.get(s, {})
        mb = mt.mass_balance(mo["M0"], hyd.get("Q") if np.isfinite(hyd.get("Q", np.nan)) else None,
                             project.M_injected)
        res["massa"] = mb
        ec_bg = cv.background[0] if cv.kind == "ec" else np.nan
        point_rows.append({
            "Ponto": name, "Seção transversal": s, "Distância do lançamento (m)": x,
            "Cond. base (µS/cm)": ec_bg,
            "Início da pluma (s)": cv.t_start, "Fim da pluma (s)": cv.t_end,
            "Chegada 10% (s)": de["t_arrival"], "Tempo do pico (s)": de["t_peak"],
            "Concentração do pico (kg/m³)": de["c_peak"], "Tempo médio de passagem (s)": mo["t_mean"],
            "Desvio padrão temporal (s)": mo["sigma_t"], "Assimetria da curva": mo["skew"],
            "∫C dt (kg·s/m³)": mo["M0"],
            "Vazão do rio pelo traçador (m³/s)": mb["Q_dilution"],
            "Massa recuperada (kg)": mb["M_recovered"],
            "Recuperação (%)": 100 * mb["recovery"] if np.isfinite(mb["recovery"]) else np.nan,
            "Truncada": "sim" if cv.truncated else "não",
            "Cauda extrapolada (%)": 100 * cv.tail_fraction,
        })
        if rel and x > 0:
            U_pk = x / de["t_peak"]
            method_rows.append(dict(Alvo=name, Método="Velocidade do pico (x/t_pico)",
                                    **{"U (m/s)": U_pk, "K (m²/s)": np.nan}))
            if opt.single_moments:
                r = mt.single_station_moments(x, t, c)
                res["momentos"] = r
                method_rows.append(dict(Alvo=name, Método="Método dos momentos em um ponto",
                                        **{"U (m/s)": r["U"], "K (m²/s)": r["D"]}))
            if opt.single_percentiles:
                r = mt.single_station_percentiles(x, t, c)
                res["percentis"] = r
                method_rows.append(dict(Alvo=name, Método="Método dos percentis em um ponto",
                                        **{"U (m/s)": r["U"], "K (m²/s)": r["D"]}))
            if opt.ade_fit:
                try:
                    r = mt.ade_fit(x, t, c)
                    res["ade"] = r
                    method_rows.append(dict(Alvo=name, Método="Método do ajuste da Advection-Dispersion Equation (ADE)",
                                            **{"U (m/s)": r["U"], "K (m²/s)": r["D"],
                                               "R²": r["R2"], "NSE": r["NSE"],
                                               "RMSE (kg/m³)": r["RMSE"]}))
                except Exception as e:
                    R.warn(f"{name}: ajuste da ADE falhou ({e})")
            if opt.chatwin:
                MA = None
                A = hyd.get("A")
                if project.M_injected and A and np.isfinite(A):
                    MA = project.M_injected / A
                r = mt.chatwin(x, t, c, None, level=opt.chatwin_level)
                res["chatwin"] = r
                if r["ok"]:
                    method_rows.append(dict(Alvo=name, Método="Método de Chatwin (M/A da curva medida)",
                                            **{"U (m/s)": r["U"], "K (m²/s)": r["D"],
                                               "R²": r["R2"]}))
                else:
                    R.warn(f"{name}: Chatwin sem solução ({r['msg']})")
                if MA is not None:
                    r2 = mt.chatwin(x, t, c, MA, level=opt.chatwin_level)
                    res["chatwin_MA"] = r2
                    if r2["ok"]:
                        method_rows.append(dict(Alvo=name, Método="Método de Chatwin (M/A = massa lançada / área informada)",
                                                **{"U (m/s)": r2["U"], "K (m²/s)": r2["D"],
                                                   "R²": r2["R2"]}))
        R.single[name] = res

    # ------------------------------------------------------------ pares
    pair_rows = []
    if len(sec_order) >= 2:
        if opt.pairs == "all":
            pairs = list(itertools.combinations(sec_order, 2))
        else:
            pairs = list(zip(sec_order[:-1], sec_order[1:]))
        for s1, s2 in pairs:
            c1v, c2v = R.section_curves[s1], R.section_curves[s2]
            x1, x2 = project.section(s1).x, project.section(s2).x
            t1, cc1 = c1v.analysis_curve(opt.use_tail)
            t2, cc2 = c2v.analysis_curve(opt.use_tail)
            m1, m2 = mt.temporal_moments(t1, cc1), mt.temporal_moments(t2, cc2)
            res = {"x1": x1, "x2": x2, "mom1": m1, "mom2": m2}
            row = {"Par de seções": f"{s1} para {s2}", "Δx (m)": x2 - x1,
                   "Δ<t> (s)": m2["t_mean"] - m1["t_mean"],
                   "Δσt² (s²)": m2["var_t"] - m1["var_t"],
                   "Conservação de massa (∫C dt 2/1)": m2["M0"] / m1["M0"]}
            if opt.two_station_moments:
                r = mt.two_station_moments(x1, m1, x2, m2)
                res["momentos"] = r
                row.update({"U Fischer (m/s)": r["U"], "K Fischer (m²/s)": r["D"]})
                method_rows.append(dict(Alvo=f"{s1} → {s2}",
                                        Método="Método de Fischer (variação dos momentos)",
                                        **{"U (m/s)": r["U"], "K (m²/s)": r["D"]}))
                if r["dvar"] <= 0:
                    R.warn(f"{s1} → {s2}: a variância não cresceu entre os pontos "
                           f"(Δσ² = {r['dvar']:.1f} s²): K pelos momentos não tem sentido "
                           f"físico (curva truncada ou mistura incompleta?).")
            if opt.routing:
                # recorte para acelerar
                nz = np.where(cc1 > 0)[0]
                t1r, c1r = t1[nz[0]:nz[-1] + 1], cc1[nz[0]:nz[-1] + 1]
                dur = c2v.t_end - c2v.t_start
                w = (t2 >= c2v.t_start - 0.3 * dur) & (t2 <= c2v.t_end + 0.3 * dur)
                t2r, c2r = t2[w], cc2[w]
                step = int(np.ceil(len(t1r) * len(t2r) / 4e6))
                if step > 1:
                    t1r, c1r = t1r[::step], c1r[::step]
                try:
                    r = mt.routing_fit(t1r, c1r, t2r, c2r, x1, x2, m1["t_mean"], m2["t_mean"],
                                       fit_U=opt.routing_fit_U,
                                       normalize_mass=opt.routing_normalize_mass)
                    r.update(t1=t1r, c1=c1r, c2=c2r)
                    res["routing"] = r
                    row.update({"K propagação (m²/s)": r["D"], "U propagação (m/s)": r["U"],
                                "R² propagação": r["R2"], "NSE propagação": r["NSE"],
                                "RMSE propagação (kg/m³)": r["RMSE"]})
                    method_rows.append(dict(Alvo=f"{s1} → {s2}",
                                            Método="Método da propagação",
                                            **{"U (m/s)": r["U"], "K (m²/s)": r["D"],
                                               "R²": r["R2"], "NSE": r["NSE"],
                                               "RMSE (kg/m³)": r["RMSE"]}))
                    if opt.routing_manual and opt.routing_D_manual:
                        rm = mt.routing_fit(t1r, c1r, t2r, c2r, x1, x2, m1["t_mean"],
                                            m2["t_mean"], normalize_mass=opt.routing_normalize_mass,
                                            D_manual=opt.routing_D_manual,
                                            U_manual=opt.routing_U_manual)
                        rm.update(t1=t1r, c1=c1r, c2=c2r)
                        res["routing_manual"] = rm
                        method_rows.append(dict(Alvo=f"{s1} → {s2}",
                                                Método="Método da propagação com valores manuais (K, U manuais)",
                                                **{"U (m/s)": rm["U"], "K (m²/s)": rm["D"],
                                                   "R²": rm["R2"], "NSE": rm["NSE"],
                                                   "RMSE (kg/m³)": rm["RMSE"]}))
                except Exception as e:
                    R.warn(f"{s1} → {s2}: propagação falhou ({e})")
            R.pairs[(s1, s2)] = res
            pair_rows.append(row)
            ratio = m2["M0"] / m1["M0"]
            if abs(ratio - 1) > 0.15:
                R.warn(f"{s1} → {s2}: ∫C dt varia {100*(ratio-1):+.0f} % entre os pontos. "
                       f"Se a vazão é a mesma, a massa não se conservou (calibração das "
                       f"sondas, fundo, curva truncada ou mistura incompleta).")

    # ------------------------------------------------------------ hidráulica/empíricas
    sec_rows, emp_rows = [], []
    U_tracer = {}
    for r in method_rows:
        if r["Método"].startswith("Método de Fischer"):
            for s in r["Alvo"].split(" → "):
                U_tracer.setdefault(s, r["U (m/s)"])
    for s in all_secs:
        h = dict(R.hydraulics[s])
        sec = project.section(s)
        U = h["V"] if np.isfinite(h.get("V", np.nan)) else U_tracer.get(s, np.nan)
        ust = h["u_star"]
        ust_note = "√(g R S)"
        if not np.isfinite(ust) and np.isfinite(U):
            ust = 0.1 * U
            ust_note = "estimado 0,1·U (informe a declividade)"
        emp = mt.empirical_D(U, h.get("W") or np.nan, h.get("h") or np.nan, ust)
        for k, v in emp.items():
            emp_rows.append({"Seção": s, "Fórmula": k, "K (m²/s)": v, "U usado (m/s)": U,
                             "u* (m/s)": ust, "u* obtido por": ust_note})
        ml = mt.mixing_lengths(U, h.get("W") or np.nan, h.get("h") or np.nan, ust)
        Lmix = ml.get("L_center" if project.injection_position == "center" else "L_margin",
                      np.nan)
        # Q por diluição médio da seção
        pts_s = by_sec.get(s, [])
        tgt = [p.name for p in pts_s] + [f"{s} (média)"]
        qd = [R.single[n]["massa"]["Q_dilution"] for n in tgt if n in R.single]
        row = {"Seção": s, "x (m)": sec.x, "Nº pontos": len(pts_s),
               "Largura (m)": h.get("W"), "Profundidade (m)": h.get("h"), "Área (m²)": h["A"],
               "Velocidade superficial (m/s)": h["Vs"], "Velocidade média (m/s)": h["V"], "Vazão (m³/s)": h["Q"],
               "Vazão de diluição (m³/s)": np.nanmean(qd) if len(qd) and np.isfinite(qd).any() else np.nan,
               "Velocidade de cisalhamento (m/s)": ust, "Coeficiente de mistura transversal(m²/s)": ml.get("eps_t", np.nan),
               "Distância para mistura transversal (m)": Lmix,
               "Mistura completa transversal: ": ("Sim" if sec.x >= Lmix else "Não (x < L)")
               if np.isfinite(Lmix) else "—"}
        sec_rows.append(row)
        if np.isfinite(Lmix) and sec.x < Lmix and pts_s:
            R.warn(f"Seção '{s}' está a {sec.x:.1f} m do lançamento, antes da distância de "
                   f"mistura transversal (~{Lmix:.0f} m). A ADE 1D pode não valer ali "
                   f"(estimativa com u* {ust_note}).")

    # ------------------------------------------------------------ tabelas
    cal_rows = [{"Sonda": c.name, "Modo": c.mode,
                 "Equação": c.equation(8) if (c.coef or c.mode == "nacl") else "",
                 "Grau": c.degree, "R²": c.r2, "RMSE": c.rmse, "Unidade RMSE": c.unit,
                 "EC mín": c.ec_range[0], "EC máx": c.ec_range[1], "Nº pontos": len(c.ec)}
                for c in project.calibrations]
    R.tables["Resumo U e K"] = pd.DataFrame(method_rows)
    R.tables["Curvas de concentração"] = pd.DataFrame(point_rows)
    if pair_rows:
        R.tables["Pares de seções"] = pd.DataFrame(pair_rows)
    R.tables["Seções e hidráulica"] = pd.DataFrame(sec_rows)
    if lateral_rows:
        R.tables["Mistura lateral"] = pd.DataFrame(lateral_rows)
    if emp_rows:
        R.tables["Fórmulas empíricas"] = pd.DataFrame(emp_rows)
    R.tables["Calibrações"] = pd.DataFrame(cal_rows)
    for k, df in R.tables.items():
        R.tables[k] = df.apply(lambda col: col.map(lambda v: _fmt(v, 6)) if col.dtype != object
                               else col)
    say("Análise concluída.")
    return R
