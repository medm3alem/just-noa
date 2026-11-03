# -*- coding: utf-8 -*-
"""
evaluation/pose_mapping.py - Passer des angles de NAO à une pose comparable à un humain.

On ne compare PAS les angles NAOqi aux points MediaPipe : les axes, signes et
amplitudes diffèrent. On passe par une représentation commune, indépendante de
la morphologie et de la position dans l'image :

    direction du bras      (épaule -> coude)   vecteur unitaire 3D
    direction de l'avant-bras (coude -> poignet) vecteur unitaire 3D
    flexion des genoux     (degrés au-delà de la position debout)

exprimés dans le REPÈRE DU CORPS : x = devant soi, y = vers sa gauche, z = vers
le haut. Pour NAO, c'est le repère du torse ; pour le joueur, il est reconstruit
à partir de ses épaules et hanches (vision/pose_features.py).

Cinématique directe des bras de NAO (rotations successives de la chaîne) :
    bras       = Ry(ShoulderPitch) . Rz(ShoulderRoll) . x
    avant-bras = Ry(ShoulderPitch) . Rz(ShoulderRoll) . Rx(ElbowYaw) . Rz(ElbowRoll) . x
Vérifications : ShoulderPitch = +90° -> bras vers le bas ; -90° -> vers le haut ;
LShoulderRoll = +90° -> bras gauche à l'horizontale vers la gauche.

Correspondance NAO -> joueur (config.MAPPING_MODE) :
- "miroir"    : le joueur fait face à NAO et l'imite comme dans un miroir :
                bras gauche de NAO <-> bras droit du joueur, axe gauche/droite inversé ;
- "meme_cote" : bras gauche <-> bras gauche ;
- "auto"      : les deux sont évalués, le meilleur est retenu (voir scoring.py).
"""
from __future__ import absolute_import, division, print_function

import math

FEATURES = ("L_upper", "L_fore", "R_upper", "R_fore", "L_knee", "R_knee")
PARTS = {
    "bras_gauche": ("L_upper", "L_fore"),
    "bras_droit": ("R_upper", "R_fore"),
    "jambes": ("L_knee", "R_knee"),
}
PART_LABELS = {"bras_gauche": u"Left arm", "bras_droit": u"Right arm", "jambes": u"Legs"}

# Articulations de NAO qui conditionnent chaque caractéristique
FEATURE_JOINTS = {
    "L_upper": ("LShoulderPitch", "LShoulderRoll"),
    "L_fore": ("LElbowYaw", "LElbowRoll"),
    "R_upper": ("RShoulderPitch", "RShoulderRoll"),
    "R_fore": ("RElbowYaw", "RElbowRoll"),
    "L_knee": ("LKneePitch", "LHipPitch"),
    "R_knee": ("RKneePitch", "RHipPitch"),
}
NAO_STAND_KNEE = 0.70          # rad : flexion des genoux de NAO en StandInit


# --- Petite algèbre 3D (sans dépendance) -----------------------------------------
def rot_x(a, v):
    c, s = math.cos(a), math.sin(a)
    return (v[0], c * v[1] - s * v[2], s * v[1] + c * v[2])


def rot_y(a, v):
    c, s = math.cos(a), math.sin(a)
    return (c * v[0] + s * v[2], v[1], -s * v[0] + c * v[2])


def rot_z(a, v):
    c, s = math.cos(a), math.sin(a)
    return (c * v[0] - s * v[1], s * v[0] + c * v[1], v[2])


def norm(v):
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def unit(v):
    n = norm(v)
    return (v[0] / n, v[1] / n, v[2] / n) if n > 1e-9 else None


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def angle_deg(a, b):
    """Angle (degrés) entre deux vecteurs unitaires."""
    return math.degrees(math.acos(max(-1.0, min(1.0, dot(a, b)))))


def mirror_y(v):
    return (v[0], -v[1], v[2])


# --- Cinématique directe de NAO ---------------------------------------------------------
def nao_arm_vectors(pose, side):
    """(direction du bras, direction de l'avant-bras) de NAO pour side = 'L' ou 'R'."""
    p, r = pose[side + "ShoulderPitch"], pose[side + "ShoulderRoll"]
    ey, er = pose[side + "ElbowYaw"], pose[side + "ElbowRoll"]
    x = (1.0, 0.0, 0.0)
    upper = rot_y(p, rot_z(r, x))
    fore = rot_y(p, rot_z(r, rot_x(ey, rot_z(er, x))))
    return upper, fore


