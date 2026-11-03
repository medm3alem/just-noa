# -*- coding: utf-8 -*-
"""
choreography/reference_pose.py - Pose de NAO à un instant donné de la chorégraphie.

    timeline = ReferenceTimeline(choreo)
    angles = timeline.pose_at(12.4)      # {"LShoulderPitch": 0.31, ...} en radians

Les angles sont reconstruits à partir des VRAIES données de motion.json :
- format simple (une valeur par keyframe) : interpolation cubique monotone
  (Fritsch-Carlson). Comme l'interpolation lissée de NAOqi, la courbe passe
  par chaque keyframe avec une vitesse nulle sur les paliers, sans dépassement ;
- format Bezier (export Choregraphe) : vraie courbe de Bézier cubique
  construite avec les poignées exportées.
Avant la première keyframe, la valeur est celle de la première keyframe (le
lecteur y place NAO avant le départ) ; après la dernière, elle reste figée.

Les articulations que la chorégraphie ne pilote pas gardent leur valeur de la
posture StandInit (config.REFERENCE_DEFAULT_POSE). Ces valeurs sont
approximatives : c'est une hypothèse documentée, pas une mesure.
"""
from __future__ import absolute_import, division, print_function

import bisect

# Posture StandInit approximative de NAO V6 (radians). Sert pour les articulations
# absentes de la chorégraphie. À affiner en lisant les angles réels du robot.
DEFAULT_POSE = {
    "HeadYaw": 0.0, "HeadPitch": 0.0,
    "LShoulderPitch": 1.40, "LShoulderRoll": 0.25, "LElbowYaw": -1.39, "LElbowRoll": -1.00,
    "LWristYaw": 0.0,
    "RShoulderPitch": 1.40, "RShoulderRoll": -0.25, "RElbowYaw": 1.39, "RElbowRoll": 1.00,
    "RWristYaw": 0.0,
    "LHipYawPitch": 0.0, "LHipRoll": 0.0, "LHipPitch": -0.45, "LKneePitch": 0.70,
    "LAnklePitch": -0.35, "LAnkleRoll": 0.0,
    "RHipYawPitch": 0.0, "RHipRoll": 0.0, "RHipPitch": -0.45, "RKneePitch": 0.70,
    "RAnklePitch": -0.35, "RAnkleRoll": 0.0,
}


def _detect_handle_time_index(keys_per_joint):
    """
    Ordre des poignées Bezier : la documentation ALMotion annonce
    [type, dAngle, dTime] mais les exports Choregraphe ont la forme
    [3, -0.33, 0] (le temps d'abord). On regarde quelle composante se comporte
    comme un temps : <= 0 pour la poignée gauche, >= 0 pour la droite.
    """
    def fits(index):
        for keys in keys_per_joint:
            for key in keys:
                left, right = key[1], key[2]
                if left[index] > 1e-9 or right[index] < -1e-9:
                    return False
        return True
    if fits(1):
        return 1
    if fits(2):
        return 2
    return 1


