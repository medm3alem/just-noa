# -*- coding: utf-8 -*-
"""
ui/widgets.py - Éléments graphiques de la HMI (Tkinter pur, sans dépendance).

    Theme       couleurs et polices, choisies une fois pour toute l'application
    VideoView   affiche les images préparées par la chaîne vision
    ScoreGauge  grand score + jauge colorée
    PartBars    une barre par partie du corps
    PoseFigure  silhouette de la pose attendue (dessinée depuis la chorégraphie)
    LineChart   courbe du score dans le temps, zones de suivi perdu en rouge
    BarChart    comparaison des parties du corps

Les graphiques sont dessinés sur un Canvas à partir des VRAIES données du bilan :
pas de bibliothèque de graphiques à installer.
"""
from __future__ import absolute_import, division, print_function

import tkinter as tk
from tkinter import font as tkfont

from evaluation.pose_mapping import PART_LABELS, skeleton_from_features


class Theme(object):
    BG = "#f4f6fb"
    CARD = "#ffffff"
    INK = "#1f2933"
    MUTED = "#6b7785"
    LINE = "#dde3ec"
    ACCENT = "#3b5bdb"
    ACCENT_DARK = "#2f4ac0"
    GOOD = "#2f9e44"
    OK = "#f08c00"
    BAD = "#e03131"
    INFO = "#3b5bdb"
    LOST = "#ffe3e3"
    family = "Helvetica"

    @classmethod
    def setup(cls, root):
        families = set(tkfont.families(root))
        for name in ("Segoe UI", "Inter", "Helvetica Neue", "DejaVu Sans", "Helvetica"):
            if name in families:
                cls.family = name
                break

    @classmethod
    def font(cls, size, weight="normal"):
        return (cls.family, size, weight)

    @classmethod
    def score_color(cls, score):
        if score is None:
            return cls.MUTED
        if score >= 70:
            return cls.GOOD
        if score >= 45:
            return cls.OK
        return cls.BAD

    LEVEL_COLORS = {"bon": GOOD, "moyen": OK, "faible": BAD, "alerte": BAD, "info": INFO}


def card(parent, padding=16, **kw):
    """Cadre blanc à bordure fine, base de toutes les zones de l'interface."""
    return tk.Frame(parent, bg=Theme.CARD, highlightthickness=1,
                    highlightbackground=Theme.LINE, padx=padding, pady=padding, **kw)


class VideoView(tk.Label):
    """Affiche la dernière image de la chaîne vision (déjà en RVB, à la bonne taille)."""

    def __init__(self, parent, pipeline, size, period_ms=40):
        # Une image vide de la bonne taille sert de fond : le Label garde sa taille
        # en pixels, et les messages s'affichent par-dessus (compound="center").
        self._blank = tk.PhotoImage(width=size[0], height=size[1])
        tk.Label.__init__(self, parent, bg="#1d232c", fg="#c9d1db", image=self._blank,
                          compound="center", font=Theme.font(11), wraplength=size[0] - 40,
                          justify="center", bd=0)
        self.pipeline, self.size, self.period_ms = pipeline, size, period_ms
        self.image = None
        self._seq = -1
        self._job = None
        try:
            from PIL import Image, ImageTk
            self._pil = (Image, ImageTk)
        except ImportError:
            self._pil = None
        self.configure(text=self._idle_text())

    def _idle_text(self):
        if self.pipeline is None:
            return u"Video unavailable\n(needs Python 3 + opencv-contrib-python + Pillow)"
        if self._pil is None:
            return u"Pillow missing: pip install Pillow"
        return u"Starting video..."

    def start(self):
        if self._job is None:
            self._tick()

    def stop(self):
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None

    def _tick(self):
        self._job = self.after(self.period_ms, self._tick)
        if self.pipeline is None or self._pil is None:
            return
        frame, seq = self.pipeline.latest_display()
        if frame is None:
            st = self.pipeline.status()
            self.configure(image=self._blank,
                           text=st["camera_msg"] if not st["camera_ok"] else self._idle_text())
            return
        if seq == self._seq:
            return
        self._seq = seq
        Image, ImageTk = self._pil
        photo = ImageTk.PhotoImage(Image.fromarray(frame))
        self.configure(image=photo, text="")
        self.image = photo          # garder une référence, sinon Tk affiche une image vide


