# -*- coding: utf-8 -*-
"""
choreography/composer.py - Composer une chorégraphie à partir de poses nommées
placées sur une grille rythmique, et l'écrire au format motion.json (Bezier).

    comp = Composer(JOINTS)
    comp.key(t, pose)                         # pose (dict partiel) atteinte à l'instant t
    comp.step(grid, 17, pose, hold=0.25)      # pose atteinte SUR le temps 17, tenue 1/4 de temps
    names, times, keys = comp.to_motion()     # format Choregraphe "Bezier"

Principes (danse fluide, NAO en sécurité) :
- une pose est ATTEINTE sur le temps : le geste se fait pendant le temps qui
  précède, ce qui donne l'impression de "taper" le temps ;
- chaque articulation a sa propre suite de clés : un bras peut tenir sa pose
  pendant que l'autre bouge, sans retour systématique à une posture neutre ;
- entre deux clés, courbe cubique d'Hermite à tangentes monotones
  (Fritsch-Carlson) : vitesse continue d'une clé à l'autre quand le geste
  continue dans le même sens, vitesse nulle sur les tenues, JAMAIS de
  dépassement des valeurs des clés (donc jamais au-delà des butées si les clés
  sont dedans) ;
- la courbe est écrite en Bézier explicite (poignées à 1/3 de l'intervalle) :
  ce que joue angleInterpolationBezier sur NAO est exactement la courbe que
  calcule choreography/reference_pose.py pour noter le joueur.

Python 2.7 et 3, sans dépendance.
"""
from __future__ import absolute_import, division

MERGE = 0.01          # s : deux clés plus proches sont fusionnées (la dernière gagne)


def monotone_slopes(times, values):
    """Pentes de Fritsch-Carlson ; nulles aux extrémités et sur les paliers."""
    n = len(times)
    if n < 2:
        return [0.0] * n
    d = [(values[i + 1] - values[i]) / (times[i + 1] - times[i]) for i in range(n - 1)]
    m = [0.0] * n
    for i in range(1, n - 1):
        m[i] = 0.0 if d[i - 1] * d[i] <= 0 else (d[i - 1] + d[i]) / 2.0
    for i in range(n - 1):
        if d[i] == 0.0:
            m[i] = m[i + 1] = 0.0
            continue
        a, b = m[i] / d[i], m[i + 1] / d[i]
        s = a * a + b * b
        if s > 9.0:
            tau = 3.0 / s ** 0.5
            m[i], m[i + 1] = tau * a * d[i], tau * b * d[i]
    m[0] = m[-1] = 0.0
    return m


def bezier_keys(times, values):
    """Clés Bezier NAOqi [angle, [3, dt_gauche, da_gauche], [3, dt_droite, da_droite]]."""
    slopes = monotone_slopes(times, values)
    keys = []
    n = len(times)
    for i in range(n):
        h_prev = times[i] - times[i - 1] if i > 0 else (times[1] - times[0] if n > 1 else 0.3)
        h_next = times[i + 1] - times[i] if i < n - 1 else h_prev
        m = slopes[i]
        keys.append([round(values[i], 4),
                     [3, round(-h_prev / 3.0, 4), round(-m * h_prev / 3.0, 5)],
                     [3, round(h_next / 3.0, 4), round(m * h_next / 3.0, 5)]])
    return keys


class Composer(object):

    def __init__(self, joints):
        self.joints = list(joints)
        self.tracks = dict((j, []) for j in self.joints)     # [(t, valeur)]
        self.moves = []                                      # [{"start", "end", "name"}]
        self.events = []

    # --- Clés --------------------------------------------------------------------
    def key(self, t, pose):
        """La pose (dict partiel {articulation: angle}) est atteinte à l'instant t."""
        for name, value in pose.items():
            if name not in self.tracks:
                raise KeyError("articulation non prevue dans cette choregraphie : %s" % name)
            self.tracks[name].append((round(float(t), 4), float(value)))

    def hold(self, t0, t1, pose):
        self.key(t0, pose)
        self.key(t1, pose)

    def last(self, name):
        """Dernière clé (t, valeur) d'une articulation, ou None."""
        track = self.tracks[name]
        return max(track, key=lambda kv: kv[0]) if track else None

    def arrive(self, t, pose, limits, max_ratio=0.5, min_travel=0.3, min_hold=0.08, peak=1.6):
        """
        La pose est atteinte à l'instant t, en partant LE PLUS TARD POSSIBLE de la
        pose précédente : la pose précédente est tenue (lisible pour le joueur),
        puis le geste dure juste ce qu'il faut pour que chaque articulation reste
        sous `max_ratio` de sa vitesse max (pic d'une courbe lissée ~ `peak` x la
        vitesse moyenne), et au moins `min_travel` s (pas de geste sec).
        Les articulations de `pose` partent ensemble (geste coordonné), sauf celles
        qui viennent de recevoir une clé : elles partent `min_hold` s après.
        Renvoie la durée du geste (s).
        """
        previous = {}
        for name in pose:
            last = self.last(name)
            if last is not None:
                previous[name] = last
        if not previous:
            self.key(t, pose)
            return 0.0
        travel = min_travel
        for name, value in pose.items():
            if name in previous and limits.get(name):
                vmax = limits[name][2]
                travel = max(travel, peak * abs(value - previous[name][1]) / (max_ratio * vmax))
        depart = t - travel
        for name, (tp, vp) in previous.items():
            # chaque articulation tient sa valeur jusqu'au départ du geste (au plus
            # tôt min_hold après sa propre dernière clé)
            d = max(tp + min_hold, depart)
            if d < t - MERGE and d > tp + MERGE:
                self.key(d, {name: vp})
        self.key(t, pose)
        latest_prev = max(tp for tp, _ in previous.values())
        return t - max(depart, latest_prev)

    def step(self, grid, beat, pose, hold=0.0):
        """Pose atteinte SUR le temps `beat` (indice, fractions permises), tenue `hold` temps."""
        self.key(grid.time(beat), pose)
        if hold > 0:
            self.key(grid.time(beat + hold), pose)

    def move(self, start, end, name):
        """Mouvement nommé (pour le bilan du joueur) entre deux instants."""
        self.moves.append({"start": round(start, 3), "end": round(end, 3), "name": name})

    def event(self, t, **fields):
        ev = dict(fields)
        ev["t"] = round(float(t), 3)
        self.events.append(ev)

    # --- Sortie ------------------------------------------------------------------
    def track(self, name):
        """Clés triées d'une articulation, clés trop proches fusionnées."""
        out = []
        for t, v in sorted(self.tracks[name], key=lambda kv: kv[0]):
            if out and t - out[-1][0] < MERGE:
                out[-1] = (out[-1][0], v)
            else:
                out.append((t, v))
        return out

    def to_motion(self):
        names, times, keys = [], [], []
        for name in self.joints:
            tr = self.track(name)
            if not tr:
                continue
            ts = [t for t, _ in tr]
            vs = [v for _, v in tr]
            names.append(name)
            times.append(ts)
            keys.append(bezier_keys(ts, vs))
        return names, times, keys

    def key_count(self):
        return sum(len(self.track(n)) for n in self.joints)
