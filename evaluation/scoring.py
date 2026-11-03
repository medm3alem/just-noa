# -*- coding: utf-8 -*-
"""
evaluation/scoring.py - Du "joueur à l'instant t" au score de toute la danse.

Trois étages :

1. ReferenceModel : pré-calcule, toutes les 50 ms de la danse, ce que le joueur
   doit faire (pose de NAO -> représentation commune -> côtés du joueur), pour
   chaque mode de correspondance (miroir / même côté).

2. Comparaison avec tolérance temporelle (SessionScorer.add) :
   un humain réagit APRÈS le robot. La pose du joueur à l'instant tau est
   comparée aux poses attendues entre tau - LEAD et tau + LAG ; on garde la
   meilleure, pénalisée si le décalage dépasse une zone libre :
       pénalité(d) = 1                      si |d| <= TIME_FREE
                   = 1 - MAX_PEN * (|d| - FREE) / (bord - FREE)   sinon
   Un mouvement très en retard n'obtient donc jamais la note maximale.

   Facteur d'activité : sur une fenêtre de 2 s, si NAO bouge nettement mais
   que le joueur reste figé, la note est multipliée par un facteur < 1
   (minimum ACTIVITY_FLOOR). Un joueur immobile ne peut pas obtenir un bon score
   simplement parce que sa pose ressemble par hasard à celle du robot.

3. Agrégation par intervalles de 0,5 s sur toute la fenêtre évaluée :
   - intervalle "suivi" s'il contient au moins une pose notée ;
   - performance = moyenne des intervalles suivis (qualité quand on te voit) ;
   - taux de suivi = intervalles suivis / intervalles totaux ;
   - score final = performance x min(1, taux de suivi / COVERAGE_FREE)
     -> être hors champ coûte des points, mais on tolère 10 % de pertes ;
   - session "non évaluable" si le taux de suivi < MIN_TRACKING.
   Les instants non détectés ne sont jamais comptés comme des erreurs à 0 :
   ils baissent la couverture, et c'est elle qui pèse sur le score final.

Le mode "auto" évalue en parallèle miroir et même côté ; le plus favorable sur
la session est retenu (et en direct, le plus favorable sur les dernières secondes).
"""
from __future__ import absolute_import, division, print_function

import math
from collections import deque

from choreography.reference_pose import ReferenceTimeline
from evaluation.comparator import Comparator, vector_spread
from evaluation.pose_mapping import (PARTS, evaluated_features, expected_player_features,
                                     map_feature_names, nao_features)

ALGORITHM_VERSION = "1.0"
DEFAULT_CATEGORIES = [(90, u"Excellent"), (75, u"Great"), (55, u"Good"),
                      (35, u"Needs work"), (0, u"Try again")]


def opt(cfg, name, default):
    return getattr(cfg, name, default) if cfg is not None else default


def category_for(score, categories=DEFAULT_CATEGORIES):
    for threshold, label in categories:
        if score >= threshold:
            return label
    return categories[-1][1]


# =============================================================================
class ReferenceModel(object):

    def __init__(self, choreo, cfg=None, dt=0.05):
        self.choreo = choreo
        self.dt = dt
        self.timeline = ReferenceTimeline(choreo, opt(cfg, "REFERENCE_DEFAULT_POSE", None))
        mode = opt(cfg, "MAPPING_MODE", "auto")
        self.modes = ["miroir", "meme_cote"] if mode == "auto" else [mode]
        nao_set = evaluated_features(self.timeline)
        self.feature_sets = dict((m, map_feature_names(nao_set, m)) for m in self.modes)

        scoring = getattr(choreo, "scoring", None) or {}
        first, last = self.timeline.first_key_time, self.timeline.last_key_time
        self.eval_start = float(scoring.get("start", max(0.0, first - 1.0)))
        self.eval_end = float(scoring.get("end", min(choreo.end, last + 0.5)))
        self.part_weights = scoring.get("weights")
        # Mouvements du bilan : ceux nommés dans meta.json (chorégraphies composées),
        # sinon découpage automatique à partir des keyframes.
        named = getattr(choreo, "moves", None) or []
        if named:
            self.moves = [(m["start"], m["end"]) for m in named]
            self.move_names = [m.get("name") or None for m in named]
        else:
            self.moves = self.timeline.move_segments()
            self.move_names = [None] * len(self.moves)

        n = int(math.ceil(choreo.end / dt)) + 2
        self.frames = dict((m, []) for m in self.modes)
        for k in range(n):
            nao = nao_features(self.timeline.pose_at(k * dt))
            for m in self.modes:
                self.frames[m].append(expected_player_features(nao, m))

    def expected(self, mode, tau):
        frames = self.frames[mode]
        k = int(round(tau / self.dt))
        return frames[min(max(k, 0), len(frames) - 1)]

    @property
    def evaluable(self):
        return any(self.feature_sets[m] for m in self.modes)


