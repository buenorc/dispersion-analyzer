# -*- coding: utf-8 -*-
"""
Métodos para estimar a velocidade média U (m/s) e o coeficiente de dispersão
longitudinal (K na interface e nos relatórios; D nas variáveis deste módulo), em
m²/s, a partir de curvas C(t) de traçador.

O manual completo — fórmulas, opções, hipóteses e limitações de cada método —
está em manual.py (exibido em Ajuda → Métodos… na interface).

Notação: x = distância do lançamento até o ponto (m); t = tempo desde o
lançamento (s); C = concentração em excesso (kg/m³).

Momentos temporais (regra do trapézio):
    M0 = ∫C dt,  <t> = ∫tC dt / M0,  σt² = ∫(t − <t>)²C dt / M0

Métodos de um único ponto (precisam do instante do lançamento e de x > 0):
  * velocidade do pico              U = x / t_pico
  * momentos (nuvem congelada)      U = x/<t>,   D = U² σt² / (2<t>)
  * percentis                       σt = (t84 − t16)/2,  U = x/t50,
                                    D = U² σt² / (2 t50)
  * ajuste da solução analítica da ADE (Levenberg–Marquardt em log U, log D e
    log M/A)
  * Chatwin (1971) linearizado:  √[t ln(k/(C√t))] = x/(2√D) − U t/(2√D),
    k = (M/A)/√(4πD) iterado;  √D = x/(2b),  U = −a x/b

Métodos entre duas seções (independem do lançamento):
  * variação dos momentos (Fischer, 1968)
        U = Δx/Δ<t>,   D = U² (σt2² − σt1²) / (2 Δ<t>)
  * propagação / routing (Fischer, 1968): D (e opcionalmente U) por mínimos
    quadrados entre C(x2,t) observada e a curva de x1 propagada pela ADE

Também: balanço de massa e vazão por diluição, hidráulica por flutuadores,
fórmulas empíricas de D e distâncias de mistura lateral.
"""
from __future__ import annotations

import numpy as np
from scipy import optimize

trapz = getattr(np, "trapezoid", None) or np.trapz


# ==========================================================================
# momentos temporais
# ==========================================================================
def temporal_moments(t, c):
    """M0 = ∫C dt, <t> = ∫tC dt / M0, σt² = ∫(t-<t>)²C dt / M0, assimetria."""
    t = np.asarray(t, float)
    c = np.asarray(c, float)
    m0 = trapz(c, t)
    if m0 <= 0:
        return dict(M0=np.nan, t_mean=np.nan, var_t=np.nan, sigma_t=np.nan, skew=np.nan)
    tm = trapz(t * c, t) / m0
    var = trapz((t - tm) ** 2 * c, t) / m0
    m3 = trapz((t - tm) ** 3 * c, t) / m0
    return dict(M0=m0, t_mean=tm, var_t=var, sigma_t=np.sqrt(var),
                skew=m3 / var ** 1.5 if var > 0 else np.nan)


def percentile_times(t, c, probs=(0.10, 0.1587, 0.50, 0.8413, 0.90)):
    t = np.asarray(t, float)
    c = np.clip(np.asarray(c, float), 0, None)
    cum = np.concatenate([[0], np.cumsum(0.5 * (c[1:] + c[:-1]) * np.diff(t))])
    if cum[-1] <= 0:
        return {p: np.nan for p in probs}
    cum /= cum[-1]
    return {p: float(np.interp(p, cum, t)) for p in probs}


def curve_descriptors(t, c):
    """Tempos característicos da curva de passagem."""
    t = np.asarray(t, float)
    c = np.asarray(c, float)
    ip = int(np.argmax(c))
    cp = c[ip]
    above = np.where(c >= 0.10 * cp)[0]
    half = np.where(c >= 0.5 * cp)[0]
    return dict(t_peak=t[ip], c_peak=cp,
                t_arrival=t[above[0]] if len(above) else np.nan,     # 10 % do pico
                t_leave=t[above[-1]] if len(above) else np.nan,
                fwhm=(t[half[-1]] - t[half[0]]) if len(half) else np.nan)


