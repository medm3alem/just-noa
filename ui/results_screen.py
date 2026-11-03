# -*- coding: utf-8 -*-
"""
ui/results_screen.py - Bilan d'une partie, et historique des parties.

ResultsScreen : score final et catégorie, résumé chiffré, courbe du score dans
le temps (zones rosées = joueur non suivi), parties du corps, carte
"NAO says" (le commentaire que NAO prononce : score + pique), conseils,
boutons Replay / Export / Main menu, et "Skip comment" tant que NAO parle.
Tout vient du rapport calculé par app/game_session.py (results/sessions/).

HistoryScreen : les dernières parties (fichiers JSON locaux), double-clic pour
revoir un bilan, export de la partie choisie ou de tout l'historique (CSV).

Textes affichés au joueur : en anglais.
"""
from __future__ import absolute_import, division, print_function

import tkinter as tk
from tkinter import ttk

from ui.widgets import BarChart, LineChart, ScoreGauge, Theme, card
from ui.game_screen import mmss

STATUS_LABELS = {"terminee": u"completed", "interrompue": u"stopped early"}
MODE_LABELS = {"miroir": u"mirror", "meme_cote": u"same side"}
INTENSITY_LABELS = {"friendly": u"friendly", "sarcastic": u"sarcastic", "savage": u"savage",
                    "off": u"sarcasm off"}


def comment_text(report):
    """Texte du commentaire de NAO tel qu'il est affiché ("" s'il n'y en a pas)."""
    comment = report.get("nao_comment") or {}
    return u"\n".join(u"“%s”" % line for line in comment.get("lines", []))


