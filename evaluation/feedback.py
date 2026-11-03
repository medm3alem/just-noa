# -*- coding: utf-8 -*-
"""
evaluation/feedback.py - Messages au joueur (en anglais), tous déduits des mesures.

Aucun encouragement n'est tiré au hasard : chaque message découle de l'état
de détection ou de l'évaluation, par ordre de priorité :

  1. joueur non détecté / partiellement visible / au bord de l'image ;
  2. avant le début de la partie notée : "Get ready" ;
  3. joueur figé alors que NAO bouge (facteur d'activité bas) : "Don't stop now!" ;
  4. progrès mesurés sur les dernières secondes : "Great recovery!",
     "You're getting better!" ;
  5. score très haut -> "Almost perfect!", haut -> "Nice moves!" ;
  6. retard moyen important -> "You're a little late!" ;
  7. correction ciblée sur la caractéristique la plus fausse :
     "Raise your left arm!", "Bend your right elbow!"... ;
  8. sinon "Keep going!".

Un message reste affiché au moins MESSAGE_HOLD secondes (pas de clignotement),
sauf les alertes de détection qui passent tout de suite. Les synonymes d'un
même niveau tournent dans l'ordre (variété sans hasard).

Les conseils de fin (advice_from_summary) reposent sur les moyennes de la
session : partie la plus faible et sens de l'erreur, retard moyen, temps hors
champ, manque d'amplitude.
"""
from __future__ import absolute_import, division, print_function

from collections import deque

from evaluation.pose_mapping import PART_LABELS

SIDE = {"L": u"left", "R": u"right"}
GOOD, OK, BAD, WARN, INFO = "bon", "moyen", "faible", "alerte", "info"

PRAISE_TOP = (u"Almost perfect!", u"Excellent!", u"You're on fire!")
PRAISE = (u"Nice moves!", u"That's more like it!", u"Great job!")
KEEP = (u"Keep going!", u"Don't give up!", u"Stay with NAO!")
LATE = (u"You're a little late!", u"Keep up with the beat!")


def correction_for(name, diff, flex=None):
    """
    Correction pour une caractéristique du joueur. `diff` = attendu - joueur
    dans le repère du corps (x devant, y gauche, z haut).
    """
    side = SIDE[name[0]]
    if name.endswith("_knee"):
        return u"Bend your knees more!" if diff > 0 else u"Straighten your legs a bit!"
    if name.endswith("_fore") and flex is not None and abs(flex) > 20:
        return (u"Bend your %s elbow!" if flex > 0 else u"Straighten your %s arm!") % side
    dx, dy, dz = diff
    outward = dy if name[0] == "L" else -dy          # vers l'extérieur du corps
    axis = max((abs(dz), "z"), (abs(outward), "y"), (abs(dx), "x"))[1]
    if axis == "z":
        return (u"Raise your %s arm!" if dz > 0 else u"Lower your %s arm!") % side
    if axis == "y":
        return (u"Spread your %s arm out!" if outward > 0 else u"Bring your %s arm in!") % side
    return (u"Reach forward with your %s arm!" if dx > 0 else u"Pull your %s arm back!") % side


class FeedbackEngine(object):

    def __init__(self, cfg=None):
        g = (lambda n, d: getattr(cfg, n, d)) if cfg is not None else (lambda n, d: d)
        self.hold = g("MESSAGE_HOLD", 1.2)
        self.excellent = g("FEEDBACK_EXCELLENT", 85.0)
        self.good = g("FEEDBACK_GOOD", 70.0)
        self.keep = g("FEEDBACK_KEEP", 50.0)
        self.late = g("FEEDBACK_LATE", 0.55)
        self.voice_enabled = g("VOICE_FEEDBACK", False)
        self.voice_interval = g("VOICE_MIN_INTERVAL", 12.0)
        self.message, self.level, self.since = u"", INFO, -1e9
        self._streak_start = None
        self._last_voice = -1e9
        self._history = deque()          # (instant, score en direct) des ~5 dernières secondes
        self._turn = 0

    def update(self, now, detection, in_window, live):
        """
        detection : "absent" | "partiel" | "bord" | "ok"
        live      : SessionScorer.live() ou None
        Renvoie (message, niveau, phrase_vocale_ou_None).
        """
        if live is not None and live.get("score") is not None:
            self._history.append((now, live["score"]))
            while self._history and now - self._history[0][0] > 5.0:
                self._history.popleft()
        msg, level, urgent = self._choose(now, detection, in_window, live)
        if urgent or msg == self.message or now - self.since >= self.hold:
            if msg != self.message:
                self.since = now
                self._turn += 1
            self.message, self.level = msg, level
        return self.message, self.level, self._voice(now, live, detection)

    def _pick(self, options):
        return options[self._turn % len(options)]

    def _score_ago(self, now, seconds):
        old = [s for t, s in self._history if now - t >= seconds]
        return old[-1] if old else None

    def _choose(self, now, detection, in_window, live):
        if detection == "absent":
            return u"Come back into the camera frame!", WARN, True
        if detection == "partiel":
            return u"Step back so I can see your whole upper body!", WARN, True
        if detection == "bord":
            return u"Move to the center of the frame!", WARN, False
        if not in_window:
            return u"Get ready... copy NAO!", INFO, False
        if live is None or live.get("score") is None:
            return u"Follow NAO's moves!", INFO, False
        score = live["score"]
        if live.get("activity", 1.0) < 0.5:
            return u"Don't stop now!", BAD, False
        before = self._score_ago(now, 3.0)
        if before is not None and before < 45 and score >= 70:
            return u"Great recovery!", GOOD, False
        if before is not None and score - before >= 15 and score >= 55:
            return u"You're getting better!", GOOD, False
        if score >= 92:
            return self._pick(PRAISE_TOP), GOOD, False
        if score >= self.excellent:
            return u"Excellent!", GOOD, False
        if score >= self.good:
            return self._pick(PRAISE), GOOD, False
        delay = live.get("delay")
        if delay is not None and delay > self.late:
            return self._pick(LATE), OK, False
        match = live.get("match")
        if match is not None and match.scores:
            worst = min(match.scores, key=match.scores.get)
            if match.scores[worst] < 0.6 and worst in match.diffs:
                flex = match.diffs.get(worst[0] + "_flex")
                return correction_for(worst, match.diffs[worst], flex), BAD, False
        if score >= self.keep:
            return self._pick(KEEP), OK, False
        return u"Follow NAO's moves!", BAD, False

    def _voice(self, now, live, detection):
        """Encouragement vocal rare : 4 s d'affilée au-dessus du seuil "Excellent"."""
        if not self.voice_enabled or detection != "ok" or not live or live.get("score") is None:
            self._streak_start = None
            return None
        if live["score"] >= self.excellent:
            if self._streak_start is None:
                self._streak_start = now
            if now - self._streak_start >= 4.0 and now - self._last_voice >= self.voice_interval:
                self._last_voice = now
                self._streak_start = None
                return "Great job!"
        else:
            self._streak_start = None
        return None