# =============================================================================
class _ModeState(object):
    """Accumulateurs d'un mode de correspondance."""

    def __init__(self, n_bins):
        self.bins = [[] for _ in range(n_bins)]
        self.part_bins = [dict() for _ in range(n_bins)]
        self.history = deque()          # (tau, valeurs joueur, valeurs attendues)
        self.live = None
        self.live_parts = {}
        # Courbes "note selon le décalage" : session entière et 4 dernières secondes
        self.curve_sum = None
        self.curve_n = 0
        self.recent_curves = deque()
        self.activity_sum = 0.0
        self.activity_n = 0
        self.diff_sums = {}
        self.diff_n = {}
        self.last_match = None
        self.last_factor = 1.0
        self.frames_scored = 0


class SessionScorer(object):

    def __init__(self, model, cfg=None):
        self.model = model
        self.cfg = cfg
        self.bin_size = opt(cfg, "SCORE_BIN", 0.5)
        span = max(0.0, model.eval_end - model.eval_start)
        self.n_bins = max(1, int(math.ceil(span / self.bin_size)))
        self.comparator = Comparator(
            tolerances=opt(cfg, "SCORE_TOLERANCES", None),
            feature_weights=opt(cfg, "FEATURE_WEIGHTS", None),
            part_weights=model.part_weights or opt(cfg, "PART_WEIGHTS", None),
            use_depth=opt(cfg, "EVAL_DEPTH", True))
        self.lag = opt(cfg, "TIME_WINDOW_LAG", 1.0)
        self.lead = opt(cfg, "TIME_WINDOW_LEAD", 0.3)
        self.free_late = opt(cfg, "TIME_FREE_LATE", 0.4)
        self.free_early = opt(cfg, "TIME_FREE_EARLY", 0.15)
        self.flex = opt(cfg, "TIME_FLEX", 0.15)
        self.max_pen = opt(cfg, "TIME_MAX_PENALTY", 0.3)
        self.act_window = opt(cfg, "ACTIVITY_WINDOW", 2.0)
        self.act_floor = opt(cfg, "ACTIVITY_FLOOR", 0.25)
        self.act_ratio = opt(cfg, "ACTIVITY_RATIO", 0.5)
        self.act_ref_min = opt(cfg, "ACTIVITY_REF_MIN", 25.0)
        self.act_noise = opt(cfg, "ACTIVITY_NOISE", 6.0)
        self.live_tau = opt(cfg, "LIVE_SMOOTHING", 1.0)
        self.states = dict((m, _ModeState(self.n_bins)) for m in model.modes)
        # Suivi commun : pour chaque intervalle, poses vues / détectées / partielles
        self.seen = [0] * self.n_bins
        self.detected = [0] * self.n_bins
        self.partial = [0] * self.n_bins
        self.max_tau = None
        self.last_tau = None
        self._depth_votes = [0, 0]
        self.delta_list = self._deltas()

    # --- Pénalité temporelle --------------------------------------------------------------
    def time_penalty(self, delta):
        # Zone libre asymétrique : réagir 0,4 s après NAO est normal (on découvre
        # le mouvement en le voyant) ; être en avance de plus de 0,15 s ne l'est pas.
        free, edge = (self.free_late, self.lag) if delta >= 0 else (self.free_early, self.lead)
        a = abs(delta)
        if a <= free:
            return 1.0
        if edge <= free:
            return 1.0 - self.max_pen
        return 1.0 - self.max_pen * min(1.0, (a - free) / (edge - free))

    def _deltas(self):
        # Triés du plus petit décalage au plus grand : à note égale (pose tenue),
        # on retient le décalage le plus faible, pas le premier rencontré.
        dt = self.model.dt
        steps_lag, steps_lead = int(round(self.lag / dt)), int(round(self.lead / dt))
        return sorted((k * dt for k in range(-steps_lead, steps_lag + 1)), key=abs)

    # --- Ajout d'une pose -------------------------------------------------------------------
    def add(self, tau, player, detected=True):
        """
        tau : instant de la chorégraphie vu par le joueur ; player : PlayerFeatures.
        Renvoie le mode affiché en direct (ou None hors fenêtre d'évaluation).
        """
        m = self.model
        self.last_tau = tau
        if tau < m.eval_start or tau > m.eval_end:
            return None
        self.max_tau = tau if self.max_tau is None else max(self.max_tau, tau)
        b = min(self.n_bins - 1, int((tau - m.eval_start) / self.bin_size))
        self.seen[b] += 1
        if detected:
            self.detected[b] += 1
        if player is not None:
            self._depth_votes[1 if player.has_depth else 0] += 1

        for mode, st in self.states.items():
            feats = m.feature_sets[mode]
            best, best_delta, best_value = None, 0.0, -1.0
            curve, matches = None, None
            if detected and player is not None and player.valid:
                curve, matches = [], []
                for delta in self.delta_list:
                    ref_tau = tau - delta
                    match = None
                    if ref_tau >= 0:
                        match = self.comparator.compare(m.expected(mode, ref_tau), player, feats)
                    if match is not None and match.overall is None:
                        match = None
                    matches.append(match)
                    curve.append(match.overall if match is not None else 0.0)
                # Retard habituel du joueur (corrélation sur 4 s, image courante comprise).
                # Chaque image est notée autour de CE retard (+/- TIME_FLEX), pas au
                # meilleur décalage trouvé par hasard : un joueur constamment en retard
                # ne peut pas "récupérer" la note pleine pendant les poses tenues.
                usual = self._usual_delay(st, curve)
                for delta, match in zip(self.delta_list, matches):
                    if match is None or (usual is not None and abs(delta - usual) > self.flex + 1e-9):
                        continue
                    value = match.overall * self.time_penalty(delta)
                    if value > best_value:
                        best, best_delta, best_value = match, delta, value
            st.last_match = best
            if best is None:
                if mode == m.modes[0] and detected:
                    self.partial[b] += 1
                continue
            factor = self._activity(st, tau, player, m.expected(mode, tau - best_delta), feats)
            score = best_value * factor
            st.bins[b].append(score)
            for part, value in best.parts.items():
                if value is not None:
                    st.part_bins[b].setdefault(part, []).append(value * factor)
            self._record_curve(st, tau, curve)
            st.frames_scored += 1
            st.activity_sum += factor
            st.activity_n += 1
            for name, d in best.diffs.items():
                if isinstance(d, tuple):
                    acc = st.diff_sums.setdefault(name, [0.0, 0.0, 0.0])
                    for i in range(3):
                        acc[i] += d[i]
                else:
                    acc = st.diff_sums.setdefault(name, [0.0])
                    acc[0] += d
                st.diff_n[name] = st.diff_n.get(name, 0) + 1
            self._update_live(st, score * 100.0, best, factor)
        return self.live_mode()

    # --- Retard du joueur ---------------------------------------------------------------------
    # Image par image, le meilleur décalage est ambigu : quand NAO tient une pose,
    # tous les décalages se valent. On cumule donc la note obtenue pour CHAQUE
    # décalage sur plusieurs secondes (corrélation) : le pic donne le retard réel.
    @staticmethod
    def _informative(curve):
        # Courbe plate (NAO tient une pose sur toute la fenêtre) : n'apprend rien
        # sur le retard ; seules les images pendant un mouvement comptent.
        return max(curve) - min(curve) >= 0.1

    def _record_curve(self, st, tau, curve):
        if not self._informative(curve):
            return
        if st.curve_sum is None:
            st.curve_sum = [0.0] * len(curve)
        for i, v in enumerate(curve):
            st.curve_sum[i] += v
        st.curve_n += 1
        st.recent_curves.append((tau, curve))
        while st.recent_curves and tau - st.recent_curves[0][0] > 4.0:
            st.recent_curves.popleft()

    def _usual_delay(self, st, curve):
        recent = [c for _t, c in st.recent_curves]
        if self._informative(curve):
            recent.append(curve)
        if len(recent) < 5:                     # pas encore assez de mouvements observés
            return None
        sums = [sum(c[i] for c in recent) for i in range(len(curve))]
        return self._peak_delay(sums, len(recent))

    def _peak_delay(self, curve_sum, n):
        if not curve_sum or n < 5:
            return None
        best = max(curve_sum)
        mean = sum(curve_sum) / len(curve_sum)
        if (best - mean) / n < 0.01:          # courbe plate : décalage non mesurable
            return None
        # Gestes lents (danses "équilibre" de 2026-11) : la note est parfaite sur tout
        # un plateau de décalages autour du vrai retard. On prend le MILIEU du plateau
        # qui contient le plus petit |d| à la note maximale (avant : son bord, ce qui
        # sous-estimait le retard de 0,05 à 0,1 s).
        tol = 1e-6 * max(1, n)
        by_delta = sorted(range(len(curve_sum)), key=lambda i: self.delta_list[i])
        pos = by_delta.index(curve_sum.index(best))      # à égalité : le plus petit |d|
        lo = hi = pos
        while lo > 0 and curve_sum[by_delta[lo - 1]] >= best - tol:
            lo -= 1
        while hi < len(by_delta) - 1 and curve_sum[by_delta[hi + 1]] >= best - tol:
            hi += 1
        middle = (self.delta_list[by_delta[lo]] + self.delta_list[by_delta[hi]]) / 2.0
        return round(middle, 2)

    def _activity(self, st, tau, player, expected, feats):
        st.history.append((tau, dict(player.values), expected))
        while st.history and tau - st.history[0][0] > self.act_window:
            st.history.popleft()
        if len(st.history) < 4 or tau - st.history[0][0] < 0.6 * self.act_window:
            st.last_factor = 1.0
            return 1.0
        ref_spread = pl_spread = 0.0
        n = 0
        for name in feats:
            ref_vals = [h[2][name] for h in st.history if name in h[2]]
            pl_vals = [h[1][name] for h in st.history if name in h[1]]
            if len(pl_vals) < 3:
                continue
            n += 1
            if isinstance(ref_vals[0], tuple):
                ref_spread += vector_spread(ref_vals)
                pl_spread += vector_spread(pl_vals)
            else:
                ref_spread += max(ref_vals) - min(ref_vals)
                pl_spread += max(pl_vals) - min(pl_vals)
        noise = self.act_noise * n            # tremblement normal de la détection
        if n == 0 or ref_spread - noise < self.act_ref_min:
            factor = 1.0                      # NAO tient une pose : rester immobile est juste
        else:
            moved = max(0.0, pl_spread - noise)
            factor = max(self.act_floor, min(1.0, moved / (self.act_ratio * (ref_spread - noise))))
        st.last_factor = factor
        return factor

    def _update_live(self, st, score, match, factor):
        # Moyenne exponentielle : réagit en ~1 s sans clignoter à chaque image.
        alpha = 1.0 - math.exp(-1.0 / max(1.0, 15.0 * self.live_tau))
        st.live = score if st.live is None else st.live + alpha * (score - st.live)
        for part, value in match.parts.items():
            if value is None:
                continue
            v = value * factor * 100.0
            old = st.live_parts.get(part)
            st.live_parts[part] = v if old is None else old + alpha * (v - old)

    # --- Lecture en direct ----------------------------------------------------------------------
    def live_mode(self):
        modes = self.model.modes
        if len(modes) == 1:
            return modes[0]
        a, b = self.states[modes[0]], self.states[modes[1]]
        if a.frames_scored < 30 or b.live is None:   # ~2 s de données avant de choisir
            return modes[0]
        return modes[0] if (a.live or 0) >= (b.live or 0) else modes[1]

    def live(self):
        mode = self.live_mode()
        st = self.states[mode]
        delay = None
        if st.recent_curves:
            sums = [sum(c[i] for _t, c in st.recent_curves) for i in range(len(self.delta_list))]
            delay = self._peak_delay(sums, len(st.recent_curves))
        return {
            "mode": mode,
            "score": st.live,
            "parts": dict(st.live_parts),
            "match": st.last_match,
            "activity": st.last_factor,
            "delay": delay,
        }

    # --- Bilan -------------------------------------------------------------------------------
    def summary(self, categories=None, until_tau=None):
        m = self.model
        categories = categories or opt(self.cfg, "SCORE_CATEGORIES", DEFAULT_CATEGORIES)
        end_tau = m.eval_end if until_tau is None else min(m.eval_end, until_tau)
        n_eval = max(0, min(self.n_bins, int(math.ceil((end_tau - m.eval_start) / self.bin_size))))
        results = dict((mode, self._mode_summary(mode, n_eval)) for mode in m.modes)
        best_mode = max(m.modes, key=lambda md: (results[md]["score"], md == m.modes[0]))
        res = results[best_mode]
        res["mapping_mode"] = best_mode
        res["mapping_scores"] = dict((md, round(r["score"], 1)) for md, r in results.items())
        res["eval_depth"] = self._depth_votes[1] >= self._depth_votes[0]
        res["eval_window"] = [round(m.eval_start, 2), round(m.eval_end, 2)]
        res["evaluated_duration_s"] = round(n_eval * self.bin_size, 1)
        min_tracking = opt(self.cfg, "MIN_TRACKING", 0.4)
        if not m.evaluable:
            res["valid"], res["invalid_reason"] = False, u"This choreography moves no body part that can be scored."
        elif n_eval * self.bin_size < opt(self.cfg, "MIN_EVAL_DURATION", 5.0):
            res["valid"], res["invalid_reason"] = False, u"The dance was too short to be scored."
        elif res["tracking_ratio"] < min_tracking:
            res["valid"], res["invalid_reason"] = False, u"The camera saw too little of you to score this dance."
        else:
            res["valid"], res["invalid_reason"] = True, None
        res["category"] = category_for(res["score"], categories) if res["valid"] else u"Not scored"
        return res

    def _mode_summary(self, mode, n_eval):
        m, st = self.model, self.states[mode]
        timeline, tracked_scores = [], []
        part_values = dict((p, []) for p in PARTS)
        for b in range(n_eval):
            center = m.eval_start + (b + 0.5) * self.bin_size
            if st.bins[b]:
                score = 100.0 * sum(st.bins[b]) / len(st.bins[b])
                tracked_scores.append(score)
                status = "ok"
                for part, vals in st.part_bins[b].items():
                    part_values[part].append(100.0 * sum(vals) / len(vals))
            else:
                score = None
                status = "partiel" if self.detected[b] else ("absent" if self.seen[b] else "non_vu")
            timeline.append({"t": round(center, 2), "score": None if score is None else round(score, 1),
                             "status": status})
        tracked = len(tracked_scores)
        tracking_ratio = tracked / n_eval if n_eval else 0.0
        performance = sum(tracked_scores) / tracked if tracked else 0.0
        coverage_free = opt(self.cfg, "COVERAGE_FREE", 0.9)
        final = performance * min(1.0, tracking_ratio / coverage_free) if coverage_free else performance
        success = opt(self.cfg, "MOVE_SUCCESS", 60.0)
        evaluated_parts = set(p for p, feats in PARTS.items()
                              if any(f in m.feature_sets[mode] for f in feats))
        parts = dict((p, round(sum(v) / len(v), 1) if v and p in evaluated_parts else None)
                     for p, v in part_values.items())
        moves = None
        if m.moves:
            details = []
            for (start, end), move_name in zip(m.moves, m.move_names):
                vals = [e["score"] for e in timeline if start <= e["t"] <= end]
                scored = [v for v in vals if v is not None]
                ok = bool(vals) and len(scored) >= 0.5 * len(vals)
                avg = sum(scored) / len(scored) if scored else None
                if start > m.eval_start + n_eval * self.bin_size:
                    continue
                details.append({"start": start, "end": end, "name": move_name,
                                "score": None if avg is None else round(avg, 1),
                                "tracked": ok, "success": bool(ok and avg is not None and avg >= success)})
            moves = {"total": len(details), "reussis": sum(1 for d in details if d["success"]),
                     "details": details}
        diffs = dict((name, [s / st.diff_n[name] for s in sums]) for name, sums in st.diff_sums.items())
        return {
            "score": round(final, 1),
            "performance": round(performance, 1),
            "tracking_ratio": round(tracking_ratio, 3),
            "correct_pose_ratio": round(sum(1 for s in tracked_scores if s >= success) / tracked, 3)
            if tracked else 0.0,
            "parts": parts,
            "timing_offset_s": self._peak_delay(st.curve_sum, st.curve_n),
            "activity": round(st.activity_sum / st.activity_n, 3) if st.activity_n else None,
            "moves": moves,
            "timeline": timeline,
            "mean_diffs": diffs,
        }