# ==========================================================================
# um único ponto
# ==========================================================================
def single_station_moments(x, t, c):
    mo = temporal_moments(t, c)
    U = x / mo["t_mean"]
    D = U ** 2 * mo["var_t"] / (2 * mo["t_mean"])
    return dict(U=U, D=D, **mo)


def single_station_percentiles(x, t, c):
    p = percentile_times(t, c)
    sig = 0.5 * (p[0.8413] - p[0.1587])
    t50 = p[0.5]
    U = x / t50
    return dict(U=U, D=U ** 2 * sig ** 2 / (2 * t50), sigma_t=sig, t50=t50,
                t16=p[0.1587], t84=p[0.8413])


def ade_solution(t, x, U, D, MA):
    """C(x,t) = (M/A) / sqrt(4πDt) · exp(-(x-Ut)²/(4Dt))   (lançamento instantâneo)."""
    t = np.asarray(t, float)
    out = np.zeros_like(t)
    p = t > 0
    out[p] = MA / np.sqrt(4 * np.pi * D * t[p]) * np.exp(-(x - U * t[p]) ** 2 / (4 * D * t[p]))
    return out


def goodness(obs, pred):
    obs = np.asarray(obs, float)
    pred = np.asarray(pred, float)
    res = obs - pred
    ss = np.sum((obs - obs.mean()) ** 2)
    nse = 1 - np.sum(res ** 2) / ss if ss > 0 else np.nan
    r = np.corrcoef(obs, pred)[0, 1] if np.std(pred) > 0 and np.std(obs) > 0 else np.nan
    return dict(RMSE=float(np.sqrt(np.mean(res ** 2))), NSE=float(nse), R2=float(r ** 2))


def ade_fit(x, t, c, MA=None):
    """Ajuste não linear da solução da ADE a um ponto (U, D e M/A)."""
    t = np.asarray(t, float)
    c = np.asarray(c, float)
    m = t > 0
    t, c = t[m], c[m]
    mo = single_station_moments(x, t, c)
    U0 = max(mo["U"], 1e-4)
    D0 = max(mo["D"], 1e-5)
    MA0 = U0 * mo["M0"] if MA is None else MA
    fit_ma = MA is None

    def resid(p):
        U, D = np.exp(p[0]), np.exp(p[1])
        ma = np.exp(p[2]) if fit_ma else MA
        return ade_solution(t, x, U, D, ma) - c

    p0 = [np.log(U0), np.log(D0)] + ([np.log(MA0)] if fit_ma else [])
    best = None
    for fD in (1.0, 0.2, 5.0):  # alguns chutes iniciais para robustez
        p0[1] = np.log(D0 * fD)
        try:
            r = optimize.least_squares(resid, p0, method="lm", max_nfev=4000)
        except Exception:
            continue
        if best is None or r.cost < best.cost:
            best = r
    U, D = np.exp(best.x[0]), np.exp(best.x[1])
    ma = np.exp(best.x[2]) if fit_ma else MA
    pred = ade_solution(t, x, U, D, ma)
    return dict(U=U, D=D, MA=ma, t=t, pred=pred, **goodness(c, pred))