def advice_from_summary(summary):
    """Conseils de fin de partie (anglais), fondés sur les moyennes de la session."""
    tips = []
    if not summary.get("valid"):
        if summary.get("invalid_reason"):
            tips.append(summary["invalid_reason"])
        tips.append(u"Stand 2 to 3 m from the camera, upper body fully visible, in a well-lit room.")
        return tips
    tracking = summary.get("tracking_ratio", 1.0)
    if tracking < 0.85:
        tips.append(u"Stay inside the camera frame: you were only tracked %d%% of the time."
                    % round(100 * tracking))
    parts = dict((p, s) for p, s in (summary.get("parts") or {}).items() if s is not None)
    if len(parts) >= 1:
        weakest = min(parts, key=parts.get)
        best = max(parts.values())
        if parts[weakest] < 70 and (len(parts) == 1 or best - parts[weakest] >= 8):
            hint = _part_hint(weakest, summary.get("mean_diffs") or {})
            tips.append(u"%s: %d/100. %s" % (PART_LABELS[weakest], round(parts[weakest]), hint))
    delay = summary.get("timing_offset_s")
    if delay is not None and delay > 0.55:
        tips.append(u"You followed NAO about %.1f s late: try to anticipate the moves." % delay)
    elif delay is not None and delay < -0.15 and tracking >= 0.75:
        tips.append(u"You were a bit ahead of NAO: wait for it.")
    activity = summary.get("activity")
    if activity is not None and activity < 0.75:
        tips.append(u"Move more: make your moves as big as NAO's.")
    moves = summary.get("moves")
    if moves and moves["total"]:
        missed = [d for d in moves["details"] if d["tracked"] and not d["success"]]
        named = [d for d in missed if d.get("name")]
        if named:
            # Danse composée : on regroupe par geste ("Palms up" raté 3 fois...)
            counts = {}
            for d in named:
                counts[d["name"]] = counts.get(d["name"], 0) + 1
            worst = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:2]
            tips.append(u"Moves to practice: " + u", ".join(
                u"%s (%d time%s)" % (n, k, u"s" if k > 1 else u"") for n, k in worst) + u".")
        elif missed and len(missed) <= 3:
            tips.append(u"Moves to practice: " + u", ".join(
                u"%.0f-%.0f s" % (d["start"], d["end"]) for d in missed) + u".")
    if summary.get("score", 0) >= 90:
        tips.append(u"Outstanding! Try a harder choreography.")
    if not tips:
        tips.append(u"Nice and steady: keep it up!")
    return tips


def _part_hint(part, diffs):
    if part == "jambes":
        knees = [diffs[k][0] for k in ("L_knee", "R_knee") if k in diffs]
        if knees and sum(knees) / len(knees) > 5:
            return u"Bend your knees more when NAO goes down."
        return u"Watch NAO's knee bends closely."
    side = "L" if part == "bras_gauche" else "R"
    upper, flex = diffs.get(side + "_upper"), diffs.get(side + "_flex")
    if flex is not None and abs(flex[0]) > 20:
        return u"Your elbow was often %s." % (u"too straight" if flex[0] > 0 else u"too bent")
    if upper is not None:
        return correction_for(side + "_upper", tuple(upper)).rstrip(u"!") + u" more clearly."
    return u"Watch the position of this arm on NAO."
