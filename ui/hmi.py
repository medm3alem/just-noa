# -*- coding: utf-8 -*-
"""
ui/hmi.py - Interface graphique du jeu Just Nao (Python 3, Tkinter).

Cinq écrans dans une seule fenêtre, une barre d'état permanente en bas.
Tout ce que voit le joueur est en anglais (les commentaires du code restent en français).

    MENU ──Danser──> PRÉPARATION ──3,2,1──> JEU ──fin──> RÉSULTATS ──Rejouer──> PRÉPARATION
      │                                                      └──Menu──> MENU
      └──Historique──> HISTORIQUE ──double-clic──> RÉSULTATS

Principes conservés de la HMI d'origine :
- l'interface n'appelle que le contrôleur (select, start, stop, wake, rest,
  skip_commentary) ;
- elle ne l'attend jamais : toutes les 100 ms, refresh() relit ctrl.status()
  (lecture de cache) et met à jour l'écran visible ;
- la vidéo est déjà préparée par le thread vision : le thread Tkinter ne fait
  qu'afficher.

Raccourcis : Espace = démarrer / arrêter, Échap = menu.
"""
from __future__ import absolute_import, division, print_function

import tkinter as tk
from tkinter import ttk

from compat import to_text
from ui.game_screen import GameScreen, PrepareScreen, mmss
from ui.results_screen import HistoryScreen, ResultsScreen
from ui.widgets import Theme, card

POLL_MS = 100
STATE_LABELS = {
    "REPOS": (u"Resting", "#868e96"), "OCCUPE": (u"Busy...", "#f08c00"),
    "PRET": (u"Ready", "#2f9e44"), "PREPARATION": (u"Getting ready...", "#f08c00"),
    "DANSE": (u"Dancing!", "#3b5bdb"), "ARRET": (u"Stopping...", "#f08c00"), "ERREUR": (u"Error", "#e03131"),
}
DETECTION_LABELS = {"ok": u"player detected", "absent": u"no player", "partiel": u"player partly visible",
                    "bord": u"player at the edge", "indisponible": u"detection unavailable"}


