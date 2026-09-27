# -*- coding: utf-8 -*-
"""Widgets auxiliares da interface (tkinter/ttk)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import numpy as np
import pandas as pd


class EditableTable(ttk.Frame):
    """Tabela editável: duplo clique edita a célula; aceita colar do Excel."""

    def __init__(self, master, columns, widths=None, height=8, **kw):
        super().__init__(master, **kw)
        self.columns = list(columns)
        self.tree = ttk.Treeview(self, columns=self.columns, show="headings", height=height,
                                 selectmode="extended")
        for i, c in enumerate(self.columns):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=(widths[i] if widths else 110), anchor="center",
                             stretch=True)
        ys = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=ys.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        bar = ttk.Frame(self)
        bar.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Button(bar, text="+ linha", command=self.add_row).pack(side="left")
        ttk.Button(bar, text="− remover", command=self.remove_rows).pack(side="left", padx=4)
        ttk.Button(bar, text="Colar (Ctrl+V)", command=self.paste).pack(side="left")
        ttk.Button(bar, text="Limpar", command=self.clear).pack(side="left", padx=4)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", self._edit)
        self.tree.bind("<Control-v>", lambda e: self.paste())
        self.tree.bind("<Delete>", lambda e: self.remove_rows())
        self._entry = None
        self.on_change = None

    # ------------------------------------------------------------------
    def add_row(self, values=None):
        vals = list(values) if values is not None else [""] * len(self.columns)
        vals += [""] * (len(self.columns) - len(vals))
        iid = self.tree.insert("", "end", values=vals[:len(self.columns)])
        self._changed()
        return iid

    def remove_rows(self):
        for i in self.tree.selection():
            self.tree.delete(i)
        self._changed()

    def clear(self):
        self.tree.delete(*self.tree.get_children())
        self._changed()

    def set_rows(self, rows):
        self.tree.delete(*self.tree.get_children())
        for r in rows:
            self.add_row(["" if v is None or (isinstance(v, float) and np.isnan(v)) else v
                          for v in r])

    def get_rows(self):
        return [list(self.tree.item(i, "values")) for i in self.tree.get_children()]

    def paste(self):
        try:
            txt = self.clipboard_get()
        except tk.TclError:
            return
        for line in txt.strip().splitlines():
            parts = line.split("\t") if "\t" in line else \
                (line.split(";") if ";" in line else line.split())
            parts = [p.strip() for p in parts]
            if parts and any(parts):
                self.add_row(parts)

    def _changed(self):
        if self.on_change:
            self.on_change()

    def _edit(self, ev):
        if self.tree.identify("region", ev.x, ev.y) != "cell":
            return
        iid = self.tree.identify_row(ev.y)
        col = self.tree.identify_column(ev.x)
        ci = int(col[1:]) - 1
        x, y, w, h = self.tree.bbox(iid, col)
        val = self.tree.item(iid, "values")[ci]
        e = ttk.Entry(self.tree)
        e.insert(0, val)
        e.select_range(0, "end")
        e.place(x=x, y=y, width=w, height=h)
        e.focus_set()

        def done(_=None, save=True):
            if save:
                vals = list(self.tree.item(iid, "values"))
                vals[ci] = e.get()
                self.tree.item(iid, values=vals)
                self._changed()
            e.destroy()

        e.bind("<Return>", done)
        e.bind("<Tab>", done)
        e.bind("<FocusOut>", done)
        e.bind("<Escape>", lambda _: done(save=False))


class DataFrameView(ttk.Frame):
    """Mostra um DataFrame numa Treeview (somente leitura)."""

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.tree = ttk.Treeview(self, show="headings")
        ys = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        xs = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

    def show(self, df: pd.DataFrame):
        self.tree.delete(*self.tree.get_children())
        cols = [str(c) for c in df.columns]
        self.tree.configure(columns=cols)
        for c in cols:
            txt = df[c].map(lambda v: f"{v:.5g}" if isinstance(v, (float, np.floating)) else str(v))
            n = max([len(c)] + [len(s) for s in txt])
            self.tree.heading(c, text=c)
            self.tree.column(c, width=max(70, min(520, 7 * n + 16)),
                             anchor="w" if df[c].dtype == object else "center", stretch=False)
        for _, r in df.iterrows():
            vals = []
            for v in r:
                if isinstance(v, (float, np.floating)):
                    vals.append("" if np.isnan(v) else f"{v:.5g}")
                else:
                    vals.append(str(v))
            self.tree.insert("", "end", values=vals)


class LabeledEntry(ttk.Frame):
    def __init__(self, master, label, var, width=14, tip=None, **kw):
        super().__init__(master, **kw)
        ttk.Label(self, text=label).pack(side="left")
        ttk.Entry(self, textvariable=var, width=width).pack(side="left", padx=4)
        if tip:
            ttk.Label(self, text=tip, foreground="#6b6a66").pack(side="left")


def fnum(s, default=None):
    """Converte texto em float (aceita vírgula decimal); vazio -> default."""
    if s is None:
        return default
    s = str(s).strip().replace(",", ".")
    if s == "":
        return default
    try:
        return float(s)
    except ValueError:
        return default
