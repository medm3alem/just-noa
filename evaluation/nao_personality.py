# -*- coding: utf-8 -*-
"""
evaluation/nao_personality.py - NAO, sarcastic dance coach: the end-of-dance comment.

From the session report (the real measurements), it builds what NAO says:

    "82 points!"                      <- score announcement
    (short pause)
    "Not bad for a human. Still no match for my circuits!"   <- roast
    ["You were about 0.7 seconds behind me."]                 <- optional fact (long mode)

How a line is chosen:
1. Special cases: unevaluable session (not enough tracking) or interrupted dance.
2. Score band (configurable thresholds): poor / weak / average / good / excellent.
3. Diagnostics, ONLY from what was measured in the report:
      barely_moves     mean activity factor  < 0.6        (player hardly moved)
      out_of_frame     tracking ratio        < 0.75
      late / early     measured delay        >= 0.7 s / <= -0.25 s
      arms_wrong       both arms scored      < 55, while moving enough
      arms_asymmetric  left/right arm gap    >= 20 points
      rigid            elbows straighter than NAO's by >= 20 degrees on average
      great_sync       |delay| <= 0.35 s with a good score
   For low and average bands, the first matching negative diagnostic is used
   (more relevant than a generic joke); for good bands, a positive one.
4. Intensity: friendly / sarcastic (default) / savage. Sarcasm off -> NEUTRAL.
5. No repetition: the last lines used are remembered (and saved on disk) and
   avoided while other lines are available.

Randomness comes from an injectable `random.Random` : tests use a fixed seed.
"""
from __future__ import absolute_import, division, print_function

import io
import json
import os
import random
from collections import deque

from evaluation.roast_library import FACTS, INTENSITIES, NEUTRAL, ROASTS

DEFAULT_BANDS = [(90, "excellent"), (71, "good"), (51, "average"), (31, "weak"), (0, "poor")]
NEGATIVE_PRIORITY = ("barely_moves", "out_of_frame", "late", "early", "arms_wrong",
                     "arms_asymmetric", "rigid")
POSITIVE = ("great_sync",)
SIDES = {"bras_gauche": "left", "bras_droit": "right"}


def opt(cfg, name, default):
    return getattr(cfg, name, default) if cfg is not None else default


def diagnose(report):
    """Liste des diagnostics mesurés dans le rapport (jamais inventés)."""
    if not report.get("valid"):
        return []
    found = []
    score = report.get("score") or 0
    activity = report.get("activity")
    delay = report.get("timing_offset_s")
    tracking = report.get("tracking_ratio", 1.0)
    arms = dict((p, v) for p, v in (report.get("parts") or {}).items()
                if p in SIDES and v is not None)
    if activity is not None and activity < 0.6:
        found.append("barely_moves")
    if tracking < 0.75:
        found.append("out_of_frame")
    # Le retard n'est fiable que si le joueur a été bien suivi.
    if delay is not None and delay >= 0.7 and tracking >= 0.6:
        found.append("late")
    if delay is not None and delay <= -0.25 and tracking >= 0.75:
        found.append("early")
    if arms and max(arms.values()) < 55 and (activity is None or activity >= 0.75):
        found.append("arms_wrong")
    if len(arms) == 2 and abs(arms["bras_gauche"] - arms["bras_droit"]) >= 20:
        found.append("arms_asymmetric")
    diffs = report.get("mean_diffs") or {}
    flex = [diffs[k][0] for k in ("L_flex", "R_flex") if k in diffs and diffs[k]]
    if flex and sum(flex) / len(flex) >= 20:
        found.append("rigid")
    if delay is not None and abs(delay) <= 0.35 and score >= 75:
        found.append("great_sync")
    return found


