# -*- coding: utf-8 -*-
"""
tools/compose_choreographies.py - Génère les chorégraphies Macarena, NAO Party,
Warm-up et Mekassarat à partir de poses nommées et d'une grille rythmique.

    python tools/compose_choreographies.py              # les quatre danses
    python tools/compose_choreographies.py macarena     # une seule
    python tools/compose_choreographies.py --check      # vérifie sans écrire

Sorties (dans choreography/library/<danse>/) : motion.json (format Bezier
Choregraphe), et dans meta.json les champs "events" (LEDs, paroles), "moves"
(mouvements nommés pour le bilan) et "composer" (tempo, poses). Les autres
champs de meta.json (titre, musique, chemin sur NAO, sync_offset, scoring...)
sont conservés.

La Calibration n'est PAS générée ici : elle reste un mouvement simple et précis
(tools/make_calibration.py).

Toutes les poses sont écrites pour le bras GAUCHE de NAO ; le bras droit est le
miroir (signes inversés pour Roll et Yaw). Elles ont été vérifiées avec le
modèle de collision de choreography/kinematics.py et sont vérifiées de nouveau,
le long de toute la trajectoire, à chaque génération et avant chaque danse,
ainsi que l'équilibre (déplacement estimé de l'appui, depuis les chutes de NAO
avec l'échauffement v4 : voir docs/DANCES.md §0).
Le résultat n'a PAS encore été validé sur le NAO physique (docs/DANCE_VALIDATION.md).
"""
from __future__ import absolute_import, division, print_function

import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, os.pardir))
sys.path.insert(0, ROOT)

from choreography.beatgrid import BeatGrid  # noqa: E402
from choreography.choreography import Choreography, save_meta, save_motion  # noqa: E402
from choreography.composer import Composer  # noqa: E402
from robot.fake_robot import NAO_LIMITS  # noqa: E402

LIBRARY = os.path.join(ROOT, "choreography", "library")
ARM = ("ShoulderPitch", "ShoulderRoll", "ElbowYaw", "ElbowRoll", "WristYaw", "Hand")
JOINTS = (["HeadYaw", "HeadPitch"] + ["L" + j for j in ARM] + ["R" + j for j in ARM])

# Si, au premier essai sur NAO, la paume est vers le HAUT au "bras tendu" de la
# Macarena, mettre -1 : la rotation des paumes est alors inversée partout.
PALM_TWIST_SIGN = 1.0

