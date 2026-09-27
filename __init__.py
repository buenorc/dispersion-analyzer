# -*- coding: utf-8 -*-
"""Dispersion Analyzer — análise de experimentos de traçador (NaCl) em rios.

Estima velocidade média, coeficiente de dispersão longitudinal, vazão por
diluição e conservação de massa a partir de curvas de condutividade.
"""
__version__ = "1.0.0"
__author__ = "Rafael de Carvalho Bueno"
__credits__ = ("Desenvolvido para uso na disciplina de Dinâmica de Lagos")
__year__ = "2026"

from .calibration import Calibration  # noqa: F401
from .project import Project, Section, Point, AnalysisOptions  # noqa: F401
from .analysis import run_analysis  # noqa: F401
