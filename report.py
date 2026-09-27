# -*- coding: utf-8 -*-
"""Gravação dos resultados: figuras PNG, planilha Excel, relatório em texto."""
from __future__ import annotations

import datetime as _dt
import os
import re

import numpy as np
import pandas as pd

from .plots import make_figures


def _safe(name):
    return re.sub(r"[^\w\-\.]+", "_", name, flags=re.UNICODE).strip("_")[:80]


def report_text(R):
    prj = R.project
    L = []
    L.append("=" * 78)
    L.append(f" DISPERSION ANALYZER — relatório\n {prj.name}")
    L.append(f" Gerado em {_dt.datetime.now():%d/%m/%Y %H:%M}")
    L.append("=" * 78)
    L.append(f"Massa lançada: {prj.M_injected if prj.M_injected else '—'} kg   |   "
             f"Lançamento: {prj.injection_time or ('t = 0 dos arquivos' if prj.time_is_relative else '—')}")
    L.append(f"Seções: {len(prj.sections)}   Pontos: {len([p for p in prj.points if p.enabled])}")
    L.append("")
    for k, df in R.tables.items():
        L.append("-" * 78)
        L.append(f" {k}")
        L.append("-" * 78)
        with pd.option_context("display.width", 200, "display.max_columns", 50,
                               "display.float_format", "{:.5g}".format):
            L.append(df.to_string(index=False))
        L.append("")
    if R.warnings:
        L.append("-" * 78)
        L.append(" Avisos")
        L.append("-" * 78)
        L += [f" * {w}" for w in R.warnings]
    L.append("")
    L.append("-" * 78)
    L.append("Notas dos métodos:")
    L.append("-" * 78)
    L.append(" - A concentração é corrigida pela condutividade natural do rio: C = f(EC) − f(EC_fundo), f = curva de calibração")
    L.append(" - A calibração da condutividade pode ser feita com um sensor de referência (opcional)")
    L.append(" - A condutividade é convertida em concentração pela curva de calibração")
    L.append(" - Cálculo dos momentos: integrais das curvas C(t), feitas pela regra do trapézio.")
    L.append(" - Método dos momentos em um ponto: nuvem congelada (Taylor), depende da distância e do instante do lançamento.")
    L.append(" - Método dos percentis em um ponto: σt = (t84 − t16)/2, menos sensível às caudas.")
    L.append(" - Método do ajuste da Advection-Dispersion Equation (ADE): solução analítica ajustada à curva observada por MMQ (U, K e M/A).")
    L.append(" - Método de Chatwin: linearização da solução analítica da ADE; a constante k é ajustada por iteração.")
    L.append(" - Método de Fischer (variação dos momentos): diferença de <t> e σt² entre duas estações (independe do lançamento).")
    L.append(" - Método da propagação: a curva do ponto 1 é propagada até o ponto 2 pela ADE; K (e U) ajustados por MMQ.")
    L.append(" - Vazão por diluição: Q = M/∫C dt; exige mistura completa na seção.")
    return "\n".join(L)


def save_results(R, outdir=None, dpi=150):
    prj = R.project
    outdir = outdir or prj.resolve(prj.output_dir) or "resultados"
    os.makedirs(outdir, exist_ok=True)
    figdir = os.path.join(outdir, "figuras")
    os.makedirs(figdir, exist_ok=True)
    if not R.figures:
        make_figures(R)
    for k, f in R.figures.items():
        f.savefig(os.path.join(figdir, _safe(k) + ".png"), dpi=dpi)

    xlsx = os.path.join(outdir, "resultados.xlsx")
    with pd.ExcelWriter(xlsx) as xw:
        for k, df in R.tables.items():
            df.to_excel(xw, sheet_name=_safe(k)[:31], index=False)
        # séries processadas
        for n, cv in list(R.curves.items()) + \
                [(k, v) for k, v in R.section_curves.items() if v.name.endswith("(média)")]:
            t, c = cv.analysis_curve()
            val = np.interp(t, cv.t, cv.value) if len(cv.value) == len(cv.t) else np.nan
            df = pd.DataFrame({"tempo_s": t, "C_excesso_kg_m3": c,
                               "sinal_medido": np.where(t <= cv.t[-1], val, np.nan)})
            df.to_excel(xw, sheet_name=_safe("serie_" + n)[:31], index=False)
        # propagação: observado x previsto
        for (s1, s2), res in R.pairs.items():
            r = res.get("routing")
            if r:
                pd.DataFrame({"tempo_s": r["t"], "C_obs": r["c2"], "C_propagada": r["pred"]}) \
                    .to_excel(xw, sheet_name=_safe(f"prop_{s1}_{s2}")[:31], index=False)
        pd.DataFrame({"avisos": R.warnings or ["—"]}).to_excel(xw, sheet_name="avisos",
                                                               index=False)

    with open(os.path.join(outdir, "relatorio.txt"), "w", encoding="utf-8") as fh:
        fh.write(report_text(R))
    try:
        prj.save(os.path.join(outdir, "projeto_usado.json"), update_base=False)
    except Exception:
        pass
    return outdir
