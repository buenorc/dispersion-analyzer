# -*- coding: utf-8 -*-
"""Figuras (matplotlib, sem pyplot: seguras para uso na interface gráfica)."""
from __future__ import annotations

import numpy as np
from matplotlib.figure import Figure

from . import methods as mt

# paleta categórica em ordem fixa (a cor segue o ponto/seção, nunca a posição)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#9a9993"      # notas explicativas abaixo do gráfico
GRID = "#e4e3df"
LS = ["-", "--", ":", "-."]


def _style(ax, xlabel="", ylabel="", title="", note=""):
    ax.set_xlabel(xlabel, color=INK2)
    ax.set_ylabel(ylabel, color=INK2)
    if title:
        ax.set_title(title, color=INK, fontsize=11, loc="left")
    if note:
        # logo abaixo do rótulo do eixo x, alinhada à esquerda do gráfico
        ax.annotate(note, xy=(0, 0), xycoords=("axes fraction", ax.xaxis.label),
                    xytext=(0, -6), textcoords="offset points", ha="left", va="top",
                    fontsize=8, color=MUTED)
    ax.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#b5b4ae")
    ax.tick_params(colors=INK2, labelsize=9)


def _fig(w=8, h=4.5):
    f = Figure(figsize=(w, h), dpi=100, layout="constrained")
    return f


def color_map(names):
    return {n: SERIES[i % len(SERIES)] for i, n in enumerate(names)}


# --------------------------------------------------------------------------
def fig_calibration(project):
    try:
        project.link_calibrations()
    except ValueError:
        pass
    cals = [c for c in project.calibrations if c.mode == "poly" and len(c.ec) >= 2]
    refs = [c for c in project.calibrations
            if c.mode == "ref" and len(c.ec) >= 2 and c.coef]
    nacl = [c for c in project.calibrations if c.mode == "nacl"]
    if not (cals or refs or nacl):
        return None
    f = _fig(12 if refs else 8, 4.5)
    ax = f.add_subplot(121 if refs else 111)
    cm = color_map([c.name for c in project.calibrations])
    hi = max([max(c.ec) for c in cals] +
             [float(np.max(c.to_ref(c.ec))) for c in refs] + [0.0]) or 2000.0
    for c in cals:
        e = np.linspace(min(c.ec), max(c.ec), 200)
        ax.plot(c.ec, c.conc, "o", ms=7, color=cm[c.name], mec="white", mew=1.5, label=c.name)
        ax.plot(e, c.to_conc(e), "-", lw=2, color=cm[c.name],
                label=f"{c.equation(4)}  (R² = {c.r2:.4f})")
    for c in nacl:
        e = np.linspace(0, hi, 200)
        ax.plot(e, c.to_conc(e), "-", lw=2, color=cm[c.name],
                label=f"{c.name}: NaCl teórico, 25 °C")
    for c in refs:
        if c._target is None:
            continue
        e = np.linspace(min(c.ec), max(c.ec), 200)
        ax.plot(e, c.to_conc(e), "--", lw=1.8, color=cm[c.name],
                label=f"{c.name} (sonda → '{c.target}')")
    _style(ax, "Condutividade (µS/cm)", "Concentração de NaCl (kg/m³)",
           "Conversão da condutividade (EC) para concentração")
    ax.legend(fontsize=8, frameon=False)
    if refs:
        a2 = f.add_subplot(122)
        top = max(max(max(c.ec), max(c.ref_ec)) for c in refs)
        a2.plot([0, top], [0, top], ":", lw=1, color=INK2, label="1:1")
        for c in refs:
            e = np.linspace(min(c.ec), max(c.ec), 200)
            a2.plot(c.ec, c.ref_ec, "o", ms=7, color=cm[c.name], mec="white", mew=1.5,
                    label=c.name)
            a2.plot(e, c.to_ref(e), "-", lw=2, color=cm[c.name],
                    label=f"{c.equation(4).split('  →')[0]}  (R² = {c.r2:.4f})")
        _style(a2, "Condutividade da sonda (µS/cm)", "Condutividade de referência (µS/cm)",
               "Calibração da sonda de condutividade")
        a2.legend(fontsize=8, frameon=False)
    return f


def fig_raw(R):
    f = _fig(9, 4.8)
    ax = f.add_subplot(111)
    cm = color_map(list(R.curves))
    for n, cv in R.curves.items():
        unit = "µS/cm" if cv.kind == "ec" else "kg/m³"
        ax.plot(cv.t, cv.value, lw=1.5, color=cm[n], label=f"{n} ({unit})")
        ax.plot(cv.t, cv.background, lw=1, ls="--", color=cm[n], alpha=0.8)
        ax.axvspan(cv.t_start, min(cv.t_end, cv.t[-1]), color=cm[n], alpha=0.06)
    _style(ax, "Tempo desde o lançamento (s)", "Condutividade medida (µS/cm)",
           "Séries brutas da condutividade",
           note="A linha tracejada representa a condutividade base do rio detectada pelo software. A faixa sombreada representa a pluma")
    ax.legend(fontsize=8, frameon=False)
    return f


