# -*- coding: utf-8 -*-
"""
vision/overlay.py - Dessin du squelette sur l'image (OpenCV).

Le squelette est dessiné APRÈS l'inversion miroir de l'image, avec des
coordonnées inversées elles aussi : l'affichage est en miroir, l'analyse
reste sur l'image d'origine (gauche = gauche anatomique du joueur).

Couleur de chaque bras = qualité de sa pose en direct (vert / orange / rouge),
gris quand il n'est pas évalué. Pas de texte dans l'image : OpenCV ne sait
pas écrire les accents, les messages sont affichés par la HMI.
"""
from __future__ import absolute_import, division, print_function

from vision.pose_features import SKELETON_EDGES

GREEN, ORANGE, RED, GREY, WHITE = (80, 200, 80), (0, 165, 255), (60, 60, 230), (170, 170, 170), (255, 255, 255)
PART_OF_EDGE = {
    ("left_shoulder", "left_elbow"): "bras_gauche", ("left_elbow", "left_wrist"): "bras_gauche",
    ("right_shoulder", "right_elbow"): "bras_droit", ("right_elbow", "right_wrist"): "bras_droit",
    ("left_hip", "left_knee"): "jambes", ("left_knee", "left_ankle"): "jambes",
    ("right_hip", "right_knee"): "jambes", ("right_knee", "right_ankle"): "jambes",
}


def quality_color(score):
    if score is None:
        return GREY
    if score >= 70:
        return GREEN
    if score >= 45:
        return ORANGE
    return RED


def draw_overlay(frame, sample, part_scores=None, mirror=True, visibility_min=0.5,
                 detected=None):
    """
    Renvoie une NOUVELLE image : miroir éventuel + squelette + pastille d'état.
    `detected` : True (vert), False (rouge), None (pas de pastille).
    """
    import cv2
    out = cv2.flip(frame, 1) if mirror else frame.copy()
    h, w = out.shape[:2]
    part_scores = part_scores or {}
    if sample is not None:
        def px(name):
            x, y, vis = sample.image[name]
            if vis is None or vis < visibility_min:
                return None
            if mirror:
                x = 1.0 - x
            return int(x * w), int(y * h)
        thick = max(2, w // 160)
        for a, b in SKELETON_EDGES:
            pa, pb = px(a), px(b)
            if pa is None or pb is None:
                continue
            part = PART_OF_EDGE.get((a, b))
            color = quality_color(part_scores.get(part)) if part else WHITE
            cv2.line(out, pa, pb, color, thick, cv2.LINE_AA)
        for name in sample.image:
            p = px(name)
            if p is not None and name != "nose":
                cv2.circle(out, p, thick + 2, WHITE, -1, cv2.LINE_AA)
    if detected is not None:
        r = max(6, w // 60)
        cv2.circle(out, (r + 10, r + 10), r, GREEN if detected else RED, -1, cv2.LINE_AA)
    return out