class ScoreGauge(tk.Canvas):
    """Score en grand + arc de jauge coloré selon la qualité."""

    def __init__(self, parent, size=170):
        tk.Canvas.__init__(self, parent, width=size, height=size, bg=Theme.CARD, highlightthickness=0)
        self.size = size

    def show(self, score, caption=u"score"):
        self.delete("all")
        s, pad = self.size, 12
        self.create_arc(pad, pad, s - pad, s - pad, start=225, extent=-270, style="arc",
                        width=14, outline=Theme.LINE)
        if score is not None:
            self.create_arc(pad, pad, s - pad, s - pad, start=225, extent=-270 * max(0, min(100, score)) / 100.0,
                            style="arc", width=14, outline=Theme.score_color(score))
        text = u"--" if score is None else u"%d" % round(score)
        self.create_text(s / 2, s / 2 - 6, text=text, font=Theme.font(40, "bold"),
                         fill=Theme.score_color(score) if score is not None else Theme.MUTED)
        self.create_text(s / 2, s / 2 + 34, text=caption, font=Theme.font(10), fill=Theme.MUTED)


class PartBars(tk.Frame):
    """Une ligne par partie du corps : nom, barre, valeur."""

    def __init__(self, parent, width=220):
        tk.Frame.__init__(self, parent, bg=Theme.CARD)
        self.width = width
        self.rows = {}
        for part in ("bras_gauche", "bras_droit", "jambes"):
            row = tk.Frame(self, bg=Theme.CARD)
            tk.Label(row, text=PART_LABELS[part], bg=Theme.CARD, fg=Theme.INK, width=11, anchor="w",
                     font=Theme.font(10)).pack(side="left")
            canvas = tk.Canvas(row, width=width - 140, height=12, bg=Theme.CARD, highlightthickness=0)
            canvas.pack(side="left", padx=6)
            value = tk.Label(row, text=u"--", bg=Theme.CARD, fg=Theme.MUTED, width=4, font=Theme.font(10))
            value.pack(side="left")
            self.rows[part] = (row, canvas, value)

    def show(self, parts, evaluated):
        for part, (row, canvas, value) in self.rows.items():
            if part not in evaluated:
                row.pack_forget()
                continue
            if not row.winfo_ismapped():
                row.pack(fill="x", pady=2)
            score = parts.get(part)
            w = int(canvas["width"])
            canvas.delete("all")
            canvas.create_rectangle(0, 2, w, 10, fill=Theme.LINE, width=0)
            if score is not None:
                canvas.create_rectangle(0, 2, w * max(0, min(100, score)) / 100.0, 10,
                                        fill=Theme.score_color(score), width=0)
            value.configure(text=u"--" if score is None else u"%d" % round(score),
                            fg=Theme.score_color(score))


class PoseFigure(tk.Canvas):
    """
    Silhouette de la pose que le joueur doit prendre maintenant, vue comme dans
    un miroir si l'affichage vidéo est en miroir. Les bras notés sont colorés.
    """

    def __init__(self, parent, width=200, height=230):
        tk.Canvas.__init__(self, parent, width=width, height=height, bg=Theme.CARD, highlightthickness=0)
        self.w, self.h = width, height

    def show(self, expected, evaluated, mirror=True):
        self.delete("all")
        if not expected:
            self.create_text(self.w / 2, self.h / 2, text=u"Target pose\nwhen NAO starts",
                             fill=Theme.MUTED, font=Theme.font(10), justify="center")
            return
        pts = skeleton_from_features(expected)
        # Hauteurs possibles : chevilles (z ~ -0.85) à poignets levés (z ~ +1.1)
        z_top, z_bottom = 1.15, -0.9
        scale = (self.h - 12) / (z_top - z_bottom)
        cx = self.w / 2

        def p(name):
            x, y, z = pts[name]
            return cx + scale * (-y if mirror else y), 6 + scale * (z_top - z)

        def seg(a, b, color, width=6):
            self.create_line(*(p(a) + p(b)), fill=color, width=width, capstyle="round")

        grey = "#c3cad5"
        seg("left_shoulder", "right_shoulder", grey)
        seg("left_hip", "right_hip", grey)
        seg("left_shoulder", "left_hip", grey)
        seg("right_shoulder", "right_hip", grey)
        for side, name in (("L", "left"), ("R", "right")):
            color = Theme.ACCENT if side + "_upper" in evaluated else grey
            seg(name + "_shoulder", name + "_elbow", color)
            seg(name + "_elbow", name + "_wrist", color if side + "_fore" in evaluated else grey)
            leg = Theme.ACCENT if side + "_knee" in evaluated else grey
            seg(name + "_hip", name + "_knee", leg)
            seg(name + "_knee", name + "_ankle", leg)
        hx, hy = p("nose")
        r = scale * 0.11
        self.create_oval(hx - r, hy - r, hx + r, hy + r, outline=grey, width=4)