class HMI(object):

    def __init__(self, ctrl, pipeline, store, cfg):
        self.ctrl, self.pipeline, self.store, self.cfg = ctrl, pipeline, store, cfg
        self.video_size = tuple(getattr(cfg, "HMI_VIDEO_SIZE", (560, 420)))
        if pipeline is not None:
            pipeline.display_size = self.video_size
        self._ids = []
        self._log_seq = 0
        self._report_seen = 0
        self._screen = None
        self._ignore_next_report = False
        self._poll_job = None

        self.root = tk.Tk()
        self.root.title(u"Just Nao")
        self.root.geometry("1220x780")
        self.root.minsize(1100, 720)
        self.root.configure(bg=Theme.BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        Theme.setup(self.root)
        self._styles()

        self._header()
        body = tk.Frame(self.root, bg=Theme.BG, padx=20, pady=8)
        body.pack(fill="both", expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.screens = {
            "menu": self._build_menu(body),
            "prepare": PrepareScreen(body, self),
            "game": GameScreen(body, self),
            "results": ResultsScreen(body, self),
            "history": HistoryScreen(body, self),
        }
        for frame in self.screens.values():
            frame.grid(row=0, column=0, sticky="nsew")
        self._status_bar()

        self.root.bind("<space>", self._on_space)
        self.root.bind("<Escape>", lambda e: self.leave_game() if self._screen == "game" else self.show_menu())
        if pipeline is not None:
            pipeline.start()
        self.show_menu()
        self._poll_job = self.root.after(POLL_MS, self._refresh)

    def run(self):
        self.root.mainloop()

    def close(self):
        for name in ("prepare", "game"):
            self.screens[name].on_hide()
        if self._poll_job is not None:
            self.root.after_cancel(self._poll_job)
            self._poll_job = None
        if self.pipeline is not None:
            self.pipeline.stop()          # libère la webcam et arrête le thread vision
        self.root.destroy()               # main.py appelle ensuite ctrl.shutdown()

    # =========================================================================
    # Construction
    # =========================================================================
    def _styles(self):
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", font=Theme.font(10), background=Theme.CARD)
        style.configure("TButton", padding=(14, 7), background="#e9edf5", foreground=Theme.INK,
                        borderwidth=0)
        style.map("TButton", background=[("active", "#dfe5f0"), ("disabled", "#f1f3f5")],
                  foreground=[("disabled", "#adb5bd")])
        for name, color, active in (("Accent", Theme.ACCENT, Theme.ACCENT_DARK),
                                    ("Danger", Theme.BAD, "#c92a2a")):
            style.configure(name + ".TButton", background=color, foreground="white",
                            font=Theme.font(11, "bold"), padding=(18, 9))
            style.map(name + ".TButton", background=[("disabled", "#ced4da"), ("active", active)],
                      foreground=[("disabled", "#f8f9fa")])
        style.configure("Treeview", rowheight=30, font=Theme.font(11), background=Theme.CARD,
                        fieldbackground=Theme.CARD, borderwidth=0)
        style.configure("Treeview.Heading", font=Theme.font(10, "bold"), background="#eef1f6",
                        borderwidth=0)
        style.map("Treeview", background=[("selected", "#dbe4ff")], foreground=[("selected", Theme.INK)])
        style.configure("Game.Horizontal.TProgressbar", thickness=10, background=Theme.ACCENT,
                        troughcolor=Theme.LINE, borderwidth=0)
        style.configure("TCheckbutton", background=Theme.CARD)
        style.configure("TRadiobutton", background=Theme.CARD)

    def _header(self):
        bar = tk.Frame(self.root, bg=Theme.BG, padx=20, pady=12)
        bar.pack(fill="x")
        tk.Label(bar, text=u"Just Nao", bg=Theme.BG, fg=Theme.INK, font=Theme.font(24, "bold")).pack(side="left")
        tk.Label(bar, text=u"  NAO dances, you copy it", bg=Theme.BG, fg=Theme.MUTED,
                 font=Theme.font(12)).pack(side="left")
        self.pill = tk.Label(bar, text=u"", fg="white", font=Theme.font(11, "bold"), padx=14, pady=5)
        self.pill.pack(side="right")

    def _build_menu(self, parent):
        screen = tk.Frame(parent, bg=Theme.BG)
        screen.columnconfigure(0, weight=3)
        screen.columnconfigure(1, weight=2)
        screen.rowconfigure(0, weight=1)

        left = card(screen, padding=16)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        tk.Label(left, text=u"Choreographies", bg=Theme.CARD, fg=Theme.INK,
                 font=Theme.font(14, "bold")).pack(anchor="w", pady=(0, 8))
        cols = (("title", u"Dance", 260), ("duration", u"Length", 70),
                ("difficulty", u"Level", 90), ("best", u"Best", 80))
        self.choreo_list = ttk.Treeview(left, columns=[c[0] for c in cols], show="headings",
                                        height=9, selectmode="browse")
        for key, label, width in cols:
            self.choreo_list.heading(key, text=label)
            self.choreo_list.column(key, width=width, anchor="w" if key == "title" else "center")
        self.choreo_list.pack(fill="both", expand=True)
        self.choreo_list.bind("<<TreeviewSelect>>", self._on_select)
        self.choreo_list.bind("<Double-1>", lambda e: self.prepare())
        self.description = tk.Label(left, text=u"", bg=Theme.CARD, fg=Theme.MUTED, font=Theme.font(11),
                                    wraplength=560, justify="left", anchor="w")
        self.description.pack(fill="x", pady=(10, 10))
        row = tk.Frame(left, bg=Theme.CARD)
        row.pack(fill="x")
        self.dance_btn = ttk.Button(row, text=u"Dance", style="Accent.TButton", command=self.prepare)
        self.dance_btn.pack(side="left")
        ttk.Button(row, text=u"History", command=self.show_history).pack(side="left", padx=8)
        ttk.Button(row, text=u"Settings", command=self.open_settings).pack(side="left")
        self.menu_msg = tk.Label(left, text=u"", bg=Theme.CARD, fg=Theme.MUTED, font=Theme.font(10),
                                 wraplength=560, justify="left", anchor="w")
        self.menu_msg.pack(fill="x", pady=(8, 0))

        right = tk.Frame(screen, bg=Theme.BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        robot = card(right, padding=16)
        robot.grid(row=0, column=0, sticky="ew")
        tk.Label(robot, text=u"Robot", bg=Theme.CARD, fg=Theme.INK, font=Theme.font(14, "bold")).pack(anchor="w")
        self.robot_info = tk.Label(robot, text=u"", bg=Theme.CARD, fg=Theme.MUTED, font=Theme.font(10),
                                   justify="left", anchor="w")
        self.robot_info.pack(fill="x", pady=(4, 10))
        btns = tk.Frame(robot, bg=Theme.CARD)
        btns.pack(fill="x")
        self.wake_btn = ttk.Button(btns, text=u"Wake up", command=lambda: self._robot(self.ctrl.wake))
        self.wake_btn.pack(side="left")
        self.rest_btn = ttk.Button(btns, text=u"Rest", command=lambda: self._robot(self.ctrl.rest))
        self.rest_btn.pack(side="left", padx=8)
        self.skip_btn = ttk.Button(btns, text=u"Skip NAO's comment", command=self.skip_commentary)
        self.skip_btn.pack(side="left")

        logs = card(right, padding=10)
        logs.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        tk.Label(logs, text=u"Log (operator)", bg=Theme.CARD, fg=Theme.INK, font=Theme.font(12, "bold")).pack(anchor="w")
        self.log_text = tk.Text(logs, height=12, wrap="word", font=("Courier", 9), state="disabled",
                                relief="flat", bg="#fafbfc", fg=Theme.INK)
        self.log_text.pack(fill="both", expand=True, pady=(6, 0))
        return screen

    def _status_bar(self):
        bar = tk.Frame(self.root, bg="#e9edf5", padx=20, pady=6)
        bar.pack(fill="x", side="bottom")
        self.status_labels = {}
        for key in ("robot", "battery", "camera", "detection"):
            label = tk.Label(bar, text=u"", bg="#e9edf5", fg="#495057", font=Theme.font(10))
            label.pack(side="left", padx=(0, 26))
            self.status_labels[key] = label

    # =========================================================================
    # Navigation
    # =========================================================================
    def _show(self, name):
        if self._screen in ("prepare", "game") and self._screen != name:
            self.screens[self._screen].on_hide()
        self._screen = name
        self.screens[name].tkraise()

    def show_menu(self):
        self._fill_choreographies()
        self._show("menu")

    def show_history(self):
        self.screens["history"].on_show()
        self._show("history")

    def show_results(self, report, from_history=False):
        self.screens["results"].show(report, from_history)
        self._show("results")

    def prepare(self, choreo_id=None):
        if choreo_id is None:
            selection = self.choreo_list.selection()
            if not selection:
                self.menu_msg.configure(text=u"Pick a choreography first.", fg=Theme.BAD)
                return
            choreo_id = selection[0]
        ok, message = self.ctrl.select(choreo_id)
        if not ok:
            self.show_menu()
            self.menu_msg.configure(text=to_text(message), fg=Theme.BAD)
            return
        self.screens["prepare"].on_show(to_text(self.ctrl.status()["title"]))
        self._show("prepare")

    def launch_dance(self):
        ok, message = self.ctrl.start()
        if not ok:
            self.screens["prepare"].hint.configure(text=to_text(message), fg=Theme.BAD)
            return
        self._ignore_next_report = False
        self.screens["game"].on_show(to_text(self.ctrl.status()["title"]))
        self._show("game")

    def skip_commentary(self):
        self.ctrl.skip_commentary()

    def stop_dance(self):
        self.ctrl.stop()               # le bilan (partie interrompue) s'affichera à son arrivée

    def leave_game(self):
        if self.ctrl.status()["state"] in ("PREPARATION", "DANSE"):
            self._ignore_next_report = True    # l'utilisateur veut le menu, pas le bilan
            self.ctrl.stop()
        self.show_menu()

    def scoring_possible(self):
        if self.pipeline is None:
            return False
        st = self.pipeline.status()
        return st["camera_ok"] and st["detector_ok"]

    def open_settings(self):
        from ui.settings_dialog import SettingsDialog
        SettingsDialog(self)

    def apply_settings(self, changed_source, changed_robot=False):
        if self.pipeline is not None:
            self.pipeline.mirror = getattr(self.cfg, "CAMERA_MIRROR", True)
            self.pipeline.use_depth = getattr(self.cfg, "EVAL_DEPTH", True)
            if changed_source and self.pipeline.camera is not None:
                self.pipeline.camera.source = self.cfg.VIDEO_SOURCE
                self.pipeline.retry_camera()
        text = u"Settings saved (used from the next dance)."
        if changed_robot:
            robot = self.ctrl.robot
            if hasattr(robot, "set_address"):
                # Passerelle Choregraphe : une connexion TCP par commande, on peut changer à chaud.
                robot.set_address(self.cfg.NAO_IP, self.cfg.BRIDGE_PORT)
                text = u"Settings saved. Robot address now %s:%d." % (self.cfg.NAO_IP, self.cfg.BRIDGE_PORT)
            else:
                text = u"Settings saved. Restart the app to use the new robot address."
        self.menu_msg.configure(text=text, fg=Theme.GOOD)

    def _robot(self, action):
        ok, message = action()
        self.menu_msg.configure(text=to_text(message), fg=Theme.MUTED if ok else Theme.BAD)

    def _on_space(self, event):
        if isinstance(event.widget, (tk.Entry, ttk.Entry)):
            return
        state = self.ctrl.status()["state"]
        if state in ("PREPARATION", "DANSE"):
            self.stop_dance()
        elif self._screen == "menu":
            self.prepare()
        elif self._screen == "prepare":
            self.screens["prepare"].start_countdown()

    # =========================================================================
    # Menu
    # =========================================================================
    def _fill_choreographies(self):
        best = self.store.best_scores() if self.store is not None else {}
        selected = self.ctrl.status()["selected"]
        self.choreo_list.delete(*self.choreo_list.get_children())
        self._ids = []
        for cid, title, duration, _desc in self.ctrl.choreographies():
            choreo = self.ctrl.library[cid]
            record = best.get(cid)
            self.choreo_list.insert("", "end", iid=cid, values=(
                to_text(title), mmss(duration), to_text(getattr(choreo, "difficulty", None) or u"-"),
                u"%d" % round(record) if record is not None else u"-"))
            self._ids.append(cid)
        if selected in self._ids:
            self.choreo_list.selection_set(selected)
            self.choreo_list.see(selected)
            self._on_select()

    def _on_select(self, event=None):
        selection = self.choreo_list.selection()
        if selection:
            self.description.configure(text=to_text(self.ctrl.library[selection[0]].description))

    # =========================================================================
    # Rafraîchissement (thread Tkinter uniquement)
    # =========================================================================
    def _refresh(self):
        try:
            st = self.ctrl.status()
            text, color = STATE_LABELS.get(st["state"], (st["state"], "#868e96"))
            self.pill.configure(text=text, bg=color)
            self._update_status_bar(st)
            self._update_logs()
            if self._screen == "menu":
                self._update_menu(st)
            elif self._screen in ("prepare", "game", "results"):
                self.screens[self._screen].refresh(st)
            if st["report_seq"] != self._report_seen:
                self._report_seen = st["report_seq"]
                self._on_report()
        finally:
            if self._poll_job is not None:
                self._poll_job = self.root.after(POLL_MS, self._refresh)

    def _on_report(self):
        report = self.ctrl.last_report()
        if report is None or self._ignore_next_report:
            self._ignore_next_report = False
            return
        if self._screen != "game":
            return
        if report.get("evaluated_duration_s", 0) > 0:
            self.show_results(report)
        else:
            self.show_menu()
            text = u"Dance over (no score: the player could not be evaluated)."
            comment = report.get("nao_comment")
            if comment:
                text += u"\nNAO: " + u" ".join(to_text(line) for line in comment["lines"])
            self.menu_msg.configure(text=text, fg=Theme.MUTED)

    def _update_menu(self, st):
        state = st["state"]
        self.dance_btn.state(["!disabled"] if state in ("REPOS", "PRET") else ["disabled"])
        self.wake_btn.state(["!disabled"] if state in ("REPOS", "ERREUR") else ["disabled"])
        self.rest_btn.state(["!disabled"] if state in ("PRET", "ERREUR") else ["disabled"])
        self.skip_btn.state(["!disabled"] if st.get("speaking") else ["disabled"])
        robot = st["robot"]
        lines = [to_text(st["message"])]
        if st.get("speaking"):
            lines.append(u"NAO is talking...")
        if robot.get("posture"):
            lines.append(u"Posture: %s" % to_text(robot["posture"]))
        if robot.get("temperature") is not None:
            lines.append(u"Motors: %.0f °C" % robot["temperature"])
        self.robot_info.configure(text=u"\n".join(lines))

    def _update_status_bar(self, st):
        robot = st["robot"]
        name = to_text(robot.get("robot") or u"?")
        lost = robot.get("connected") is False
        if lost:
            name += u" (connection lost!)"
        self.status_labels["robot"].configure(text=u"Robot: " + name,
                                              fg=Theme.BAD if lost else "#495057")
        battery = robot.get("battery")
        self.status_labels["battery"].configure(
            text=u"Battery: %s" % (u"%d %%" % battery if battery is not None else u"?"))
        if self.pipeline is None:
            self.status_labels["camera"].configure(text=u"Video: unavailable")
            self.status_labels["detection"].configure(text=u"")
            return
        vs = self.pipeline.status()
        self.status_labels["camera"].configure(
            text=u"Camera: %s" % (u"on" if vs["camera_ok"] else u"unavailable"),
            fg="#495057" if vs["camera_ok"] else Theme.BAD)
        self.status_labels["detection"].configure(
            text=u"Detection: %s (%.0f fps)" % (DETECTION_LABELS.get(vs["detection"], vs["detection"]),
                                                 vs["fps"]))

    def _update_logs(self):
        self._log_seq, lines = self.ctrl.logs_since(self._log_seq)
        if not lines:
            return
        self.log_text.configure(state="normal")
        for line in lines:
            self.log_text.insert("end", to_text(line) + u"\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