class ResultsScreen(tk.Frame):

    def __init__(self, parent, app):
        tk.Frame.__init__(self, parent, bg=Theme.BG)
        self.app = app
        self.report = None
        self.from_history = False
        self.columnconfigure(1, weight=1)

        head = tk.Frame(self, bg=Theme.BG)
        head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        self.title = tk.Label(head, text=u"", bg=Theme.BG, fg=Theme.INK, font=Theme.font(22, "bold"))
        self.title.pack(side="left")
        self.subtitle = tk.Label(head, text=u"", bg=Theme.BG, fg=Theme.MUTED, font=Theme.font(11))
        self.subtitle.pack(side="left", padx=12)
        ttk.Button(head, text=u"Main menu", command=self.app.show_menu).pack(side="right")
        self.export_btn = ttk.Button(head, text=u"Export", command=self._export)
        self.export_btn.pack(side="right", padx=8)
        self.replay_btn = ttk.Button(head, text=u"Replay", style="Accent.TButton",
                                     command=self._replay)
        self.replay_btn.pack(side="right")

        left = card(self, padding=18)
        left.grid(row=1, column=0, sticky="nsew")
        self.gauge = ScoreGauge(left, size=180)
        self.gauge.pack()
        self.category = tk.Label(left, text=u"", bg=Theme.CARD, fg=Theme.INK, font=Theme.font(18, "bold"))
        self.category.pack(pady=(0, 10))
        self.facts = tk.Frame(left, bg=Theme.CARD)
        self.facts.pack(fill="x")
        self.parts = BarChart(left, width=280, height=100)
        self.parts.pack(pady=(12, 0))

        right = tk.Frame(self, bg=Theme.BG)
        right.grid(row=1, column=1, sticky="nsew", padx=(16, 0))

        nao = card(right, padding=14)
        nao.pack(fill="x")
        nao_head = tk.Frame(nao, bg=Theme.CARD)
        nao_head.pack(fill="x")
        self.nao_title = tk.Label(nao_head, text=u"NAO says", bg=Theme.CARD, fg=Theme.INK,
                                  font=Theme.font(12, "bold"))
        self.nao_title.pack(side="left")
        self.nao_mode = tk.Label(nao_head, text=u"", bg=Theme.CARD, fg=Theme.MUTED, font=Theme.font(9))
        self.nao_mode.pack(side="left", padx=8)
        self.skip_btn = ttk.Button(nao_head, text=u"Skip comment", command=self.app.skip_commentary)
        self.skip_btn.pack(side="right")
        self.nao_text = tk.Label(nao, text=u"", bg=Theme.CARD, fg=Theme.ACCENT_DARK,
                                 font=Theme.font(13, "bold"), wraplength=600, justify="left", anchor="w")
        self.nao_text.pack(fill="x", pady=(6, 0))

        chart_card = card(right, padding=14)
        chart_card.pack(fill="x", pady=(12, 0))
        tk.Label(chart_card, text=u"Score during the dance", bg=Theme.CARD, fg=Theme.INK,
                 font=Theme.font(12, "bold")).pack(anchor="w")
        tk.Label(chart_card, text=u"pink areas: the camera could not track you", bg=Theme.CARD,
                 fg=Theme.MUTED, font=Theme.font(9)).pack(anchor="w")
        self.chart = LineChart(chart_card, width=600, height=170)
        self.chart.pack(pady=(6, 0))
        tips_card = card(right, padding=14)
        tips_card.pack(fill="both", expand=True, pady=(12, 0))
        tk.Label(tips_card, text=u"Tips", bg=Theme.CARD, fg=Theme.INK,
                 font=Theme.font(12, "bold")).pack(anchor="w")
        self.tips = tk.Frame(tips_card, bg=Theme.CARD)
        self.tips.pack(fill="both", expand=True)
        self.feedback = tk.Label(right, text=u"", bg=Theme.BG, fg=Theme.MUTED, font=Theme.font(9),
                                 anchor="w", justify="left", wraplength=600)
        self.feedback.pack(fill="x", pady=(6, 0))

    def show(self, report, from_history=False):
        self.report = report
        self.from_history = from_history
        self.feedback.configure(text=u"")
        self.title.configure(text=report.get("title", report.get("choreography", u"")))
        date = report.get("date", u"").replace("T", u" at ")[:-3]
        self.subtitle.configure(text=u"%s, dance %s" % (date, STATUS_LABELS.get(report.get("status"), u"")))
        valid = report.get("valid")
        self.gauge.show(report.get("score") if valid else None, u"final score" if valid else u"not scored")
        self.category.configure(text=report.get("category", u""),
                                fg=Theme.score_color(report.get("score")) if valid else Theme.MUTED)
        for child in self.facts.winfo_children():
            child.destroy()
        moves = report.get("moves")
        delay = report.get("timing_offset_s")
        rows = [
            (u"Scored time", u"%s" % mmss(report.get("evaluated_duration_s", 0))),
            (u"Player tracked", u"%d %% of the time" % round(100 * report.get("tracking_ratio", 0))),
            (u"Correct poses", u"%d %% of tracked time" % round(100 * report.get("correct_pose_ratio", 0))),
            (u"Moves done right", u"%d / %d" % (moves["reussis"], moves["total"]) if moves else u"-"),
            (u"Average delay", u"%.2f s" % delay if delay is not None else u"not measurable"),
            (u"Matching", MODE_LABELS.get(report.get("mapping_mode"), u"-")),
        ]
        for i, (label, value) in enumerate(rows):
            tk.Label(self.facts, text=label, bg=Theme.CARD, fg=Theme.MUTED, font=Theme.font(10),
                     anchor="w").grid(row=i, column=0, sticky="w", pady=1)
            tk.Label(self.facts, text=value, bg=Theme.CARD, fg=Theme.INK, font=Theme.font(10, "bold"),
                     anchor="e").grid(row=i, column=1, sticky="e", padx=(16, 0))
        self.parts.show(report.get("parts") or {})
        self.chart.show(report.get("timeline") or [])
        self._show_comment(report, from_history)
        for child in self.tips.winfo_children():
            child.destroy()
        for tip in report.get("advice", []):
            tk.Label(self.tips, text=u"• " + tip, bg=Theme.CARD, fg=Theme.INK, font=Theme.font(11),
                     wraplength=580, justify="left", anchor="w").pack(fill="x", pady=2)
        self.replay_btn.configure(text=u"Replay")
        self.refresh(self.app.ctrl.status())

    def _show_comment(self, report, from_history):
        comment = report.get("nao_comment")
        self.nao_title.configure(text=u"NAO said" if from_history else u"NAO says")
        if not comment:
            self.nao_text.configure(text=u"(no comment from NAO for this dance)", fg=Theme.MUTED)
            self.nao_mode.configure(text=u"")
            return
        self.nao_text.configure(text=comment_text(report), fg=Theme.ACCENT_DARK)
        mode = INTENSITY_LABELS.get(comment.get("intensity"), comment.get("intensity", u""))
        silent = not getattr(self.app.cfg, "NAO_SPEAKS", True) and not from_history
        self.nao_mode.configure(text=u"(%s%s)" % (mode, u", voice off" if silent else u""))

    def refresh(self, st):
        """Appelé toutes les 100 ms par la HMI : le bouton "Skip" ne sert que si NAO parle."""
        speaking = bool(st.get("speaking")) and not self.from_history
        self.skip_btn.state(["!disabled"] if speaking else ["disabled"])

    def _replay(self):
        if self.report is not None:
            self.app.skip_commentary()      # on rejoue : NAO arrête de commenter
            self.app.prepare(self.report.get("choreography"))

    def _export(self):
        if self.report is None or self.app.store is None:
            return
        try:
            csv_path = self.app.store.export_csv(self.report)
            json_path = self.app.store.export_json(self.report)
            self.feedback.configure(text=u"Exported:\n%s\n%s" % (csv_path, json_path), fg=Theme.GOOD)
        except (OSError, IOError) as err:
            self.feedback.configure(text=u"Export failed: %s" % err, fg=Theme.BAD)