def fig_concentration(R):
    f = _fig(9, 4.8)
    ax = f.add_subplot(111)
    prj = R.project
    secs = [s.name for s in prj.sections]
    cm = color_map(secs)
    k = {}
    for p in prj.points:
        if p.name not in R.curves:
            continue
        cv = R.curves[p.name]
        i = k.setdefault(p.section, 0)
        k[p.section] += 1
        ax.plot(cv.t, cv.c, lw=1.6, ls=LS[i % 4], color=cm.get(p.section, INK),
                label=f"{p.name} — {p.section} ({p.lateral})" if p.lateral else
                f"{p.name} — {p.section}")
        if len(cv.t_tail):
            ax.plot(cv.t_tail, cv.c_tail, lw=1.2, ls=":", color=cm.get(p.section, INK))
    for s, cv in R.section_curves.items():
        if cv.name.endswith("(média)"):
            nz = np.where(cv.c > 0)[0]
            sl = slice(max(nz[0] - 5, 0), nz[-1] + 6) if len(nz) else slice(None)
            ax.plot(cv.t[sl], cv.c[sl], lw=2.6, color=cm.get(s, INK), alpha=0.55, label=cv.name)
    _style(ax, "Tempo desde o lançamento (s)", "Concentração do traçador (kg/m³)",
           "Concentração de NaCl medida ao longo do tempo")
    ax.legend(fontsize=8, frameon=False)
    return f


def fig_ade(R, name):
    r = R.single.get(name, {}).get("ade")
    if not r:
        return None
    cv = R.curves.get(name) or next((c for c in R.section_curves.values() if c.name == name), None)
    f = _fig(8, 4.2)
    ax = f.add_subplot(111)
    t, c = cv.analysis_curve()
    ax.plot(t, c, "o", ms=3.5, color=SERIES[0], alpha=0.7, label="observado")
    ax.plot(r["t"], r["pred"], lw=2, color=SERIES[1],
            label=f"ADE: U = {r['U']:.3f} m/s, K = {r['D']:.4f} m²/s (NSE = {r['NSE']:.3f})")
    _style(ax, "Tempo desde o lançamento (s)", "Concentração de NaCl (kg/m³)", f"Método do ajuste da Advection-Dispersion Equation (ADE) — {name}")
    ax.legend(fontsize=8, frameon=False)
    return f


def fig_chatwin(R, name):
    res = R.single.get(name, {})
    rs = [(k, res[k]) for k in ("chatwin", "chatwin_MA") if k in res and res[k].get("ok")]
    if not rs:
        return None
    f = _fig(8, 4.2)
    ax = f.add_subplot(111)
    for i, (k, r) in enumerate(rs):
        lab = "M/A dos dados" if k == "chatwin" else "M/A = M/A_seção"
        ax.plot(r["t"], r["y"], "o", ms=4, color=SERIES[2 * i], alpha=0.8, label=lab)
        tt = np.linspace(r["t"].min(), r["t"].max(), 50)
        ax.plot(tt, r["b"] + r["a"] * tt, lw=2, color=SERIES[2 * i + 1],
                label=f"y = {r['b']:.3f} {r['a']:+.4f} t  → U = {r['U']:.3f} m/s, "
                      f"K = {r['D']:.4f} m²/s (R² = {r['R2']:.3f})")
    ax.axhline(0, color="#b5b4ae", lw=1)
    _style(ax, "Tempo (s)", "Parâmetro de Chatwin Y", f"Método de Chatwin — {name}",
           note="O parâmetro de Chatwin é calculado como Y = ±√[t·ln(k / (C√t))]")
    ax.legend(fontsize=8, frameon=False)
    return f


def fig_routing(R, key):
    res = R.pairs.get(key, {})
    r = res.get("routing")
    if not r:
        return None
    f = _fig(9, 4.6)
    gs = f.add_gridspec(1, 3)
    ax = f.add_subplot(gs[0, :2])
    ax.plot(r["t1"], r["c1"], lw=1.6, color=SERIES[0], label=f"{key[0]} (montante, observado)")
    ax.plot(r["t"], r["c2"], "o", ms=3.5, color=SERIES[1], alpha=0.75,
            label=f"{key[1]} (jusante, observado)")
    ax.plot(r["t"], r["pred"], lw=2, color=SERIES[6],
            label=f"Propagado: K = {r['D']:.4f} m²/s, U = {r['U']:.3f} m/s (NSE = {r['NSE']:.3f})")
    rm = res.get("routing_manual")
    if rm:
        ax.plot(rm["t"], rm["pred"], lw=1.5, ls="--", color=SERIES[7],
                label=f"Manual: K = {rm['D']:.3g}, U = {rm['U']:.3g} (NSE = {rm['NSE']:.3f})")
    _style(ax, "Tempo desde o lançamento (s)", "Concentração de NaCl (kg/m³)", f"Método da propagação entre duas estações: {key[0]} para {key[1]}")
    ax.legend(fontsize=7.5, frameon=False)
    ax2 = f.add_subplot(gs[0, 2])
    ax2.semilogx(r["D_scan"], r["RMSE_scan"], lw=2, color=SERIES[0])
    ax2.axvline(r["D"], color=SERIES[1], lw=1.5, ls="--")
    _style(ax2, "Coeficiente de difusão turbulenta (m²/s)", "Erro quadrático médio da concentração (kg/m³)", "Convergência")
    return f