def nao_knee_flex_deg(pose, side):
    """Flexion du genou au-delà de la position debout de NAO (degrés, >= 0)."""
    return max(0.0, math.degrees(pose[side + "KneePitch"] - NAO_STAND_KNEE))


def nao_features(pose):
    """Caractéristiques de NAO dans son propre repère (côtés de NAO)."""
    lu, lf = nao_arm_vectors(pose, "L")
    ru, rf = nao_arm_vectors(pose, "R")
    return {"L_upper": lu, "L_fore": lf, "R_upper": ru, "R_fore": rf,
            "L_knee": nao_knee_flex_deg(pose, "L"), "R_knee": nao_knee_flex_deg(pose, "R")}


def expected_player_features(nao, mode):
    """
    Ce que le JOUEUR doit faire (dans son repère, ses côtés) pour imiter NAO.
    mode = "miroir" ou "meme_cote".
    """
    if mode == "meme_cote":
        return dict(nao)
    if mode != "miroir":
        raise ValueError("mode de correspondance inconnu : %r" % mode)
    return {
        "L_upper": mirror_y(nao["R_upper"]), "L_fore": mirror_y(nao["R_fore"]),
        "R_upper": mirror_y(nao["L_upper"]), "R_fore": mirror_y(nao["L_fore"]),
        "L_knee": nao["R_knee"], "R_knee": nao["L_knee"],
    }


def evaluated_features(timeline):
    """
    Caractéristiques à évaluer pour cette chorégraphie : seulement celles dont
    NAO bouge vraiment les articulations. Un bras que la danse ne pilote pas
    n'est pas noté (sa pose "par défaut" de robot n'a pas d'équivalent humain).
    Renvoie un ensemble de noms côté NAO ; le mapping s'occupe des côtés joueur.
    """
    feats = set()
    for feat, joints in FEATURE_JOINTS.items():
        if any(timeline.driven(j) for j in joints):
            feats.add(feat)
    # L'avant-bras ne se lit qu'avec la direction du bras : on l'ajoute si l'épaule bouge.
    for side in ("L", "R"):
        if side + "_fore" in feats:
            feats.add(side + "_upper")
    return feats


def map_feature_names(nao_feature_set, mode):
    """Noms de caractéristiques NAO -> noms côté joueur selon le mode."""
    if mode == "meme_cote":
        return set(nao_feature_set)
    swap = {"L": "R", "R": "L"}
    return set(swap[f[0]] + f[1:] for f in nao_feature_set)


# --- Pour dessiner la "pose attendue" dans la HMI --------------------------------------
BODY = {   # squelette humain moyen dans le repère du corps (mètres)
    "shoulder": 0.19, "hip": 0.10, "torso": 0.50, "upper": 0.29, "fore": 0.27,
    "thigh": 0.43, "shin": 0.42, "head": 0.14,
}


def skeleton_from_features(features, body=BODY):
    """
    Points 3D (repère du corps, origine au milieu des hanches) d'un humain qui
    réalise ces caractéristiques. Sert à la "pose attendue" de la HMI et au
    joueur simulé des tests. Les genoux sont fléchis vers l'avant.
    """
    pts = {}
    up = body["torso"]
    pts["left_shoulder"] = (0.0, body["shoulder"], up)
    pts["right_shoulder"] = (0.0, -body["shoulder"], up)
    pts["left_hip"] = (0.0, body["hip"], 0.0)
    pts["right_hip"] = (0.0, -body["hip"], 0.0)
    pts["nose"] = (0.05, 0.0, up + body["head"])
    for side, name in (("L", "left"), ("R", "right")):
        s = pts[name + "_shoulder"]
        u = features.get(side + "_upper") or (0.0, 0.0, -1.0)
        f = features.get(side + "_fore") or u
        e = tuple(s[i] + body["upper"] * u[i] for i in range(3))
        w = tuple(e[i] + body["fore"] * f[i] for i in range(3))
        pts[name + "_elbow"], pts[name + "_wrist"] = e, w
        flex = math.radians(features.get(side + "_knee") or 0.0)
        h = pts[name + "_hip"]
        thigh = (math.sin(flex / 2), 0.0, -math.cos(flex / 2))     # cuisse vers l'avant
        shin = (-math.sin(flex / 2), 0.0, -math.cos(flex / 2))     # tibia vers l'arrière
        k = tuple(h[i] + body["thigh"] * thigh[i] for i in range(3))
        a = tuple(k[i] + body["shin"] * shin[i] for i in range(3))
        pts[name + "_knee"], pts[name + "_ankle"] = k, a
    return pts
