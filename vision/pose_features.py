# -*- coding: utf-8 -*-
"""
vision/pose_features.py - Des points du squelette à la représentation commune.

Entrée : un PoseSample (points MediaPipe, ou d'un autre fournisseur).
Sortie : les mêmes caractéristiques que pour NAO (evaluation/pose_mapping.py),
dans le repère du corps du JOUEUR : x devant lui, y vers SA gauche, z vers le haut.

Le repère est reconstruit à partir du joueur lui-même :
    gauche = épaule gauche - épaule droite
    haut   = milieu des épaules - milieu des hanches (ou la verticale de la
             caméra si les hanches sont hors champ), rendu perpendiculaire
    devant = gauche ^ haut
Les directions sont des vecteurs unitaires : le résultat ne dépend ni de la
taille du joueur, ni de sa distance à la caméra, ni de sa position dans l'image,
ni d'une légère rotation du corps.

Une articulation peu visible (visibilité < seuil) rend sa caractéristique
INVALIDE : elle n'est pas notée, au lieu d'être comptée comme une erreur.

Les points sont toujours ceux de l'image NON inversée : "gauche" désigne la
gauche anatomique du joueur, même si l'affichage est en miroir.
"""
from __future__ import absolute_import, division, print_function

import math

from evaluation.pose_mapping import angle_deg, cross, dot, unit

# Indices des points MediaPipe Pose (modèle à 33 points)
LANDMARK_INDEX = {
    "nose": 0, "left_shoulder": 11, "right_shoulder": 12, "left_elbow": 13,
    "right_elbow": 14, "left_wrist": 15, "right_wrist": 16, "left_hip": 23,
    "right_hip": 24, "left_knee": 25, "right_knee": 26, "left_ankle": 27,
    "right_ankle": 28,
}
SKELETON_EDGES = [
    ("left_shoulder", "right_shoulder"), ("left_hip", "right_hip"),
    ("left_shoulder", "left_hip"), ("right_shoulder", "right_hip"),
    ("left_shoulder", "left_elbow"), ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"), ("right_elbow", "right_wrist"),
    ("left_hip", "left_knee"), ("left_knee", "left_ankle"),
    ("right_hip", "right_knee"), ("right_knee", "right_ankle"),
]
HUMAN_STAND_KNEE_DEG = 8.0     # flexion naturelle d'un genou "debout"


class PoseSample(object):
    """
    Une pose détectée sur une image.
      t      : instant de CAPTURE de l'image (horloge compat.now())
      image  : {nom: (x, y, visibilité)} coordonnées normalisées 0..1 de l'image
      world  : {nom: (x, y, z)} en mètres (x droite image, y bas, z profondeur),
               ou None si le fournisseur ne donne que du 2D
      aspect : largeur / hauteur de l'image (pour le 2D)
    """
    __slots__ = ("t", "image", "world", "aspect")

    def __init__(self, t, image, world=None, aspect=4.0 / 3.0):
        self.t, self.image, self.world, self.aspect = t, image, world, aspect


class PlayerFeatures(object):
    """Caractéristiques du joueur + diagnostic de visibilité."""
    __slots__ = ("values", "valid", "has_depth", "torso_estimated", "visible", "border")

    def __init__(self):
        self.values = {}            # nom -> vecteur unitaire ou angle (degrés)
        self.valid = set()          # caractéristiques exploitables
        self.has_depth = False
        self.torso_estimated = False
        self.visible = {}           # point -> bool
        self.border = False         # un point important touche le bord de l'image


def _finite(p):
    return p is not None and all(not math.isnan(c) and not math.isinf(c) for c in p)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _mid(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)


def extract_features(sample, visibility_min=0.5, use_depth=True, border_margin=0.02):
    """PoseSample -> PlayerFeatures (aucune exception : les cas douteux sont invalides)."""
    out = PlayerFeatures()
    if sample is None or not sample.image:
        return out

    for name, (x, y, vis) in sample.image.items():
        ok = vis is not None and vis >= visibility_min and _finite((x, y, vis))
        out.visible[name] = ok
        if ok and name != "nose" and not (border_margin <= x <= 1 - border_margin
                                          and border_margin <= y <= 1 - border_margin):
            out.border = True

    def vis(*names):
        return all(out.visible.get(n, False) for n in names)

    # Coordonnées 3D : monde (mètres) si dispo, sinon image corrigée de l'aspect.
    out.has_depth = bool(use_depth and sample.world)
    if out.has_depth:
        pts = dict(sample.world)
    else:
        pts = dict((n, (x * sample.aspect, y, 0.0)) for n, (x, y, _v) in sample.image.items())
    if not all(_finite(p) for p in pts.values()):
        pts = dict((n, p) for n, p in pts.items() if _finite(p))

    # --- Repère du corps --------------------------------------------------------------
    if not vis("left_shoulder", "right_shoulder") or \
            "left_shoulder" not in pts or "right_shoulder" not in pts:
        return out                     # sans les deux épaules, rien n'est fiable
    left = unit(_sub(pts["left_shoulder"], pts["right_shoulder"]))
    if left is None:
        return out
    mid_sh = _mid(pts["left_shoulder"], pts["right_shoulder"])
    if vis("left_hip", "right_hip") and "left_hip" in pts and "right_hip" in pts:
        up_raw = _sub(mid_sh, _mid(pts["left_hip"], pts["right_hip"]))
    else:
        up_raw = (0.0, -1.0, 0.0)      # hanches hors champ : verticale de la caméra
        out.torso_estimated = True
    up = unit(_sub(up_raw, tuple(dot(up_raw, left) * c for c in left)))
    if up is None:
        return out
    forward = cross(left, up)

    def to_body(v):
        return (dot(v, forward), dot(v, left), dot(v, up))

    # --- Bras ----------------------------------------------------------------------------
    for side, name in (("L", "left"), ("R", "right")):
        s, e, w = name + "_shoulder", name + "_elbow", name + "_wrist"
        if vis(s, e) and s in pts and e in pts:
            u = unit(to_body(_sub(pts[e], pts[s])))
            if u is not None:
                out.values[side + "_upper"] = u
                out.valid.add(side + "_upper")
        if vis(e, w) and e in pts and w in pts:
            f = unit(to_body(_sub(pts[w], pts[e])))
            if f is not None:
                out.values[side + "_fore"] = f
                out.valid.add(side + "_fore")

    # --- Genoux ---------------------------------------------------------------------------
    for side, name in (("L", "left"), ("R", "right")):
        h, k, a = name + "_hip", name + "_knee", name + "_ankle"
        if vis(h, k, a) and h in pts and k in pts and a in pts:
            thigh, shin = unit(_sub(pts[h], pts[k])), unit(_sub(pts[a], pts[k]))
            if thigh is not None and shin is not None:
                flex = 180.0 - angle_deg(thigh, shin)
                out.values[side + "_knee"] = max(0.0, flex - HUMAN_STAND_KNEE_DEG)
                out.valid.add(side + "_knee")
    return out