def chatwin(x, t, c, MA=None, level=0.10, max_iter=200, tol=1e-6):
    """Método de Chatwin (1971) corrigido.

        y(t) = sqrt( t · ln( k / (C sqrt(t)) ) ) = x/(2√D) - U t/(2√D),
        k = (M/A)/sqrt(4πD)

    Reta y = b + a·t  ->  √D = x/(2b),  U = -a·x/b.
    Como k depende de D, o cálculo é iterado até convergir. No ramo
    descendente (t > x/U) a raiz é negativa. Se M/A não for informado, usa
    o valor coerente com os próprios dados: M/A = U·∫C dt.
    Usa apenas pontos com C > level·C_pico (a cauda ruidosa distorce a reta).
    """
    t = np.asarray(t, float)
    c = np.asarray(c, float)
    mo = single_station_moments(x, t, c)
    U, D = mo["U"], mo["D"]
    cp = c.max()
    use = (c > level * cp) & (t > 0)
    tt, cc = t[use], c[use]
    hist = []
    for it in range(max_iter):
        ma = MA if MA is not None else U * mo["M0"]
        k = ma / np.sqrt(4 * np.pi * D)
        arg = np.log(k / (cc * np.sqrt(tt)))
        ok = arg > 0
        if ok.sum() < 4:
            return dict(U=np.nan, D=np.nan, ok=False, msg="k pequeno demais (ln<0)")
        y = np.sqrt(tt[ok] * arg[ok])
        y = np.where(tt[ok] > x / U, -y, y)  # ramo descendente
        a, b = np.polyfit(tt[ok], y, 1)
        if b <= 0 or a >= 0:
            return dict(U=np.nan, D=np.nan, ok=False, msg="reta sem significado físico")
        D_new = (x / (2 * b)) ** 2
        U_new = -a * x / b
        hist.append((U_new, D_new))
        conv = abs(D_new - D) / D < tol and abs(U_new - U) / U < tol
        U, D = U_new, D_new
        if conv:
            break
    yh = b + a * tt[ok]
    r2 = 1 - np.sum((y - yh) ** 2) / np.sum((y - y.mean()) ** 2)
    return dict(U=U, D=D, k=k, a=a, b=b, R2=r2, t=tt[ok], y=y, iterations=it + 1,
                MA=ma, ok=True, msg="")


# ==========================================================================
# dois pontos
# ==========================================================================
def two_station_moments(x1, mom1, x2, mom2):
    dt = mom2["t_mean"] - mom1["t_mean"]
    dx = x2 - x1
    U = dx / dt
    D = U ** 2 * (mom2["var_t"] - mom1["var_t"]) / (2 * dt)
    return dict(U=U, D=D, dt_mean=dt, dvar=mom2["var_t"] - mom1["var_t"], dx=dx)


def routing_predict(t_out, t1, c1, dtbar, U, D):
    """Procedimento de propagação (Fischer, 1968):

    C(x2,t) = ∫ C(x1,τ) U / sqrt(4π D Δt̄) · exp{-[U(Δt̄ - t + τ)]² / (4 D Δt̄)} dτ
    """
    t1 = np.asarray(t1, float)
    c1 = np.asarray(c1, float)
    w = np.zeros_like(t1)  # pesos da regra do trapézio (dt pode ser irregular)
    d = np.diff(t1)
    w[:-1] += d / 2
    w[1:] += d / 2
    nz = c1 > 0
    t1, c1, w = t1[nz], c1[nz], w[nz]
    t_out = np.asarray(t_out, float)
    arg = dtbar - t_out[:, None] + t1[None, :]
    ker = U / np.sqrt(4 * np.pi * D * dtbar) * np.exp(-(U * arg) ** 2 / (4 * D * dtbar))
    return ker @ (c1 * w)


def routing_fit(t1, c1, t2, c2, x1, x2, tbar1, tbar2, fit_U=False,
                normalize_mass=False, D_bounds=(1e-5, 50.0), D_manual=None, U_manual=None):
    """Otimiza D (e U) minimizando o erro quadrático entre C(x2,t) observado
    e propagado. Se D_manual for dado, apenas avalia (tentativa e erro, como
    no L3)."""
    t1 = np.asarray(t1, float)
    c1 = np.asarray(c1, float)
    t2 = np.asarray(t2, float)
    c2 = np.asarray(c2, float)
    dtbar = tbar2 - tbar1
    U0 = (x2 - x1) / dtbar
    scale = 1.0
    if normalize_mass:
        scale = trapz(c2, t2) / trapz(c1, t1)
    c1s = c1 * scale

    def sse(D, U):
        return np.sum((routing_predict(t2, t1, c1s, dtbar, U, D) - c2) ** 2)

    if D_manual is not None:
        D = float(D_manual)
        U = float(U_manual) if U_manual is not None else U0
    elif not fit_U:
        U = U0
        r = optimize.minimize_scalar(lambda lg: sse(10 ** lg, U),
                                     bounds=np.log10(D_bounds), method="bounded",
                                     options=dict(xatol=1e-4))
        D = 10 ** r.x
    else:
        best = None
        for lg0 in np.linspace(np.log10(D_bounds[0]) + 1, np.log10(D_bounds[1]) - 1, 5):
            r = optimize.minimize(lambda p: sse(10 ** p[0], 10 ** p[1]),
                                  [lg0, np.log10(U0)], method="Nelder-Mead",
                                  options=dict(xatol=1e-5, fatol=1e-12, maxiter=2000))
            if best is None or r.fun < best.fun:
                best = r
        D, U = 10 ** best.x[0], 10 ** best.x[1]
    pred = routing_predict(t2, t1, c1s, dtbar, U, D)
    # curva de sensibilidade RMSE x D
    Ds = np.logspace(np.log10(max(D / 30, D_bounds[0])), np.log10(min(D * 30, D_bounds[1])), 60)
    rm = np.array([np.sqrt(sse(d, U) / len(t2)) for d in Ds])
    return dict(D=D, U=U, U_moments=U0, dtbar=dtbar, mass_scale=scale, t=t2, pred=pred,
                D_scan=Ds, RMSE_scan=rm, **goodness(c2, pred))


