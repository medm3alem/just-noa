# -*- coding: utf-8 -*-
"""
ui/hmi_classic.py - Interface graphique d'origine (Python 2.7 et 3, sans jeu).

Conservée pour le mode NAOqi direct en Python 2.7 : main.py la choisit quand
Python 3 ou les dépendances du jeu ne sont pas disponibles. La HMI de jeu est ui/hmi.py.

Deux écrans dans la même fenêtre :
- MENU PRINCIPAL : liste des chorégraphies, Danser, Réveiller / Repos, journal ;
- DANSE : titre, progression, Arrêter / Rejouer / Menu, et le panneau vidéo
  (webcam ou flux annoté du groupe 2).
Une barre d'état en bas affiche en permanence l'état du robot.

Comme l'interface clavier, la HMI ne fait qu'appeler le contrôleur. Elle ne
l'attend jamais : toutes les 200 ms, `_refresh()` lit `ctrl.status()` (une
lecture de cache, sans réseau) et met l'affichage à jour. C'est le schéma
classique avec Tkinter : une boucle `after()` dans le thread principal plutôt
que des appels Tkinter depuis d'autres threads (interdits).

Raccourcis : Espace = démarrer / arrêter, Échap = menu principal,
Entrée dans la liste = danser.

Python 2 : les textes affichés sont écrits u"..." pour que les accents
passent correctement dans Tkinter.
"""
from __future__ import absolute_import, division, print_function

try:
    import Tkinter as tk
    import ttk
except ImportError:
    import tkinter as tk
    from tkinter import ttk

import config
from compat import to_text
from ui.video_panel import VideoPanel

POLL_MS = 200

STATE_LABELS = {
    "REPOS": (u"Resting", "#6b6b6b"),
    "OCCUPE": (u"Busy...", "#b07d00"),
    "PRET": (u"Ready", "#2e7d32"),
    "PREPARATION": (u"Getting ready...", "#b07d00"),
    "DANSE": (u"Dancing!", "#1565c0"),
    "ARRET": (u"Stopping...", "#b07d00"),
    "ERREUR": (u"Error", "#c62828"),
}
ACCENT = "#1565c0"
DANGER = "#c62828"


