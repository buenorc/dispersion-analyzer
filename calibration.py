# -*- coding: utf-8 -*-
"""
Curva de calibração condutividade elétrica (µS/cm) -> concentração de NaCl (kg/m³ = g/L).

Cada condutivímetro (sonda) tem a sua curva. Modos:

  poly    C = polinômio(EC), ajustado a padrões de sal medidos com a sonda;
  factor  C = fator·EC (sem pontos de calibração);
  nacl    C a partir da condutividade teórica do NaCl a 25 °C (tabela de Λ);
  ref     calibração em DUAS ETAPAS: a sonda é comparada com um condutivímetro
          de referência (EC_ref = polinômio(EC_sonda)) e a EC_ref é convertida em
          concentração por outra calibração do projeto (poly, factor ou nacl),
          a do condutivímetro de referência. Assim os padrões de sal só precisam
          ser medidos uma vez, com o instrumento de precisão, e cada sonda é
          comparada com ele (em balde ou no próprio rio).

O ajuste é feito com precisão total (np.polyfit). ATENÇÃO: não copie os
coeficientes do rótulo da linha de tendência do Excel: ele mostra só 1 algarismo
significativo por padrão (no L3, 2,2508E-06 virou 2E-06, o que dá ~13 % de erro
no pico).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np

MODES = ("poly", "factor", "nacl", "ref")

# Condutividade molar do NaCl em água a 25 °C (S·cm²/mol), CRC Handbook of
# Chemistry and Physics ("Equivalent conductivity of electrolytes in aqueous
# solution"). κ (µS/cm) = Λ · c (mol/L) · 1000.
NACL_MOLAR_MASS = 58.443                 # g/mol
_NACL_C = np.array([0.0, 0.0005, 0.001, 0.005, 0.01, 0.02, 0.05, 0.1])        # mol/L
_NACL_L = np.array([126.39, 124.44, 123.68, 120.59, 118.45, 115.70, 111.01, 106.69])


def nacl_ec25(conc_gl):
    """Condutividade (µS/cm, 25 °C) de uma solução de NaCl em água pura."""
    c = np.asarray(conc_gl, float) / NACL_MOLAR_MASS
    lam = np.interp(np.sqrt(np.clip(c, 0, None)), np.sqrt(_NACL_C), _NACL_L)
    return lam * c * 1000.0


_NACL_GRID = np.linspace(0.0, np.sqrt(_NACL_C[-1] * NACL_MOLAR_MASS), 2000) ** 2   # g/L
_NACL_EC = nacl_ec25(_NACL_GRID)
NACL_EC_MAX = float(_NACL_EC[-1])        # limite da tabela (~10 700 µS/cm)


def nacl_conc(ec25):
    """Inversa de nacl_ec25: concentração de NaCl (g/L) a partir de EC a 25 °C."""
    return np.interp(np.asarray(ec25, float), _NACL_EC, _NACL_GRID)


@dataclass
class Calibration:
    name: str = "Sonda 1"
    ec: list = field(default_factory=list)      # condutividade medida pela sonda (µS/cm)
    conc: list = field(default_factory=list)    # concentração (kg/m³ = g/L)
    degree: int = 2                              # 1, 2 ou 3
    mode: str = "poly"                           # 'poly', 'factor', 'nacl' ou 'ref'
    # modo "fator": C = factor * EC (sem pontos de calibração)
    factor: float = 0.00050                      # kg/m³ por µS/cm (~NaCl)
    # entrada como no L3: nº de colheres (doses) num volume conhecido
    input_mode: str = "conc"                     # 'conc' (g/L) ou 'doses'
    x_input: list = field(default_factory=list)  # 1ª coluna digitada (conc., doses ou EC_ref)
    dose_g: float = 0.125                        # massa de sal por dose (g)
    vol_ml: float = 700.0                        # volume de água (mL)
    # modo "ref": EC da sonda -> EC do condutivímetro de referência -> C
    ref_ec: list = field(default_factory=list)   # EC do condutivímetro de referência (µS/cm)
    target: str = ""                             # calibração que converte EC_ref em C
    # preenchidos pelo ajuste
    coef: list = field(default_factory=list)     # maior grau primeiro
    r2: float = float("nan")
    rmse: float = float("nan")

    def __post_init__(self):
        self._target = None                      # Calibration ligada (modo 'ref')

    # ------------------------------------------------------------------
    @staticmethod
    def conc_from_doses(n_doses, dose_mass_g, volume_ml):
        """Concentração (g/L) a partir do nº de colheres/doses de sal
        adicionadas num volume de água (como na planilha L3)."""
        n = np.asarray(n_doses, float)
        return n * dose_mass_g / (volume_ml / 1000.0)

    @property
    def unit(self):
        """Unidade da saída do polinômio ajustado."""
        return "µS/cm" if self.mode == "ref" else "kg/m³"

    def link(self, target):
        """Liga a calibração de referência (modo 'ref')."""
        self._target = None
        if target is self:
            raise ValueError(f"Calibração '{self.name}': a referência não pode ser ela mesma.")
        if target is not None and target.mode == "ref":
            raise ValueError(f"Calibração '{self.name}': a referência '{target.name}' também é "
                             f"do tipo sonda × referência. Escolha uma curva EC para C.")
        self._target = target
        return self

    def fit(self):
        if self.mode == "factor":
            self.coef = [self.factor, 0.0]
            self.r2 = self.rmse = float("nan")
            return self
        if self.mode == "nacl":
            self.coef = []
            self.r2 = self.rmse = float("nan")
            return self
        if self.mode == "ref":
            if self.x_input:
                self.ref_ec = [float(v) for v in self.x_input]
            y = np.asarray(self.ref_ec, float)
        else:
            if self.x_input:
                xi = np.asarray(self.x_input, float)
                self.conc = [float(v) for v in (self.conc_from_doses(xi, self.dose_g, self.vol_ml)
                                                if self.input_mode == "doses" else xi)]
            y = np.asarray(self.conc, float)
        x = np.asarray(self.ec, float)
        ok = np.isfinite(x) & np.isfinite(y)
        x, y = x[ok], y[ok]
        deg = int(min(self.degree, max(len(x) - 1, 1)))
        if len(x) < 2:
            raise ValueError(f"Calibração '{self.name}': são necessários ao menos 2 pontos.")
        p = np.polyfit(x, y, deg)
        yh = np.polyval(p, x)
        ss = np.sum((y - y.mean()) ** 2)
        self.coef = [float(c) for c in p]
        self.r2 = float(1 - np.sum((y - yh) ** 2) / ss) if ss > 0 else float("nan")
        self.rmse = float(np.sqrt(np.mean((y - yh) ** 2)))
        return self

    # ------------------------------------------------------------------
    def to_ref(self, ec):
        """Modo 'ref': EC da sonda -> EC do condutivímetro de referência."""
        if not self.coef:
            self.fit()
        return np.polyval(self.coef, np.asarray(ec, float))

    def to_conc(self, ec):
        if self.mode == "nacl":
            return nacl_conc(ec)
        if self.mode == "ref":
            if self._target is None:
                raise ValueError(f"Calibração '{self.name}': escolha a curva do condutivímetro "
                                 f"de referência (EC para concentração).")
            return self._target.to_conc(self.to_ref(ec))
        if not self.coef:
            self.fit()
        return np.polyval(self.coef, np.asarray(ec, float))

    def excess(self, ec, ec_background):
        """Concentração em excesso (acima do rio): f(EC) - f(EC_fundo)."""
        return self.to_conc(ec) - self.to_conc(ec_background)

    @property
    def ec_range(self):
        if self.mode == "factor":
            return (-np.inf, np.inf)
        if self.mode == "nacl":
            return (0.0, NACL_EC_MAX)
        if not self.ec:
            return (-np.inf, np.inf)
        return (float(np.nanmin(self.ec)), float(np.nanmax(self.ec)))

    def equation(self, digits=6):
        if self.mode == "nacl":
            return "C = NaCl teórico a 25 °C (Λ tabelada, CRC)"
        if not self.coef:
            self.fit()
        terms = []
        n = len(self.coef) - 1
        for i, c in enumerate(self.coef):
            k = n - i
            s = f"{c:+.{digits}g}"
            terms.append(s + ("·EC" + (f"^{k}" if k > 1 else "") if k > 0 else ""))
        if self.mode == "ref":
            return "EC_ref = " + " ".join(terms).lstrip("+") + f"  →  C: '{self.target}'"
        return "C = " + " ".join(terms).lstrip("+")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        obj = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        y = obj.ref_ec if obj.mode == "ref" else obj.conc
        if obj.mode in ("factor", "nacl") or (obj.ec and (y or obj.x_input)):
            obj.fit()
        return obj
