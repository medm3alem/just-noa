# -*- coding: utf-8 -*-
"""
robot/base.py - LE CONTRAT commun à tous les robots du projet.

NaoRobot (vrai NAOqi, robot réel ou virtuel) et FakeRobot (simulation) offrent
exactement ces méthodes. Le lecteur, le contrôleur et les interfaces ne
connaissent QUE ce contrat : on développe sur FakeRobot, puis on branche le
vrai robot sans rien changer ailleurs.

Règle d'équipe : on ne modifie pas une signature sans prévenir les deux autres.

Conventions :
- angles en radians, temps en secondes ;
- les méthodes marquées "bloquant" ne rendent la main qu'à la fin de l'action
  (ou quand la méthode stop_* correspondante est appelée depuis un autre thread).
"""
from __future__ import absolute_import, print_function


class RobotError(Exception):
    """Erreur compréhensible par l'utilisateur (robot injoignable, fichier absent...)."""


class Robot(object):
    name = "robot"

    def __init__(self, log=None):
        # Fonction d'affichage des messages. Le contrôleur la remplace par la
        # sienne pour que tout arrive dans le même journal (console ou HMI).
        self.log = log or print

    # --- Connexion -------------------------------------------------------------
    def connect(self):
        """Ouvre la connexion. Lève RobotError si impossible."""
        raise NotImplementedError

    def close(self):
        """Ferme proprement la connexion."""
        raise NotImplementedError

    # --- Cycle de vie (bloquant) ----------------------------------------------
    def wake_up(self):
        """Active les moteurs (stiffness)."""
        raise NotImplementedError

    def rest(self):
        """Position accroupie sûre, moteurs relâchés."""
        raise NotImplementedError

    def go_to_posture(self, posture, speed):
        """Rejoint une posture prédéfinie ("StandInit", "Stand", "Crouch"...)."""
        raise NotImplementedError

    def is_awake(self):
        """True si les moteurs sont actifs."""
        raise NotImplementedError

    # --- Mouvement -------------------------------------------------------------
    def joint_limits(self, names):
        """{nom: (min, max, vitesse_max) ou None si articulation inconnue}."""
        raise NotImplementedError

    def move_to(self, names, angles, duration):
        """Bloquant. Va à une pose (un angle par articulation) en `duration` s."""
        raise NotImplementedError

    def play_motion(self, names, times, keys):
        """
        Bloquant. Joue une chorégraphie au format Choregraphe :
        times[i] = instants des keyframes de names[i], keys[i] = angles
        (format simple) ou [angle, poignée1, poignée2] (format Bezier).
        """
        raise NotImplementedError

    def stop_motion(self, names):
        """Interrompt immédiatement play_motion / move_to sur ces articulations."""
        raise NotImplementedError

    # --- Musique ---------------------------------------------------------------
    def prepare_audio(self, local_path, robot_path=None, start=0.0):
        """
        Précharge la musique ; renvoie une poignée (ou None si pas d'audio).
        local_path : copie sur le PC ; robot_path : fichier SUR le robot
        (meta.json "audio_robot") ; start : position de départ dans le fichier (s).
        """
        raise NotImplementedError

    def play_audio(self, handle):
        """Bloquant. Joue la musique préchargée jusqu'au bout ou jusqu'à stop_audio."""
        raise NotImplementedError

    def stop_audio(self, handle):
        """Coupe la musique."""
        raise NotImplementedError

    def release_audio(self, handle):
        """Libère la mémoire de la musique préchargée."""
        raise NotImplementedError

    # --- Expression --------------------------------------------------------------
    def say(self, text):
        """Bloquant. Synthèse vocale."""
        raise NotImplementedError

    def stop_speech(self):
        """Coupe la parole en cours."""
        raise NotImplementedError

    def set_leds(self, rgb, duration):
        """Yeux de NAO : couleur 0xRRGGBB atteinte en `duration` s."""
        raise NotImplementedError

    # --- État et sécurité --------------------------------------------------------
    def status(self):
        """
        dict : connected, robot, backend, battery (%), posture, awake,
        temperature (°C max des moteurs surveillés). None = inconnu.
        """
        raise NotImplementedError

    def on_fall(self, callback):
        """Enregistre une fonction sans argument appelée si NAO tombe."""
        raise NotImplementedError