class LineChart(tk.Canvas):
    """Courbe du score par intervalle ; zones rosées = joueur non suivi."""

    def __init__(self, parent, width=560, height=200):
        tk.Canvas.__init__(self, parent, width=width, height=height, bg=Theme.CARD, highlightthickness=0)
        self.w, self.h = width, height

    def show(self, timeline):
        self.delete("all")
        left, right, top, bottom = 34, self.w - 10, 10, self.h - 24
        if not timeline:
            self.create_text(self.w / 2, self.h / 2, text=u"No data", fill=Theme.MUTED)
            return
        t0, t1 = timeline[0]["t"], timeline[-1]["t"]
        span = max(0.5, t1 - t0)
        step = (right - left) / max(1, len(timeline))

        def x(i):
            return left + (i + 0.5) * step

        def y(v):
            return bottom - (bottom - top) * v / 100.0

        for i, row in enumerate(timeline):
            if row["score"] is None:
                self.create_rectangle(x(i) - step / 2, top, x(i) + step / 2, bottom,
                                      fill=Theme.LOST, width=0)
        for v in (0, 25, 50, 75, 100):
            self.create_line(left, y(v), right, y(v), fill=Theme.LINE)
            self.create_text(left - 6, y(v), text=str(v), anchor="e", fill=Theme.MUTED, font=Theme.font(8))
        segment = []
        for i, row in enumerate(timeline + [{"score": None}]):
            if row["score"] is not None:
                segment.extend((x(i), y(row["score"])))
            else:
                if len(segment) >= 4:
                    self.create_line(*segment, fill=Theme.ACCENT, width=2.5, smooth=True)
                elif len(segment) == 2:
                    self.create_oval(segment[0] - 2, segment[1] - 2, segment[0] + 2, segment[1] + 2,
                                     fill=Theme.ACCENT, outline="")
                segment = []
        for k in range(5):
            t = t0 + span * k / 4.0
            self.create_text(left + (right - left) * k / 4.0, bottom + 12, text=u"%d s" % round(t),
                             fill=Theme.MUTED, font=Theme.font(8))


class BarChart(tk.Canvas):
    """Barres horizontales : une par partie du corps évaluée."""

    def __init__(self, parent, width=260, height=120):
        tk.Canvas.__init__(self, parent, width=width, height=height, bg=Theme.CARD, highlightthickness=0)
        self.w, self.h = width, height

    def show(self, parts):
        self.delete("all")
        order = ("bras_gauche", "bras_droit", "jambes")
        items = [(PART_LABELS[p], parts[p]) for p in order if parts.get(p) is not None]
        if not items:
            self.create_text(self.w / 2, self.h / 2, text=u"No body part scored", fill=Theme.MUTED)
            return
        row_h = min(34, (self.h - 10) / len(items))
        for i, (label, value) in enumerate(items):
            yc = 8 + row_h * (i + 0.5)
            self.create_text(0, yc, text=label, anchor="w", fill=Theme.INK, font=Theme.font(10))
            x0, x1 = 92, self.w - 40
            self.create_rectangle(x0, yc - 6, x1, yc + 6, fill=Theme.LINE, width=0)
            self.create_rectangle(x0, yc - 6, x0 + (x1 - x0) * value / 100.0, yc + 6,
                                  fill=Theme.score_color(value), width=0)
            self.create_text(self.w - 4, yc, text=u"%d" % round(value), anchor="e",
                             fill=Theme.score_color(value), font=Theme.font(10, "bold"))
