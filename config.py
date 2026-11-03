# -*- coding: utf-8 -*-
"""
config.py - Tous les réglages de Just Nao au même endroit.

Ce qui dépend du robot, du réseau ou de la salle de démo se règle ici :
on ne touche pas au code pour changer d'IP, de langue ou de source vidéo.
"""
import os

# --- Dossiers du projet ----------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIBRARY_DIR = os.path.join(BASE_DIR, "choreography", "library")

# --- Connexion NAOqi (remplacées par --ip / --port en ligne de commande) ----
NAO_IP = "192.168.2.121"    # appuyer une fois sur le bouton du torse : NAO dit son IP
NAO_PORT = 9559             # 9559 sur un vrai robot ; autre port pour le robot virtuel
BRIDGE_PORT = 8766          # port de la passerelle Choregraphe (choregraphe_bridge.py)

# --- Musique ----------------------------------------------------------------
# ALAudioPlayer lit les fichiers SUR LE ROBOT, pas sur le PC : on y copie les
# musiques une fois pour toutes (voir README, section "Musique").
ROBOT_AUDIO_DIR = "/home/nao/just_nao/audio"
AUDIO_VOLUME = 0.8          # 0.0 à 1.0

# --- Parole -------------------------------------------------------------------
TTS_LANGUAGE = "English"    # doit être installée sur le robot
TTS_VOLUME = 0.8
COUNTDOWN_TEXT = "Three! Two! One! Let's dance!"

# --- Sécurité -----------------------------------------------------------------
POSTURE = "StandInit"       # posture de référence avant et après chaque danse
POSTURE_SPEED = 0.5         # fraction de la vitesse max (0.0 à 1.0)
PREPOSITION_TIME = 1.5      # s pour rejoindre en douceur la pose de départ d'une danse
DISABLE_AUTONOMOUS_LIFE = True   # sinon NAO bouge la tête tout seul pendant la danse
LIMIT_TOLERANCE = 0.01      # rad de tolérance sur les butées articulaires
SPEED_WARN_RATIO = 0.6      # alerte si un mouvement demande > 60 % de la vitesse max

# --- Surveillance de l'état ---------------------------------------------------
STATUS_PERIOD = 2.0         # s entre deux lectures de l'état du robot
BATTERY_WARN = 20           # % : alerte batterie faible
TEMPERATURE_WARN = 65.0     # °C, seuil indicatif d'alerte moteur
TEMP_JOINTS = [             # moteurs qui chauffent le plus quand NAO reste debout
    "LHipPitch", "RHipPitch", "LKneePitch", "RKneePitch",
    "LAnklePitch", "RAnklePitch", "LShoulderPitch", "RShoulderPitch",
]

# --- Vidéo (HMI) ----------------------------------------------------------------
# 0 = première webcam du PC (pour tester) ; plus tard l'URL du flux annoté
# fourni par le groupe 2, par ex. "http://localhost:8080/stream.mjpg".
# None = panneau vidéo désactivé.
VIDEO_SOURCE = 0
VIDEO_SIZE = (480, 360)
VIDEO_FPS = 25

# =============================================================================
# JEU INTERACTIF (Python 3) : vision, évaluation, résultats
# Toutes ces valeurs sont des points de départ raisonnables, pas des vérités :
# docs/EVALUATION.md explique chacune et comment l'ajuster.
# =============================================================================

# --- Caméra et détection de pose --------------------------------------------------
POSE_MODEL_PATH = os.path.join(BASE_DIR, "models", "pose_landmarker_full.task")
CAMERA_SIZE = (640, 480)        # résolution demandée à la webcam
CAMERA_MIRROR = True            # affichage en miroir (l'analyse, elle, n'est jamais inversée)
VISION_MAX_FPS = 20             # analyses par seconde au maximum
LANDMARK_VISIBILITY_MIN = 0.5   # en dessous, un point est considéré comme masqué
FILTER_MIN_CUTOFF = 1.2         # lissage One Euro : plus petit = plus lisse à l'arrêt
FILTER_BETA = 0.4               # plus grand = moins de retard dans les gestes rapides

# --- Correspondance NAO / joueur -----------------------------------------------------
MAPPING_MODE = "auto"           # "miroir", "meme_cote" ou "auto" (le meilleur des deux)
EVAL_DEPTH = True               # True : directions 3D ; False : plan de face seulement
REFERENCE_DEFAULT_POSE = None   # angles NAO à utiliser hors chorégraphie (None = StandInit approx.)

