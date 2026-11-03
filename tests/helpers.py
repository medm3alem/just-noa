# -*- coding: utf-8 -*-
"""Outils communs aux tests : chorégraphies de test et partie simulée complète."""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config  # noqa: E402
from app.game_session import GameSession  # noqa: E402
from choreography.choreography import Choreography  # noqa: E402
from vision.pose_features import extract_features  # noqa: E402
from vision.synthetic import SyntheticPlayer  # noqa: E402

LIBRARY = os.path.join(ROOT, "choreography", "library")


FIXTURES = os.path.join(ROOT, "tests", "fixtures")


def library_choreo(name):
    return Choreography(os.path.join(LIBRARY, name))


def fixture_choreo(name):
    """Chorégraphies figées pour les tests (ex. nao_party_v1 : le 1er test Choregraphe de Med)."""
    return Choreography(os.path.join(FIXTURES, name))


def make_choreo(names, times, keys, meta=None):
    """Crée une chorégraphie temporaire (dossier meta.json + motion.json)."""
    folder = tempfile.mkdtemp(prefix="jn_test_")
    base = {"title": "Test", "audio": None, "countdown": False}
    base.update(meta or {})
    with open(os.path.join(folder, "meta.json"), "w") as f:
        json.dump(base, f)
    with open(os.path.join(folder, "motion.json"), "w") as f:
        json.dump({"names": names, "times": times, "keys": keys}, f)
    return Choreography(folder)


def swing_choreo(seconds, first=0.6, step=0.8, meta=None):
    """
    Bras qui s'ouvrent et se referment SUR LE CÔTÉ, symétriques, pendant `seconds` s.
    Depuis la chute de NAO (2026-11-02), toute chorégraphie passe le contrôle
    d'équilibre : les anciens bras "haut / bas ensemble par devant" toutes les 0,8 s
    seraient refusés. Les mouvements de côté symétriques s'équilibrent.
    """
    times, t = [], first
    while t < seconds:
        times.append(round(t, 2))
        t += step
    out = [1.15 if i % 2 == 0 else 0.2 for i in range(len(times))]
    names = ["LShoulderPitch", "RShoulderPitch", "LShoulderRoll", "RShoulderRoll"]
    keys = [[1.45] * len(times), [1.45] * len(times), out, [-v for v in out]]
    return make_choreo(names, [list(times) for _ in names], keys, meta)


def play_session(choreo, fps=15.0, status="terminee", stop_at=None, cfg=config, **player_kw):
    """
    Joue une partie entière avec un joueur simulé et renvoie le rapport.
    L'horloge est simulée : tau = instant de danse, images toutes les 1/fps s.
    """
    origin = 1000.0
    session = GameSession(choreo, cfg, origin_fn=lambda: origin)
    player = SyntheticPlayer(session.model, **player_kw)
    tau, end = 0.0, choreo.end if stop_at is None else stop_at
    while tau < end:
        t_capture = origin + tau + session.latency
        sample = player.sample(t_capture, tau)
        feats = extract_features(sample) if sample is not None else None
        detection = "absent" if sample is None else ("ok" if feats.valid else "partiel")
        session.add_sample(t_capture, feats, detection)
        tau += 1.0 / fps
    return session.finish(status)
