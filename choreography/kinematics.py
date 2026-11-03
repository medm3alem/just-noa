# -*- coding: utf-8 -*-
"""
choreography/kinematics.py - Géométrie du haut du corps de NAO : positions des
bras, distances de sécurité, limites de la tête.

Sert à VÉRIFIER une chorégraphie avant de l'envoyer au robot (et à la composer) :
- cinématique directe des bras (mêmes conventions que evaluation/pose_mapping.py :
  repère du torse, x devant, y à gauche de NAO, z en haut, millimètres) ;
- modèle de collision volontairement prudent : bras = capsules (segments
  épaissis), tête = sphère, torse / bassin = boîtes, cuisses = capsules ;
- enveloppe de la tête : l'amplitude de HeadPitch se réduit quand la tête est
  tournée (anti-collision tête / épaules de NAO).

Les dimensions des segments viennent de la documentation Aldebaran (NAO V5/V6) ;
les volumes (rayons, boîtes) sont des approximations GÉNÉREUSES mesurées sur
photos : une distance positive ici laisse de la marge sur le vrai robot, mais
ce n'est pas une garantie. Validation finale : sur le robot, à vitesse réduite
(docs/DANCE_VALIDATION.md).

Python 2.7 et 3, sans dépendance.
"""
from __future__ import absolute_import, division

import math

# --- Dimensions (mm), documentation NAO V5/V6 -------------------------------------
SHOULDER_Y, SHOULDER_Z = 98.0, 100.0
UPPER_ARM = 105.0
ELBOW_OFFSET_Y = 15.0
LOWER_ARM = 55.95
HAND_LENGTH = 85.0            # poignet -> bout des doigts (HandOffsetX 57.75 + doigts)
NECK_Z = 126.5
HIP_Y, HIP_Z = 50.0, 85.0
THIGH = 100.0

# --- Volumes de collision (approximations prudentes) ---------------------------------
R_UPPER, R_FORE, R_HAND = 28.0, 26.0, 22.0
HEAD_CENTER, HEAD_RADIUS = (5.0, 0.0, NECK_Z + 58.0), 70.0
TORSO_BOX = ((-50.0, 58.0), (-64.0, 64.0), (-58.0, 112.0))
PELVIS_BOX = ((-48.0, 48.0), (-74.0, 74.0), (-125.0, -55.0))
SHOULDER_RADIUS = 34.0        # boîtier de l'épaule (obstacle pour l'AUTRE bras)
THIGH_RADIUS = 42.0
STAND_HIP_PITCH = -0.45       # cuisses un peu vers l'avant en StandInit

# Seuils (mm) : < 0 = interpénétration du modèle (erreur), < WARN = marge faible.
CLEARANCE_ERROR = 0.0
CLEARANCE_WARN = 8.0

ARM_JOINTS = ("ShoulderPitch", "ShoulderRoll", "ElbowYaw", "ElbowRoll", "WristYaw")

# Enveloppe tête (documentation NAO, "head anti-collision") : |HeadYaw| en degrés ->
# (HeadPitch min, max) en degrés. On interpole et on garde 2° de marge.
HEAD_ENVELOPE_DEG = [
    (0.0, -38.5, 29.5), (27.85, -38.5, 24.18), (43.32, -31.4, 21.2), (51.74, -27.5, 18.91),
    (62.45, -24.64, 17.19), (87.49, -18.91, 11.46), (119.52, -25.73, 18.91),
]
HEAD_MARGIN_DEG = 2.0


# --- Algèbre 3D minimale ---------------------------------------------------------------
def _rx(a, v):
    c, s = math.cos(a), math.sin(a)
    return (v[0], c * v[1] - s * v[2], s * v[1] + c * v[2])


def _ry(a, v):
    c, s = math.cos(a), math.sin(a)
    return (c * v[0] + s * v[2], v[1], -s * v[0] + c * v[2])


