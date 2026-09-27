# -*- coding: utf-8 -*-
"""
Dispersion Analyzer — interface gráfica (tkinter).
Author: de Carvalho Bueno, Rafael
"""
from __future__ import annotations

import gc
import os
import sys
import threading
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from . import __version__, __author__, __credits__, __year__
from .analysis import run_analysis, load_point_series
from .calibration import Calibration
from .io_utils import read_table, guess_columns, guess_temp_column
from .plots import make_figures, fig_calibration, _style, SERIES
from .processing import process_curve
from .project import Project, Section, Point, AnalysisOptions
from .report import save_results, report_text
from .widgets import EditableTable, DataFrameView, fnum
from . import theme as th

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
FROZEN = getattr(sys, "frozen", False)
if FROZEN:
    # Executável (PyInstaller): o pacote é extraído numa pasta temporária que
    # some ao fechar o programa. Os exemplos vão empacotados e são copiados para
    # uma pasta gravável do usuário, onde os resultados também ficam.
    BUNDLE_DIR = getattr(sys, "_MEIPASS", PKG_DIR)
    ROOT_DIR = os.path.join(os.path.expanduser("~"), "Documents", "Dispersion Analyzer")
else:
    ROOT_DIR = os.path.dirname(PKG_DIR)
EXAMPLE = os.path.join(ROOT_DIR, "exemplos", "L3", "projeto_L3.json")
EXAMPLE_SYN = os.path.join(ROOT_DIR, "exemplos", "sintetico", "projeto_sintetico.json")
EXAMPLES = [
    ("Experimento com 2 pontos", EXAMPLE,
     "Corrego do Aviário: 2 condutivímetros em dois pontos longitudinais."),
    ("Exemplo sintético", EXAMPLE_SYN,
     "Arquivos do datalogger com data/hora e 3 sondas na mesma seção; "
     "U = 0,25 m/s e D = 0,40 m²/s conhecidos."),
]
MUTED = th.MUTED

CAL_MODES = {
    "poly": "Padrões de sal medidos com a sonda",
    "nacl": "NaCl teórico (sem dados de entrada)",
    "factor": "Fator fixo linear",
    "ref": "Calibração com sonda de referência",
}
CAL_MODE_KEY = {v: k for k, v in CAL_MODES.items()}
CAL_HINTS = {
    "poly": "Soluções de sal medidas com a própria sonda."
            "Primeira coluna é a concentração ou nº de doses"
            "Segunda coluna é condutividade da sonda",
    "nacl": "Sem dados de entrada. Utiliza a condutividade tabelada do NaCl puro em água pura a 25 °C"
            "Referência: 0,584 g/L ≈ 1184 µS/cm (Válida até 10 700 µS/cm)"
            "A sonda precisa registrar EC compensada para 25 °C",
    "factor": "C = fator·EC (≈ 0,0005 kg/m³ por µS/cm para NaCl diluído).",
    "ref": "Calibração em duas etapas. Uma sonda de referência é calibrada com um outro método"
           "As sondas são calibradas com o sensor de referência"
           "É possível ter mais de uma sonda de referência",
}


# ==========================================================================
class FigurePanel(ttk.Frame):
    """Área que exibe uma Figure do matplotlib (com barra de zoom/salvar)."""

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.canvas = None
        self.toolbar = None
        self.fig = None

    def show(self, fig):
        if self.canvas is not None:
            self.canvas.get_tk_widget().destroy()
            self.toolbar.destroy()
        self.fig = fig
        if fig is None:
            self.canvas = None
            return
        self.canvas = FigureCanvasTkAgg(fig, master=self)
        self.toolbar = NavigationToolbar2Tk(self.canvas, self, pack_toolbar=False)
        self.toolbar.update()
        th.style_mpl_toolbar(self.toolbar)
        self.toolbar.pack(side="bottom", fill="x")
        fig.set_facecolor("white")
        self.canvas.get_tk_widget().configure(bg="white", highlightthickness=0)
        self.canvas.get_tk_widget().pack(side="top", fill="both", expand=True)
        self.canvas.draw_idle()