# --- Poses du bras GAUCHE (rad ; Hand de 0 fermée à 1 ouverte) -------------------------
#            ShoulderPitch, ShoulderRoll, ElbowYaw, ElbowRoll, WristYaw, Hand
POSES = {
    # Bras le long du corps, coude légèrement plié (proche de StandInit)
    "ready":      (1.30, 0.15, -1.40, -0.90, 0.00, 0.40),
    # Bras devant, un peu bas, coude souple : prêt à se tendre
    "prep":       (0.45, 0.20, -1.00, -0.70, 0.00, 0.60),
    # Après le "Ay !" : le bras gauche redescend devant, à mi-hauteur
    "prep_high":  (0.10, 0.30, -1.00, -0.60, 0.00, 0.60),
    # Macarena 1-2 : bras tendu devant, à hauteur d'épaule, paume vers le bas
    "forward":    (-0.05, 0.22, -0.30, -0.07, -0.15, 1.00),
    # Macarena 3-4 : même bras, paume vers le haut (rotation avant-bras + poignet)
    "palm_up":    (-0.05, 0.22, 1.00, -0.07, 1.72, 1.00),
    # Macarena 5-6 : main vers l'épaule opposée. Le premier bras croise HAUT, le
    # second BAS : les avant-bras restent à ~7 cm l'un de l'autre.
    "cross_high": (-0.35, -0.13, 0.03, -1.35, -1.28, 0.60),
    "cross_low":  (0.30, -0.13, 0.03, -1.35, -1.28, 0.60),
    # Passage vers la tête : avant-bras levé devant l'épaule, la main passe devant le
    # visage à distance (trajectoire cherchée pour garder >= 2 cm de marge, < 50 % vitesse)
    "head_via":   (-0.36, 0.00, -0.63, -0.76, 0.12, 0.70),
    # Macarena 7-8 : main à côté / derrière la tête (NAO ne peut pas la poser derrière)
    "head":       (-0.72, 0.19, -1.19, -1.23, 0.03, 0.70),
    # Macarena 9-10 : main sur le côté de la hanche, coude écarté
    "hip_front":  (1.55, 0.52, -0.76, -0.70, -0.93, 0.30),
    # Macarena 11-12 : main un peu en arrière de la hanche ("poche arrière")
    "hip_back":   (1.75, 0.45, -0.30, -0.45, -1.30, 0.30),
    # Macarena 15 : mains qui remontent devant le visage
    "chest_high": (0.32, 0.15, -1.50, -1.45, 0.00, 0.80),
    # Macarena 16 "Ay !" : bras levés en V, mains ouvertes (NAO Party seulement depuis
    # la version équilibre : lever les deux bras ensemble pousse NAO vers l'arrière)
    "hooray":     (-0.95, 0.75, -1.40, -0.35, 0.00, 1.00),
    # Macarena 16 "Ay !" (version équilibre) : un poing vers le ciel devant, l'autre bras
    # ouvert sur le côté. Bras ouvert = mouvement dans le plan frontal (ShoulderRoll avec
    # le bras vers le bas) : il ne pousse NAO ni vers l'avant ni vers l'arrière.
    "ay_up":      (-0.45, 0.35, -1.00, -0.25, 0.00, 1.00),
    "tada":       (1.35, 1.20, -0.30, -0.25, 0.00, 1.00),
    # --- Warm-up / NAO Party ---
    "front":      (-0.05, 0.15, -1.40, -0.07, 0.00, 1.00),    # bras devant, paumes face à face
    "side":       (0.00, 1.15, -1.40, -0.10, 0.00, 1.00),     # bras à l'horizontale sur le côté
    "up":         (-1.35, 0.35, -1.40, -0.15, 0.00, 1.00),    # bras levé, un peu ouvert
    "down":       (1.45, 0.12, -1.20, -0.35, 0.00, 0.50),     # bras le long du corps
    "curl":       (0.25, 0.25, -1.40, -1.40, 0.00, 0.20),     # biceps : avant-bras vers le haut
    "punch":      (0.05, -0.05, -0.60, -0.07, 0.00, 0.10),    # poing devant, bras tendu
    "guard":      (0.55, 0.25, -0.60, -1.30, 0.00, 0.10),     # poing replié devant la poitrine
    "wave_out":   (-0.70, 0.90, -1.40, -0.60, 0.00, 1.00),    # main levée, ouverte (salut)
    "wave_in":    (-0.70, 0.60, -1.40, -1.10, 0.00, 1.00),
    "disco_up":   (-0.75, 0.70, -1.40, -0.20, 0.00, 0.20),    # disco : doigt vers le ciel, en diagonale
    "disco_down": (0.65, -0.05, -1.40, -0.20, 0.00, 0.20),    # disco : bras en bas devant, en travers
    # Echauffement prudent : amplitudes faibles autour de la position de repos.
    # Aucune elevation au-dessus des epaules, pas de mouvement simultane ample.
    # --- Poses "équilibre" (version 2026-11-02 après la chute de NAO) ---
    # Ouverture latérale : le bras reste vers le bas (ShoulderPitch ~1.5) et s'écarte
    # par ShoulderRoll, dans le plan frontal : il ne pousse NAO ni en avant ni en arrière.
    "side_lat":   (1.50, 1.20, -1.40, -0.15, 0.00, 1.00),
    "side_mid":   (1.50, 0.70, -1.40, -0.25, 0.00, 0.80),
    "reach_up":   (-1.20, 0.30, -1.40, -0.15, 0.00, 1.00),    # un bras au-dessus de la tête
    "front_low":  (0.55, 0.15, -1.40, -0.25, 0.00, 0.80),     # bras devant, vers le bas
    "curl_hi":    (0.55, 0.22, -1.40, -1.40, 0.00, 0.30),     # avant-bras levé (biceps)
    "curl_lo":    (0.55, 0.22, -1.40, -0.30, 0.00, 0.70),     # avant-bras redescendu
    "chest_open": (1.00, 0.95, -1.40, -1.30, 0.00, 0.70),     # mains devant la poitrine, coudes ouverts
    "chest_close": (1.00, 0.30, -1.40, -1.30, 0.00, 0.70),    # coudes rentrés
    # --- Mekassarat ---
    "twirl_a":    (0.35, 0.42, -1.40, -1.30, -1.30, 1.00),    # mains levées devant, poignets tournés
    "twirl_b":    (0.35, 0.62, -1.40, -1.30, 1.30, 0.60),
    "flap_out":   (0.95, 0.90, -1.40, -1.35, 0.00, 0.50),     # "ailes" : coudes ouverts
    "flap_in":    (0.95, 0.35, -1.40, -1.35, 0.00, 0.50),
    "point_up":   (-0.75, 0.85, -1.20, -0.10, 0.00, 0.10),    # doigt vers le ciel, en diagonale sur le côté
    "side_high":  (-0.60, 1.25, -1.40, -0.15, 0.00, 1.00),    # bras sur le côté, un peu au-dessus de l'horizontale
    "snake_up":   (1.20, 1.15, -1.40, -0.70, 0.60, 1.00),     # bras ouverts, coude qui ondule
    "snake_down": (1.35, 1.05, -1.40, -0.10, -0.60, 1.00),
    "warm_rest": (1.40, 0.12, -1.20, -0.35, 0.00, 0.50),
    "warm_small": (0.38, 0.20, -1.20, -0.45, 0.00, 0.75),
    "warm_elbow": (0.98, 0.18, -1.20, -1.15, 0.00, 0.75),
    "warm_open": (0.95, 0.57, -1.20, -0.50, 0.00, 0.80),
}


def arm(side, name, **override):
    """Pose `name` pour le bras `side` ("L" ou "R"), miroir pour le bras droit."""
    p, r, ey, er, wy, hand = POSES[name]
    if name in ("forward", "palm_up"):
        wy *= PALM_TWIST_SIGN
        ey = ey * PALM_TWIST_SIGN if name == "palm_up" else ey
    values = {"ShoulderPitch": p, "ShoulderRoll": r, "ElbowYaw": ey, "ElbowRoll": er,
              "WristYaw": wy, "Hand": hand}
    values.update(override)
    if side == "R":
        for j in ("ShoulderRoll", "ElbowYaw", "ElbowRoll", "WristYaw"):
            values[j] = -values[j]
    return dict((side + j, v) for j, v in values.items())


