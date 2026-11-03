# -*- coding: utf-8 -*-
"""
vision/pose_filter.py - Lissage des points détectés (filtre "One Euro").

Les points de MediaPipe tremblent de quelques pixels d'une image à l'autre.
Une moyenne glissante réduirait le tremblement mais ajouterait du retard. Le
filtre One Euro (Casiez et al., 2012) adapte son lissage à la vitesse : fort
quand le point est presque immobile (tremblement supprimé), faible quand il
bouge vite (peu de retard). Deux réglages dans config.py :
  FILTER_MIN_CUTOFF : plus petit = plus lisse à l'arrêt ;
  FILTER_BETA       : plus grand = moins de retard dans les mouvements rapides.

Si le joueur disparaît plus de `reset_after` secondes, le filtre repart de zéro
pour ne pas "glisser" depuis une ancienne position.
"""
from __future__ import absolute_import, division, print_function

import math

from vision.pose_features import PoseSample


class OneEuroFilter(object):

    def __init__(self, min_cutoff=1.2, beta=0.4, d_cutoff=1.0):
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self.x_prev = self.dx_prev = self.t_prev = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, t):
        if self.t_prev is None or t <= self.t_prev:
            self.x_prev, self.dx_prev, self.t_prev = x, 0.0, t
            return x
        dt = t - self.t_prev
        dx = (x - self.x_prev) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        dx_hat = a_d * dx + (1 - a_d) * self.dx_prev
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._alpha(cutoff, dt)
        x_hat = a * x + (1 - a) * self.x_prev
        self.x_prev, self.dx_prev, self.t_prev = x_hat, dx_hat, t
        return x_hat


class PoseFilter(object):
    """Applique un filtre One Euro à chaque coordonnée de chaque point."""

    def __init__(self, min_cutoff=1.2, beta=0.4, reset_after=0.5):
        self.min_cutoff, self.beta, self.reset_after = min_cutoff, beta, reset_after
        self._filters = {}
        self._last_t = None

    def reset(self):
        self._filters = {}
        self._last_t = None

    def _f(self, key):
        f = self._filters.get(key)
        if f is None:
            f = self._filters[key] = OneEuroFilter(self.min_cutoff, self.beta)
        return f

    def __call__(self, sample):
        if sample is None:
            return None
        if self._last_t is not None and sample.t - self._last_t > self.reset_after:
            self.reset()
        self._last_t = sample.t
        t = sample.t
        image = {}
        for name, (x, y, vis) in sample.image.items():
            image[name] = (self._f((name, "x"))(x, t), self._f((name, "y"))(y, t), vis)
        world = None
        if sample.world:
            world = {}
            for name, (x, y, z) in sample.world.items():
                world[name] = (self._f((name, "wx"))(x, t), self._f((name, "wy"))(y, t),
                               self._f((name, "wz"))(z, t))
        return PoseSample(t, image, world, sample.aspect)
