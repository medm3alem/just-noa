# -*- coding: utf-8 -*-
"""
vision/synthetic.py - Un joueur SIMULÉ, pour les tests et la démo sans caméra.

Il fabrique, à partir de la chorégraphie, les points qu'un détecteur de pose
renverrait pour un humain qui imite NAO, avec des défauts réglables : retard,
bruit, morphologie, rotation du corps, parties cachées, immobilité, absence.

Ce n'est PAS une mesure : la HMI l'affiche clairement comme "joueur simulé".
Il sert à vérifier que le score se comporte comme prévu (tests/) et à
démontrer toute la boucle de jeu sans webcam (option --joueur-simule).
"""
from __future__ import absolute_import, division, print_function

import math
import random

from evaluation.pose_mapping import BODY, nao_features, skeleton_from_features
from vision.pose_features import PoseSample

ARM_POINTS = {"L": ("left_elbow", "left_wrist"), "R": ("right_elbow", "right_wrist")}
LEG_POINTS = ("left_knee", "right_knee", "left_ankle", "right_ankle")
REST = {"L_upper": (0.0, 0.0, -1.0), "L_fore": (0.0, 0.0, -1.0),
        "R_upper": (0.0, 0.0, -1.0), "R_fore": (0.0, 0.0, -1.0), "L_knee": 0.0, "R_knee": 0.0}


def body_to_mediapipe(p):
    """Repère du corps (x devant, y gauche, z haut) -> repère monde MediaPipe."""
    return (p[1], -p[2], -p[0])


class SyntheticPlayer(object):

    def __init__(self, model, mode="miroir", lag=0.3, noise=0.01, scale=1.0, yaw_deg=0.0,
                 hide=(), static=False, absent=False, wrong=False, seed=1, aspect=4.0 / 3.0):
        self.model = model
        self.mode = mode
        self.lag, self.noise, self.scale = lag, noise, scale
        self.yaw = math.radians(yaw_deg)
        self.hide, self.static, self.absent, self.wrong = set(hide), static, absent, wrong
        self.rng = random.Random(seed)
        self.aspect = aspect
        self.body = dict((k, v * scale) for k, v in BODY.items())

    def features_at(self, tau):
        if self.static:
            return dict(REST)
        expected = self.model.expected(self.mode, tau - self.lag)
        if self.wrong:
            # Fait l'inverse en hauteur : bras levés quand NAO les baisse, et inversement.
            return dict((k, (v[0], v[1], -v[2]) if isinstance(v, tuple) else v)
                        for k, v in expected.items())
        return expected

    def sample(self, t_capture, tau):
        """PoseSample tel qu'un détecteur le produirait, ou None si absent."""
        if self.absent:
            return None
        pts = skeleton_from_features(self.features_at(tau), self.body)
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        world, image = {}, {}
        k_img = 0.42 / self.scale          # même taille apparente : la caméra "recule"
        for name, (x, y, z) in pts.items():
            x, y = c * x - s * y, s * x + c * y                    # rotation autour de la verticale
            x, y, z = (v + self.rng.gauss(0.0, self.noise) for v in (x, y, z))
            mp = body_to_mediapipe((x, y, z - 0.25 * self.scale))
            world[name] = mp
            vis = 0.95
            if name in self.hide or ("legs" in self.hide and name in LEG_POINTS) or \
                    any(side + "_arm" in self.hide and name in pts_ for side, pts_ in ARM_POINTS.items()):
                vis = 0.1
            image[name] = (0.5 + mp[0] * k_img / self.aspect, 0.45 + mp[1] * k_img, vis)
        return PoseSample(t_capture, image, world, self.aspect)


def reference_nao_features(model, tau):
    """Caractéristiques de NAO lui-même (côtés du robot) : utile pour les tests."""
    return nao_features(model.timeline.pose_at(tau))


def idle_sample(t, aspect=4.0 / 3.0):
    """Joueur simulé au repos, bras le long du corps (avant le départ de la danse)."""
    pts = skeleton_from_features(dict(REST), BODY)
    world, image = {}, {}
    for name, (x, y, z) in pts.items():
        mp = body_to_mediapipe((x, y, z - 0.25))
        world[name] = mp
        image[name] = (0.5 + mp[0] * 0.42 / aspect, 0.45 + mp[1] * 0.42, 0.95)
    return PoseSample(t, image, world, aspect)