class NaoPersonality(object):

    def __init__(self, cfg=None, rng=None, history_path=None, history_size=15):
        self.cfg = cfg
        self.rng = rng or random.Random()
        self.history_path = history_path
        self.recent = deque(maxlen=history_size)
        self._load_history()

    # --- Réglages (lus à chaque partie : la fenêtre Paramètres agit tout de suite) ---
    @property
    def enabled(self):
        return opt(self.cfg, "ROAST_ENABLED", True)

    @property
    def intensity(self):
        value = opt(self.cfg, "ROAST_INTENSITY", "sarcastic")
        return value if value in INTENSITIES else "sarcastic"

    @property
    def long_mode(self):
        return opt(self.cfg, "COMMENTARY_LENGTH", "short") == "long"

    def band(self, score):
        for threshold, name in opt(self.cfg, "ROAST_BANDS", DEFAULT_BANDS):
            if score >= threshold:
                return name
        return "poor"

    # --- Construction du commentaire ----------------------------------------------------
    def comment(self, report):
        """
        Renvoie {"lines": [...], "announce", "roast", "fact", "category", "intensity",
        "diagnostics"} : le texte que NAO dira (et que la HMI affiche).
        """
        status = report.get("status")
        valid = bool(report.get("valid"))
        score = int(round(report.get("score") or 0))
        diagnostics = diagnose(report)

        if status == "interrompue":
            category = "interrupted"
            announce = "Dance stopped." if not valid else "%d points, but you stopped early." % score
        elif not valid:
            category = "unevaluable"
            announce = "No score this time."
        else:
            band = self.band(score)
            category = self._pick_category(band, diagnostics)
            announce = self._announce(score, band)

        roast = self._pick_line(category, self.band(score) if valid else None)
        fact = (self._fact(report, diagnostics, category)
                if self.long_mode and valid and status != "interrompue" else None)
        lines = [line for line in (announce, roast, fact) if line]
        return {"lines": lines, "announce": announce, "roast": roast, "fact": fact,
                "category": category, "intensity": self.intensity if self.enabled else "off",
                "diagnostics": diagnostics}

    @staticmethod
    def _announce(score, band):
        if band == "excellent":
            return "%d points?!" % score
        if band in ("good", "average"):
            return "%d points!" % score
        return "%d points." % score

    def _pick_category(self, band, diagnostics):
        if band in ("poor", "weak", "average"):
            for d in NEGATIVE_PRIORITY:
                if d in diagnostics and self._has_fresh(d):
                    return d
        else:
            for d in POSITIVE:
                if d in diagnostics and self._has_fresh(d) and self.rng.random() < 0.5:
                    return d
        return band

    def _candidates(self, category, band):
        if not self.enabled:
            if category in ("unevaluable", "interrupted"):
                return list(NEUTRAL[category])
            key = "high" if band in ("good", "excellent") else ("mid" if band == "average" else "low")
            return list(NEUTRAL[key])
        by_intensity = ROASTS[category]
        return list(by_intensity.get(self.intensity) or by_intensity["sarcastic"])

    def _has_fresh(self, category):
        return any(line not in self.recent for line in self._candidates(category, None))

    def _pick_line(self, category, band):
        candidates = self._candidates(category, band)
        fresh = [c for c in candidates if c not in self.recent]
        line = self.rng.choice(fresh or candidates)
        self.recent.append(line)
        self._save_history()
        return line

    def _fact(self, report, diagnostics, category=None):
        delay = report.get("timing_offset_s")
        arms = dict((SIDES[p], v) for p, v in (report.get("parts") or {}).items()
                    if p in SIDES and v is not None)
        # D'abord le fait qui justifie la pique choisie, puis les autres mesures.
        if category in diagnostics:
            diagnostics = [category] + [d for d in diagnostics if d != category]
        for d in diagnostics:
            if d in ("late", "early", "out_of_frame", "barely_moves", "arms_asymmetric", "great_sync"):
                return self._fact_for(d, report, delay, arms)
        moves = report.get("moves")
        if moves and moves.get("total"):
            return FACTS["moves"].format(done=moves["reussis"], total=moves["total"])
        if arms:
            return FACTS["best_arm"].format(best=max(arms, key=arms.get))
        return None

    @staticmethod
    def _fact_for(d, report, delay, arms):
        if d in ("late", "early"):
            return FACTS[d].format(delay=abs(delay))
        if d == "out_of_frame":
            return FACTS[d].format(tracking=int(round(100 * report["tracking_ratio"])))
        if d == "arms_asymmetric":
            return FACTS[d].format(best=max(arms, key=arms.get), worst=min(arms, key=arms.get))
        return FACTS[d]

    # --- Mémoire des dernières phrases (évite les répétitions d'une partie à l'autre) ---
    def _load_history(self):
        if not self.history_path or not os.path.isfile(self.history_path):
            return
        try:
            with io.open(self.history_path, encoding="utf-8") as f:
                for line in json.load(f)[-self.recent.maxlen:]:
                    self.recent.append(line)
        except (ValueError, OSError, IOError, TypeError):
            pass

    def _save_history(self):
        if not self.history_path:
            return
        try:
            folder = os.path.dirname(self.history_path)
            if folder and not os.path.isdir(folder):
                os.makedirs(folder)
            with io.open(self.history_path, "w", encoding="utf-8") as f:
                f.write(u"%s" % json.dumps(list(self.recent)))   # ASCII : sûr en Python 2 et 3
        except (OSError, IOError):
            pass
