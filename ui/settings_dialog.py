# -*- coding: utf-8 -*-
"""
ui/settings_dialog.py - Fenêtre Settings (textes en anglais : ils sont vus par le joueur).

Sections :
- Language      : anglais (seule langue des textes joueur pour l'instant) ;
- NAO's voice   : NAO parle à la fin (score + commentaire), commentaire
                  sarcastique oui/non, intensité (friendly / sarcastic / savage),
                  longueur (short / long), encouragements vocaux pendant la danse ;
- Imitation     : correspondance miroir / même côté / automatique ;
- Camera        : choix de la webcam (numéro ou URL), affichage miroir, 3D, latences ;
- Robot         : IP de NAO et port de la passerelle Choregraphe.

Les changements sont enregistrés dans results/settings.json (app/settings.py).
La caméra et l'adresse de la passerelle sont appliquées tout de suite, le reste
à la prochaine danse.
"""
from __future__ import absolute_import, division, print_function

import tkinter as tk
from tkinter import ttk

from app import settings
from ui.widgets import Theme

CAMERA_CHOICES = (u"0", u"1", u"2", u"3")


class SettingsDialog(tk.Toplevel):

    def __init__(self, app):
        tk.Toplevel.__init__(self, app.root)
        self.app, cfg = app, app.cfg
        self.title(u"Settings")
        self.configure(bg=Theme.CARD, padx=20, pady=12)
        self.resizable(False, False)
        self.transient(app.root)

        self.speaks = tk.BooleanVar(value=getattr(cfg, "NAO_SPEAKS", True))
        self.sarcasm = tk.BooleanVar(value=getattr(cfg, "ROAST_ENABLED", True))
        self.intensity = tk.StringVar(value=getattr(cfg, "ROAST_INTENSITY", "sarcastic"))
        self.length = tk.StringVar(value=getattr(cfg, "COMMENTARY_LENGTH", "short"))
        self.voice = tk.BooleanVar(value=getattr(cfg, "VOICE_FEEDBACK", False))
        self.mapping = tk.StringVar(value=getattr(cfg, "MAPPING_MODE", "auto"))
        self.mirror = tk.BooleanVar(value=getattr(cfg, "CAMERA_MIRROR", True))
        self.depth = tk.BooleanVar(value=getattr(cfg, "EVAL_DEPTH", True))
        self.robot_lat = tk.StringVar(value=u"%.2f" % getattr(cfg, "ROBOT_LATENCY", 0.1))
        self.camera_lat = tk.StringVar(value=u"%.2f" % getattr(cfg, "CAMERA_LATENCY", 0.08))
        self.source = tk.StringVar(value=str(getattr(cfg, "VIDEO_SOURCE", 0)))
        self.ip = tk.StringVar(value=str(getattr(cfg, "NAO_IP", "192.168.2.121")))
        self.port = tk.StringVar(value=str(getattr(cfg, "BRIDGE_PORT", 8766)))

        # Deux colonnes pour tenir sur un écran de portable.
        left = tk.Frame(self, bg=Theme.CARD)
        left.grid(row=0, column=0, sticky="nw", padx=(0, 24))
        right = tk.Frame(self, bg=Theme.CARD)
        right.grid(row=0, column=1, sticky="nw")

        r = self._section(left, u"Language", 0)
        tk.Label(left, text=u"English (all player-facing text and NAO's voice)", bg=Theme.CARD,
                 fg=Theme.MUTED, font=Theme.font(10)).grid(row=r, column=0, columnspan=2, sticky="w")
        r += 1
        r = self._section(left, u"NAO's voice and personality", r)
        r = self._check(left, u"NAO announces the score at the end", self.speaks, r)
        r = self._check(left, u"Sarcastic comments (off = kind comments only)", self.sarcasm, r)
        tk.Label(left, text=u"Roast intensity", bg=Theme.CARD, fg=Theme.INK,
                 font=Theme.font(10)).grid(row=r, column=0, columnspan=2, sticky="w", pady=(4, 0))
        r += 1
        for value, label in (("friendly", u"Friendly (gentle teasing)"),
                             ("sarcastic", u"Sarcastic (default)"),
                             ("savage", u"Savage (still about the dance only)")):
            ttk.Radiobutton(left, text=label, value=value, variable=self.intensity).grid(
                row=r, column=0, columnspan=2, sticky="w", padx=(12, 0))
            r += 1
        tk.Label(left, text=u"Comment length", bg=Theme.CARD, fg=Theme.INK,
                 font=Theme.font(10)).grid(row=r, column=0, columnspan=2, sticky="w", pady=(4, 0))
        r += 1
        for value, label in (("short", u"Short: score + one line"),
                             ("long", u"Long: score + one line + one measured fact")):
            ttk.Radiobutton(left, text=label, value=value, variable=self.length).grid(
                row=r, column=0, columnspan=2, sticky="w", padx=(12, 0))
            r += 1
        r = self._check(left, u"Spoken encouragements during the dance (rare)", self.voice, r)
        r = self._section(left, u"Imitation", r)
        for value, label in (("auto", u"Automatic (the better of the two)"),
                             ("miroir", u"Mirror: NAO's left arm = my right arm"),
                             ("meme_cote", u"Same side: NAO's left arm = my left arm")):
            ttk.Radiobutton(left, text=label, value=value, variable=self.mapping).grid(
                row=r, column=0, columnspan=2, sticky="w")
            r += 1

        r = self._section(right, u"Camera", 0)
        tk.Label(right, text=u"Camera (webcam number or URL)", bg=Theme.CARD, fg=Theme.INK,
                 font=Theme.font(10)).grid(row=r, column=0, sticky="w", pady=2)
        ttk.Combobox(right, textvariable=self.source, values=CAMERA_CHOICES, width=26).grid(
            row=r, column=1, sticky="w", padx=(8, 0))
        r += 1
        r = self._check(right, u"Mirror display", self.mirror, r)
        r = self._check(right, u"3D scoring (untick if depth is unreliable)", self.depth, r)
        r = self._entry(right, u"Camera latency (s)", self.camera_lat, r)
        r = self._entry(right, u"Robot latency (s)", self.robot_lat, r)
        r = self._section(right, u"Robot connection", r)
        r = self._entry(right, u"NAO IP address", self.ip, r, width=18)
        r = self._entry(right, u"Choregraphe bridge port", self.port, r)
        tk.Label(right, text=u"Only on a trusted local network: the bridge moves the robot.",
                 bg=Theme.CARD, fg=Theme.MUTED, font=Theme.font(9), wraplength=360,
                 justify="left").grid(row=r, column=0, columnspan=2, sticky="w")
        r += 1

        self.error = tk.Label(self, text=u"", bg=Theme.CARD, fg=Theme.BAD, font=Theme.font(9))
        self.error.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        buttons = tk.Frame(self, bg=Theme.CARD)
        buttons.grid(row=2, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text=u"Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text=u"Save", style="Accent.TButton", command=self._save).pack(
            side="right", padx=8)
        self.grab_set()

    @staticmethod
    def _section(parent, text, row):
        tk.Label(parent, text=text, bg=Theme.CARD, fg=Theme.INK, font=Theme.font(12, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(10, 4))
        return row + 1

    @staticmethod
    def _check(parent, text, var, row):
        ttk.Checkbutton(parent, text=text, variable=var).grid(row=row, column=0, columnspan=2, sticky="w")
        return row + 1

    @staticmethod
    def _entry(parent, label, var, row, width=8):
        tk.Label(parent, text=label, bg=Theme.CARD, fg=Theme.INK, font=Theme.font(10)).grid(
            row=row, column=0, sticky="w", pady=2)
        ttk.Entry(parent, textvariable=var, width=width).grid(row=row, column=1, sticky="w", padx=(8, 0))
        return row + 1

    def _save(self):
        cfg = self.app.cfg
        try:
            robot_lat = float(self.robot_lat.get().replace(",", "."))
            camera_lat = float(self.camera_lat.get().replace(",", "."))
            if not (0 <= robot_lat <= 1 and 0 <= camera_lat <= 1):
                raise ValueError
        except ValueError:
            self.error.configure(text=u"Latencies: numbers between 0 and 1 second.")
            return
        ip = settings.check_ip(self.ip.get())
        port = settings.check_port(self.port.get())
        if ip is None or port is None:
            self.error.configure(text=u"Robot: enter an IP like 192.168.2.121 and a port between 1 and 65535.")
            return
        source = self.source.get().strip()
        source = int(source) if source.isdigit() else source
        if source == u"":
            self.error.configure(text=u"Camera: enter a webcam number (0, 1...) or a URL.")
            return
        cfg.NAO_SPEAKS = self.speaks.get()
        cfg.ROAST_ENABLED = self.sarcasm.get()
        cfg.ROAST_INTENSITY = self.intensity.get()
        cfg.COMMENTARY_LENGTH = self.length.get()
        cfg.VOICE_FEEDBACK = self.voice.get()
        cfg.MAPPING_MODE = self.mapping.get()
        cfg.CAMERA_MIRROR = self.mirror.get()
        cfg.EVAL_DEPTH = self.depth.get()
        cfg.ROBOT_LATENCY, cfg.CAMERA_LATENCY = robot_lat, camera_lat
        changed_source = source != getattr(cfg, "VIDEO_SOURCE", 0)
        cfg.VIDEO_SOURCE = source
        changed_robot = (ip, port) != (getattr(cfg, "NAO_IP", None), getattr(cfg, "BRIDGE_PORT", None))
        cfg.NAO_IP, cfg.BRIDGE_PORT = ip, port
        try:
            settings.save(cfg)
        except (OSError, IOError) as err:
            self.error.configure(text=u"Could not save: %s" % err)
            return
        self.app.apply_settings(changed_source, changed_robot)
        self.destroy()