def mmss(seconds):
    seconds = int(seconds or 0)
    return u"%02d:%02d" % (seconds // 60, seconds % 60)


class HMI(object):

    def __init__(self, ctrl, video_source=None):
        self.ctrl = ctrl
        self.video_source = video_source
        self._log_seq = 0
        self._ids = []
        self._screen = None

        self.root = tk.Tk()
        self.root.title(u"Just Nao")
        self.root.geometry("1000x680")
        self.root.minsize(900, 620)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._setup_style()

        self._build_header()
        body = ttk.Frame(self.root, padding=(16, 8, 16, 8))
        body.pack(fill="both", expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.menu_screen = self._build_menu(body)
        self.dance_screen = self._build_dance(body)
        self._build_status_bar()

        self.root.bind("<space>", self._on_space)
        self.root.bind("<Escape>", lambda e: self.go_menu())
        self.show_menu()
        self.root.after(POLL_MS, self._refresh)

    def run(self):
        self.root.mainloop()

    def close(self):
        if getattr(self, "video", None) is not None:
            self.video.stop()
        self.root.destroy()    # main.py appelle ensuite ctrl.shutdown()

    # =========================================================================
    # Construction de l'interface
    # =========================================================================
    def _setup_style(self):
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")       # rendu identique sous Windows et Linux
        style.configure(".", font=("Helvetica", 11))
        style.configure("Title.TLabel", font=("Helvetica", 20, "bold"))
        style.configure("Big.TLabel", font=("Helvetica", 26, "bold"))
        style.configure("Muted.TLabel", foreground="#666666")
        style.configure("Status.TLabel", font=("Helvetica", 10), foreground="#333333")
        style.configure("TButton", padding=(12, 6))
        for name, color in (("Primary", ACCENT), ("Danger", DANGER)):
            style.configure(name + ".TButton", foreground="white", background=color,
                            font=("Helvetica", 12, "bold"), padding=(16, 10))
            style.map(name + ".TButton",
                      background=[("disabled", "#bdbdbd"), ("active", color)],
                      foreground=[("disabled", "#f5f5f5")])
        style.configure("Horizontal.TProgressbar", thickness=14)

    def _build_header(self):
        bar = ttk.Frame(self.root, padding=(16, 12, 16, 4))
        bar.pack(fill="x")
        ttk.Label(bar, text=u"Just Nao", style="Title.TLabel").pack(side="left")
        ttk.Label(bar, text=u"   NAO dances, you copy it", style="Muted.TLabel").pack(side="left")
        self.state_pill = tk.Label(bar, text="", fg="white", font=("Helvetica", 11, "bold"),
                                   padx=12, pady=4)
        self.state_pill.pack(side="right")

    def _build_menu(self, parent):
        screen = ttk.Frame(parent)
        screen.grid(row=0, column=0, sticky="nsew")
        screen.columnconfigure(0, weight=3)
        screen.columnconfigure(1, weight=2)
        screen.rowconfigure(0, weight=1)

        # --- Chorégraphies --------------------------------------------------------
        left = ttk.LabelFrame(screen, text=u" Choreographies ", padding=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        self.listbox = tk.Listbox(left, font=("Helvetica", 13), activestyle="none",
                                  selectbackground=ACCENT, height=8, exportselection=False)
        self.listbox.grid(row=0, column=0, sticky="nsew")
        for cid, title, duration, _desc in self.ctrl.choreographies():
            self._ids.append(cid)
            self.listbox.insert("end", u"  %s   (%s)" % (to_text(title), mmss(duration)))
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        self.listbox.bind("<Return>", lambda e: self.dance())
        self.listbox.bind("<Double-Button-1>", lambda e: self.dance())

        self.description = ttk.Label(left, text="", style="Muted.TLabel", wraplength=300,
                                     justify="left")
        self.description.grid(row=1, column=0, sticky="w", pady=(10, 10))
        # Le texte se replie à la largeur réelle du cadre (qui dépend de la fenêtre)
        left.bind("<Configure>", lambda e: self.description.configure(wraplength=e.width - 30))
        row = ttk.Frame(left)
        row.grid(row=2, column=0, sticky="ew")
        self.btn_dance = ttk.Button(row, text=u"Dance", style="Primary.TButton",
                                    command=self.dance)
        self.btn_dance.pack(side="left")
        self.menu_feedback = ttk.Label(row, text="", style="Muted.TLabel", wraplength=220)
        self.menu_feedback.pack(side="left", padx=12)

        # --- Robot et journal -----------------------------------------------------------
        right = ttk.Frame(screen)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        robot_box = ttk.LabelFrame(right, text=u" Robot ", padding=12)
        robot_box.grid(row=0, column=0, sticky="ew")
        self.btn_wake = ttk.Button(robot_box, text=u"Wake up (stand)", command=self._wake)
        self.btn_wake.pack(side="left")
        self.btn_rest = ttk.Button(robot_box, text=u"Rest", command=self._rest)
        self.btn_rest.pack(side="left", padx=8)

        log_box = ttk.LabelFrame(right, text=u" Log (operator) ", padding=8)
        log_box.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        log_box.rowconfigure(0, weight=1)
        log_box.columnconfigure(0, weight=1)
        self.log_text = tk.Text(log_box, height=12, wrap="word", font=("Courier", 9),
                                state="disabled", relief="flat", background="#fafafa")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_box, command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)

        # Sélection initiale = chorégraphie déjà choisie par le contrôleur
        selected = self.ctrl.status()["selected"]
        if selected in self._ids:
            index = self._ids.index(selected)
            self.listbox.selection_set(index)
            self.listbox.activate(index)
            self._on_select()
        return screen

    def _build_dance(self, parent):
        screen = ttk.Frame(parent)
        screen.grid(row=0, column=0, sticky="nsew")
        screen.columnconfigure(1, weight=1)

        self.dance_title = ttk.Label(screen, text="", style="Big.TLabel")
        self.dance_title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        video_box = ttk.Frame(screen)
        video_box.grid(row=1, column=0, sticky="nw")
        self.video = VideoPanel(video_box, self.video_source, config.VIDEO_SIZE, config.VIDEO_FPS)
        self.video.pack()
        ttk.Label(video_box, text=u"You (webcam / video stream)",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 0))

        side = ttk.Frame(screen, padding=(20, 0, 0, 0))
        side.grid(row=1, column=1, sticky="nsew")
        side.columnconfigure(0, weight=1)
        self.dance_state = ttk.Label(side, text="", font=("Helvetica", 16, "bold"))
        self.dance_state.grid(row=0, column=0, sticky="w")
        self.dance_message = ttk.Label(side, text="", style="Muted.TLabel", wraplength=360)
        self.dance_message.grid(row=1, column=0, sticky="w", pady=(2, 16))
        self.progress = ttk.Progressbar(side, maximum=1000, style="Horizontal.TProgressbar")
        self.progress.grid(row=2, column=0, sticky="ew")
        self.time_label = ttk.Label(side, text=u"00:00 / 00:00", style="Muted.TLabel")
        self.time_label.grid(row=3, column=0, sticky="e", pady=(4, 20))

        self.btn_stop = ttk.Button(side, text=u"Stop", style="Danger.TButton",
                                   command=self._stop)
        self.btn_stop.grid(row=4, column=0, sticky="ew")
        self.btn_replay = ttk.Button(side, text=u"Replay", style="Primary.TButton",
                                     command=self._start)
        self.btn_replay.grid(row=5, column=0, sticky="ew", pady=8)
        ttk.Button(side, text=u"Main menu", command=self.go_menu).grid(
            row=6, column=0, sticky="ew")
        ttk.Label(side, text=u"Space: start / stop     Esc: menu",
                  style="Muted.TLabel").grid(row=7, column=0, sticky="w", pady=(16, 0))
        return screen

    def _build_status_bar(self):
        bar = tk.Frame(self.root, bg="#eceff1", padx=16, pady=6)
        bar.pack(fill="x", side="bottom")
        self.status_labels = {}
        for key in ("robot", "battery", "posture", "temperature"):
            label = tk.Label(bar, text="", bg="#eceff1", fg="#333333", font=("Helvetica", 10))
            label.pack(side="left", padx=(0, 24))
            self.status_labels[key] = label

    # =========================================================================
    # Navigation et actions
    # =========================================================================
    def show_menu(self):
        self._screen = "menu"
        self.menu_feedback.configure(text="")
        self.menu_screen.tkraise()

    def show_dance(self):
        self._screen = "dance"
        self.dance_screen.tkraise()

    def go_menu(self):
        if self.ctrl.status()["state"] in ("PREPARATION", "DANSE"):
            self.ctrl.stop()
        self.show_menu()

    def dance(self):
        selection = self.listbox.curselection()
        if not selection:
            self.menu_feedback.configure(text=u"Pick a choreography first")
            return
        ok, message = self.ctrl.select(self._ids[int(selection[0])])
        if ok:
            ok, message = self.ctrl.start()
        self.menu_feedback.configure(text=to_text(message))
        if ok:
            self.show_dance()

    def _start(self):
        ok, message = self.ctrl.start()
        self.dance_message.configure(text=to_text(message))

    def _stop(self):
        ok, message = self.ctrl.stop()
        self.dance_message.configure(text=to_text(message))

    def _wake(self):
        self.menu_feedback.configure(text=to_text(self.ctrl.wake()[1]))

    def _rest(self):
        self.menu_feedback.configure(text=to_text(self.ctrl.rest()[1]))

    def _on_space(self, event):
        state = self.ctrl.status()["state"]
        if state in ("PREPARATION", "DANSE"):
            self._stop()
        elif self._screen == "dance":
            self._start()
        else:
            self.dance()

    def _on_select(self, event=None):
        selection = self.listbox.curselection()
        if not selection:
            return
        cid = self._ids[int(selection[0])]
        for item_id, _title, _duration, description in self.ctrl.choreographies():
            if item_id == cid:
                self.description.configure(text=to_text(description))

    # =========================================================================
    # Rafraîchissement périodique (thread principal uniquement)
    # =========================================================================
    def _refresh(self):
        try:
            st = self.ctrl.status()
            self._update_header(st)
            self._update_buttons(st["state"])
            self._update_dance(st)
            self._update_status_bar(st["robot"])
            self._update_logs()
        finally:
            self.root.after(POLL_MS, self._refresh)

    def _update_header(self, st):
        text, color = STATE_LABELS.get(st["state"], (st["state"], "#6b6b6b"))
        self.state_pill.configure(text=text, bg=color)

    def _update_buttons(self, state):
        def enable(button, condition):
            button.state(["!disabled"] if condition else ["disabled"])
        enable(self.btn_dance, state in ("REPOS", "PRET"))
        enable(self.btn_replay, state in ("REPOS", "PRET"))
        enable(self.btn_stop, state in ("PREPARATION", "DANSE"))
        enable(self.btn_wake, state in ("REPOS", "ERREUR"))
        enable(self.btn_rest, state in ("PRET", "ERREUR"))

    def _update_dance(self, st):
        self.dance_title.configure(text=to_text(st["title"] or u""))
        text, color = STATE_LABELS.get(st["state"], (st["state"], "#333333"))
        if st["state"] == "PRET" and st["message"] == "Dance finished":
            text = u"Finished! Well done"
        self.dance_state.configure(text=text, foreground=color)
        self.dance_message.configure(text=to_text(st["message"]))
        duration = st["duration"] or 0.0
        elapsed = st["elapsed"] if st["state"] in ("DANSE", "ARRET") else 0.0
        self.progress["value"] = int(1000 * elapsed / duration) if duration else 0
        self.time_label.configure(text=u"%s / %s" % (mmss(elapsed), mmss(duration)))

    def _update_status_bar(self, robot):
        def fmt(value, pattern, unknown=u"?"):
            return pattern % value if value is not None else unknown
        connected = robot.get("connected")
        name = to_text(robot.get("robot") or u"?")
        if connected is False:
            name += u"  (connection lost!)"
        elif robot.get("backend"):
            name += u"  (%s)" % to_text(robot["backend"])
        self.status_labels["robot"].configure(text=u"Robot: " + name)
        self.status_labels["battery"].configure(
            text=u"Battery: " + fmt(robot.get("battery"), u"%d %%"))
        self.status_labels["posture"].configure(
            text=u"Posture: " + to_text(robot.get("posture") or u"?"))
        temp = robot.get("temperature")
        hot = temp is not None and temp >= config.TEMPERATURE_WARN
        self.status_labels["temperature"].configure(
            text=u"Moteurs : " + fmt(temp, u"%.0f °C"), fg=DANGER if hot else "#333333")

    def _update_logs(self):
        self._log_seq, lines = self.ctrl.logs_since(self._log_seq)
        if not lines:
            return
        self.log_text.configure(state="normal")
        for line in lines:
            self.log_text.insert("end", to_text(line) + u"\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