def _rz(a, v):
    c, s = math.cos(a), math.sin(a)
    return (c * v[0] - s * v[1], s * v[0] + c * v[1], v[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a):
    return math.sqrt(_dot(a, a))


def _scale(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


# --- Cinématique directe --------------------------------------------------------------
def arm_points(pose, side):
    """
    Points d'un bras de NAO (mm, repère du torse) :
    {"shoulder", "elbow", "wrist", "tip", "palm"}. `palm` est la normale de la
    paume (vecteur unitaire), utile pour vérifier "paume vers le haut / le bas".
    side = "L" ou "R". Les articulations absentes de `pose` valent 0.
    """
    sign = 1.0 if side == "L" else -1.0
    p = pose.get(side + "ShoulderPitch", 0.0)
    r = pose.get(side + "ShoulderRoll", 0.0)
    ey = pose.get(side + "ElbowYaw", 0.0)
    er = pose.get(side + "ElbowRoll", 0.0)
    wy = pose.get(side + "WristYaw", 0.0)

    def upper_frame(v):
        return _ry(p, _rz(r, v))

    def fore_frame(v):
        return upper_frame(_rx(ey, _rz(er, v)))

    def hand_frame(v):
        return fore_frame(_rx(wy, v))

    shoulder = (0.0, sign * SHOULDER_Y, SHOULDER_Z)
    elbow = _add(shoulder, upper_frame((UPPER_ARM, sign * ELBOW_OFFSET_Y, 0.0)))
    wrist = _add(elbow, fore_frame((LOWER_ARM, 0.0, 0.0)))
    tip = _add(wrist, hand_frame((HAND_LENGTH, 0.0, 0.0)))
    # Hypothèse documentée : bras à zéro (tendu devant), paume vers le BAS. C'est
    # cohérent avec StandInit, où les paumes de NAO se font face (vers l'intérieur).
    palm = hand_frame((0.0, 0.0, -1.0))
    return {"shoulder": shoulder, "elbow": elbow, "wrist": wrist, "tip": tip, "palm": palm}


def arm_capsules(pose, side):
    pts = arm_points(pose, side)
    return [("upper", pts["shoulder"], pts["elbow"], R_UPPER),
            ("fore", pts["elbow"], pts["wrist"], R_FORE),
            ("hand", pts["wrist"], pts["tip"], R_HAND)]


# --- Distances -------------------------------------------------------------------------
def _clamp(x, lo, hi):
    return lo if x < lo else (hi if x > hi else x)


def segment_distance(p1, q1, p2, q2):
    """Distance minimale entre les segments [p1 q1] et [p2 q2]."""
    d1, d2, r = _sub(q1, p1), _sub(q2, p2), _sub(p1, p2)
    a, e, f = _dot(d1, d1), _dot(d2, d2), _dot(d2, r)
    eps = 1e-9
    if a <= eps and e <= eps:
        return _norm(r)
    if a <= eps:
        s, t = 0.0, _clamp(f / e, 0.0, 1.0)
    else:
        c = _dot(d1, r)
        if e <= eps:
            t, s = 0.0, _clamp(-c / a, 0.0, 1.0)
        else:
            b = _dot(d1, d2)
            denom = a * e - b * b
            s = _clamp((b * f - c * e) / denom, 0.0, 1.0) if denom > eps else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                t, s = 0.0, _clamp(-c / a, 0.0, 1.0)
            elif t > 1.0:
                t, s = 1.0, _clamp((b - c) / a, 0.0, 1.0)
    c1 = _add(p1, _scale(d1, s))
    c2 = _add(p2, _scale(d2, t))
    return _norm(_sub(c1, c2))


def point_segment_distance(p, a, b):
    ab = _sub(b, a)
    denom = _dot(ab, ab)
    t = _clamp(_dot(_sub(p, a), ab) / denom, 0.0, 1.0) if denom > 1e-9 else 0.0
    return _norm(_sub(p, _add(a, _scale(ab, t))))


def point_box_distance(p, box):
    d = 0.0
    inside = True
    for i in range(3):
        lo, hi = box[i]
        if p[i] < lo:
            d += (lo - p[i]) ** 2
            inside = False
        elif p[i] > hi:
            d += (p[i] - hi) ** 2
            inside = False
    if inside:
        return -min(min(p[i] - box[i][0], box[i][1] - p[i]) for i in range(3))
    return math.sqrt(d)


def segment_box_distance(a, b, box, samples=9):
    """Approximation : distance minimale des points du segment à la boîte."""
    best = None
    for k in range(samples):
        t = k / float(samples - 1)
        d = point_box_distance(_add(a, _scale(_sub(b, a), t)), box)
        best = d if best is None or d < best else best
    return best


def _thigh(side):
    sign = 1.0 if side == "L" else -1.0
    hip = (0.0, sign * HIP_Y, -HIP_Z)
    knee = _add(hip, (THIGH * math.sin(-STAND_HIP_PITCH), 0.0, -THIGH * math.cos(STAND_HIP_PITCH)))
    return hip, knee


def pose_clearances(pose):
    """
    Distances libres (mm) entre les volumes de NAO pour une pose :
    {"<bras>_<segment>/<obstacle>": distance}. Négatif = les volumes se touchent.
    Seuls les bras bougent ici : jambes et torse sont supposés en StandInit.
    """
    out = {}
    caps = {"L": arm_capsules(pose, "L"), "R": arm_capsules(pose, "R")}
    thighs = {"L": _thigh("L"), "R": _thigh("R")}
    for side in ("L", "R"):
        other = "R" if side == "L" else "L"
        osign = 1.0 if other == "L" else -1.0
        other_shoulder = (0.0, osign * SHOULDER_Y, SHOULDER_Z)
        for name, a, b, r in caps[side]:
            key = side + "_" + name
            out[key + "/head"] = point_segment_distance(HEAD_CENTER, a, b) - HEAD_RADIUS - r
            if name != "upper":       # le haut du bras est attaché au torse
                out[key + "/torso"] = segment_box_distance(a, b, TORSO_BOX) - r
            out[key + "/pelvis"] = segment_box_distance(a, b, PELVIS_BOX) - r
            for tside in ("L", "R"):
                h, k = thighs[tside]
                out[key + "/thigh_" + tside] = segment_distance(a, b, h, k) - r - THIGH_RADIUS
            out[key + "/shoulder_" + other] = (point_segment_distance(other_shoulder, a, b)
                                               - r - SHOULDER_RADIUS)
    for ln, la, lb, lr in caps["L"]:
        for rn, ra, rb, rr in caps["R"]:
            out["L_%s/R_%s" % (ln, rn)] = segment_distance(la, lb, ra, rb) - lr - rr
    return out


def min_clearance(pose):
    """(distance libre minimale en mm, nom de la paire la plus proche)."""
    clear = pose_clearances(pose)
    name = min(clear, key=clear.get)
    return clear[name], name


# --- Tête ------------------------------------------------------------------------------
def head_pitch_range(yaw):
    """(min, max) de HeadPitch (rad) autorisés pour un HeadYaw donné, marge comprise."""
    y = abs(math.degrees(yaw))
    table = HEAD_ENVELOPE_DEG
    if y >= table[-1][0]:
        lo, hi = table[-1][1], table[-1][2]
    else:
        for (y0, lo0, hi0), (y1, lo1, hi1) in zip(table, table[1:]):
            if y0 <= y <= y1:
                k = (y - y0) / (y1 - y0)
                lo, hi = lo0 + k * (lo1 - lo0), hi0 + k * (hi1 - hi0)
                break
    return math.radians(lo + HEAD_MARGIN_DEG), math.radians(hi - HEAD_MARGIN_DEG)


# --- Vérification d'une trajectoire complète ---------------------------------------
def check_trajectory(pose_at, start, end, step=0.02, arms=True, head=True):
    """
    Parcourt la trajectoire (pose_at(t) -> dict d'angles) de `start` à `end`.
    Renvoie (erreurs, alertes, pire_marge_mm) ; une ligne par problème, au premier
    instant où il apparaît (pas une ligne par échantillon).
    """
    errors, warnings = [], []
    seen = set()
    worst = None
    n = max(1, int(math.ceil((end - start) / step)))
    for k in range(n + 1):
        t = start + k * step
        pose = pose_at(t)
        if arms:
            clear = pose_clearances(pose)
            for pair, d in clear.items():
                if worst is None or d < worst[0]:
                    worst = (d, pair, t)
                if d < CLEARANCE_ERROR and ("E", pair) not in seen:
                    seen.add(("E", pair))
                    errors.append("collision possible %s a t=%.2f s (%.0f mm)" % (pair, t, d))
                elif d < CLEARANCE_WARN and ("W", pair) not in seen and ("E", pair) not in seen:
                    seen.add(("W", pair))
                    warnings.append("marge faible %s a t=%.2f s (%.0f mm)" % (pair, t, d))
        if head and "HeadPitch" in pose and "HeadYaw" in pose:
            lo, hi = head_pitch_range(pose["HeadYaw"])
            pitch = pose["HeadPitch"]
            if (pitch < lo - 1e-3 or pitch > hi + 1e-3) and "head" not in seen:
                seen.add("head")
                errors.append("tete : HeadPitch %.2f rad hors enveloppe [%.2f ; %.2f] pour HeadYaw %.2f "
                              "a t=%.2f s" % (pitch, lo, hi, pose["HeadYaw"], t))
    return errors, warnings, worst


# --- Équilibre (estimation) -----------------------------------------------------------
# Masses NAO (kg, documentation Aldebaran, NAO V5/V6). Les jambes et le torse ne
# bougent pas : ils sont regroupés en un seul bloc.
MASS_SHOULDER, MASS_UPPER, MASS_ELBOW, MASS_FORE, MASS_HAND = 0.09304, 0.15777, 0.06483, 0.07761, 0.18533
MASS_HEAD = 0.60533 + 0.07842
MASS_TOTAL = 5.48
MASS_REST = MASS_TOTAL - 2 * (MASS_SHOULDER + MASS_UPPER + MASS_ELBOW + MASS_FORE + MASS_HAND) - MASS_HEAD
REST_COM = (-5.0, 0.0, -40.0)        # mm, torse + jambes en StandInit (approximation)
GROUND_Z = -317.0                    # mm : le sol sous le torse en StandInit
GRAVITY = 9.81


def mass_points(pose):
    """[(masse kg, (x, y, z) mm)] des parties qui bougent (bras, tête) + le reste du corps."""
    out = [(MASS_REST, REST_COM)]
    for side in ("L", "R"):
        p = arm_points(pose, side)
        s, e, w, t = p["shoulder"], p["elbow"], p["wrist"], p["tip"]
        out.append((MASS_SHOULDER, s))
        out.append((MASS_UPPER, _add(s, _scale(_sub(e, s), 0.45))))
        out.append((MASS_ELBOW, e))
        out.append((MASS_FORE, _add(e, _scale(_sub(w, e), 0.5))))
        out.append((MASS_HAND, _add(w, _scale(_sub(t, w), 0.35))))
    head = _rz(pose.get("HeadYaw", 0.0), _ry(pose.get("HeadPitch", 0.0), (-1.0, 0.0, 56.0)))
    out.append((MASS_HEAD, _add((0.0, 0.0, NECK_Z), head)))
    return out


def zmp_profile(pose_at, start, end, step=0.01):
    """
    Point de pression au sol (ZMP, modèle à masses ponctuelles) le long de la danse,
    en mm, RELATIF à celui de NAO immobile en StandInit : [(t, dx, dy, dyn_x, dyn_y)].
    dx > 0 : vers les orteils, dx < 0 : vers les talons (côté le plus fragile).
    dyn_x, dyn_y : part DYNAMIQUE (ZMP - projection du centre de masse), due aux
    accélérations des bras et de la tête : c'est elle qui fait "basculer" le robot.
    C'est une ESTIMATION (segments = points, corps rigide) : elle sert à comparer des
    danses entre elles, pas à garantir la stabilité.
    """
    from choreography.reference_pose import DEFAULT_POSE
    ref = mass_points(DEFAULT_POSE)
    ref_x = sum(m * p[0] for m, p in ref) / MASS_TOTAL
    ref_y = sum(m * p[1] for m, p in ref) / MASS_TOTAL
    n = max(2, int((end - start) / step))
    frames = [mass_points(pose_at(start + k * step)) for k in range(n + 1)]
    out = []
    dt = step
    for k in range(1, n):
        num_x = num_y = den = com_x = com_y = 0.0
        for i, (m, p) in enumerate(frames[k]):
            a = [(frames[k + 1][i][1][c] - 2 * p[c] + frames[k - 1][i][1][c]) / (dt * dt) / 1000.0
                 for c in range(3)]                       # m/s^2
            h = (p[2] - GROUND_Z) / 1000.0
            num_x += m * (p[0] / 1000.0 * (a[2] + GRAVITY) - h * a[0])
            num_y += m * (p[1] / 1000.0 * (a[2] + GRAVITY) - h * a[1])
            den += m * (a[2] + GRAVITY)
            com_x += m * p[0]
            com_y += m * p[1]
        zx, zy = 1000.0 * num_x / den, 1000.0 * num_y / den
        cx, cy = com_x / MASS_TOTAL, com_y / MASS_TOTAL
        out.append((start + k * dt, zx - ref_x, zy - ref_y, zx - cx, zy - cy))
    return out


def balance_summary(pose_at, start, end, step=0.01, window=0.1):
    """
    {"back", "fwd", "lat", "dyn"} en mm : recul et avancée max du ZMP, écart latéral
    max, et plus grande part dynamique (avant/arrière), moyennés sur `window` s (les
    pics de quelques ms n'ont pas le temps de faire basculer le robot).
    """
    prof = zmp_profile(pose_at, start, end, step)
    k = max(1, int(round(window / step)))

    def smooth(values):
        return [sum(values[i:i + k]) / len(values[i:i + k]) for i in range(0, len(values) - k + 1)]
    xs = smooth([p[1] for p in prof])
    ys = smooth([p[2] for p in prof])
    ds = smooth([p[3] for p in prof])
    return {"back": -min(xs), "fwd": max(xs), "lat": max(abs(v) for v in ys),
            "dyn": max(abs(v) for v in ds)}


# Seuils (mm) : (alerte, refus). Calés sur le seul repère réel disponible :
# l'échauffement v4 a fait TOMBER NAO. Dans ce modèle il atteignait 17 mm vers
# l'arrière et 22 mm vers l'avant, dont 11 mm de part DYNAMIQUE (les deux bras
# accélérés ensemble). Une pose tenue (bras devant : ~13 mm) ne fait pas tomber
# NAO ; ce sont surtout les accélérations : "dyn" est donc le critère principal.
# Le test NAO Party d'origine (joué sans souci) reste sous 10 mm au total.
BALANCE_LIMITS = {"back": (14.0, 20.0), "fwd": (18.0, 25.0), "lat": (16.0, 24.0), "dyn": (6.0, 9.0)}