def both(name_l, name_r=None, **override):
    pose = arm("L", name_l, **override)
    pose.update(arm("R", name_r or name_l, **override))
    return pose


def head(yaw=0.0, pitch=0.0):
    return {"HeadYaw": yaw, "HeadPitch": pitch}


class Dance(object):
    """
    Raccourcis de composition sur une grille : chaque appel place une pose ATTEINTE
    sur un temps (indice de temps, fractions permises). Le départ du geste est
    calculé par Composer.arrive() pour rester sous MAX_RATIO de la vitesse max.
    """
    MAX_RATIO = 0.5

    def __init__(self, grid, min_travel_beats=0.6):
        self.grid = grid
        self.comp = Composer(JOINTS)
        self.min_travel = min_travel_beats * grid.period

    def start(self, beat, pose_l, pose_r=None, yaw=0.0, pitch=0.0):
        t = self.grid.time(beat)
        self.comp.key(t, both(pose_l, pose_r))
        self.comp.key(t, head(yaw, pitch))

    def _arrive(self, beat, pose, travel, flow, hold=None, ratio=None):
        ratio = ratio or self.MAX_RATIO
        if flow:
            # geste enchaîné : pas de tenue, la courbe passe par la pose sans s'arrêter
            # si le mouvement continue dans le même sens
            self.comp.arrive(self.grid.time(beat), pose, NAO_LIMITS, ratio, min_travel=1e3, min_hold=0.0)
        else:
            self.comp.arrive(self.grid.time(beat), pose, NAO_LIMITS, ratio,
                             self.min_travel if travel is None else travel * self.grid.period,
                             min_hold=0.08 if hold is None else hold * self.grid.period)

    def arm(self, side, beat, name, travel=None, flow=False, hold=None, ratio=None, **override):
        sides = ("L", "R") if side == "LR" else (side,)
        pose = {}
        for sd in sides:
            pose.update(arm(sd, name, **override))
        self._arrive(beat, pose, travel, flow, hold, ratio)

    def arms(self, beat, name_l, name_r, travel=None, flow=False, hold=None, ratio=None, **override):
        pose = arm("L", name_l, **override)
        pose.update(arm("R", name_r, **override))
        self._arrive(beat, pose, travel, flow, hold, ratio)

    def hands(self, beat, left, right, travel=0.3):
        self.comp.arrive(self.grid.time(beat), {"LHand": left, "RHand": right}, NAO_LIMITS,
                         self.MAX_RATIO, travel * self.grid.period)

    def head(self, beat, yaw=0.0, pitch=0.0, travel=None):
        self.comp.arrive(self.grid.time(beat), head(yaw, pitch), NAO_LIMITS, self.MAX_RATIO,
                         self.min_travel if travel is None else travel * self.grid.period)

    def move(self, beat0, beat1, name):
        self.comp.move(self.grid.time(beat0), self.grid.time(beat1), name)

    def leds(self, beat, color, duration=0.12):
        self.comp.event(self.grid.time(beat), type="leds", color=color, duration=duration)

    def say(self, t, text):
        self.comp.event(t, type="say", text=text)


# =============================================================================
# MACARENA
# =============================================================================
MAC_MOVES = [(1, "Right arm out"), (3, "Palms up"), (5, "Hands to shoulders"),
             (7, "Hands behind head"), (9, "Hands on hips"), (11, "Hands behind hips"),
             (13, "Wiggle"), (15, "Ay!")]                # 16 : poing droit en l'air, bras gauche ouvert

# Variation de chaque cycle de 16 temps (les gestes restent ceux de la Macarena)
#   head : "front"  regard droit, petit hochement sur les hanches ;
#          "follow" la tête regarde la main qui vient de bouger ;
#          "groove" petit hochement de tête sur chaque temps
#   big  : bras tendus un peu plus haut, "Ay !" un peu plus ouvert
MAC_STYLES = [
    {"head": "front", "big": False},      # 1 : version de base, la plus lisible
    {"head": "follow", "big": False},     # 2 : la tête suit les mains
    {"head": "groove", "big": True},      # 3 : nouvelle phrase musicale, plus de rebond
    {"head": "follow", "big": True},      # 4
    {"head": "groove", "big": True},      # 5
    {"head": "front", "big": False},      # 6 : musique moins forte, plus sobre
    {"head": "follow", "big": True},      # 7 : final, "Ay !" tenu jusqu'à la fin
]


