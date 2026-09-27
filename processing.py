# -*- coding: utf-8 -*-
"""
Pré-processamento das curvas de passagem (condutividade -> concentração em excesso).

Etapas:
1. recorte da janela de análise (t_min, t_max);
2. suavização opcional (média móvel);
3. condutividade de fundo do rio (automática = média dos valores da própria
   rodada antes do início da subida, como corrigido no comentário do L3;
   janela manual; valor informado; ou linha de base linear pré/pós nuvem);
4. conversão para concentração em excesso: C = f(EC) - f(EC_fundo);
5. delimitação da nuvem (início da subida até voltar a < x % do pico);
6. extrapolação exponencial opcional da cauda quando a série foi
   interrompida antes da nuvem passar (curva truncada).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .calibration import Calibration
from .methods import trapz


@dataclass
class ProcessingOptions:
    baseline_mode: str = "auto"          # auto | window | value | linear
    baseline_window: tuple = (None, None)
    baseline_value: float | None = None  # mesma unidade da série (µS/cm ou kg/m³)
    t_min: float | None = None
    t_max: float | None = None
    smooth: int = 0                      # janela da média móvel (nº de amostras)
    end_threshold: float = 0.02          # fim da nuvem: C < 2 % do pico
    clip_negative: bool = True
    tail_extrapolation: bool = False

    @classmethod
    def from_dict(cls, d):
        d = dict(d or {})
        if "baseline_window" in d and d["baseline_window"] is not None:
            d["baseline_window"] = tuple(d["baseline_window"])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Curve:
    name: str
    t: np.ndarray                 # tempo (s)
    value: np.ndarray             # série original recortada (EC ou C)
    c: np.ndarray                 # concentração em excesso (kg/m³), já limpa
    c_unclipped: np.ndarray
    background: np.ndarray        # fundo (mesma unidade de value)
    kind: str = "ec"
    t_start: float = np.nan
    t_end: float = np.nan
    t_peak: float = np.nan
    c_peak: float = np.nan
    truncated: bool = False
    t_tail: np.ndarray = field(default_factory=lambda: np.array([]))
    c_tail: np.ndarray = field(default_factory=lambda: np.array([]))
    tail_fraction: float = 0.0
    warnings: list = field(default_factory=list)

    def analysis_curve(self, with_tail=True):
        """Curva usada nos métodos: concentração limpa (+ cauda extrapolada)."""
        if with_tail and len(self.t_tail):
            return (np.concatenate([self.t, self.t_tail]),
                    np.concatenate([self.c, self.c_tail]))
        return self.t, self.c


def moving_average(y, n):
    n = int(n or 0)
    if n <= 1:
        return y
    k = np.ones(n) / n
    ypad = np.pad(y, (n // 2, n - 1 - n // 2), mode="edge")
    return np.convolve(ypad, k, mode="valid")


def _robust_sigma(y):
    if len(y) < 3:
        return 0.0
    d = np.diff(y)
    return 1.4826 * np.median(np.abs(d - np.median(d))) / np.sqrt(2)


def _robust_mean(y, peak):
    """Média dos valores de fundo descartando picos isolados (ruído, bolhas)."""
    y = np.asarray(y, float)
    if len(y) < 4:
        return float(np.mean(y))
    med = np.median(y)
    dev = np.abs(y - med)
    u = np.unique(y)
    res = np.min(np.diff(u)) if len(u) > 1 else 0.0   # resolução (quantização do ADC)
    s = max(1.4826 * np.median(dev), 0.01 * abs(peak - med), res, 1e-12)
    keep = dev <= 3 * s
    return float(np.mean(y[keep])) if keep.any() else float(med)


def detect_rise(t, v):
    """Índice do início da subida da curva (antes do pico)."""
    ip = int(np.nanargmax(v))
    if ip < 3:
        return 0, ip
    n0 = max(3, min(ip // 3, 30))
    b0 = np.nanmedian(v[:n0])
    sig = _robust_sigma(v[:ip])
    thr = b0 + max(4 * sig, 0.03 * (v[ip] - b0))
    i = ip
    while i > 0 and v[i - 1] > thr:
        i -= 1
    return i, ip


def process_curve(name, t, value, kind="ec", calibration: Calibration | None = None,
                  opts: ProcessingOptions | None = None) -> Curve:
    opts = opts or ProcessingOptions()
    t = np.asarray(t, float)
    v = np.asarray(value, float)
    warn = []
    m = np.isfinite(t) & np.isfinite(v)
    if opts.t_min is not None:
        m &= t >= opts.t_min
    if opts.t_max is not None:
        m &= t <= opts.t_max
    t, v = t[m], v[m]
    if len(t) < 5:
        raise ValueError(f"{name}: poucos dados após o recorte ({len(t)}).")
    vs = moving_average(v, opts.smooth)

    # ------------------------------------------------------------ fundo
    i_rise, ip = detect_rise(t, vs)
    mode = opts.baseline_mode
    bg = np.full_like(vs, np.nan)
    if mode == "value" and opts.baseline_value is not None:
        bg[:] = float(opts.baseline_value)
    elif mode == "window" and opts.baseline_window and opts.baseline_window[0] is not None:
        a, b = opts.baseline_window
        w = (t >= a) & (t <= (b if b is not None else a))
        if not w.any():
            raise ValueError(f"{name}: janela de fundo sem dados.")
        bg[:] = np.mean(vs[w])
    else:
        if i_rise < 3:
            warn.append("Poucos dados antes da subida da curva: fundo estimado com os "
                        "primeiros valores; informe o fundo manualmente se possível.")
            pre = vs[:max(i_rise, 1)]
        else:
            # afasta-se do início da subida (o pé da curva já tem um pouco de sal)
            i_end = i_rise - max(1, (ip - i_rise) // 2)
            pre = vs[:i_end] if i_end >= 3 else vs[:max(i_rise - 1, 1)]
        bg[:] = _robust_mean(pre, vs[ip])
        if mode == "linear":
            # fundo linear entre o trecho pré-nuvem e o trecho pós-nuvem
            tail_n = max(3, len(vs) // 20)
            post = vs[-tail_n:]
            if np.mean(post) - bg[0] > 0.1 * (vs[ip] - bg[0]):
                warn.append("Fundo linear pedido, mas a curva não retornou ao fundo "
                            "(série truncada). Usado fundo constante.")
            else:
                t_pre = np.mean(t[:len(pre)])
                t_post = np.mean(t[-tail_n:])
                b0 = _robust_mean(pre, vs[ip])
                bg = b0 + (_robust_mean(post, vs[ip]) - b0) * (t - t_pre) / (t_post - t_pre)

    # ------------------------------------------------------------ conversão
    if kind == "ec":
        if calibration is None:
            raise ValueError(f"{name}: série de condutividade sem calibração associada.")
        c = calibration.to_conc(vs) - calibration.to_conc(bg)
        lo, hi = calibration.ec_range
        if np.nanmax(vs) > hi * 1.05:
            warn.append(f"Condutividade máxima ({np.nanmax(vs):.1f} µS/cm) acima do maior "
                        f"ponto da calibração ({hi:.1f}): extrapolação da curva.")
        if calibration.mode in ("poly", "ref") and len(calibration.coef) >= 3:
            # verifica se a curva é monotônica no intervalo medido
            e = np.linspace(np.nanmin(vs), np.nanmax(vs), 200)
            if np.any(np.diff(calibration.to_conc(e)) < 0):
                warn.append("A curva de calibração não é monotônica no intervalo medido.")
    else:
        c = vs - bg

    # ------------------------------------------------------------ nuvem
    ip = int(np.nanargmax(c))
    cpk = c[ip]
    if cpk <= 0:
        raise ValueError(f"{name}: não foi encontrada a passagem da nuvem (pico <= fundo).")
    i0, _ = detect_rise(t, c)
    thr = opts.end_threshold * cpk
    i1 = None
    for i in range(ip, len(c)):
        if c[i] < thr and np.all(c[i:min(i + 3, len(c))] < thr):
            i1 = i
            break
    truncated = i1 is None
    if truncated:
        i1 = len(c) - 1
        frac_end = c[-1] / cpk
        warn.append(f"Série truncada: no fim do registro C = {100*frac_end:.1f} % do pico. "
                    f"A cauda não medida subestima a massa e a variância (considere "
                    f"ativar a extrapolação da cauda).")
    cc = c.copy()
    if opts.clip_negative:
        cc[:i0] = 0.0
        cc[i1 + 1:] = 0.0
        cc = np.clip(cc, 0, None)

    curve = Curve(name, t, v, cc, c, bg, kind, t[i0], t[i1], t[ip], cpk, truncated,
                  warnings=warn)

    # ------------------------------------------------------------ cauda
    if truncated and opts.tail_extrapolation:
        seg = (t > t[ip]) & (c > 0) & (c < 0.6 * cpk)
        if seg.sum() >= 5:
            A = np.vstack([np.ones(seg.sum()), t[seg] - t[-1]]).T
            coef, *_ = np.linalg.lstsq(A, np.log(c[seg]), rcond=None)
            k = -coef[1]
            if k > 0:
                c_end = max(c[-1], 1e-12)
                dt = np.median(np.diff(t))
                t_stop = t[-1] + np.log(c_end / (0.001 * cpk)) / k
                tt = np.arange(t[-1] + dt, max(t_stop, t[-1] + dt), dt)
                curve.t_tail = tt
                curve.c_tail = c_end * np.exp(-k * (tt - t[-1]))
                m_meas = trapz(cc, t)
                m_tail = trapz(np.r_[c_end, curve.c_tail], np.r_[t[-1], tt])
                curve.tail_fraction = m_tail / (m_meas + m_tail)
                curve.t_end = tt[-1] if len(tt) else t[-1]
            else:
                warn.append("Extrapolação da cauda não aplicada: trecho final não decrescente.")
        else:
            warn.append("Extrapolação da cauda não aplicada: poucos pontos na recessão.")
    return curve


# --------------------------------------------------------------------------
def common_grid(curves, dt=None):
    t0 = min(c.analysis_curve()[0][0] for c in curves)
    t1 = max(c.analysis_curve()[0][-1] for c in curves)
    if dt is None:
        dt = min(np.median(np.diff(c.t)) for c in curves)
    return np.arange(t0, t1 + dt / 2, dt)


def section_mean_curve(name, curves, weights=None):
    """Curva média da seção (várias sondas na mesma seção transversal).

    Interpola as curvas numa grade comum e faz a média ponderada (pesos =
    subáreas ou vazões parciais; iguais se não informados). Fora do período
    registrado por uma sonda, ela não entra na média.
    """
    if len(curves) == 1:
        return curves[0]
    w = np.ones(len(curves)) if weights is None else np.asarray(weights, float)
    grid = common_grid(curves)
    num = np.zeros_like(grid)
    den = np.zeros_like(grid)
    for wi, cv in zip(w, curves):
        tt, cc = cv.analysis_curve()
        inside = (grid >= tt[0]) & (grid <= tt[-1])
        num[inside] += wi * np.interp(grid[inside], tt, cc)
        den[inside] += wi
    cm = np.where(den > 0, num / np.where(den > 0, den, 1), 0.0)
    ip = int(np.argmax(cm))
    starts = [cv.t_start for cv in curves]
    ends = [cv.t_end for cv in curves]
    out = Curve(name, grid, cm, cm, cm, np.zeros_like(grid), "conc",
                float(np.min(starts)), float(np.max(ends)), grid[ip], cm[ip],
                any(cv.truncated for cv in curves))
    return out