def fig_summary(R):
    df = R.tables.get("Resumo U e K")
    if df is None or df.empty:
        return None
    d = df[np.isfinite(df["K (m²/s)"].astype(float))]
    d = d[d["K (m²/s)"] > 0]
    if d.empty:
        return None
    f = _fig(9, 0.8 + 0.34 * len(d) + 0.4)
    ax = f.add_subplot(111)
    alvos = list(dict.fromkeys(d["Alvo"]))
    cm = color_map(alvos)
    y = np.arange(len(d))[::-1]
    ax.barh(y, d["K (m²/s)"], color=[cm[a] for a in d["Alvo"]], height=0.62, edgecolor="white",
            linewidth=2)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{a} · {m}" for a, m in zip(d["Alvo"], d["Método"])], fontsize=8)
    ax.set_xscale("log")
    for yi, v in zip(y, d["K (m²/s)"]):
        ax.text(v * 1.05, yi, f"{v:.3g}", va="center", fontsize=8, color=INK2)
    ax.set_xlim(d["K (m²/s)"].min() / 2, d["K (m²/s)"].max() * 3)
    _style(ax, "Coeficiente de difusão turbulenta (m²/s)", "", "Coeficiente de difusão turbulenta por diferentes métodos")
    return f


def fig_mass(R):
    df = R.tables.get("Curvas de concentração")
    if df is None or df.empty:
        return None
    f = _fig(8, 3.8)
    ax = f.add_subplot(111)
    cm = color_map(list(df["Ponto"]))
    x = np.arange(len(df))
    ax.bar(x, df["∫C dt (kg·s/m³)"], color=[cm[n] for n in df["Ponto"]], width=0.6,
           edgecolor="white", linewidth=2)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{n}\n{xx:g} m" for n, xx in zip(df["Ponto"], df["Distância do lançamento (m)"])],
                       fontsize=8)
    for xi, v, q in zip(x, df["∫C dt (kg·s/m³)"], df["Vazão do rio pelo traçador (m³/s)"]):
        lab = f"{v:.3g}" + (f"\nQ = {q:.3g} m³/s" if np.isfinite(q) else "")
        ax.text(xi, v, lab, ha="center", va="bottom", fontsize=8, color=INK2)
    _style(ax, "", "Integral da concentração ao longo do tempo (kg·s/m³)",
           "Conservação de massa do constituinte",
           note="A integral da concentração ao longo do tempo deve ser igual em todas as seções. ")
    ax.margins(y=0.25)
    return f


def fig_lateral(R, section):
    pts = [p for p in R.project.points if p.section == section and p.name in R.curves]
    if len(pts) < 2:
        return None
    f = _fig(8, 4.2)
    ax = f.add_subplot(111)
    for i, p in enumerate(pts):
        cv = R.curves[p.name]
        ax.plot(cv.t, cv.c, lw=1.6, color=SERIES[i % 8], label=f"{p.name} ({p.lateral or '—'})")
    m = R.section_curves[section]
    ax.plot(m.t, m.c, lw=2.6, color=INK, alpha=0.6, label="Média da seção")
    _style(ax, "Tempo (s)", "C (kg/m³)", f"Distribuição lateral — seção {section}")
    ax.legend(fontsize=8, frameon=False)
    return f


def make_figures(R):
    figs = {}

    def add(k, f):
        if f is not None:
            figs[k] = f

    add("01 Calibracao", fig_calibration(R.project))
    add("02 Series brutas", fig_raw(R))
    add("03 Serie de concentracao", fig_concentration(R))
    add("04 Conservação da massa", fig_mass(R))
    add("05 Resumo K", fig_summary(R))
    for s in R.section_curves:
        add(f"06 Análise transversal: {s}", fig_lateral(R, s))
    for name in R.single:
        add(f"07 Método ADE: {name}", fig_ade(R, name))
        add(f"08 Método de Chatwin: {name}", fig_chatwin(R, name))
    for key in R.pairs:
        add(f"09 Método da propagação: {key[0]}_{key[1]}", fig_routing(R, key))
    R.figures = figs
    return figs