def macarena(grid):
    # Gestes sur ~0,9 temps (au lieu de 0,6) : accélérations plus douces pour l'équilibre
    d = Dance(grid, min_travel_beats=0.9)
    cycles = grid.n_cycles()
    # Pose de départ (rejointe avant la musique) : bras droit déjà levé devant, prêt.
    d.start(grid.cycle_start(0) - 1, "ready", "prep")
    for c in range(cycles):
        style = MAC_STYLES[c % len(MAC_STYLES)]
        b = grid.cycle_start(c) - 1                    # b + n = temps n du cycle (1..16)
        up = 0.06 if style["big"] else 0.0
        fwd = {"ShoulderPitch": POSES["forward"][0] - up}
        palm = {"ShoulderPitch": POSES["palm_up"][0] - up}

        # 1-2 : bras droit puis gauche tendus devant. Le gauche part dès la fin du "Ay !"
        # (geste lent sur ~1,7 temps : moins d'à-coup pour l'équilibre)
        d.arm("R", b + 1, "forward", **fwd)
        d.arm("L", b + 2, "forward", travel=1.8, **fwd)
        # 3-4 : paumes vers le haut, l'une après l'autre
        d.arm("R", b + 3, "palm_up", **palm)
        d.arm("L", b + 4, "palm_up", **palm)
        # 5-6 : main vers l'épaule opposée (droite en haut, gauche en dessous)
        d.arm("R", b + 5, "cross_high")
        d.arm("L", b + 6, "cross_low")
        # 7-8 : mains derrière la tête. Le bras droit reste croisé jusqu'au "6" (les deux
        # bras sont croisés un instant), puis passe par un point de passage (head_via)
        # sans s'arrêter, pour contourner le visage.
        d.arm("R", b + 6.25, "head_via", travel=0.85)
        d.arm("R", b + 7, "head", flow=True)
        d.arm("L", b + 7.25, "head_via", travel=0.85)
        d.arm("L", b + 8, "head", flow=True)
        # 9-10 : mains sur les hanches. Le geste tête -> hanche est le plus long de la
        # danse (2,3 rad à l'épaule) : il part 1/3 de temps après l'arrivée à la tête et
        # dure ~1,6 temps, à 55 % au plus de la vitesse max (au lieu de 50 %).
        d.arm("R", b + 9, "hip_front", hold=0.12, ratio=0.47)
        d.arm("L", b + 10, "hip_front", hold=0.12, ratio=0.47)
        # 11-12 : mains derrière les hanches
        d.arm("R", b + 11, "hip_back")
        d.arm("L", b + 12, "hip_back")
        # 13-15 : "Dale a tu cuerpo alegria" : coudes qui pompent (le bassin de NAO ne
        # bouge pas : le mouvement passe dans les épaules et la tête). Le bras droit
        # monte doucement vers le "Ay !" pendant que le gauche pompe encore.
        d.arm("R", b + 13, "hip_back", travel=0.9, ShoulderRoll=0.62)
        d.arm("L", b + 13, "hip_back", travel=0.9, ShoulderRoll=0.42)
        d.arm("L", b + 14, "hip_back", travel=0.9, ShoulderRoll=0.62)
        d.arm("L", b + 15, "hip_back", travel=0.9, ShoulderRoll=0.42)
        # 16 "Ay !" : poing droit vers le ciel, bras gauche ouvert sur le côté
        ay = {"ShoulderRoll": POSES["ay_up"][1] + up}
        d.arm("R", b + 16, "ay_up", travel=2.6, **ay)
        d.arm("L", b + 16, "tada", travel=0.95, ShoulderRoll=POSES["tada"][1] + up)
        if c == cycles - 1:
            final = arm("R", "ay_up", **ay)
            final.update(arm("L", "tada", ShoulderRoll=POSES["tada"][1] + up))
            d.comp.key(grid.time(b + 16) + 0.55, final)

        _macarena_head(d, b, style["head"])
        for n, name in MAC_MOVES:
            d.move(b + n, b + n + 2, name)
        d.leds(b + 1, "#00BFFF" if c % 2 == 0 else "#FF55AA", 0.15)
        d.leds(b + 16, "#FFD400", 0.2)
    if cycles:
        d.head(grid.cycle_start(cycles - 1) + 15 + 0.95, 0.0, -0.18, travel=0.3)
    # Courtes remarques pendant la danse (ne pretendent pas mesurer le joueur).
    if cycles >= 5:
        d.say(grid.time(grid.cycle_start(2)) - 0.2, "Come on, my grandma has more rhythm!")
        d.say(grid.time(grid.cycle_start(5)) - 0.2, "Are you dancing, or buffering?")
    return d.comp


def _macarena_head(d, b, mode):
    y = 0.22
    if mode == "follow":
        # la tête regarde la main qui vient de bouger (côté droit de NAO = yaw négatif)
        for n, yaw in ((1, -y), (2, y), (3, -y), (4, y), (5, 0.0), (7, -y), (8, y), (9, -0.12), (10, 0.12),
                       (12, 0.0)):
            d.head(b + n, yaw, 0.05)
    elif mode == "groove":
        # hochement : tête un peu basse sur le temps, relevée entre deux temps
        for n in (1, 2, 3, 4, 5, 6, 7, 10, 11, 12):     # pas pendant le grand geste tête -> hanche
            d.head(b + n, 0.0, 0.07, travel=0.45)
            d.head(b + n + 0.5, 0.0, -0.02, travel=0.45)
    else:
        d.head(b + 1, 0.0, 0.0)
        d.head(b + 9, 0.0, 0.08)
        d.head(b + 12, 0.0, 0.0)
    # 13-14 : la tête balance de droite à gauche ; 15 : regard en face ; 16 : tête levée
    d.head(b + 13, -0.30, 0.05, travel=0.9)
    d.head(b + 14, 0.30, 0.05, travel=0.9)
    d.head(b + 15, 0.0, 0.0, travel=0.9)
    d.head(b + 16, 0.0, -0.12, travel=0.9)


