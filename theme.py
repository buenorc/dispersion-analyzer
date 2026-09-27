# -*- coding: utf-8 -*-
"""Tema visual moderno (claro, plano) para a interface — só ttk, sem dependências."""
from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

# paleta
BG = "#ffffff"          # fundo das páginas
WINDOW = "#eef1f5"      # moldura da janela, abas não selecionadas
CARD = "#ffffff"        # cartões, tabelas, campos
BORDER = "#dde1e7"
BORDER_STRONG = "#c5cbd3"
INK = "#1f2328"         # texto principal
INK2 = "#57606a"        # texto secundário
MUTED = "#6e7781"       # dicas
ACCENT = "#2a78d6"
ACCENT_HOVER = "#1f65bb"
ACCENT_SOFT = "#e3eefb"  # seleção
HEADER = "#ffffff"
ERROR = "#c62828"
OK = "#1a7f37"


def _font_family():
    fams = set(tkfont.families())
    for f in ("Segoe UI", "SF Pro Text", "Helvetica Neue", "Inter", "Ubuntu", "DejaVu Sans"):
        if f in fams:
            return f
    return "TkDefaultFont"


def apply_theme(root: tk.Misc):
    fam = _font_family()
    base = (fam, 10)
    bold = (fam, 10, "bold")
    mono = ("Consolas" if sys.platform.startswith("win") else "Menlo"
            if sys.platform == "darwin" else "DejaVu Sans Mono", 9)

    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        try:
            tkfont.nametofont(name).configure(family=fam, size=10)
        except tk.TclError:
            pass

    root.configure(bg=WINDOW)
    # widgets tk clássicos (Listbox, Text, Toplevel, Menu, lista do Combobox)
    o = root.option_add
    o("*Toplevel.background", BG)
    o("*Listbox.background", CARD)
    o("*Listbox.foreground", INK)
    o("*Listbox.selectBackground", ACCENT_SOFT)
    o("*Listbox.selectForeground", INK)
    o("*Listbox.relief", "flat")
    o("*Listbox.highlightThickness", 1)
    o("*Listbox.highlightColor", ACCENT)
    o("*Listbox.highlightBackground", BORDER)
    o("*Listbox.activeStyle", "none")
    o("*Listbox.font", base)
    o("*Text.background", CARD)
    o("*Text.foreground", INK)
    o("*Text.relief", "flat")
    o("*Text.highlightThickness", 1)
    o("*Text.highlightColor", ACCENT)
    o("*Text.highlightBackground", BORDER)
    o("*Text.selectBackground", ACCENT_SOFT)
    o("*Text.selectForeground", INK)
    o("*Text.insertBackground", INK)
    o("*Text.padX", 8)
    o("*Text.padY", 6)
    o("*Text.font", mono)
    o("*TCombobox*Listbox.background", CARD)
    o("*TCombobox*Listbox.foreground", INK)
    o("*TCombobox*Listbox.selectBackground", ACCENT)
    o("*TCombobox*Listbox.selectForeground", "white")
    o("*TCombobox*Listbox.font", base)
    o("*Menu.background", CARD)
    o("*Menu.foreground", INK)
    o("*Menu.activeBackground", ACCENT_SOFT)
    o("*Menu.activeForeground", INK)
    o("*Menu.relief", "flat")
    o("*Menu.font", base)

    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=BG, foreground=INK, font=base, bordercolor=BORDER,
                lightcolor=BG, darkcolor=BG, troughcolor=BG, fieldbackground=CARD,
                focuscolor=ACCENT, selectbackground=ACCENT_SOFT, selectforeground=INK,
                insertcolor=INK, arrowcolor=INK2)
    s.configure("TFrame", background=BG)
    s.configure("Card.TFrame", background=CARD)
    s.configure("Header.TFrame", background=HEADER)
    s.configure("TLabel", background=BG, foreground=INK)
    s.configure("Muted.TLabel", foreground=MUTED)
    s.configure("Card.TLabel", background=CARD)
    s.configure("Header.TLabel", background=HEADER, foreground=INK, font=(fam, 15, "bold"))
    s.configure("HeaderSub.TLabel", background=HEADER, foreground=MUTED, font=(fam, 10))
    s.configure("Link.TLabel", background=BG, foreground=ACCENT, font=(fam, 10, "underline"))
    s.configure("TMenubutton", background="#f1f4f8", foreground=INK, bordercolor="#d3d9e1",
                lightcolor="#f1f4f8", darkcolor="#f1f4f8", relief="flat", padding=(12, 5),
                arrowsize=0)
    s.map("TMenubutton", background=[("active", ACCENT_SOFT)],
          lightcolor=[("active", ACCENT_SOFT)], darkcolor=[("active", ACCENT_SOFT)],
          foreground=[("active", ACCENT_HOVER)])
    s.configure("Status.TLabel", background=WINDOW, foreground=INK2, padding=(14, 5))
    s.configure("Accent.TLabel", background=HEADER, foreground=ACCENT, font=(fam, 15, "bold"))

    # caixas com título
    s.configure("TLabelframe", background=BG, bordercolor=BORDER, relief="solid",
                borderwidth=1, lightcolor=BORDER, darkcolor=BORDER, padding=8)
    s.configure("TLabelframe.Label", background=BG, foreground=ACCENT, font=bold)

    # botões
    BTN = "#f1f4f8"
    s.configure("TButton", background=BTN, foreground=INK, bordercolor="#d3d9e1",
                lightcolor=BTN, darkcolor=BTN, relief="flat", padding=(12, 5),
                focusthickness=0, focuscolor=BTN)
    s.map("TButton",
          background=[("disabled", "#f6f7f9"), ("pressed", "#d6e4f7"), ("active", ACCENT_SOFT)],
          bordercolor=[("active", "#9cc0ec")],
          lightcolor=[("pressed", "#d6e4f7"), ("active", ACCENT_SOFT)],
          darkcolor=[("pressed", "#d6e4f7"), ("active", ACCENT_SOFT)],
          foreground=[("disabled", MUTED), ("active", ACCENT_HOVER)])
    s.configure("Accent.TButton", background=ACCENT, foreground="white", bordercolor=ACCENT,
                lightcolor=ACCENT, darkcolor=ACCENT, font=bold, padding=(18, 8),
                focuscolor=ACCENT)
    s.map("Accent.TButton",
          background=[("disabled", "#9dbfe9"), ("pressed", "#17569f"), ("active", ACCENT_HOVER)],
          lightcolor=[("active", ACCENT_HOVER)], darkcolor=[("active", ACCENT_HOVER)],
          bordercolor=[("active", ACCENT_HOVER)], foreground=[("disabled", "white")])

    # abas
    s.configure("TNotebook", background=WINDOW, borderwidth=0, tabmargins=(12, 6, 12, 0),
                lightcolor=BG, darkcolor=BG, bordercolor=BORDER)
    s.configure("TNotebook.Tab", background=WINDOW, foreground=INK2, padding=(18, 9),
                borderwidth=0, lightcolor=WINDOW, darkcolor=WINDOW, bordercolor=WINDOW,
                font=base, focuscolor=WINDOW)
    s.map("TNotebook.Tab",
          background=[("selected", CARD), ("active", "#e3e8ee")],
          foreground=[("selected", ACCENT), ("active", INK)],
          lightcolor=[("selected", ACCENT)], bordercolor=[("selected", BORDER)],
          font=[("selected", bold)])
    s.configure("Sub.TNotebook", background=CARD, tabmargins=(0, 4, 0, 0))
    s.configure("Sub.TNotebook.Tab", background="#f3f5f8", lightcolor="#f3f5f8",
                darkcolor="#f3f5f8", bordercolor="#f3f5f8")
    s.configure("Sub.TNotebook.Tab", padding=(14, 6))

    # campos
    for w in ("TEntry", "TCombobox", "TSpinbox"):
        s.configure(w, fieldbackground=CARD, background=CARD, foreground=INK,
                    bordercolor=BORDER_STRONG, lightcolor=CARD, darkcolor=CARD, padding=(6, 4),
                    arrowsize=13, insertcolor=INK)
        s.map(w, bordercolor=[("focus", ACCENT), ("hover", "#9aa4b0")],
              lightcolor=[("focus", ACCENT)],
              fieldbackground=[("readonly", CARD), ("disabled", "#f3f5f8")],
              selectbackground=[("focus", ACCENT_SOFT)], selectforeground=[("focus", INK)])

    # seleção (caixa branca; marcada = azul com ✓ branco)
    for w in ("TCheckbutton", "TRadiobutton"):
        s.configure(w, background=BG, foreground=INK, indicatorbackground=CARD,
                    indicatorforeground=CARD, upperbordercolor=BORDER_STRONG,
                    lowerbordercolor=BORDER_STRONG, focuscolor=BG, padding=(2, 3),
                    indicatormargin=(0, 0, 8, 0), indicatorsize=15)
        s.map(w, indicatorbackground=[("selected", ACCENT), ("pressed", ACCENT_SOFT)],
              indicatorforeground=[("selected", "white")],
              upperbordercolor=[("selected", ACCENT), ("active", ACCENT)],
              lowerbordercolor=[("selected", ACCENT), ("active", ACCENT)],
              background=[("active", BG)], foreground=[("disabled", MUTED)])

    # tabelas
    s.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=INK,
                bordercolor=BORDER, lightcolor=CARD, darkcolor=CARD, rowheight=28, font=base)
    s.map("Treeview", background=[("selected", ACCENT_SOFT)], foreground=[("selected", INK)])
    s.configure("Treeview.Heading", background="#eef1f5", foreground=INK2, font=bold,
                relief="flat", bordercolor=BORDER, lightcolor="#eef1f5", darkcolor="#eef1f5",
                padding=(8, 6))
    s.map("Treeview.Heading", background=[("active", "#e3e8ef")])

    # barras de rolagem finas, progresso, divisórias
    for o_ in ("Vertical", "Horizontal"):
        s.configure(f"{o_}.TScrollbar", background="#cfd5dc", troughcolor=CARD,
                    bordercolor=CARD, lightcolor="#cfd5dc", darkcolor="#cfd5dc",
                    arrowcolor=INK2, gripcount=0, arrowsize=12, relief="flat")
        s.map(f"{o_}.TScrollbar", background=[("active", "#aeb6c0")])
    s.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor="#e4e8ee",
                bordercolor="#e4e8ee", lightcolor=ACCENT, darkcolor=ACCENT, thickness=6)
    s.configure("TPanedwindow", background=BG)
    s.configure("Sash", sashthickness=8, gripcount=0, background=BG)
    s.configure("TSeparator", background=BORDER)
    return s


def style_mpl_toolbar(toolbar):
    """Deixa a barra do matplotlib (widgets tk) com o mesmo fundo do tema."""
    try:
        toolbar.configure(background=CARD)
        for w in toolbar.winfo_children():
            try:
                w.configure(background=CARD, highlightthickness=0, bd=0,
                            activebackground=ACCENT_SOFT)
            except tk.TclError:
                try:
                    w.configure(background=CARD)
                except tk.TclError:
                    pass
    except tk.TclError:
        pass
