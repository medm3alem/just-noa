# -*- coding: utf-8 -*-
"""
ui/game_screen.py - Préparation d'une danse, puis écran de jeu.

PrepareScreen : le joueur se place. Liste de vérifications mise à jour en
direct (robot, caméra, détection, joueur entièrement visible, chorégraphie),
aperçu vidéo avec squelette, puis compte à rebours et départ.
Sans caméra ni détection, on peut quand même lancer NAO : "Danser sans score".

GameScreen : vidéo + squelette coloré, score en direct, message au joueur,
barres par partie du corps, silhouette de la pose attendue, progression.
Tout est relu toutes les 100 ms dans ctrl.status() (lecture de cache, sans
réseau ni calcul lourd dans le thread Tkinter).
"""
from __future__ import absolute_import, division, print_function

import tkinter as tk
from tkinter import ttk

from ui.widgets import PartBars, PoseFigure, ScoreGauge, Theme, VideoView, card



STATE_TEXT = {"REPOS": u"resting", "OCCUPE": u"busy", "PRET": u"ready",
              "PREPARATION": u"getting ready", "DANSE": u"dancing", "ARRET": u"stopping",
              "ERREUR": u"error"}


def mmss(seconds):
    seconds = max(0, int(round(seconds or 0)))
    return u"%d:%02d" % (seconds // 60, seconds % 60)


class PrepareScreen(tk.Frame):

    def __init__(self, parent, app):
        tk.Frame.__init__(self, parent, bg=Theme.BG)
        self.app = app
        self._countdown_job = None

        head = tk.Frame(self, bg=Theme.BG)
        head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        self.title = tk.Label(head, text=u"", bg=Theme.BG, fg=Theme.INK, font=Theme.font(22, "bold"))
        self.title.pack(side="left")
        tk.Label(head, text=u"  Face the camera, with your whole upper body visible", bg=Theme.BG,
                 fg=Theme.MUTED, font=Theme.font(11)).pack(side="left")

        self.video = VideoView(self, app.pipeline, app.video_size)
        self.video.grid(row=1, column=0, sticky="nw")
        self.countdown = tk.Label(self, text=u"", bg="#1d232c", fg="white", font=Theme.font(96, "bold"))

        side = card(self, padding=18)
        side.grid(row=1, column=1, sticky="nsew", padx=(16, 0))
        tk.Label(side, text=u"Checklist", bg=Theme.CARD, fg=Theme.INK,
                 font=Theme.font(14, "bold")).pack(anchor="w", pady=(0, 8))
        self.checks = {}
        for key, label in (("robot", u"Robot connected"), ("camera", u"Camera"),
                           ("detector", u"Pose detection"), ("player", u"Player visible"),
                           ("choreo", u"Choreography ready")):
            row = tk.Frame(side, bg=Theme.CARD)
            row.pack(fill="x", pady=3)
            icon = tk.Canvas(row, width=18, height=18, bg=Theme.CARD, highlightthickness=0)
            icon.create_oval(3, 3, 15, 15, fill=Theme.LINE, outline="", tags="dot")
            icon.pack(side="left", padx=(0, 6))
            tk.Label(row, text=label, bg=Theme.CARD, fg=Theme.INK, font=Theme.font(11)).pack(side="left")
            detail = tk.Label(side, text=u"", bg=Theme.CARD, fg=Theme.MUTED, font=Theme.font(9),
                              wraplength=260, justify="left")
            detail.pack(anchor="w", padx=(26, 0))
            self.checks[key] = (icon, detail)
        self.hint = tk.Label(side, text=u"", bg=Theme.CARD, fg=Theme.MUTED, font=Theme.font(10),
                             wraplength=280, justify="left")
        self.hint.pack(anchor="w", pady=(12, 12))
        self.go = ttk.Button(side, text=u"Start", style="Accent.TButton", command=self.start_countdown)
        self.go.pack(fill="x")
        ttk.Button(side, text=u"Retry camera", command=self._retry).pack(fill="x", pady=(8, 0))
        ttk.Button(side, text=u"Back to menu", command=self.app.show_menu).pack(fill="x", pady=(8, 0))

    def on_show(self, choreo_title):
        self.title.configure(text=choreo_title)
        self.cancel_countdown()
        self.video.start()

    def on_hide(self):
        self.cancel_countdown()
        self.video.stop()

    def _retry(self):
        if self.app.pipeline is not None:
            self.app.pipeline.retry_camera()

    def refresh(self, st):
        robot = st["robot"]
        vision = self.app.pipeline.status() if self.app.pipeline is not None else None
        robot_ok = robot.get("connected") is not False and st["state"] in ("REPOS", "PRET")
        if robot.get("connected") is False:
            robot_detail = u"No connection to NAO: check the robot, the network and the bridge"
        elif st["state"] not in ("REPOS", "PRET"):
            robot_detail = u"Robot busy (%s)" % STATE_TEXT.get(st["state"], st["state"])
        else:
            robot_detail = u""
        self._set("robot", robot_ok, robot_detail)
        if vision is None:
            for key in ("camera", "detector", "player"):
                self._set(key, False, u"Vision unavailable (needs Python 3, OpenCV, Pillow)")
        else:
            self._set("camera", vision["camera_ok"], u"" if vision["camera_ok"] else vision["camera_msg"])
            self._set("detector", vision["detector_ok"],
                      u"" if vision["detector_ok"] else vision["detector_msg"])
            det = vision["detection"]
            texts = {"ok": u"", "absent": u"Nobody detected: step in front of the camera", "partiel":
                     u"Step back: shoulders, elbows and wrists must be visible",
                     "bord": u"Move to the center of the picture", "indisponible": u"No detection"}
            self._set("player", det == "ok", texts.get(det, det))
        self._set("choreo", st["selected"] is not None, u"")
        scoring = vision is not None and vision["camera_ok"] and vision["detector_ok"]
        self.go.configure(text=u"Start" if scoring else u"Dance without score")
        self.go.state(["!disabled"] if robot_ok and self._countdown_job is None else ["disabled"])
        if not scoring:
            self.hint.configure(text=u"Without a camera or pose detection, NAO still dances, "
                                     u"but no score is computed (demo mode).")
        elif vision["detection"] != "ok":
            self.hint.configure(text=u"You can start: scoring begins as soon as you are detected.")
        else:
            self.hint.configure(text=u"All set!")

    def _set(self, key, ok, detail):
        icon, label = self.checks[key]
        icon.itemconfigure("dot", fill=Theme.GOOD if ok else Theme.BAD)
        label.configure(text=detail)

    # --- Compte à rebours (non bloquant : after()) ---------------------------------------
    def start_countdown(self):
        n = int(getattr(self.app.cfg, "PREPARE_COUNTDOWN", 3))
        if n <= 0:
            self.app.launch_dance()
            return
        self.countdown.grid(row=1, column=0, sticky="nsew")
        self._tick(n)

    def _tick(self, n):
        if n == 0:
            self.cancel_countdown()
            self.app.launch_dance()
            return
        self.countdown.configure(text=str(n))
        self._countdown_job = self.after(1000, self._tick, n - 1)

    def cancel_countdown(self):
        if self._countdown_job is not None:
            self.after_cancel(self._countdown_job)
            self._countdown_job = None
        self.countdown.grid_forget()


class GameScreen(tk.Frame):

    def __init__(self, parent, app):
        tk.Frame.__init__(self, parent, bg=Theme.BG)
        self.app = app
        self.columnconfigure(1, weight=1)
        head = tk.Frame(self, bg=Theme.BG)
        head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        self.title = tk.Label(head, text=u"", bg=Theme.BG, fg=Theme.INK, font=Theme.font(22, "bold"))
        self.title.pack(side="left")
        self.state = tk.Label(head, text=u"", bg=Theme.BG, fg=Theme.MUTED, font=Theme.font(12))
        self.state.pack(side="left", padx=14)
        ttk.Button(head, text=u"Menu", command=self.app.leave_game).pack(side="right")
        self.stop_btn = ttk.Button(head, text=u"Stop", style="Danger.TButton", command=self.app.stop_dance)
        self.stop_btn.pack(side="right", padx=8)

        left = tk.Frame(self, bg=Theme.BG)
        left.grid(row=1, column=0, sticky="nw")
        self.video = VideoView(left, app.pipeline, app.video_size)
        self.video.pack()
        self.message = tk.Label(left, text=u"", bg=Theme.BG, fg=Theme.INK, font=Theme.font(22, "bold"),
                                anchor="w")
        self.message.pack(fill="x", pady=(10, 4))
        bar = tk.Frame(left, bg=Theme.BG)
        bar.pack(fill="x")
        self.progress = ttk.Progressbar(bar, maximum=1000, style="Game.Horizontal.TProgressbar")
        self.progress.pack(side="left", fill="x", expand=True)
        self.time = tk.Label(bar, text=u"", bg=Theme.BG, fg=Theme.MUTED, font=Theme.font(10), width=14)
        self.time.pack(side="left")

        side = card(self, padding=14)
        side.grid(row=1, column=1, sticky="nsew", padx=(16, 0))
        self.gauge = ScoreGauge(side)
        self.gauge.pack()
        self.parts = PartBars(side)
        self.parts.pack(fill="x", pady=(4, 10))
        tk.Label(side, text=u"Target pose", bg=Theme.CARD, fg=Theme.MUTED,
                 font=Theme.font(10)).pack(anchor="w")
        self.figure = PoseFigure(side, width=230, height=250)
        self.figure.pack()
        self.mode = tk.Label(side, text=u"", bg=Theme.CARD, fg=Theme.MUTED, font=Theme.font(9))
        self.mode.pack(anchor="w")

    def on_show(self, title):
        self.title.configure(text=title)
        self.message.configure(text=u"NAO is getting ready...", fg=Theme.MUTED)
        self.gauge.show(None)
        self.video.start()

    def on_hide(self):
        self.video.stop()

    def refresh(self, st):
        state = st["state"]
        labels = {"PREPARATION": u"NAO is getting ready...", "DANSE": u"Your turn: dance!",
                  "ARRET": u"Finishing the dance...", "PRET": u"Done", "ERREUR": u"Error"}
        self.state.configure(text=labels.get(state, state))
        self.stop_btn.state(["!disabled"] if state in ("PREPARATION", "DANSE") else ["disabled"])
        duration = st["duration"] or 0.0
        elapsed = st["elapsed"] if state in ("DANSE", "ARRET") else 0.0
        self.progress["value"] = int(1000 * elapsed / duration) if duration else 0
        self.time.configure(text=u"%s left" % mmss(duration - elapsed) if duration else u"")
        game = st.get("game")
        if game is None:
            if state == "ERREUR":
                self.message.configure(text=st["message"], fg=Theme.BAD)
            elif self.app.pipeline is None or not self.app.scoring_possible():
                self.message.configure(text=u"Demo mode: no score", fg=Theme.MUTED)
            return
        self.gauge.show(game["score"], u"score" if game["in_window"] else u"waiting")
        evaluated = set(game["features"])
        parts = set(p for p, feats in (("bras_gauche", ("L_upper", "L_fore")),
                                        ("bras_droit", ("R_upper", "R_fore")),
                                        ("jambes", ("L_knee", "R_knee")))
                    if any(f in evaluated for f in feats))
        self.parts.show(game["parts"], parts)
        self.figure.show(game["expected"], evaluated, mirror=getattr(self.app.cfg, "CAMERA_MIRROR", True))
        if state == "PREPARATION":
            self.message.configure(text=u"NAO is getting ready... take your place!", fg=Theme.MUTED)
        else:
            self.message.configure(text=game["message"], fg=Theme.LEVEL_COLORS.get(game["level"], Theme.INK))
        self.mode.configure(text=u"Matching: %s" % (u"mirror" if game["mode"] == "miroir"
                                                     else u"same side"))
