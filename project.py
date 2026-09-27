# -*- coding: utf-8 -*-
"""
Modelo do projeto (experimento) — salvo/lido em JSON.

Estrutura flexível:
  * um ou vários pontos de monitoramento;
  * vários pontos na MESMA seção transversal (ex.: margem esquerda, centro,
    margem direita). A seção recebe uma curva média (ponderada) e os pontos
    também são analisados individualmente;
  * cada ponto tem o seu arquivo, as suas colunas, a sua sonda/calibração e
    o seu ajuste de relógio.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict

from .calibration import Calibration
from .processing import ProcessingOptions


@dataclass
class Section:
    name: str
    x: float                         # distância do lançamento (m)
    width: float | None = None       # largura (m)
    depth: float | None = None       # profundidade média (m)
    area: float | None = None        # área molhada (m²) — se vazio, largura·prof.
    float_dist: float | None = None  # distância percorrida pelo flutuador (m)
    float_times: list = field(default_factory=list)  # tempos dos flutuadores (s)
    velocity: float | None = None    # velocidade média conhecida (m/s)
    Q: float | None = None           # vazão conhecida (m³/s)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def _clock_shift(inj_project, inj_point, dayfirst=True):
    """Diferença (s) entre o lançamento do projeto e o horário antigo do ponto."""
    if not inj_point or not str(inj_point).strip() or not inj_project:
        return 0.0
    a, b = str(inj_project).strip(), str(inj_point).strip()
    try:
        return float(a.replace(",", ".")) - float(b.replace(",", "."))
    except ValueError:
        pass
    try:
        import pandas as pd
        ta, tb = pd.to_datetime(a, dayfirst=dayfirst), pd.to_datetime(b, dayfirst=dayfirst)
        if ":" in a and ":" in b and (len(a) <= 8 or len(b) <= 8):   # um deles só 'hh:mm:ss'
            ta, tb = ta - ta.normalize(), tb - tb.normalize()
        return (ta - tb).total_seconds()
    except (ValueError, TypeError):
        return 0.0


@dataclass
class Point:
    name: str
    section: str
    file: str = ""
    lateral: str = ""                # posição na seção (ME, C, MD, 2 m da margem...)
    weight: float = 1.0              # peso na média da seção (subárea / vazão parcial)
    sheet: str = ""
    time_col: str = ""
    value_col: str = ""
    temp_col: str = ""
    kind: str = "ec"                 # 'ec' (µS/cm) ou 'conc' (kg/m³)
    calibration: str = ""            # nome da calibração
    time_offset: float = 0.0         # correção do relógio (s)
    enabled: bool = True
    processing: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @property
    def options(self):
        return ProcessingOptions.from_dict(self.processing)


@dataclass
class AnalysisOptions:
    single_moments: bool = True
    single_percentiles: bool = True
    ade_fit: bool = True
    chatwin: bool = True
    chatwin_level: float = 0.10
    two_station_moments: bool = True
    routing: bool = True
    routing_fit_U: bool = False
    routing_normalize_mass: bool = False
    routing_manual: bool = False     # avaliar também D e U manuais (tentativa e erro)
    routing_D_manual: float | None = None
    routing_U_manual: float | None = None
    pairs: str = "consecutive"       # 'consecutive' ou 'all'
    use_tail: bool = True
    analyze_points_individually: bool = True

    @classmethod
    def from_dict(cls, d):
        d = dict(d or {})
        # projetos antigos: sem a caixa, o D manual preenchido valia como ligado
        if "routing_manual" not in d:
            d["routing_manual"] = d.get("routing_D_manual") is not None
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Project:
    name: str = "Experimento de dispersão"
    output_dir: str = "resultados"
    M_injected: float | None = None      # massa de NaCl lançada (kg)
    injection_time: str = ""             # 'dd/mm/aaaa hh:mm:ss' ou 'hh:mm:ss' ou segundos
    time_is_relative: bool = True        # tempo dos arquivos já é "s desde o lançamento"
    dayfirst: bool = True
    injection_position: str = "center"   # 'center' ou 'margin'
    slope: float | None = None           # declividade (m/m) para u* = sqrt(g R S)
    float_coef: float = 0.85             # V_média = coef · V_superficial
    calibrations: list = field(default_factory=list)
    sections: list = field(default_factory=list)
    points: list = field(default_factory=list)
    analysis: AnalysisOptions = field(default_factory=AnalysisOptions)
    base_dir: str = ""                   # pasta do arquivo .json (caminhos relativos)

    # ------------------------------------------------------------------
    def calibration(self, name):
        try:
            self.link_calibrations()
        except ValueError:
            pass            # o erro aparece ao converter (to_conc) e nos avisos
        for c in self.calibrations:
            if c.name == name:
                return c
        return self.calibrations[0] if self.calibrations else None

    def link_calibrations(self):
        """Liga cada calibração 'sonda × referência' à curva EC → C indicada."""
        by_name = {c.name: c for c in self.calibrations}
        for c in self.calibrations:
            if c.mode == "ref":
                c.link(by_name.get(c.target))

    def section(self, name):
        for s in self.sections:
            if s.name == name:
                return s
        return None

    def resolve(self, path):
        if not path or os.path.isabs(path) or not self.base_dir:
            return path
        return os.path.normpath(os.path.join(self.base_dir, path))

    def ensure_sections(self):
        for p in self.points:
            if self.section(p.section) is None:
                self.sections.append(Section(p.section, 0.0))
        self.sections.sort(key=lambda s: s.x)

    # ------------------------------------------------------------------
    def to_dict(self):
        d = asdict(self)
        d.pop("base_dir", None)
        return d

    def save(self, path, update_base=True):
        base = os.path.dirname(os.path.abspath(path))
        d = self.to_dict()
        for p in d["points"]:
            f = self.resolve(p.get("file"))
            p["file"] = f
            if f and os.path.isabs(f):
                try:
                    p["file"] = os.path.relpath(f, base)
                except ValueError:
                    pass  # outro disco no Windows
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(d, fh, indent=2, ensure_ascii=False)
        if update_base:
            self.base_dir = base
            for p in self.points:
                p.file = self.resolve(p.file) if not os.path.isabs(p.file or "/") else p.file

    @classmethod
    def from_dict(cls, d, base_dir=""):
        p = cls(**{k: v for k, v in d.items()
                   if k in cls.__dataclass_fields__ and
                   k not in ("calibrations", "sections", "points", "analysis")})
        p.calibrations = [Calibration.from_dict(c) for c in d.get("calibrations", [])]
        p.sections = [Section.from_dict(s) for s in d.get("sections", [])]
        # projetos antigos: o ponto tinha x próprio; hoje vale sempre o x da seção.
        # Se a seção não existia, ela é criada com o x que estava no ponto.
        for x in d.get("points", []):
            if x.get("x") is not None and p.section(x.get("section")) is None:
                p.sections.append(Section(x["section"], float(x["x"])))
        p.points = [Point.from_dict(x) for x in d.get("points", [])]
        # projetos antigos: o ponto podia ter o seu próprio horário de lançamento
        # (lido no relógio do datalogger). Hoje isso é a "correção do relógio".
        for pt, x in zip(p.points, d.get("points", [])):
            dt = _clock_shift(p.injection_time, x.get("injection_time"), p.dayfirst)
            if dt:
                pt.time_offset = (pt.time_offset or 0.0) + dt
        p.analysis = AnalysisOptions.from_dict(d.get("analysis"))
        p.base_dir = base_dir
        return p

    @classmethod
    def load(cls, path):
        with open(path, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        return cls.from_dict(d, os.path.dirname(os.path.abspath(path)))