# --- Synchronisation de l'évaluation ----------------------------------------------------
CAMERA_LATENCY = 0.08           # s entre le geste et l'image reçue
ROBOT_LATENCY = 0.10            # s entre la commande et le mouvement de NAO (passerelle comprise)
TIME_WINDOW_LAG = 1.0           # s de retard du joueur pris en compte au maximum
TIME_WINDOW_LEAD = 0.3          # s d'avance prise en compte au maximum
TIME_FREE_LATE = 0.5            # retard toléré sans pénalité (temps de réaction ; 0,55-0,65 s mesurés sur Macarena)
TIME_FREE_EARLY = 0.15          # avance tolérée sans pénalité
TIME_FLEX = 0.15                # variation permise autour du retard habituel du joueur
TIME_MAX_PENALTY = 0.3          # pénalité maximale (au bord de la fenêtre)

# --- Notation ----------------------------------------------------------------------------
SCORE_TOLERANCES = {            # degrés : (erreur sans pénalité, erreur à note nulle)
    "upper": (20.0, 60.0), "fore": (25.0, 70.0), "knee": (15.0, 45.0)}
FEATURE_WEIGHTS = {"upper": 0.6, "fore": 0.4, "knee": 0.5}
PART_WEIGHTS = {"bras_gauche": 1.0, "bras_droit": 1.0, "jambes": 0.6}
ACTIVITY_WINDOW = 2.0           # s : fenêtre du facteur d'activité
ACTIVITY_FLOOR = 0.25           # note x 0,25 au minimum si le joueur reste figé
ACTIVITY_RATIO = 0.5            # le joueur doit bouger au moins moitié autant que NAO
ACTIVITY_REF_MIN = 25.0         # degrés : en dessous, NAO est considéré immobile
ACTIVITY_NOISE = 6.0            # degrés de tremblement normal par caractéristique
SCORE_BIN = 0.5                 # s : taille des intervalles du bilan
COVERAGE_FREE = 0.9             # 10 % de temps hors champ sans pénalité
MIN_TRACKING = 0.4              # en dessous de 40 % de suivi : partie non évaluable
MIN_EVAL_DURATION = 5.0         # s minimum pour noter une partie
MOVE_SUCCESS = 60.0             # note minimale d'un mouvement "réussi"
SCORE_CATEGORIES = [(90, u"Excellent"), (75, u"Great"), (55, u"Good"),
                    (35, u"Needs work"), (0, u"Try again")]
LIVE_SMOOTHING = 1.0            # s : lissage du score affiché en direct

# --- Messages au joueur -------------------------------------------------------------------
MESSAGE_HOLD = 1.2              # s minimum d'affichage d'un message
FEEDBACK_EXCELLENT = 85.0
FEEDBACK_GOOD = 70.0
FEEDBACK_KEEP = 50.0
FEEDBACK_LATE = 0.55            # s de retard avant "You're a little late!"
VOICE_FEEDBACK = False          # encouragements vocaux PENDANT la danse (rares, désactivés : musique forte)
VOICE_MIN_INTERVAL = 12.0       # s minimum entre deux encouragements vocaux

# --- Résultats --------------------------------------------------------------------------------
RESULTS_DIR = os.path.join(BASE_DIR, "results")
PREPARE_COUNTDOWN = 3           # s de compte à rebours à l'écran avant de lancer NAO
HMI_VIDEO_SIZE = (560, 420)     # taille de la vidéo dans la HMI de jeu

# --- NAO, coach sarcastique : commentaire de fin de danse (anglais) -------------
NAO_SPEAKS = True               # NAO annonce le score et commente (False : affichage seulement)
ROAST_ENABLED = True            # piques sarcastiques ; False : commentaires gentils neutres
ROAST_INTENSITY = "sarcastic"   # "friendly", "sarcastic" ou "savage"
COMMENTARY_LENGTH = "short"     # "short" : score + pique ; "long" : + un fait mesuré
ROAST_PAUSE = 0.7               # s de silence entre l'annonce du score et la pique
ROAST_BANDS = [(90, "excellent"), (71, "good"), (51, "average"), (31, "weak"), (0, "poor")]
ANNOUNCE_INTERRUPTED = True     # petit commentaire aussi quand le joueur arrête la danse