# =============================================================================
# WARM-UP (sans musique, 96 BPM, version équilibre)
# =============================================================================
def warmup():
    """
    Échauffement, version équilibre (2026-11-02, après la chute de NAO avec la v4).

    Rythme vivant mais sans à-coup : une pose tous les 2 temps à 96 BPM (1,25 s),
    puis un geste par temps pour les biceps. Deux règles d'équilibre :
    - jamais les deux bras ensemble vers l'avant / l'arrière / le haut : soit un
      seul bras, soit les deux en OPPOSITION (l'un monte quand l'autre descend :
      leurs élans s'annulent) ;
    - les gestes à deux bras se font sur le CÔTÉ (plan frontal), symétriques.
    """
    grid = BeatGrid.regular(bpm=96.0, first_beat=1.0, count=48, phrase_length=8)
    d = Dance(grid, min_travel_beats=1.2)
    d.start(0, "down")
    blocks = [
        # (1er temps, nom du mouvement, consigne, [(temps relatif, pose gauche, pose droite, durée du geste)])
        (1, "Arms out to the sides", "Open your arms to the sides!",
         [(2, "side_lat", "side_lat", 1.8), (4, "down", "down", 1.8),
          (6, "side_lat", "side_lat", 1.8), (8, "down", "down", 1.8)]),
        (9, "One arm forward, then the other", "One arm forward, then the other!",
         [(2, "down", "front", 1.8), (4, "front", "down", 1.8),
          (6, "down", "front", 1.8), (8, "front", "down", 1.8)]),
        # Lever les bras PAR LE CÔTÉ (pas par devant) : l'élan reste dans le plan frontal
        (17, "Arms up through the sides", "Now reach up, through the sides!",
         [(2, "side_lat", "side_lat", 1.8), (3.5, "side_high", "side_high", "flow"), (5, "reach_up", "reach_up", "flow"),
          (6.5, "side_high", "side_high", 1.4), (8, "side_lat", "side_lat", "flow")]),
        (25, "Elbow curls", "Bend your elbows, one after the other!",
         [(2, "curl_lo", "curl_lo", 1.9), (3, "curl_hi", "curl_lo", 0.9), (4, "curl_lo", "curl_hi", 0.9),
          (5, "curl_hi", "curl_lo", 0.9), (6, "curl_lo", "curl_hi", 0.9), (7, "curl_hi", "curl_lo", 0.9),
          (8, "curl_lo", "curl_hi", 0.9)]),
        (33, "Open and close", "Open your chest!",
         [(2, "chest_open", "chest_open", 1.8), (4, "chest_close", "chest_close", 1.8),
          (6, "chest_open", "chest_open", 1.8), (8, "chest_close", "chest_close", 1.8)]),
    ]
    for start, name, cue, steps in blocks:
        b = start - 1
        d.say(max(0.0, grid.time(b) - 0.3), cue)
        d.leds(b + 1, "#00A0FF", 0.1)
        for n, lname, rname, travel in steps:
            if travel == "flow":
                d.arms(b + n, lname, rname, flow=True)     # geste continu, sans arrêt
            else:
                d.arms(b + n, lname, rname, travel=travel)
        d.move(b + 1, b + 9, name)
    d.arms(42, "side_mid", "side_mid", travel=1.8)
    d.arms(44, "down", "down", travel=1.8)
    # La tête suit le bras qui travaille (petits mouvements)
    for n, yaw in ((10, -0.15), (12, 0.15), (14, -0.15), (16, 0.15), (18, -0.15), (20, 0.15),
                   (22, -0.15), (24, 0.15), (26, 0.0)):
        d.head(n, yaw, 0.0)
    d.say(grid.time(21), "Easy there, I am not a helicopter!")
    d.say(grid.time(37), "Looking good! My grandma approves!")
    d.say(grid.time(44), "Great warm-up!")
    return d.comp, grid