class HistoryScreen(tk.Frame):

    COLUMNS = (("date", u"Date", 140), ("title", u"Dance", 200), ("score", u"Score", 60),
               ("category", u"Rating", 110), ("tracking", u"Tracked", 70), ("status", u"Status", 110),
               ("nao", u"NAO said", 330))

    def __init__(self, parent, app):
        tk.Frame.__init__(self, parent, bg=Theme.BG)
        self.app = app
        self.paths = {}
        head = tk.Frame(self, bg=Theme.BG)
        head.pack(fill="x", pady=(0, 12))
        tk.Label(head, text=u"Game history", bg=Theme.BG, fg=Theme.INK,
                 font=Theme.font(22, "bold")).pack(side="left")
        ttk.Button(head, text=u"Main menu", command=self.app.show_menu).pack(side="right")
        ttk.Button(head, text=u"Export all (CSV)", command=self._export_all).pack(side="right", padx=8)
        ttk.Button(head, text=u"Export selected", command=self._export_selected).pack(side="right")
        ttk.Button(head, text=u"Open results", style="Accent.TButton", command=self._open).pack(
            side="right", padx=8)
        box = card(self, padding=8)
        box.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(box, columns=[c[0] for c in self.COLUMNS], show="headings", height=18)
        for key, label, width in self.COLUMNS:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w" if key in ("date", "title", "nao") else "center")
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(box, command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-1>", lambda e: self._open())
        self.empty = tk.Label(self, text=u"", bg=Theme.BG, fg=Theme.MUTED, font=Theme.font(11),
                              wraplength=1100, justify="left")
        self.empty.pack(pady=8)

    def on_show(self):
        self.tree.delete(*self.tree.get_children())
        self.paths = {}
        sessions = self.app.store.list() if self.app.store is not None else []
        for path, rep in sessions:
            valid = rep.get("valid")
            comment = rep.get("nao_comment") or {}
            item = self.tree.insert("", "end", values=(
                rep.get("date", u"").replace("T", u" ")[:-3], rep.get("title", rep.get("choreography")),
                u"%d" % round(rep.get("score", 0)) if valid else u"-", rep.get("category", u""),
                u"%d %%" % round(100 * rep.get("tracking_ratio", 0)),
                STATUS_LABELS.get(rep.get("status"), rep.get("status")),
                u" ".join(comment.get("lines", [])[1:2]) or u"-"))
            self.paths[item] = path
        self.empty.configure(text=u"" if sessions else u"No dance saved yet.", fg=Theme.MUTED)

    def _selected_report(self):
        selection = self.tree.selection()
        if not selection:
            self.empty.configure(text=u"Select a dance in the list first.", fg=Theme.BAD)
            return None
        try:
            return self.app.store.load(self.paths[selection[0]])
        except (ValueError, OSError, IOError) as err:
            self.empty.configure(text=u"Cannot read this dance: %s" % err, fg=Theme.BAD)
            return None

    def _open(self):
        report = self._selected_report()
        if report is not None:
            self.app.show_results(report, from_history=True)

    def _export_selected(self):
        report = self._selected_report()
        if report is None:
            return
        try:
            paths = (self.app.store.export_csv(report), self.app.store.export_json(report))
            self.empty.configure(text=u"Exported:  %s\n                 %s" % paths, fg=Theme.GOOD)
        except (OSError, IOError) as err:
            self.empty.configure(text=u"Export failed: %s" % err, fg=Theme.BAD)

    def _export_all(self):
        if self.app.store is None:
            return
        try:
            path = self.app.store.export_history_csv()
            self.empty.configure(text=u"History exported: %s" % path, fg=Theme.GOOD)
        except (OSError, IOError) as err:
            self.empty.configure(text=u"Export failed: %s" % err, fg=Theme.BAD)