# ==========================================================================
class PointDialog(tk.Toplevel):
    """Janela para configurar um ponto de monitoramento."""

    def __init__(self, app, point: Point):
        super().__init__(app)
        self.app = app
        self.point = point
        self.result = None
        self.title(f"Ponto de monitoramento: {point.name}")
        h = min(900, self.winfo_screenheight() - 90)
        self.geometry(f"1200x{h}")
        self.transient(app)
        self.df = None

        o = point.options
        V = lambda v: tk.StringVar(value="" if v is None else str(v))
        self.v = dict(
            name=V(point.name), section=V(point.section), lateral=V(point.lateral),
            weight=V(point.weight), file=V(point.file), sheet=V(point.sheet),
            time_col=V(point.time_col), value_col=V(point.value_col), temp_col=V(point.temp_col),
            kind=V(point.kind), calibration=V(point.calibration), offset=V(point.time_offset),
            bmode=V(o.baseline_mode), bw0=V(o.baseline_window[0] if o.baseline_window else ""),
            bw1=V(o.baseline_window[1] if o.baseline_window else ""), bval=V(o.baseline_value),
            tmin=V(o.t_min), tmax=V(o.t_max), smooth=V(o.smooth), endthr=V(o.end_threshold),
        )
        self.enabled = tk.BooleanVar(value=point.enabled)
        self.clip = tk.BooleanVar(value=o.clip_negative)
        self.tail = tk.BooleanVar(value=o.tail_extrapolation)

        left = ttk.Frame(self, padding=8)
        left.pack(side="left", fill="y")
        right = ttk.Frame(self, padding=(0, 8, 8, 8))
        right.pack(side="left", fill="both", expand=True)

        def row(parent, r, label, widget, tip=""):
            """Põe rótulo, campo e dica na linha r; devolve os widgets (para ocultar)."""
            ws = [ttk.Label(parent, text=label), widget]
            ws[0].grid(row=r, column=0, sticky="w", pady=1)
            widget.grid(row=r, column=1, sticky="we", pady=1)
            if tip:
                ws.append(ttk.Label(parent, text=tip, foreground=MUTED))
                ws[2].grid(row=r, column=2, sticky="w", padx=4)
            return ws

        g = ttk.LabelFrame(left, text="Identificação", padding=6)
        g.pack(fill="x")
        first_group = g
        row(g, 0, "Nome", ttk.Entry(g, textvariable=self.v["name"], width=26))
        secs = [s.name for s in app.project.sections]
        row(g, 1, "Seção", ttk.Combobox(g, textvariable=self.v["section"], values=secs, width=24),
            "pontos com a mesma seção\nsão combinados para algumas métricas")
        row(g, 3, "Posição na seção", ttk.Entry(g, textvariable=self.v["lateral"], width=26),
            "ex.: ME, centro, MD")
        row(g, 4, "Peso na média", ttk.Entry(g, textvariable=self.v["weight"], width=26),
            "subárea ou vazão parcial")
        ttk.Checkbutton(g, text="Ponto ativo na análise", variable=self.enabled).grid(
            row=5, column=0, columnspan=2, sticky="w")

        g = ttk.LabelFrame(left, text="Arquivo de dados", padding=6)
        g.pack(fill="x", pady=6)
        f = ttk.Frame(g)
        ttk.Entry(f, textvariable=self.v["file"], width=30).pack(side="left", fill="x", expand=True)
        ttk.Button(f, text="…", width=3, command=self.browse).pack(side="left")
        row(g, 0, "Arquivo", f)
        row(g, 1, "Aba da planilha xlsx", ttk.Entry(g, textvariable=self.v["sheet"], width=26),
            "Necessária para arquivo xlsx")
        self.cb_t = ttk.Combobox(g, textvariable=self.v["time_col"], width=24)
        self.cb_v = ttk.Combobox(g, textvariable=self.v["value_col"], width=24)
        self.cb_T = ttk.Combobox(g, textvariable=self.v["temp_col"], width=24)
        row(g, 2, "Coluna do tempo", self.cb_t)
        row(g, 3, "Coluna da condutividade", self.cb_v)
        row(g, 4, "Coluna da temperatura", self.cb_T, "Opcional")
        row(g, 5, "Tipo do sinal", ttk.Combobox(g, textvariable=self.v["kind"],
                                                values=["ec", "conc"], width=24, state="readonly"),
            "ec = µS/cm e conc = kg/m³")
        row(g, 6, "Calibração (sonda)", ttk.Combobox(
            g, textvariable=self.v["calibration"],
            values=[c.name for c in app.project.calibrations], width=24, state="readonly"))
        row(g, 7, "Correção do relógio (s)", ttk.Entry(g, textvariable=self.v["offset"], width=26),
            "Datalogger não sincronizado")

        g = ttk.LabelFrame(left, text="Pré-processamento", padding=6)
        g.pack(fill="x")
        row(g, 0, "Fundo do rio", ttk.Combobox(g, textvariable=self.v["bmode"], width=24,
                                               values=["auto", "window", "value", "linear"],
                                               state="readonly"),
            "auto = antes da subida")
        f = ttk.Frame(g)
        ttk.Entry(f, textvariable=self.v["bw0"], width=10).pack(side="left")
        ttk.Label(f, text=" a ").pack(side="left")
        ttk.Entry(f, textvariable=self.v["bw1"], width=10).pack(side="left")
        w_window = row(g, 1, "Janela da cond. natural (s)", f, "modo window")
        w_value = row(g, 2, "Condutividade natural do rio", ttk.Entry(g, textvariable=self.v["bval"], width=26),
                      "modo value (µS/cm)")

        def baseline_mode_changed(*_):
            # só mostra o campo do modo escolhido (auto e linear não usam nenhum)
            mode = self.v["bmode"].get()
            for ws, m in ((w_window, "window"), (w_value, "value")):
                for w in ws:
                    w.grid() if mode == m else w.grid_remove()
        self.v["bmode"].trace_add("write", baseline_mode_changed)
        baseline_mode_changed()
        f = ttk.Frame(g)
        ttk.Entry(f, textvariable=self.v["tmin"], width=10).pack(side="left")
        ttk.Label(f, text=" a ").pack(side="left")
        ttk.Entry(f, textvariable=self.v["tmax"], width=10).pack(side="left")
        row(g, 3, "Recorte dos dados (s)", f)
        row(g, 4, "Média móvel (amostras)", ttk.Entry(g, textvariable=self.v["smooth"], width=26), "Suavisa os dados de entrada")
        row(g, 5, "Fim da pluma (fração)", ttk.Entry(g, textvariable=self.v["endthr"], width=26),
            "Limite de detecção. 0,02 = 2 % do pico")
        f = ttk.Frame(g)
        ttk.Checkbutton(f, text="Zerar fora da pluma", variable=self.clip).pack(side="left")
        ttk.Checkbutton(f, text="Extrapolar cauda truncada", variable=self.tail).pack(
            side="left", padx=(16, 0))
        f.grid(row=6, column=0, columnspan=3, sticky="w", pady=(4, 0))

        b = ttk.Frame(left)
        b.pack(side="bottom", fill="x", pady=(8, 0), before=first_group)
        ttk.Button(b, text="Pré-visualizar", command=self.preview).pack(side="left")
        ttk.Button(b, text="OK", command=self.ok, style="Accent.TButton").pack(side="right")
        ttk.Button(b, text="Cancelar", command=self.destroy).pack(side="right", padx=4)

        self.head = tk.Text(right, height=7, font=("Consolas", 9), wrap="none")
        self.head.pack(fill="x")
        self.fig = FigurePanel(right)
        self.fig.pack(fill="both", expand=True)
        self.msg = ttk.Label(right, text="", foreground=th.ERROR, wraplength=700, justify="left")
        self.msg.pack(fill="x")

        if point.file:
            self.load_columns()
        self.grab_set()

    # ------------------------------------------------------------------
    def browse(self):
        f = filedialog.askopenfilename(parent=self, title="Arquivo de dados",
                                       filetypes=[("Dados", "*.txt *.csv *.tsv *.dat *.xlsx *.xls"),
                                                  ("Todos", "*.*")])
        if f:
            self.v["file"].set(f)
            self.v["time_col"].set("")
            self.v["value_col"].set("")
            self.load_columns()

    def load_columns(self):
        try:
            path = self.app.project.resolve(self.v["file"].get())
            self.df = read_table(path, self.v["sheet"].get() or None)
        except Exception as e:
            self.msg.config(text=f"Erro ao ler o arquivo: {e}")
            return
        cols = list(self.df.columns)
        for cb in (self.cb_t, self.cb_v, self.cb_T):
            cb.configure(values=[""] + cols if cb is self.cb_T else cols)
        t, v, kind = guess_columns(self.df)
        if not self.v["time_col"].get():
            self.v["time_col"].set(t)
        if not self.v["value_col"].get():
            self.v["value_col"].set(v)
            self.v["kind"].set(kind)
        if not self.v["temp_col"].get():
            self.v["temp_col"].set(guess_temp_column(self.df) or "")
        self.head.delete("1.0", "end")
        self.head.insert("end", f"{len(self.df)} linhas · colunas: {cols}\n")
        self.head.insert("end", self.df.head(5).to_string())
        self.msg.config(text="")

    def collect(self) -> Point:
        v = {k: s.get().strip() for k, s in self.v.items()}
        proc = dict(baseline_mode=v["bmode"] or "auto",
                    baseline_window=(fnum(v["bw0"]), fnum(v["bw1"])),
                    baseline_value=fnum(v["bval"]), t_min=fnum(v["tmin"]), t_max=fnum(v["tmax"]),
                    smooth=int(fnum(v["smooth"], 0)), end_threshold=fnum(v["endthr"], 0.02),
                    clip_negative=self.clip.get(), tail_extrapolation=self.tail.get())
        return Point(name=v["name"] or "P", section=v["section"] or v["name"] or "S1",
                     file=v["file"], lateral=v["lateral"],
                     weight=fnum(v["weight"], 1.0), sheet=v["sheet"], time_col=v["time_col"],
                     value_col=v["value_col"], temp_col=v["temp_col"], kind=v["kind"] or "ec",
                     calibration=v["calibration"], time_offset=fnum(v["offset"], 0.0),
                     enabled=self.enabled.get(), processing=proc)

    def preview(self):
        self.app.ui_to_project()
        p = self.collect()
        try:
            fig = self.app.preview_figure(p)
            self.fig.show(fig)
            self.msg.config(text=self.app._last_preview_msg)
        except Exception as e:
            self.msg.config(text=f"Erro: {e}")

    def ok(self):
        p = self.collect()
        if self.app.project.section(p.section) is None:
            messagebox.showwarning("Ponto", f"A seção '{p.section}' não existe. Crie a seção "
                                   "(com a distância do lançamento) na aba 3.",
                                   parent=self)
            return
        self.result = p
        self.destroy()