class JointTrack(object):
    """Trajectoire d'une articulation : instants + clés -> angle(t)."""

    def __init__(self, times, keys, bezier=False, time_index=1):
        if len(times) != len(keys) or not times:
            raise ValueError("autant d'instants que de cles attendus")
        self.times = [float(t) for t in times]
        self.bezier = bezier
        if bezier:
            self.values = [float(k[0]) for k in keys]
            angle_index = 3 - time_index          # 1 <-> 2
            self.left = [(float(k[1][time_index]), float(k[1][angle_index])) for k in keys]
            self.right = [(float(k[2][time_index]), float(k[2][angle_index])) for k in keys]
        else:
            self.values = [float(k) for k in keys]
            self.slopes = self._monotone_slopes()

    # --- Interpolation cubique monotone (Fritsch-Carlson) ------------------------
    def _monotone_slopes(self):
        t, v = self.times, self.values
        n = len(t)
        if n == 1:
            return [0.0]
        d = [(v[i + 1] - v[i]) / (t[i + 1] - t[i]) for i in range(n - 1)]
        m = [0.0] * n
        m[0], m[-1] = d[0], d[-1]
        for i in range(1, n - 1):
            m[i] = 0.0 if d[i - 1] * d[i] <= 0 else (d[i - 1] + d[i]) / 2.0
        for i in range(n - 1):
            if d[i] == 0.0:
                m[i] = m[i + 1] = 0.0
                continue
            a, b = m[i] / d[i], m[i + 1] / d[i]
            s = a * a + b * b
            if s > 9.0:                       # limite pour rester monotone
                tau = 3.0 / s ** 0.5
                m[i], m[i + 1] = tau * a * d[i], tau * b * d[i]
        # Une keyframe est un point d'arrivée de NAO : vitesse nulle aux extrémités.
        m[0] = m[-1] = 0.0
        return m

    def value(self, t):
        times = self.times
        if t <= times[0]:
            return self.values[0]
        if t >= times[-1]:
            return self.values[-1]
        i = bisect.bisect_right(times, t) - 1
        if self.bezier:
            return self._bezier_value(i, t)
        h = times[i + 1] - times[i]
        s = (t - times[i]) / h
        v0, v1 = self.values[i], self.values[i + 1]
        m0, m1 = self.slopes[i] * h, self.slopes[i + 1] * h
        s2, s3 = s * s, s * s * s
        return ((2 * s3 - 3 * s2 + 1) * v0 + (s3 - 2 * s2 + s) * m0
                + (-2 * s3 + 3 * s2) * v1 + (s3 - s2) * m1)

    # --- Bézier cubique (export Choregraphe) ---------------------------------------
    def _bezier_value(self, i, t):
        t0, t3 = self.times[i], self.times[i + 1]
        a0, a3 = self.values[i], self.values[i + 1]
        dt1, da1 = self.right[i]
        dt2, da2 = self.left[i + 1]
        span = t3 - t0
        # Poignées bornées dans le segment : garantit un temps monotone.
        t1 = t0 + min(max(dt1, 0.0), span)
        t2 = t3 + max(min(dt2, 0.0), -span)
        a1, a2 = a0 + da1, a3 + da2
        lo, hi = 0.0, 1.0
        for _ in range(40):                   # résolution x(u) = t par dichotomie
            u = (lo + hi) / 2.0
            x = _cubic(t0, t1, t2, t3, u)
            if x < t:
                lo = u
            else:
                hi = u
        return _cubic(a0, a1, a2, a3, (lo + hi) / 2.0)


def _cubic(p0, p1, p2, p3, u):
    w = 1.0 - u
    return w * w * w * p0 + 3 * w * w * u * p1 + 3 * w * u * u * p2 + u * u * u * p3


class ReferenceTimeline(object):
    """Toutes les trajectoires d'une chorégraphie + posture par défaut."""

    def __init__(self, choreo, default_pose=None):
        self.default_pose = dict(DEFAULT_POSE)
        if default_pose:
            self.default_pose.update(default_pose)
        time_index = _detect_handle_time_index(choreo.keys) if choreo.bezier else 1
        self.tracks = {}
        for name, times, keys in zip(choreo.names, choreo.times, choreo.keys):
            self.tracks[name] = JointTrack(times, keys, choreo.bezier, time_index)
        self.first_key_time = min(t[0] for t in choreo.times) if choreo.times else 0.0
        self.last_key_time = max(t[-1] for t in choreo.times) if choreo.times else 0.0
        self.key_times = sorted(set(round(t, 3) for joint in choreo.times for t in joint))

    def pose_at(self, t):
        """Angles (rad) de toutes les articulations connues à l'instant t (s)."""
        pose = dict(self.default_pose)
        for name, track in self.tracks.items():
            pose[name] = track.value(t)
        return pose

    def driven(self, name, min_range=0.05):
        """True si la chorégraphie fait réellement bouger cette articulation."""
        track = self.tracks.get(name)
        if track is None:
            return False
        return max(track.values) - min(track.values) >= min_range or \
            abs(track.values[0] - self.default_pose.get(name, track.values[0])) >= min_range

    def move_segments(self, min_length=1.0, merge=0.3):
        """
        Découpe la danse en "mouvements" à partir des keyframes : on regroupe les
        instants proches (< merge s) puis on fusionne les intervalles trop courts
        (< min_length s, typiquement une transition) avec le suivant.
        Renvoie [(début, fin)], vide si la danse est un mouvement continu.
        """
        clusters = []
        for t in self.key_times:
            if not clusters or t - clusters[-1] > merge:
                clusters.append(t)
        segments, start = [], None
        for a, b in zip(clusters, clusters[1:]):
            start = a if start is None else start
            if b - start >= min_length:
                segments.append((start, b))
                start = None
        return segments
