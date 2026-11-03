# -*- coding: utf-8 -*-
"""
app/game_session.py - Une partie : de la première image notée au bilan.

Le lien entre les trois horloges :

    image capturée à l'instant  t_img           (compat.now(), thread vision)
    t = 0 de la chorégraphie à  t_origin        (compat.now(), lecteur sync/player.py)
    -> instant de danse vu par le joueur :
       tau = (t_img - CAMERA_LATENCY) - t_origin - ROBOT_LATENCY

CAMERA_LATENCY : l'image arrive après le geste (capture + transfert) ;
ROBOT_LATENCY  : NAO (ou Choregraphe via la passerelle) bouge après l'envoi de
la commande. Les deux se règlent dans config.py. Le retard propre du joueur
(réaction humaine) est absorbé par la fenêtre de tolérance de scoring.py.

Thread-safety : add_sample() est appelé par le thread vision, snapshot() par
la HMI, finish() par le contrôleur ; tout passe par un verrou.
"""
from __future__ import absolute_import, division, print_function

import datetime
import threading

from compat import now
from evaluation.feedback import FeedbackEngine, advice_from_summary
from evaluation.scoring import ALGORITHM_VERSION, ReferenceModel, SessionScorer


class GameSession(object):

    def __init__(self, choreo, cfg, origin_fn, on_voice=None):
        """
        origin_fn() -> instant now() du t = 0 de la chorégraphie, ou None tant
        que la musique et le mouvement ne sont pas partis.
        on_voice(texte) : appelé (rarement) pour un encouragement vocal.
        """
        self.choreo = choreo
        self.cfg = cfg
        self.origin_fn = origin_fn
        self.on_voice = on_voice
        self.model = ReferenceModel(choreo, cfg)
        self.scorer = SessionScorer(self.model, cfg)
        self.feedback = FeedbackEngine(cfg)
        self.latency = getattr(cfg, "CAMERA_LATENCY", 0.08) + getattr(cfg, "ROBOT_LATENCY", 0.10)
        self.created = datetime.datetime.now()
        self._lock = threading.Lock()
        self._detection = "absent"
        self._message = (u"", "info")
        self._last_sample_t = None
        self._frames = 0
        self._report = None

    # --- Appelé par le thread vision -----------------------------------------------------
    def add_sample(self, sample_t, features, detection):
        """
        sample_t  : instant de capture de l'image (now())
        features  : PlayerFeatures (ou None si personne)
        detection : "absent" | "partiel" | "bord" | "ok"
        """
        with self._lock:
            if self._report is not None:
                return
            self._frames += 1
            self._last_sample_t = sample_t
            self._detection = detection
            origin = self.origin_fn()
            in_window = False
            if origin is not None:
                tau = sample_t - origin - self.latency
                in_window = self.model.eval_start <= tau <= self.model.eval_end
                self.scorer.add(tau, features, detected=detection != "absent")
            live = self.scorer.live() if in_window else None
            msg, level, voice = self.feedback.update(sample_t, detection, in_window, live)
            self._message = (msg, level)
        if voice and self.on_voice is not None:
            self.on_voice(voice)          # hors verrou : peut passer par le réseau

    def required_features(self):
        """Caractéristiques que le joueur doit montrer (côtés du joueur, mode en direct)."""
        with self._lock:
            return set(self.model.feature_sets[self.scorer.live_mode()])

    def live_parts(self):
        """Notes en direct par partie du corps (0..100), pour colorer le squelette."""
        with self._lock:
            return dict(self.scorer.live()["parts"]) if self.scorer.last_tau is not None else {}

    # --- Appelé par la HMI ----------------------------------------------------------------------
    def snapshot(self):
        with self._lock:
            origin = self.origin_fn()
            tau = None if origin is None else now() - origin - self.latency
            live = self.scorer.live()
            mode = live["mode"]
            stale = self._last_sample_t is None or now() - self._last_sample_t > 1.0
            in_window = tau is not None and self.model.eval_start <= tau <= self.model.eval_end
            return {
                "tau": tau,
                "in_window": in_window,
                "detection": "absent" if stale else self._detection,
                "score": live["score"] if in_window else None,
                "parts": live["parts"] if in_window else {},
                "mode": mode,
                "message": self._message[0],
                "level": self._message[1],
                "expected": self.model.expected(mode, tau) if tau is not None else None,
                "features": sorted(self.model.feature_sets[mode]),
                "eval_window": (self.model.eval_start, self.model.eval_end),
            }

    # --- Appelé par le contrôleur ----------------------------------------------------------------
    def finish(self, status):
        """
        Fige la session et renvoie le rapport complet (dict prêt pour le JSON).
        status : "terminee" (fin naturelle) ou "interrompue" (Stop, chute, erreur).
        Politique : une session interrompue est notée sur la partie dansée et
        enregistrée avec ce statut ; elle ne compte pas pour le meilleur score.
        """
        with self._lock:
            if self._report is not None:
                return self._report
            if status == "terminee":
                until = None                                  # toute la fenêtre évaluée
            else:                                             # seulement la partie dansée
                until = self.scorer.max_tau if self.scorer.max_tau is not None else self.model.eval_start
            summary = self.scorer.summary(until_tau=until)
            summary["advice"] = advice_from_summary(summary)
            self._report = {
                "format": "just_nao_session",
                "algorithm_version": ALGORITHM_VERSION,
                "date": self.created.isoformat(timespec="seconds"),
                "status": status,
                "choreography": self.choreo.id,
                "title": self.choreo.title,
                "duration_s": round(self.choreo.end, 1),
                "frames_analysed": self._frames,
                "settings": {
                    "mapping": getattr(self.cfg, "MAPPING_MODE", "auto"),
                    "tolerances": getattr(self.cfg, "SCORE_TOLERANCES", None),
                    "latency_s": round(self.latency, 3),
                    "time_window": [getattr(self.cfg, "TIME_WINDOW_LEAD", 0.3),
                                    getattr(self.cfg, "TIME_WINDOW_LAG", 0.8)],
                },
            }
            self._report.update(summary)
            return self._report

    @property
    def report(self):
        return self._report