# =============================================================================
# NAO PARTY (sans musique, 112 BPM, paroles et LEDs) - version équilibre
# =============================================================================
def nao_party():
    grid = BeatGrid.regular(bpm=112.0, first_beat=4.6, count=72, phrase_length=16)
    d = Dance(grid, min_travel_beats=0.8)
    d.start(-2, "down")
    # Intro parlée avant le premier temps, comme le test Choregraphe d'origine
    d.say(0.0, "Hey everybody!")
    d.say(1.6, "Are you ready to party?")
    d.say(3.2, "Let's go!")
    lyrics = [(1, "Wave your hands!"), (17, "Punch! Punch!"), (33, "Disco time!"), (49, "Big finish!")]
    for n, text in lyrics:
        d.say(grid.time(n) - 0.6, text)
    colors = ["#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#FF00FF", "#00FFFF"]
    for i, n in enumerate(range(1, 65, 4)):
        d.leds(n, colors[i % len(colors)], 0.1)

    # Phrase 1 (1-16) : salut d'une main, de l'autre, puis des deux ; les bras
    # redescendent par le côté
    d.arm("L", 1, "wave_out", travel=2.6)
    for n in (2, 3):
        d.arm("L", n, "wave_in" if n % 2 == 0 else "wave_out")
    d.arm("L", 6, "side_mid", travel=2.0)
    d.arm("R", 4, "wave_out", travel=2.4)
    for n in (5, 6, 7):
        d.arm("R", n, "wave_in" if n % 2 == 1 else "wave_out")
    d.arm("L", 8, "wave_out", travel=1.9)
    d.arm("R", 8, "wave_out")
    for n in (9, 10, 11, 12):
        w = "wave_in" if n % 2 == 1 else "wave_out"
        d.arms(n, w, w)
    d.arms(14, "side_lat", "side_lat", travel=1.9)
    d.arms(16, "side_mid", "side_mid", travel=1.8)
    d.move(1, 9, "Wave")
    d.move(9, 17, "Wave with both hands")
    # Phrase 2 (17-32) : garde, puis coups de poing ALTERNÉS : un bras se tend
    # pendant que l'autre revient (élans opposés)
    d.arms(18, "guard", "guard", travel=1.9)
    for k, n in enumerate(range(19, 29)):
        left = (k % 2 == 0)
        d.arms(n, "punch" if left else "guard", "guard" if left else "punch", travel=0.9)
    d.arms(30, "guard", "guard", travel=1.0)
    d.move(17, 29, "Punches")
    d.move(29, 33, "Guard")
    # Phrase 3 (33-48) : disco, un bras vers le ciel, l'autre en bas, en opposition
    for k in range(8):
        n = 33 + 2 * k
        if k % 2 == 0:
            d.arms(n, "disco_down", "disco_up", travel=1.8)
        else:
            d.arms(n, "disco_up", "disco_down", travel=1.8)
        d.hands(n + 1, 1.0, 1.0, travel=0.45)     # mains qui s'ouvrent entre deux "points"
        d.hands(n + 1.7, 0.2, 0.2, travel=0.45)
    d.move(33, 41, "Disco")
    d.move(41, 49, "Disco")
    # Phrase 4 (49-64) : "ailes" (coudes qui s'ouvrent et se ferment), bras ouverts qui
    # ondulent, grand final bras ouverts sur le côté
    d.arms(50, "flap_in", "flap_in", travel=1.9)
    for n in range(51, 57):
        f = "flap_out" if n % 2 == 1 else "flap_in"
        d.arms(n, f, f, travel=0.9)
    d.arms(58, "snake_up", "snake_down", travel=1.8)
    for n in (59, 60, 61, 62):
        if n % 2 == 1:
            d.arms(n, "snake_down", "snake_up", travel=0.9)
        else:
            d.arms(n, "snake_up", "snake_down", travel=0.9)
    d.arms(64, "tada", "tada", travel=1.8)
    d.comp.key(grid.time(64) + 1.2, both("tada"))
    d.move(49, 57, "Wings")
    d.move(57, 65, "Snake arms and big finish")
    # Tête : droite / gauche en rythme, droite pendant les coups de poing
    for n in range(1, 64, 2):
        if 17 <= n < 31:
            d.head(n, 0.0, 0.06 if n % 4 == 1 else 0.0)
        else:
            yaw = 0.18 if (n // 4) % 2 == 0 else -0.18
            d.head(n, yaw, 0.04)
    d.head(64, 0.0, -0.12)
    d.say(grid.time(24), "Nice moves! Keep up with me!")
    d.say(grid.time(45), "Those arms look a little rusty!")
    d.say(grid.time(64) + 1.4, "Thank you!")
    return d.comp, grid


# =============================================================================
# MEKASSARAT (Ahmed Saad), extrait 0:17.55 -> 1:06 du morceau, 110 BPM
# =============================================================================
MEK_COLORS = ["#FF8C00", "#FFD400", "#FF2D55", "#00E5FF", "#B000FF", "#00FF66"]


def mekassarat(grid):
    """
    89 temps (j = 0..88), phrases de 16 temps mesurées dans beats.json :
      j 0-15  montée (peu de percussions)  -> poignets qui tournent, mains qui montent
      j 16-31 la grosse caisse arrive      -> "ailes", puis doigt vers le ciel en alternance
      j 32-47 groove plus fort             -> bras ouverts qui ondulent (serpent)
      j 48-63                              -> une main qui salue au-dessus de la tête, puis l'autre
      j 64-79                              -> disco en opposition
      j 80-88 final (le plus fort)         -> ailes rapides, puis bras ouverts sur le coup final (j 88)
    Règles d'équilibre comme l'échauffement : bras en opposition ou mouvements de côté.
    """
    d = Dance(grid, min_travel_beats=0.8)
    j = lambda n: grid.phrase_phase + n                 # noqa: E731  (j = temps de l'extrait)
    d.start(j(0), "down")

    # j 0-15 : poignets qui tournent devant la poitrine, puis plus haut
    d.arms(j(2), "twirl_a", "twirl_a", travel=1.9)
    for n in range(3, 16):
        lift = {"ShoulderPitch": POSES["twirl_a"][0] - (0.25 if n >= 8 else 0.0)}
        if n % 2 == 1:
            d.arms(j(n), "twirl_b", "twirl_a", travel=0.9, **lift)
        else:
            d.arms(j(n), "twirl_a", "twirl_b", travel=0.9, **lift)
    d.move(j(0), j(8), "Hand twirls")
    d.move(j(8), j(16), "Hand twirls up high")

    # j 16-31 : "ailes" sur chaque temps, puis doigt vers le ciel, en alternance
    d.arms(j(17), "flap_in", "flap_in", travel=1.8)
    for n in range(18, 24):
        f = "flap_out" if n % 2 == 0 else "flap_in"
        d.arms(j(n), f, f, travel=0.9)
    for k, n in enumerate(range(25, 32, 2)):
        # un doigt vers le ciel, l'autre main devant la poitrine
        if k % 2 == 0:
            d.arms(j(n), "flap_in", "point_up", travel=1.8)
        else:
            d.arms(j(n), "point_up", "flap_in", travel=1.8)
    d.move(j(16), j(24), "Wings")
    d.move(j(24), j(32), "Point to the sky")

    # j 32-47 : bras ouverts qui ondulent, en opposition gauche / droite
    d.arms(j(33), "snake_up", "snake_down", travel=1.9)
    for n in range(34, 48):
        if n % 2 == 0:
            d.arms(j(n), "snake_down", "snake_up", travel=0.9)
        else:
            d.arms(j(n), "snake_up", "snake_down", travel=0.9)
    d.move(j(32), j(40), "Snake arms")
    d.move(j(40), j(48), "Snake arms")

    # j 48-63 : main droite qui salue au-dessus de la tête (gauche sur la hanche), puis
    # l'autre. Les deux grands gestes (monter / descendre) ne se font pas en même temps.
    d.arm("L", j(49), "hip_front", travel=1.6)
    d.arm("R", j(50), "wave_out", travel=2.6)
    for n in (51, 52, 53, 54):
        d.arm("R", j(n), "wave_in" if n % 2 == 1 else "wave_out", travel=0.9)
    d.arm("R", j(57), "hip_front", travel=2.4)
    d.arm("L", j(59), "wave_out", travel=2.4)
    for n in (60, 61, 62):
        d.arm("L", j(n), "wave_in" if n % 2 == 0 else "wave_out", travel=0.9)
    d.move(j(48), j(56), "Wave up high")
    d.move(j(56), j(64), "Wave with the other hand")

    # j 64-79 : disco en opposition, mains qui scintillent
    for k in range(8):
        n = 65 + 2 * k
        if k == 0:
            d.arms(j(n), "disco_down", "disco_up", travel=2.4)
        elif k % 2 == 0:
            d.arms(j(n), "disco_down", "disco_up", travel=1.8)
        else:
            d.arms(j(n), "disco_up", "disco_down", travel=1.8)
        if k < 7:                                       # pas juste avant le final
            d.hands(j(n + 1), 1.0, 1.0, travel=0.45)
            d.hands(j(n + 1.7), 0.2, 0.2, travel=0.45)
    d.move(j(64), j(72), "Disco")
    d.move(j(72), j(80), "Disco")

    # j 80-88 : final, ailes sur chaque temps puis bras ouverts sur le coup final
    d.arms(j(81), "flap_in", "flap_in", travel=1.9)
    for n in range(82, 87):
        f = "flap_out" if n % 2 == 0 else "flap_in"
        d.arms(j(n), f, f, travel=0.9)
    d.arms(j(88), "tada", "tada", travel=1.9)
    d.comp.key(grid.time(j(88)) + 0.3, both("tada"))
    d.move(j(80), j(88), "Big finish")

    # Tête : hochement sur les temps forts, balancement gauche / droite dans le groove
    for n in range(1, 88, 2):
        if n < 16:
            d.head(j(n), 0.0, 0.07, travel=0.9)
            d.head(j(n + 1), 0.0, 0.0, travel=0.9)
        elif n < 80:
            yaw = 0.2 if (n // 2) % 2 == 0 else -0.2
            d.head(j(n), yaw, 0.04, travel=1.6)
        else:
            d.head(j(n), 0.0, 0.08, travel=0.9)
            d.head(j(n + 1), 0.0, 0.0, travel=0.9)
    d.head(j(88), 0.0, -0.12, travel=0.9)

    # LEDs : une couleur par phrase, flash au retour de la grosse caisse, au final, au coup final
    for k, n in enumerate(range(0, 81, 16)):
        d.leds(j(n), MEK_COLORS[k % len(MEK_COLORS)], 0.15)
    for n in range(80, 88, 2):
        d.leds(j(n), "#FFFFFF", 0.08)
    d.leds(j(88), "#FFD400", 0.3)
    # Deux remarques pendant la danse (comme les autres danses)
    d.say(grid.time(j(32)) - 0.4, "Yalla! Show me your moves!")
    d.say(grid.time(j(64)) - 0.4, "Even my circuits are dancing!")
    return d.comp


# =============================================================================
def write(folder, comp, meta_update, check_only=False):
    names, times, keys = comp.to_motion()
    meta_path = os.path.join(folder, "meta.json")
    with io.open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    meta.update(meta_update)
    meta["events"] = sorted(comp.events, key=lambda e: e["t"])
    meta["moves"] = comp.moves
    if check_only:
        return names, times, keys, meta
    save_motion(os.path.join(folder, "motion.json"), names, times, keys)
    save_meta(meta_path, meta)
    return names, times, keys, meta


def report(folder):
    ch = Choreography(folder)
    limits = dict((n, NAO_LIMITS.get(n)) for n in ch.names)
    errors, warnings = ch.validate(limits, speed_warn_ratio=0.5, collision_step=0.01)
    from choreography.reference_pose import ReferenceTimeline
    tl = ReferenceTimeline(ch)
    worst = {}
    for name in ch.names:
        track = tl.tracks[name]
        t0, t1 = ch.times[ch.names.index(name)][0], ch.times[ch.names.index(name)][-1]
        n = int((t1 - t0) / 0.005)
        prev, best = track.value(t0), 0.0
        for k in range(1, n + 1):
            v = track.value(t0 + k * 0.005)
            best = max(best, abs(v - prev) / 0.005)
            prev = v
        worst[name] = best / NAO_LIMITS[name][2]
    top = sorted(worst.items(), key=lambda kv: -kv[1])[:4]
    from choreography.kinematics import balance_summary
    bal = balance_summary(tl.pose_at, tl.first_key_time, tl.last_key_time, step=0.02)
    print("  %s : equilibre (ZMP) recul %.1f mm, avancee %.1f mm, cote %.1f mm, part dynamique %.1f mm"
          % (ch.id, bal["back"], bal["fwd"], bal["lat"], bal["dyn"]))
    print("  %s : %d articulations, %d cles, fin %.1f s ; vitesse max %s"
          % (ch.id, len(ch.names), sum(len(t) for t in ch.times), ch.end,
             ", ".join("%s %d%%" % (n, 100 * r) for n, r in top)))
    for e in errors:
        print("  [ERREUR] " + e)
    for w in warnings:
        print("  [ATTENTION] " + w)
    return errors


def main(argv=None):
    p = argparse.ArgumentParser(description="Genere les choregraphies a partir des poses et du rythme")
    p.add_argument("which", nargs="*", default=["macarena", "nao_party", "echauffement", "mekassarat"])
    p.add_argument("--check", action="store_true", help="verifier sans modifier la bibliotheque")
    args = p.parse_args(argv)
    failed = False
    for which in args.which:
        folder = os.path.join(LIBRARY, which)
        if which == "macarena":
            grid = BeatGrid.load(os.path.join(folder, "beats.json"))
            comp = macarena(grid)
            last = max(t for tr in comp.tracks.values() for t, _ in tr)
            update = {"description": "Upper-body Macarena on the beat (103 BPM): arms out, palms up, "
                                     "shoulders, head, hips, elbows and \"Ay!\", 7 times with variations.",
                      "end": round(max(last + 0.05, grid.time(len(grid.beats) - 1) + 0.6), 2),
                      "scoring": {"start": round(grid.time(grid.cycle_start(0)), 2), "end": round(last, 2)},
                      "composer": {"bpm": round(grid.bpm, 2), "first_beat": grid.beats[0],
                                   "cycles": grid.n_cycles(), "beats_file": "beats.json"}}
        elif which == "mekassarat":
            grid = BeatGrid.load(os.path.join(folder, "beats.json"))
            comp = mekassarat(grid)
            last = max(t for tr in comp.tracks.values() for t, _ in tr)
            update = {"title": "Mekassarat (Ahmed Saad)",
                      "description": "Egyptian pop at 110 BPM: hand twirls, wings, pointing to the sky, "
                                     "snake arms, waves and disco, with a big finish.",
                      "difficulty": "medium",
                      "audio": "mekassarat_extrait.wav",
                      "audio_robot": "/home/nao/music/mekassarat_extrait.wav",
                      "audio_start": 0.0, "countdown": False,
                      "end": round(min(grid.time(len(grid.beats) - 1) + 0.38, 48.45), 2),
                      "scoring": {"start": round(grid.time(grid.phrase_phase + 2), 2), "end": round(last, 2)},
                      "composer": {"bpm": round(grid.bpm, 2), "first_beat": grid.beats[0],
                                   "beats_file": "beats.json",
                                   "source": "Ahmed Saad - Mekassarat, 0:17.55 -> 1:06.00"}}
        elif which == "echauffement":
            comp, grid = warmup()
            last = max(t for tr in comp.tracks.values() for t, _ in tr)
            update = {"description": "Arms out to the sides, one arm forward then the other, reach up, "
                                     "elbow curls, open and close: lively but gentle on NAO's balance.",
                      "end": round(last + 1.2, 2), "countdown": True,
                      "composer": {"bpm": round(grid.bpm, 2), "first_beat": grid.beats[0]}}
        elif which == "nao_party":
            comp, grid = nao_party()
            last = max(t for tr in comp.tracks.values() for t, _ in tr)
            update = {"description": "Waves, punches, disco, wings, snake arms and a big finish at 112 BPM, "
                                     "with NAO's voice and eye LEDs (no music).",
                      "end": round(last + 1.5, 2), "countdown": False,
                      "composer": {"bpm": round(grid.bpm, 2), "first_beat": grid.beats[0]}}
        else:
            print("choregraphie inconnue : %s" % which)
            return 2
        if args.check:
            # Vérification seule : la danse est écrite dans une copie temporaire du dossier
            import shutil
            import tempfile
            tmp = tempfile.mkdtemp(prefix="jn_check_")
            try:
                copy = os.path.join(tmp, which)
                shutil.copytree(folder, copy)
                write(copy, comp, update)
                failed = bool(report(copy)) or failed
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        else:
            write(folder, comp, update)
            failed = bool(report(folder)) or failed
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