# ==========================================================================
class App(tk.Tk):
    def __init__(self, project_path=None):
        super().__init__()
        self.title(f"Dispersion Analyzer {__version__} — experimentos de traçador em rios")
        self.geometry("1320x860")
        self.minsize(1050, 700)
        if FROZEN and sys.platform.startswith("win"):
            try:   # ícone gerado pelo app/build.py; default= vale também p/ as janelas filhas
                self.iconbitmap(default=os.path.join(BUNDLE_DIR, "assets", "dispersion.ico"))
            except tk.TclError:
                pass
        th.apply_theme(self)
        self.project = Project()
        self.project.calibrations = [Calibration("Sonda 1")]
        self.project_path = None
        self.results = None
        self._cal_index = None
        self._last_preview_msg = ""

        self._menu()
        self._header()
        self.status = ttk.Label(self, text="Pronto.", anchor="w", style="Status.TLabel")
        self.status.pack(fill="x", side="bottom")
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=0, pady=(0, 0))
        self._tab_experiment()
        self._tab_calibration()
        self._tab_sections()
        self._tab_points()
        self._tab_analysis()
        self._tab_results()
        self.project_to_ui()
        if project_path:
            self.open_project(project_path)

    # ------------------------------------------------------------------ cabeçalho
    def _header(self):
        h = ttk.Frame(self, style="Header.TFrame", padding=(20, 12))
        h.pack(fill="x", side="top")
        logo = tk.Canvas(h, width=34, height=34, bg=th.HEADER, highlightthickness=0)
        logo.create_oval(2, 2, 32, 32, fill=th.ACCENT, outline="")
        logo.create_line(8, 21, 13, 21, 17, 9, 21, 25, 26, 17, fill="white", width=2.2,
                         capstyle="round", joinstyle="round")
        logo.pack(side="left", padx=(0, 12))
        t = ttk.Frame(h, style="Header.TFrame")
        t.pack(side="left")
        ttk.Label(t, text="Dispersion Analyzer", style="Header.TLabel").pack(anchor="w")
        ttk.Label(t, text="Traçador salino em rios: velocidade, dispersão longitudinal, vazão e "
                          "conservação da massa", style="HeaderSub.TLabel").pack(anchor="w")
        b = ttk.Frame(h, style="Header.TFrame")
        b.pack(side="right")
        mb = ttk.Menubutton(b, text="Exemplos  ▾")
        em = tk.Menu(mb, tearoff=0)
        for label, path, _ in EXAMPLES:
            em.add_command(label=label, command=lambda p=path: self.load_example(p))
        mb["menu"] = em
        mb.pack(side="left", padx=4)
        ttk.Button(b, text="Abrir projeto", command=self.open_project).pack(side="left", padx=4)
        ttk.Button(b, text="Salvar", command=self.save_project).pack(side="left", padx=4)
        ttk.Button(b, text="Sobre", command=self.show_about).pack(side="left", padx=4)
        self.head_run = ttk.Button(b, text="▶  Executar", style="Accent.TButton",
                                   command=self.run)
        self.head_run.pack(side="left", padx=(8, 0))
        tk.Frame(self, height=1, bg=th.BORDER).pack(fill="x", side="top")

    # ------------------------------------------------------------------ menu
    def _menu(self):
        m = tk.Menu(self)
        a = tk.Menu(m, tearoff=0)
        a.add_command(label="Novo projeto", command=self.new_project)
        a.add_command(label="Abrir projeto…", command=self.open_project)
        a.add_command(label="Salvar projeto", command=self.save_project)
        a.add_command(label="Salvar projeto como…", command=lambda: self.save_project(True))
        a.add_separator()
        for label, path, _ in EXAMPLES:
            a.add_command(label=label, command=lambda p=path: self.load_example(p))
        a.add_separator()
        a.add_command(label="Sair", command=self.destroy)
        m.add_cascade(label="Arquivo", menu=a)
        h = tk.Menu(m, tearoff=0)
        h.add_command(label="Métodos…", command=self.show_methods_help)
        h.add_command(label="Sobre o Dispersion Analyzer", command=self.show_about)
        m.add_cascade(label="Ajuda", menu=h)
        self.config(menu=m)

    def set_status(self, t):
        self.status.config(text=t)
        self.update_idletasks()

    # ------------------------------------------------------------------ aba 1
    def _tab_experiment(self):
        f = ttk.Frame(self.nb, padding=(18, 16))
        self.nb.add(f, text="1. Experimento")
        self.ev = {k: tk.StringVar() for k in
                   ("name", "outdir", "M", "inj", "slope", "fcoef")}
        self.time_mode = tk.StringVar(value="relative")
        self.dayfirst = tk.BooleanVar(value=True)
        self.inj_pos = tk.StringVar(value="center")

        def row(r, label, w, tip=""):
            ttk.Label(f, text=label).grid(row=r, column=0, sticky="w", pady=4)
            w.grid(row=r, column=1, sticky="w", pady=4)
            if tip:
                ttk.Label(f, text=tip, foreground=MUTED).grid(row=r, column=2, sticky="w", padx=8)

        row(0, "Nome do experimento", ttk.Entry(f, textvariable=self.ev["name"], width=50))
        o = ttk.Frame(f)
        ttk.Entry(o, textvariable=self.ev["outdir"], width=44).pack(side="left")
        ttk.Button(o, text="…", width=3, command=lambda: self.ev["outdir"].set(
            filedialog.askdirectory() or self.ev["outdir"].get())).pack(side="left")
        row(1, "Pasta de resultados", o)
        row(2, "Massa de NaCl lançada (kg)", ttk.Entry(f, textvariable=self.ev["M"], width=16),
            "necessária para vazão por diluição e recuperação de massa")
        tf = ttk.LabelFrame(f, text="Instante do lançamento", padding=8)
        tf.grid(row=3, column=0, columnspan=3, sticky="we", pady=8)
        ttk.Radiobutton(tf, text="O tempo dos arquivos já está em segundos desde o lançamento (t = 0)",
                        variable=self.time_mode, value="relative").grid(row=0, column=0,
                                                                        columnspan=3, sticky="w")
        ttk.Radiobutton(tf, text="Data/hora do lançamento:", variable=self.time_mode,
                        value="datetime").grid(row=1, column=0, sticky="w")
        ttk.Entry(tf, textvariable=self.ev["inj"], width=24).grid(row=1, column=1, sticky="w")
        ttk.Label(tf, text="ex.: 30/09/2026 14:05:00  ou  14:05:00", foreground=MUTED).grid(
            row=1, column=2, sticky="w", padx=6)
        ttk.Radiobutton(tf, text="Desconhecido (só métodos entre dois pontos)",
                        variable=self.time_mode, value="unknown").grid(row=2, column=0,
                                                                        columnspan=3, sticky="w")
        ttk.Checkbutton(tf, text="Datas no formato dia/mês/ano", variable=self.dayfirst).grid(
            row=3, column=0, sticky="w")
        hf = ttk.LabelFrame(f, text="Hidráulica (opcional — fórmulas empíricas e distância de mistura)",
                            padding=8)
        hf.grid(row=4, column=0, columnspan=3, sticky="we")
        ttk.Label(hf, text="Declividade do trecho S (m/m)").grid(row=0, column=0, sticky="w")
        ttk.Entry(hf, textvariable=self.ev["slope"], width=12).grid(row=0, column=1, sticky="w")
        ttk.Label(hf, text="u* = √(g·R·S); se vazio, u* ≈ 0,1·U", foreground=MUTED).grid(
            row=0, column=2, sticky="w", padx=6)
        ttk.Label(hf, text="Coeficiente do flutuador").grid(row=1, column=0, sticky="w")
        ttk.Entry(hf, textvariable=self.ev["fcoef"], width=12).grid(row=1, column=1, sticky="w")
        ttk.Label(hf, text="V_média = coef · V_superficial (0,80–0,90)", foreground=MUTED).grid(
            row=1, column=2, sticky="w", padx=6)
        ttk.Label(hf, text="Lançamento do sal").grid(row=2, column=0, sticky="w")
        pf = ttk.Frame(hf)
        ttk.Radiobutton(pf, text="no centro", variable=self.inj_pos, value="center").pack(side="left")
        ttk.Radiobutton(pf, text="na margem", variable=self.inj_pos, value="margin").pack(side="left")
        pf.grid(row=2, column=1, columnspan=2, sticky="w")

        txt = ("Como usar:\n"
               " 1. Preencha os dados do experimento (esta aba).\n"
               " 2. Cadastre uma calibração por condutivímetro (aba 2).\n"
               " 3. Cadastre as seções transversais:\n"
               "    Distância do lançamento, largura, profundidade, flutuadores (aba 3).\n"
               "    Seções sem ponto de monitoramento servem só para a hidráulica.\n"
               " 4. Adicione os arquivos dos pontos de monitoramento (aba 4).\n"
               "    Um ou vários pontos de monitoramento são permitidos\n"
               "    Inclusive é possível adicionar mais pontos de monitoramento em uma mesam seção\n"
               "    Neste caso, os pontos são combinados, mas comparações entre pontos são feitas.\n"
               " 5. Escolha os métodos e execute (aba 5).\n" 
               " 6. Os resultados aparecem na aba 6 e são gravados na pasta de resultados\n"
               "    Fornecendo figuras, planilha e relatório dos resultados.\n\n")
        
        ttk.Label(f, text=txt, foreground=MUTED, justify="left").grid(row=5, column=0,
                                                                     columnspan=3, sticky="w",
                                                                     pady=14)
        ex = ttk.LabelFrame(f, text="Primeira vez? Comece por um exemplo", padding=12)
        ex.grid(row=0, column=3, rowspan=6, sticky="new", padx=(28, 0))
        for label, path, desc in EXAMPLES:
            lk = ttk.Label(ex, text="→  " + label, style="Link.TLabel", cursor="hand2",
                           wraplength=290)
            lk.pack(anchor="w", pady=(4, 0))
            lk.bind("<Button-1>", lambda e, p=path: self.load_example(p))
            ttk.Label(ex, text=desc, foreground=MUTED, wraplength=270,
                      justify="left").pack(anchor="w", padx=(22, 0), pady=(0, 6))
        ttk.Separator(ex).pack(fill="x", pady=8)
        ttk.Label(ex, text=f"Desenvolvido por {__author__}", foreground=th.INK2).pack(anchor="w")
        ttk.Label(ex, text=__credits__, foreground=MUTED, wraplength=270,
                  justify="left").pack(anchor="w")
        f.columnconfigure(3, weight=1)

    # ------------------------------------------------------------------ aba 2
    def _tab_calibration(self):
        f = ttk.Frame(self.nb, padding=(18, 16))
        self.nb.add(f, text="2. Calibração")
        left = ttk.Frame(f)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="Sondas / condutivímetros").pack(anchor="w")
        self.cal_list = tk.Listbox(left, height=10, exportselection=False, width=26)
        self.cal_list.pack(fill="y", expand=False)
        self.cal_list.bind("<<ListboxSelect>>", lambda e: self.select_cal())
        b = ttk.Frame(left)
        b.pack(fill="x", pady=4)
        ttk.Button(b, text="Nova", command=self.new_cal).pack(side="left")
        ttk.Button(b, text="Remover", command=self.del_cal).pack(side="left", padx=3)
        ttk.Button(b, text="Renomear", command=self.rename_cal).pack(side="left")

        mid = ttk.Frame(f, padding=(10, 0))
        mid.pack(side="left", fill="y")
        self.cv = dict(mode=tk.StringVar(value=CAL_MODES["poly"]), degree=tk.StringVar(value="2"),
                       factor=tk.StringVar(value="0.0005"), input=tk.StringVar(value="conc"),
                       dose=tk.StringVar(value="0.125"), vol=tk.StringVar(value="700"),
                       target=tk.StringVar(value=""))
        g = ttk.Frame(mid)
        g.pack(fill="x")
        ttk.Label(g, text="Tipo").grid(row=0, column=0, sticky="w")
        ttk.Combobox(g, textvariable=self.cv["mode"], values=list(CAL_MODES.values()), width=36,
                     state="readonly").grid(row=0, column=1, columnspan=3, sticky="w")
        ttk.Label(g, text="Grau do polinômio").grid(row=1, column=0, sticky="w")
        self.cal_w_degree = ttk.Spinbox(g, from_=1, to=3, textvariable=self.cv["degree"], width=4)
        self.cal_w_degree.grid(row=1, column=1, sticky="w")
        ttk.Label(g, text="Fator (kg/m³ por µS/cm)").grid(row=2, column=0, sticky="w")
        self.cal_w_factor = ttk.Entry(g, textvariable=self.cv["factor"], width=10)
        self.cal_w_factor.grid(row=2, column=1, sticky="w")
        ttk.Label(g, text="Curva da referência (EC → C)").grid(row=3, column=0, sticky="w")
        self.cal_w_target = ttk.Combobox(g, textvariable=self.cv["target"], width=22,
                                         state="readonly")
        self.cal_w_target.grid(row=3, column=1, columnspan=3, sticky="w")
        self.cal_hint = ttk.Label(g, text="", foreground=MUTED, wraplength=380, justify="left")
        self.cal_hint.grid(row=4, column=0, columnspan=4, sticky="w", pady=(4, 0))
        ttk.Label(g, text="1ª coluna da tabela:").grid(row=5, column=0, sticky="w", pady=(8, 0))
        self.cal_w_input = [
            ttk.Radiobutton(g, text="concentração (g/L)", variable=self.cv["input"],
                            value="conc"),
            ttk.Radiobutton(g, text="nº de doses de sal", variable=self.cv["input"],
                            value="doses")]
        self.cal_w_input[0].grid(row=6, column=0, columnspan=4, sticky="w")
        self.cal_w_input[1].grid(row=7, column=0, columnspan=4, sticky="w")
        ttk.Label(g, text="massa por dose (g)").grid(row=8, column=0, sticky="w")
        self.cal_w_dose = ttk.Entry(g, textvariable=self.cv["dose"], width=10)
        self.cal_w_dose.grid(row=8, column=1, sticky="w")
        ttk.Label(g, text="volume (mL)").grid(row=8, column=2, sticky="w", padx=(10, 0))
        self.cal_w_vol = ttk.Entry(g, textvariable=self.cv["vol"], width=8)
        self.cal_w_vol.grid(row=8, column=3, sticky="w")
        self.cal_table = EditableTable(mid, ["Conc. (g/L) ou nº doses", "Condutividade (µS/cm)"],
                                       [170, 170], height=10)
        self.cal_table.pack(fill="both", expand=True, pady=8)
        b = ttk.Frame(mid)
        b.pack(fill="x")
        ttk.Button(b, text="Importar arquivo…", command=self.import_cal).pack(side="left")
        ttk.Button(b, text="Ajustar curva", command=self.fit_cal).pack(side="left", padx=4)
        self.cal_info = ttk.Label(mid, text="", wraplength=380, justify="left")
        self.cal_info.pack(fill="x", pady=6)

        self.cal_fig = FigurePanel(f)
        self.cal_fig.pack(side="left", fill="both", expand=True)
        self.cv["mode"].trace_add("write", lambda *a: self._cal_mode_changed())
        self._cal_mode_changed()

    def _cal_mode(self):
        return CAL_MODE_KEY.get(self.cv["mode"].get(), "poly")

    def _cal_mode_changed(self):
        """Habilita os campos e troca os títulos da tabela conforme o tipo."""
        m = self._cal_mode()
        en = lambda w, on: w.configure(state=("normal" if on else "disabled"))
        en(self.cal_w_degree, m in ("poly", "ref"))
        en(self.cal_w_factor, m == "factor")
        self.cal_w_target.configure(state=("readonly" if m == "ref" else "disabled"))
        for w in self.cal_w_input:
            en(w, m == "poly")
        en(self.cal_w_dose, m == "poly")
        en(self.cal_w_vol, m == "poly")
        self.cal_hint.config(text=CAL_HINTS[m])
        c0, c1 = self.cal_table.columns
        if m == "ref":
            self.cal_table.tree.heading(c0, text="EC referência (µS/cm)")
            self.cal_table.tree.heading(c1, text="EC da sonda (µS/cm)")
        else:
            self.cal_table.tree.heading(c0, text=c0)
            self.cal_table.tree.heading(c1, text=c1)

    def _refresh_cal_list(self, select=0):
        self.cal_list.delete(0, "end")
        for c in self.project.calibrations:
            self.cal_list.insert("end", c.name)
        if self.project.calibrations:
            select = min(select, len(self.project.calibrations) - 1)
            self.cal_list.selection_set(select)
            self._cal_index = None
            self.select_cal()

    def _commit_cal(self):
        i = self._cal_index
        if i is None or i >= len(self.project.calibrations):
            return
        c = self.project.calibrations[i]
        c.mode = self._cal_mode()
        c.target = self.cv["target"].get()
        c.degree = int(fnum(self.cv["degree"].get(), 2))
        c.factor = fnum(self.cv["factor"].get(), 0.0005)
        c.input_mode = self.cv["input"].get()
        c.dose_g = fnum(self.cv["dose"].get(), 0.125)
        c.vol_ml = fnum(self.cv["vol"].get(), 700)
        rows = [(fnum(r[0]), fnum(r[1])) for r in self.cal_table.get_rows()]
        rows = [r for r in rows if r[0] is not None and r[1] is not None]
        c.x_input = [r[0] for r in rows]
        c.ec = [r[1] for r in rows]
        c.coef = []

    def select_cal(self):
        sel = self.cal_list.curselection()
        if not sel:
            return
        self._commit_cal()
        i = sel[0]
        self._cal_index = i
        c = self.project.calibrations[i]
        self.cal_w_target.configure(values=[o.name for o in self.project.calibrations
                                            if o is not c and o.mode != "ref"])
        self.cv["target"].set(c.target)
        self.cv["mode"].set(CAL_MODES.get(c.mode, CAL_MODES["poly"]))
        self.cv["degree"].set(str(c.degree))
        self.cv["factor"].set(str(c.factor))
        self.cv["input"].set(c.input_mode)
        self.cv["dose"].set(str(c.dose_g))
        self.cv["vol"].set(str(c.vol_ml))
        xi = c.x_input if c.x_input else (c.ref_ec if c.mode == "ref" else c.conc)
        self.cal_table.set_rows([[a, b] for a, b in zip(xi, c.ec)])
        self.fit_cal(silent=True)

    def new_cal(self):
        self._commit_cal()
        n = len(self.project.calibrations) + 1
        self.project.calibrations.append(Calibration(f"Sonda {n}"))
        self._refresh_cal_list(n - 1)

    def del_cal(self):
        sel = self.cal_list.curselection()
        if sel and messagebox.askyesno("Remover", "Remover a calibração selecionada?"):
            self.project.calibrations.pop(sel[0])
            self._cal_index = None
            self._refresh_cal_list()

    def rename_cal(self):
        sel = self.cal_list.curselection()
        if not sel:
            return
        c = self.project.calibrations[sel[0]]
        w = tk.Toplevel(self)
        w.title("Renomear")
        v = tk.StringVar(value=c.name)
        ttk.Entry(w, textvariable=v, width=30).pack(padx=10, pady=10)

        def ok():
            old = c.name
            c.name = v.get().strip() or old
            for p in self.project.points:
                if p.calibration == old:
                    p.calibration = c.name
            for o in self.project.calibrations:
                if o.target == old:
                    o.target = c.name
            w.destroy()
            self._refresh_cal_list(sel[0])
            self.refresh_points()

        ttk.Button(w, text="OK", command=ok).pack(pady=(0, 10))

    def import_cal(self):
        f = filedialog.askopenfilename(title="Tabela de calibração (2 colunas: conc./doses, EC)",
                                       filetypes=[("Dados", "*.txt *.csv *.xlsx *.xls"),
                                                  ("Todos", "*.*")])
        if not f:
            return
        try:
            df = read_table(f)
            num = df.select_dtypes("number")
            self.cal_table.set_rows(num.iloc[:, :2].values.tolist())
            self.fit_cal()
        except Exception as e:
            messagebox.showerror("Calibração", str(e))

    def fit_cal(self, silent=False):
        self._commit_cal()
        if self._cal_index is None:
            return
        c = self.project.calibrations[self._cal_index]
        try:
            c.fit()
            self.project.link_calibrations()
            lo, hi = c.ec_range
            info = f"{c.equation(8)}\n"
            if c.mode in ("poly", "ref"):
                info += f"R² = {c.r2:.5f}   RMSE = {c.rmse:.4g} {c.unit}\n" \
                        f"Faixa calibrada: {lo:.1f} a {hi:.1f} µS/cm"
            if c.mode == "nacl":
                info += "Ex.: 500 µS/cm → {:.3f} g/L;  1000 µS/cm → {:.3f} g/L".format(
                    *c.to_conc([500, 1000]))
            if c.mode == "ref":
                if c._target is None:
                    info += "\nEscolha a curva da referência (EC → C)."
                else:
                    info += "\nEx.: {:.0f} µS/cm na sonda → {:.0f} µS/cm na referência → " \
                            "{:.4f} g/L".format(hi, float(c.to_ref(hi)), float(c.to_conc(hi)))
            self.cal_info.config(text=info, foreground=th.INK)
            shown = [c] + ([c._target] if c.mode == "ref" and c._target is not None else [])
            self.cal_fig.show(fig_calibration(Project(calibrations=shown)) or Figure())
        except Exception as e:
            self.cal_info.config(text=str(e), foreground=th.ERROR)
            self.cal_fig.show(Figure())

    # ------------------------------------------------------------------ aba 3
    def _tab_sections(self):
        f = ttk.Frame(self.nb, padding=(18, 16))
        self.nb.add(f, text="3. Seções")
        ttk.Label(f, text=(
            "Uma linha por seção transversal. Duplo clique para editar; Ctrl+V cola linhas do Excel.\n"
            "Obrigatórios: Seção (nome) e x (distância do lançamento, m). Só com eles já se "
            "calculam U e K pelo traçador.\n"
            "Opcionais: Largura e Profundidade (ou Área; vazia = largura × profundidade) → "
            "fórmulas empíricas, mistura lateral e Chatwin com M/A informada.  "
            "Flutuador: distância e tempos separados por espaço (ex.: 5.49 3.53 4.25) → V e "
            "Q = V·A.  V ou Q conhecidas substituem os flutuadores.  Com Q (conhecida ou V·A) "
            "calcula-se a recuperação da massa lançada."), foreground=MUTED,
                  wraplength=1200, justify="left").pack(anchor="w")
        self.sec_cols = ["Seção", "Distância do lançamento (m)", "Largura (m)", "Profundidade (m)", "Área (m²)",
                         "Distância flutuador (m)", "Tempos flutuador (s)", "V conhecida (m/s)",
                         "Q conhecida (m³/s)"]
        self.sec_table = EditableTable(f, self.sec_cols,
                                       [140, 70, 90, 110, 80, 130, 220, 120, 120], height=16)
        self.sec_table.pack(fill="both", expand=True, pady=6)

    def _sections_from_table(self):
        secs = []
        for r in self.sec_table.get_rows():
            if not str(r[0]).strip():
                continue
            times = [fnum(v) for v in str(r[6]).replace(";", " ").replace("/", " ").split()]
            secs.append(Section(str(r[0]).strip(), fnum(r[1], 0.0), fnum(r[2]), fnum(r[3]),
                                fnum(r[4]), fnum(r[5]), [t for t in times if t],
                                fnum(r[7]), fnum(r[8])))
        return secs

    # ------------------------------------------------------------------ aba 4
    def _tab_points(self):
        f = ttk.Frame(self.nb, padding=(18, 16))
        self.nb.add(f, text="4. Pontos de monitoramento")
        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Button(top, text="Adicionar arquivo(s)…", command=self.add_points).pack(side="left")
        ttk.Button(top, text="Editar…", command=self.edit_point).pack(side="left", padx=4)
        ttk.Button(top, text="Duplicar", command=self.dup_point).pack(side="left")
        ttk.Button(top, text="Remover", command=self.del_point).pack(side="left", padx=4)
        ttk.Button(top, text="Pré-visualizar", command=self.preview_selected).pack(side="left")
        ttk.Label(top, text="  Duplo clique edita. Vários arquivos de uma vez = vários pontos.",
                  foreground=MUTED).pack(side="left")
        pw = ttk.PanedWindow(f, orient="vertical")
        pw.pack(fill="both", expand=True, pady=6)
        cols = ["Ativo", "Nome", "Seção", "Distância (m)", "Posição", "Peso", "Tipo", "Calibração",
                "Arquivo"]
        tf = ttk.Frame(pw)
        self.pt_tree = ttk.Treeview(tf, columns=cols, show="headings", height=7)
        for c, w in zip(cols, [50, 110, 130, 70, 90, 60, 60, 150, 480]):
            self.pt_tree.heading(c, text=c)
            self.pt_tree.column(c, width=w, anchor="center" if c != "Arquivo" else "w")
        self.pt_tree.pack(fill="both", expand=True)
        self.pt_tree.bind("<Double-1>", lambda e: self.edit_point())
        self.pt_tree.bind("<<TreeviewSelect>>", lambda e: self.preview_selected())
        pw.add(tf, weight=1)
        self.pt_fig = FigurePanel(pw)
        pw.add(self.pt_fig, weight=3)
        self.pt_msg = ttk.Label(f, text="", foreground=th.ERROR, wraplength=1200,
                                justify="left")
        self.pt_msg.pack(fill="x")

    def refresh_points(self):
        self.pt_tree.delete(*self.pt_tree.get_children())
        for i, p in enumerate(self.project.points):
            self.pt_tree.insert("", "end", iid=str(i), values=[
                "sim" if p.enabled else "não", p.name, p.section,
                self._section_x(p), p.lateral, p.weight, p.kind, p.calibration, p.file])

    def _section_x(self, p):
        """x do ponto = x da seção a que ele pertence (só para exibir na tabela)."""
        s = self.project.section(p.section)
        return "" if s is None else s.x

    def _sel_point(self):
        s = self.pt_tree.selection()
        return int(s[0]) if s else None

    def add_points(self):
        self.ui_to_project()
        files = filedialog.askopenfilenames(title="Arquivos dos pontos de monitoramento",
                                            filetypes=[("Dados", "*.txt *.csv *.tsv *.dat *.xlsx *.xls"),
                                                       ("Todos", "*.*")])
        if not files:
            return
        for fpath in files:
            n = len(self.project.points) + 1
            sec = self.project.sections[0].name if self.project.sections else f"Seção {n}"
            cal = self.project.calibrations[0].name if self.project.calibrations else ""
            p = Point(f"P{n}", sec, fpath, calibration=cal)
            dlg = PointDialog(self, p)
            self.wait_window(dlg)
            if dlg.result:
                self.project.points.append(dlg.result)
        self.refresh_points()

    def edit_point(self):
        i = self._sel_point()
        if i is None:
            return
        self.ui_to_project()
        dlg = PointDialog(self, self.project.points[i])
        self.wait_window(dlg)
        if dlg.result:
            self.project.points[i] = dlg.result
            self.refresh_points()
            self.pt_tree.selection_set(str(i))

    def dup_point(self):
        i = self._sel_point()
        if i is None:
            return
        import copy
        p = copy.deepcopy(self.project.points[i])
        p.name += "_copia"
        self.project.points.append(p)
        self.refresh_points()

    def del_point(self):
        i = self._sel_point()
        if i is not None and messagebox.askyesno("Remover", "Remover o ponto selecionado?"):
            self.project.points.pop(i)
            self.refresh_points()

    def preview_figure(self, p: Point):
        prj = self.project
        raw = load_point_series(prj, p)
        cal = prj.calibration(p.calibration) if p.kind == "ec" else None
        if cal is not None and not cal.coef:
            cal.fit()
        cv = process_curve(p.name, raw.t, raw.value, p.kind, cal, p.options)
        fig = Figure(figsize=(9, 5), layout="constrained")
        a1 = fig.add_subplot(121)
        a1.plot(raw.t, raw.value, lw=1, color="#b5b4ae", label="bruto")
        a1.plot(cv.t, cv.value, lw=1.5, color=SERIES[0], label="analisado")
        a1.plot(cv.t, cv.background, "--", lw=1.3, color=SERIES[1], label="fundo")
        a1.axvspan(cv.t_start, min(cv.t_end, cv.t[-1]), color=SERIES[2], alpha=0.1, label="nuvem")
        _style(a1, "Tempo (s)" + ("" if raw.relative_to_injection else " desde o 1º dado"),
               "Condutividade (µS/cm)" if p.kind == "ec" else "kg/m³", f"{p.name}: sinal")
        a1.legend(fontsize=8, frameon=False, loc="upper left")
        if raw.temp is not None and np.isfinite(raw.temp).any():
            a1b = a1.inset_axes([0.62, 0.62, 0.36, 0.3])
            a1b.plot(raw.t, raw.temp, lw=1, color=SERIES[6])
            a1b.set_title("Temperatura (°C)", fontsize=7)
            a1b.tick_params(labelsize=6)
        a2 = fig.add_subplot(122)
        a2.plot(cv.t, cv.c_unclipped, lw=1, color="#b5b4ae", label="C bruta")
        a2.plot(cv.t, cv.c, lw=1.8, color=SERIES[0], label="C analisada")
        if len(cv.t_tail):
            a2.plot(cv.t_tail, cv.c_tail, ":", lw=1.8, color=SERIES[1], label="cauda extrapolada")
        _style(a2, "Tempo (s)", "Concentração (kg/m³)", "Concentração")
        a2.legend(fontsize=8, frameon=False)
        msg = f"{len(raw.t)} registros · Δt mediano {np.median(np.diff(raw.t)):.2f} s · " \
              f"Valor base natural {cv.background[0]:.2f} · Pico de concentração = {cv.c_peak:.4g} kg/m³ em t = {cv.t_peak:.0f} s"
        if not raw.relative_to_injection:
            msg += "\nAtenção: instante do lançamento desconhecido, tempo relativo ao 1º registro."
        if cv.warnings:
            msg += "\n" + "\n".join(cv.warnings)
        self._last_preview_msg = msg
        return fig

    def preview_selected(self):
        i = self._sel_point()
        if i is None:
            return
        self.ui_to_project()
        try:
            self.pt_fig.show(self.preview_figure(self.project.points[i]))
            self.pt_msg.config(text=self._last_preview_msg, foreground=th.INK)
        except Exception as e:
            self.pt_msg.config(text=f"Erro: {e}", foreground=th.ERROR)

    # ------------------------------------------------------------------ aba 5
    def _tab_analysis(self):
        f = ttk.Frame(self.nb, padding=(18, 16))
        self.nb.add(f, text="5. Análise")
        self.av = {k: tk.BooleanVar() for k in
                   ("single_moments", "single_percentiles", "ade_fit", "chatwin",
                    "two_station_moments", "routing", "routing_fit_U", "routing_normalize_mass",
                    "routing_manual", "use_tail", "analyze_points_individually")}
        self.av_s = {k: tk.StringVar() for k in
                     ("chatwin_level", "routing_D_manual", "routing_U_manual")}
        self.pairs = tk.StringVar(value="consecutive")
        self.autosave = tk.BooleanVar(value=True)
        g1 = ttk.LabelFrame(f, text="Um único ponto (exige o instante do lançamento)", padding=8)
        g1.grid(row=0, column=0, sticky="nwe", padx=(0, 8))
        for k, t in (("single_moments", "Momentos dos momentos (U, K)"),
                     ("single_percentiles", "Método dos percentis (robusto a caudas)"),
                     ("ade_fit", "Método do ajuste da ADE (U, K, M/A)"),
                     ("chatwin", "Método de Chatwin (linearização, k iterado)")):
            ttk.Checkbutton(g1, text=t, variable=self.av[k]).pack(anchor="w")
        r = ttk.Frame(g1)
        r.pack(anchor="w", padx=20)
        ttk.Label(r, text="Chatwin: usar C =").pack(side="left")
        ttk.Entry(r, textvariable=self.av_s["chatwin_level"], width=6).pack(side="left")
        ttk.Label(r, text="× C pico").pack(side="left")
        g2 = ttk.LabelFrame(f, text="Entre seções (dois ou mais pontos em x diferentes)", padding=8)
        g2.grid(row=0, column=1, sticky="nwe")
        ttk.Checkbutton(g2, text="Método de Fischer (variação dos momentos)",
                        variable=self.av["two_station_moments"]).pack(anchor="w")
        ttk.Checkbutton(g2, text="Método da propagação (MMQ)",
                        variable=self.av["routing"]).pack(anchor="w")
        ttk.Checkbutton(g2, text="Otimizar também U", variable=self.av["routing_fit_U"]).pack(
            anchor="w", padx=(24, 0))
        ttk.Checkbutton(g2, text="Normalizar a massa (compara só a forma das curvas)",
                        variable=self.av["routing_normalize_mass"]).pack(anchor="w", padx=(24, 0))
        ttk.Checkbutton(g2, text="Avaliar também D e U manuais (tentativa e erro)",
                        variable=self.av["routing_manual"]).pack(anchor="w", padx=(24, 0))
        r = ttk.Frame(g2)
        r.pack(anchor="w", padx=(48, 0), pady=2)
        ttk.Label(r, text="D").pack(side="left")
        e_d = ttk.Entry(r, textvariable=self.av_s["routing_D_manual"], width=8)
        e_d.pack(side="left", padx=3)
        ttk.Label(r, text="m²/s    U").pack(side="left")
        e_u = ttk.Entry(r, textvariable=self.av_s["routing_U_manual"], width=8)
        e_u.pack(side="left", padx=3)
        ttk.Label(r, text="m/s (vazio = Δx/Δ<t>)").pack(side="left")

        def manual_toggled(*_):
            st = "normal" if self.av["routing_manual"].get() else "disabled"
            e_d.configure(state=st)
            e_u.configure(state=st)
        self.av["routing_manual"].trace_add("write", manual_toggled)
        manual_toggled()
        r = ttk.Frame(g2)
        r.pack(anchor="w", pady=2)
        ttk.Label(r, text="Pares de seções:").pack(side="left")
        ttk.Radiobutton(r, text="consecutivas", variable=self.pairs,
                        value="consecutive").pack(side="left")
        ttk.Radiobutton(r, text="todas as combinações", variable=self.pairs,
                        value="all").pack(side="left")
        g3 = ttk.LabelFrame(f, text="Geral", padding=8)
        g3.grid(row=1, column=0, columnspan=2, sticky="we", pady=8)
        ttk.Checkbutton(g3, text="Usar a cauda extrapolada nos cálculos (quando ativada no ponto)",
                        variable=self.av["use_tail"]).pack(anchor="w")
        ttk.Checkbutton(g3, text="Analisar cada ponto individualmente (além da média da seção)",
                        variable=self.av["analyze_points_individually"]).pack(anchor="w")
        ttk.Checkbutton(g3, text="Salvar resultados automaticamente na pasta de resultados",
                        variable=self.autosave).pack(anchor="w")
        b = ttk.Frame(f)
        b.grid(row=2, column=0, columnspan=2, sticky="we")
        self.run_btn = ttk.Button(b, text="▶  Executar análise", command=self.run,
                                  style="Accent.TButton")
        self.run_btn.pack(side="left")
        self.pbar = ttk.Progressbar(b, mode="indeterminate", length=200)
        self.pbar.pack(side="left", padx=10)
        self.log = ScrolledText(f, height=18, font=("Consolas", 9))
        self.log.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=8)
        f.rowconfigure(3, weight=1)
        f.columnconfigure(0, weight=1)
        f.columnconfigure(1, weight=1)

    def logmsg(self, m):
        self.log.insert("end", m + "\n")
        self.log.see("end")

    # ------------------------------------------------------------------ aba 6
    def _tab_results(self):
        f = ttk.Frame(self.nb, padding=(18, 16))
        self.nb.add(f, text="6. Resultados")
        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Button(top, text="Salvar resultados em…", command=self.save_results_as).pack(side="left")
        ttk.Button(top, text="Abrir pasta de resultados", command=self.open_outdir).pack(
            side="left", padx=4)
        self.res_info = ttk.Label(top, text="Execute a análise (aba 5).", foreground=MUTED)
        self.res_info.pack(side="left", padx=10)
        nb = ttk.Notebook(f, style="Sub.TNotebook")
        nb.pack(fill="both", expand=True, pady=6)
        # tabelas
        t = ttk.Frame(nb, padding=4)
        nb.add(t, text="Tabelas")
        self.tab_sel = ttk.Combobox(t, state="readonly", width=40)
        self.tab_sel.pack(anchor="w")
        self.tab_sel.bind("<<ComboboxSelected>>", lambda e: self.show_table())
        self.tab_view = DataFrameView(t)
        self.tab_view.pack(fill="both", expand=True, pady=4)
        # figuras
        g = ttk.Frame(nb, padding=4)
        nb.add(g, text="Figuras")
        r = ttk.Frame(g)
        r.pack(fill="x")
        ttk.Button(r, text="◀", width=3, command=lambda: self.step_fig(-1)).pack(side="left")
        self.fig_sel = ttk.Combobox(r, state="readonly", width=50)
        self.fig_sel.pack(side="left", padx=4)
        ttk.Button(r, text="▶", width=3, command=lambda: self.step_fig(1)).pack(side="left")
        self.fig_sel.bind("<<ComboboxSelected>>", lambda e: self.show_fig())
        self.res_fig = FigurePanel(g)
        self.res_fig.pack(fill="both", expand=True)
        # relatório
        rp = ttk.Frame(nb, padding=4)
        nb.add(rp, text="Relatório e avisos")
        self.report = ScrolledText(rp, font=("Consolas", 9), wrap="none")
        self.report.pack(fill="both", expand=True)

    def show_table(self):
        if self.results and self.tab_sel.get() in self.results.tables:
            self.tab_view.show(self.results.tables[self.tab_sel.get()])

    def show_fig(self):
        if self.results and self.fig_sel.get() in self.results.figures:
            self.res_fig.show(self.results.figures[self.fig_sel.get()])

    def step_fig(self, d):
        vals = list(self.fig_sel["values"])
        if not vals:
            return
        i = (vals.index(self.fig_sel.get()) + d) % len(vals) if self.fig_sel.get() in vals else 0
        self.fig_sel.set(vals[i])
        self.show_fig()

    # ------------------------------------------------------------------ projeto <-> UI
    def project_to_ui(self):
        p = self.project
        self.ev["name"].set(p.name)
        self.ev["outdir"].set(p.output_dir)
        self.ev["M"].set("" if p.M_injected is None else str(p.M_injected))
        self.ev["inj"].set(p.injection_time)
        self.ev["slope"].set("" if p.slope is None else str(p.slope))
        self.ev["fcoef"].set(str(p.float_coef))
        self.time_mode.set("datetime" if p.injection_time else
                           ("relative" if p.time_is_relative else "unknown"))
        self.dayfirst.set(p.dayfirst)
        self.inj_pos.set(p.injection_position)
        self._cal_index = None
        self._refresh_cal_list()
        self.sec_table.set_rows([[s.name, s.x, s.width, s.depth, s.area, s.float_dist,
                                  " ".join(f"{t:g}" for t in s.float_times), s.velocity, s.Q]
                                 for s in p.sections])
        a = p.analysis
        for k in self.av:
            self.av[k].set(getattr(a, k))
        self.av_s["chatwin_level"].set(str(a.chatwin_level))
        self.av_s["routing_D_manual"].set("" if a.routing_D_manual is None else str(a.routing_D_manual))
        self.av_s["routing_U_manual"].set("" if a.routing_U_manual is None else str(a.routing_U_manual))
        self.pairs.set(a.pairs)
        self.refresh_points()

    def ui_to_project(self):
        p = self.project
        p.name = self.ev["name"].get().strip() or "Experimento"
        p.output_dir = self.ev["outdir"].get().strip() or "resultados"
        p.M_injected = fnum(self.ev["M"].get())
        mode = self.time_mode.get()
        p.injection_time = self.ev["inj"].get().strip() if mode == "datetime" else ""
        p.time_is_relative = mode == "relative"
        p.dayfirst = self.dayfirst.get()
        p.injection_position = self.inj_pos.get()
        p.slope = fnum(self.ev["slope"].get())
        p.float_coef = fnum(self.ev["fcoef"].get(), 0.85)
        self._commit_cal()
        p.sections = self._sections_from_table()
        a = AnalysisOptions(**{k: v.get() for k, v in self.av.items()})
        a.chatwin_level = fnum(self.av_s["chatwin_level"].get(), 0.10)
        a.routing_D_manual = fnum(self.av_s["routing_D_manual"].get())
        a.routing_U_manual = fnum(self.av_s["routing_U_manual"].get())
        a.pairs = self.pairs.get()
        p.analysis = a
        if not p.base_dir:
            p.base_dir = os.getcwd()
        return p

    # ------------------------------------------------------------------ arquivo
    def new_project(self):
        self.project = Project()
        self.project.calibrations = [Calibration("Sonda 1")]
        self.project_path = None
        self.results = None
        self.project_to_ui()
        self.title(f"Dispersion Analyzer {__version__} — novo projeto")

    def load_example(self, path):
        if not os.path.exists(path) and FROZEN:
            try:
                import shutil
                src = os.path.join(BUNDLE_DIR, os.path.relpath(os.path.dirname(path), ROOT_DIR))
                shutil.copytree(src, os.path.dirname(path), dirs_exist_ok=True)
            except Exception as e:
                messagebox.showerror("Exemplo", f"Não foi possível copiar o exemplo:\n{e}")
                return
        elif not os.path.exists(path):
            try:
                self.set_status("Gerando o exemplo…")
                sys.path.insert(0, ROOT_DIR)
                if path == EXAMPLE_SYN:
                    sys.path.insert(0, os.path.join(ROOT_DIR, "exemplos"))
                    import gerar_exemplo_sintetico
                    gerar_exemplo_sintetico.main()
                else:
                    import l3_solucao
                    l3_solucao.main()
            except Exception as e:
                messagebox.showerror("Exemplo", f"Não foi possível gerar o exemplo:\n{e}")
                return
        self.open_project(path)
        self.nb.select(3)

    def show_about(self):
        w = tk.Toplevel(self)
        w.title("Sobre")
        w.transient(self)
        w.resizable(False, False)
        fam = th._font_family()
        c = ttk.Frame(w, padding=(36, 26))
        c.pack(fill="both", expand=True)
        logo = tk.Canvas(c, width=56, height=56, bg=th.BG, highlightthickness=0)
        logo.create_oval(2, 2, 54, 54, fill=th.ACCENT, outline="")
        logo.create_line(12, 34, 21, 34, 28, 14, 35, 42, 44, 28, fill="white", width=3.5,
                         capstyle="round", joinstyle="round")
        logo.pack()
        ttk.Label(c, text="Dispersion Analyzer", font=(fam, 16, "bold")).pack(pady=(10, 0))
        ttk.Label(c, text=f"versão {__version__}", foreground=MUTED).pack()
        ttk.Label(c, text="Análise de experimentos de traçador salino (NaCl) em rios:\n"
                          "velocidade média, coeficiente de dispersão longitudinal,\n"
                          "vazão por diluição e conservação de massa.",
                  justify="center").pack(pady=(14, 10))
        ttk.Separator(c).pack(fill="x", pady=6)
        ttk.Label(c, text="Desenvolvido por", foreground=MUTED).pack(pady=(6, 0))
        ttk.Label(c, text=__author__, font=(fam, 12, "bold")).pack()
        ttk.Label(c, text="para uso na disciplina de", foreground=MUTED).pack(pady=(12, 0))
        ttk.Label(c, text="Dinâmica de Lagos", font=(fam, 12, "bold"),
                  foreground=th.ACCENT).pack()
        ttk.Label(c, text="Universidade Federal do Paraná (UFPR)").pack()
        ttk.Label(c, text=f"© {__year__}", foreground=MUTED).pack(pady=(12, 0))
        ttk.Button(c, text="Fechar", style="Accent.TButton", command=w.destroy).pack(pady=(16, 0))
        w.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - w.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - w.winfo_height()) // 3
        w.geometry(f"+{x}+{y}")
        w.grab_set()

    def open_project(self, path=None):
        path = path or filedialog.askopenfilename(title="Abrir projeto",
                                                  filetypes=[("Projeto", "*.json")])
        if not path:
            return
        if not os.path.exists(path):
            messagebox.showerror("Abrir", f"Arquivo não encontrado:\n{path}\n\n"
                                          f"(para o exemplo, rode antes: python l3_solucao.py)")
            return
        try:
            self.project = Project.load(path)
        except Exception as e:
            messagebox.showerror("Abrir", f"Erro ao ler o projeto:\n{e}")
            return
        if not self.project.calibrations:
            self.project.calibrations = [Calibration("Sonda 1")]
        self.project_path = path
        self.results = None
        self.project_to_ui()
        self.title(f"Dispersion Analyzer {__version__} — {os.path.basename(path)}")
        self.set_status(f"Projeto aberto: {path}")

    def save_project(self, ask=False):
        self.ui_to_project()
        path = self.project_path
        if ask or not path:
            path = filedialog.asksaveasfilename(title="Salvar projeto", defaultextension=".json",
                                                filetypes=[("Projeto", "*.json")])
            if not path:
                return
        self.project.save(path)
        self.project_path = path
        self.refresh_points()
        self.set_status(f"Projeto salvo: {path}")

    # ------------------------------------------------------------------ execução
    def run(self):
        try:
            prj = self.ui_to_project()
        except Exception as e:
            messagebox.showerror("Dados", str(e))
            return
        if not prj.points:
            messagebox.showwarning("Análise", "Adicione ao menos um ponto de monitoramento (aba 4).")
            return
        self.log.delete("1.0", "end")
        self.run_btn.state(["disabled"])
        self.head_run.state(["disabled"])
        self.pbar.start(12)
        q = []
        autosave = self.autosave.get()

        def work():
            try:
                R = run_analysis(prj, progress=lambda m: q.append(("log", m)))
                q.append(("log", "Gerando figuras…"))
                make_figures(R)
                if autosave:
                    out = save_results(R, prj.resolve(prj.output_dir))
                    q.append(("log", f"Resultados gravados em: {out}"))
                    R.outdir = out
                q.append(("done", R))
            except Exception as e:
                q.append(("error", (e, traceback.format_exc())))

        # O coletor de lixo não pode rodar na thread de cálculo: ele destruiria
        # objetos do Tk (imagens, variáveis) fora da thread principal, o que gera
        # "RuntimeError: main thread is not in main loop". Coleta-se aqui e
        # depois de terminar, sempre na thread principal.
        gc.collect()
        gc.disable()
        th = threading.Thread(target=work, daemon=True)
        th.start()

        def poll():
            while q:
                kind, val = q.pop(0)
                if kind == "log":
                    self.logmsg(val)
                elif kind in ("done", "error"):
                    gc.enable()
                    gc.collect()
                if kind == "done":
                    self.finish(val)
                    return
                elif kind == "error":
                    e, tb = val
                    self.logmsg(tb)
                    self.pbar.stop()
                    self.run_btn.state(["!disabled"])
                    self.head_run.state(["!disabled"])
                    messagebox.showerror("Erro na análise", str(e))
                    return
            self.after(100, poll)

        poll()

    def finish(self, R):
        self.pbar.stop()
        self.run_btn.state(["!disabled"])
        self.head_run.state(["!disabled"])
        self.results = R
        for w in R.warnings:
            self.logmsg("AVISO: " + w)
        self.tab_sel.configure(values=list(R.tables))
        if R.tables:
            self.tab_sel.set(next(iter(R.tables)))
            self.show_table()
        self.fig_sel.configure(values=list(R.figures))
        if R.figures:
            self.fig_sel.set("05 Resumo K" if "05 Resumo K" in R.figures else next(iter(R.figures)))
            self.show_fig()
        self.report.delete("1.0", "end")
        self.report.insert("end", report_text(R))
        n = len(R.warnings)
        self.res_info.config(text=f"{len(R.tables)} tabelas · {len(R.figures)} figuras · "
                                  f"{n} aviso(s)" + (f" · salvo em {getattr(R, 'outdir', '')}"
                                                     if getattr(R, "outdir", None) else ""))
        self.nb.select(5)
        self.set_status("Análise concluída.")

    def save_results_as(self):
        if not self.results:
            return
        d = filedialog.askdirectory(title="Pasta para os resultados")
        if d:
            out = save_results(self.results, d)
            self.results.outdir = out
            self.set_status(f"Resultados gravados em {out}")

    def open_outdir(self):
        d = getattr(self.results, "outdir", None) if self.results else None
        d = d or self.project.resolve(self.project.output_dir)
        if d and os.path.isdir(d):
            if sys.platform.startswith("win"):
                os.startfile(d)
            elif sys.platform == "darwin":
                os.system(f'open "{d}"')
            else:
                os.system(f'xdg-open "{d}"')
        else:
            messagebox.showinfo("Resultados", "A pasta de resultados ainda não existe.")

    def show_methods_help(self):
        w = tk.Toplevel(self)
        w.title("Manual dos métodos")
        t = ScrolledText(w, width=112, height=40, font=("Consolas", 9), wrap="word")
        t.pack(fill="both", expand=True)
        from .manual import METODOS
        t.insert("end", METODOS)
        t.configure(state="disabled")   # só leitura (ainda permite selecionar e copiar)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    app = App(argv[0] if argv else None)
    app.mainloop()


if __name__ == "__main__":
    main()