# ==========================================================================
# massa e vazão
# ==========================================================================
def mass_balance(M0, Q=None, M_injected=None):
    """M0 = ∫C dt (kg·s/m³). Massa recuperada = Q·M0; vazão por diluição = M/M0."""
    out = dict(M0=M0, M_recovered=np.nan, recovery=np.nan, Q_dilution=np.nan)
    if Q:
        out["M_recovered"] = Q * M0
    if M_injected:
        out["Q_dilution"] = M_injected / M0
        if Q:
            out["recovery"] = Q * M0 / M_injected
    return out


# ==========================================================================
# hidráulica e fórmulas empíricas
# ==========================================================================
G = 9.81


def section_hydraulics(width=None, depth=None, area=None, float_dist=None, float_times=None,
                       float_coef=0.85, velocity=None, Q=None, slope=None):
    """Velocidade por flutuadores (superficial x coeficiente), área, vazão, u*."""
    out = {}
    A = area if area else (width * depth if width and depth else np.nan)
    Vs = np.nan
    if float_times:
        ft = np.asarray([v for v in float_times if v], float)
        fd = np.asarray(float_dist if np.ndim(float_dist) else [float_dist] * len(ft), float)
        if len(ft):
            vs_i = fd[:len(ft)] / ft
            Vs = float(np.mean(vs_i))
            out["Vs_std"] = float(np.std(vs_i, ddof=1)) if len(ft) > 1 else np.nan
            out["n_floats"] = len(ft)
    V = velocity if velocity else (float_coef * Vs if np.isfinite(Vs) else np.nan)
    Qc = Q if Q else V * A
    h = depth if depth else (A / width if width and A == A else np.nan)
    R = A / (width + 2 * h) if width and h == h else h
    ustar = np.sqrt(G * R * slope) if slope else np.nan
    out.update(A=A, Vs=Vs, V=V, Q=Qc, h=h, W=width, R=R, u_star=ustar)
    return out


def empirical_D(U, W, h, u_star):
    """Fórmulas empíricas para D_L (m²/s)."""
    if not all(np.isfinite([U, W, h, u_star])) or u_star <= 0 or h <= 0:
        return {}
    return {
        "Elder (1959)": 5.93 * h * u_star,
        "Fischer (1975)": 0.011 * U ** 2 * W ** 2 / (h * u_star),
        "Liu (1977)": 0.18 * (u_star / U) ** 1.5 * U ** 2 * W ** 2 / (h * u_star),
        "Seo & Cheong (1998)": 5.915 * (W / h) ** 0.620 * (U / u_star) ** 1.428 * h * u_star,
        "Kashefipour & Falconer (2002)": 10.612 * h * U ** 2 / u_star,
    }


def mixing_lengths(U, W, h, u_star):
    """Distâncias para mistura lateral completa (Fischer et al., 1979),
    ε_t = 0,6 h u*. Antes disso a ADE 1D (período de Taylor) não vale."""
    if not all(np.isfinite([U, W, h, u_star])) or u_star <= 0:
        return {}
    eps = 0.6 * h * u_star
    return dict(eps_t=eps, L_center=0.1 * U * W ** 2 / eps, L_margin=0.4 * U * W ** 2 / eps)
