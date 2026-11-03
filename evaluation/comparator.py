# -*- coding: utf-8 -*-
"""
evaluation/comparator.py - Comparer UNE pose du joueur à UNE pose attendue.

Pour chaque caractéristique valide :
  - direction d'un segment (bras, avant-bras) : erreur = angle entre la direction
    attendue et celle du joueur (degrés) ;
  - genou : erreur = écart de flexion (degrés).
L'erreur devient une note 0..1 :

      note = 1                         si erreur <= tolérance "pleine"
      note = 0                         si erreur >= tolérance "nulle"
      note décroît linéairement entre les deux

(tolérances par type dans config.SCORE_TOLERANCES). Une petite erreur ne coûte
rien : MediaPipe et la morphologie introduisent déjà ~10-15° de bruit.

Mode 2D (config.EVAL_DEPTH = False, ou fournisseur sans profondeur) : on compare
les directions projetées dans le plan de face. Une direction attendue presque
dans l'axe de la caméra (bras tendu vers l'avant) est alors peu lisible : son
poids est réduit selon la longueur de sa projection.

Les caractéristiques invalides (point masqué, hors champ) ne sont PAS notées.
Si moins de la moitié du poids attendu est mesurable, la pose est déclarée
"insuffisante" (None) : ni réussie, ni ratée.
"""
from __future__ import absolute_import, division, print_function

import math

from evaluation.pose_mapping import PARTS, angle_deg, dot, unit

DEFAULT_TOLERANCES = {"upper": (20.0, 60.0), "fore": (25.0, 70.0), "knee": (15.0, 45.0)}
DEFAULT_FEATURE_WEIGHTS = {"upper": 0.6, "fore": 0.4, "knee": 0.5}
DEFAULT_PART_WEIGHTS = {"bras_gauche": 1.0, "bras_droit": 1.0, "jambes": 0.6}


def feature_kind(name):
    return name.split("_", 1)[1]


def linear_score(error, full, zero):
    if error <= full:
        return 1.0
    if error >= zero:
        return 0.0
    return 1.0 - (error - full) / (zero - full)


def elbow_flex(upper, fore):
    """Flexion du coude (degrés) : 0 = bras tendu."""
    return angle_deg(upper, fore)


class FrameMatch(object):
    """Résultat d'une comparaison instantanée."""
    __slots__ = ("overall", "parts", "scores", "errors", "diffs", "coverage")

    def __init__(self):
        self.overall = None      # 0..1, ou None si pose insuffisante
        self.parts = {}          # partie -> 0..1 ou None
        self.scores = {}         # caractéristique -> 0..1
        self.errors = {}         # caractéristique -> degrés
        self.diffs = {}          # caractéristique -> (attendu - joueur) pour les conseils
        self.coverage = 0.0      # part du poids attendu réellement mesurée


class Comparator(object):

    def __init__(self, tolerances=None, feature_weights=None, part_weights=None,
                 use_depth=True, min_coverage=0.5):
        self.tol = dict(DEFAULT_TOLERANCES, **(tolerances or {}))
        self.fw = dict(DEFAULT_FEATURE_WEIGHTS, **(feature_weights or {}))
        self.pw = dict(DEFAULT_PART_WEIGHTS, **(part_weights or {}))
        self.use_depth = use_depth
        self.min_coverage = min_coverage

    def compare(self, expected, player, features):
        """expected : {nom: valeur attendue}, player : PlayerFeatures, features : noms notés."""
        m = FrameMatch()
        if not features:
            return m
        depth = self.use_depth and player.has_depth
        part_acc = {}
        total_w = measured_w = 0.0
        for name in features:
            kind = feature_kind(name)
            w = self.fw[kind]
            total_w += w
            if name not in player.valid or name not in expected:
                continue
            exp, got = expected[name], player.values[name]
            if kind == "knee":
                err = abs(exp - got)
                m.diffs[name] = exp - got
            else:
                if not depth:
                    proj = (0.0, exp[1], exp[2])
                    length = math.sqrt(proj[1] ** 2 + proj[2] ** 2)
                    if length < 0.2:          # direction "vers la caméra" : illisible en 2D
                        continue
                    w *= min(1.0, length / 0.5)
                    exp_v, got_v = unit(proj), unit((0.0, got[1], got[2]))
                    if got_v is None:
                        continue
                else:
                    exp_v, got_v = exp, got
                err = angle_deg(exp_v, got_v)
                m.diffs[name] = tuple(exp_v[i] - got_v[i] for i in range(3))
            score = linear_score(err, *self.tol[kind])
            m.errors[name], m.scores[name] = err, score
            measured_w += w
            part = _part_of(name)
            acc = part_acc.setdefault(part, [0.0, 0.0])
            acc[0] += w * score
            acc[1] += w

        # Flexion des coudes (pour les conseils "plie / tends le coude")
        for side in ("L", "R"):
            u, f = side + "_upper", side + "_fore"
            if u in m.scores and f in m.scores and depth:
                m.diffs[side + "_flex"] = (elbow_flex(expected[u], expected[f])
                                           - elbow_flex(player.values[u], player.values[f]))

        m.coverage = measured_w / total_w if total_w else 0.0
        for part, (s, w) in part_acc.items():
            m.parts[part] = s / w if w else None
        if m.coverage >= self.min_coverage and part_acc:
            num = sum(self.pw[p] * s for p, s in m.parts.items() if s is not None)
            den = sum(self.pw[p] for p, s in m.parts.items() if s is not None)
            m.overall = num / den if den else None
        return m


def _part_of(feature):
    for part, feats in PARTS.items():
        if feature in feats:
            return part
    raise KeyError(feature)


def vector_spread(vectors):
    """Amplitude (degrés) d'un ensemble de directions : 2 x écart max à la moyenne."""
    if len(vectors) < 2:
        return 0.0
    mean = unit(tuple(sum(v[i] for v in vectors) for i in range(3)))
    if mean is None:
        return 180.0
    return 2.0 * max(math.degrees(math.acos(max(-1.0, min(1.0, dot(v, mean))))) for v in vectors)
