# -*- coding: utf-8 -*-
"""
robot/fake_robot.py - Un NAO simulé : ni robot, ni SDK, ni réseau.

Il respecte le même contrat que NaoRobot (robot/base.py) en imitant les durées :
un mouvement de 30 s "dure" 30 s, une phrase dure le temps de la dire. Le
lecteur et le contrôleur ne voient pas la différence, ce qui permet de
développer et tester toute l'application (clavier, HMI, synchro, arrêt) chez soi.

Sous Windows, la musique WAV est même jouée sur le PC (module winsound).
Pour voir les mouvements en 3D, on utilise plutôt NaoRobot connecté au robot
virtuel de Choregraphe.
"""
from __future__ import absolute_import, print_function

import os
import threading
import time
import wave

from robot.base import Robot, RobotError

try:
    import winsound     # Windows uniquement : lecture d'un WAV sur le PC
except ImportError:
    winsound = None

# Butées de NAO (V5/V6) : (min rad, max rad, vitesse max rad/s).
# Valeurs indicatives de la documentation Aldebaran. NaoRobot, lui, lit les
# vraies valeurs du robot connecté avec ALMotion.getLimits().
NAO_LIMITS = {
    "HeadYaw": (-2.0857, 2.0857, 8.26797),
    "HeadPitch": (-0.6720, 0.5149, 7.19407),
    "LShoulderPitch": (-2.0857, 2.0857, 7.19407),
    "LShoulderRoll": (-0.3142, 1.3265, 9.22756),
    "LElbowYaw": (-2.0857, 2.0857, 7.19407),
    "LElbowRoll": (-1.5446, -0.0349, 9.22756),
    "LWristYaw": (-1.8238, 1.8238, 24.6229),
    "LHand": (0.0, 1.0, 8.33),
    "RShoulderPitch": (-2.0857, 2.0857, 7.19407),
    "RShoulderRoll": (-1.3265, 0.3142, 9.22756),
    "RElbowYaw": (-2.0857, 2.0857, 7.19407),
    "RElbowRoll": (0.0349, 1.5446, 9.22756),
    "RWristYaw": (-1.8238, 1.8238, 24.6229),
    "RHand": (0.0, 1.0, 8.33),
    "LHipYawPitch": (-1.145303, 0.740810, 4.16174),
    "LHipRoll": (-0.379472, 0.790477, 4.16174),
    "LHipPitch": (-1.535889, 0.484090, 6.40239),
    "LKneePitch": (-0.092346, 2.112528, 6.40239),
    "LAnklePitch": (-1.189516, 0.922747, 6.40239),
    "LAnkleRoll": (-0.397880, 0.769001, 4.16174),
    "RHipYawPitch": (-1.145303, 0.740810, 4.16174),
    "RHipRoll": (-0.790477, 0.379472, 4.16174),
    "RHipPitch": (-1.535889, 0.484090, 6.40239),
    "RKneePitch": (-0.103083, 2.120198, 6.40239),
    "RAnklePitch": (-1.186448, 0.932056, 6.40239),
    "RAnkleRoll": (-0.768992, 0.397935, 4.16174),
}


def wav_duration(path):
    """Durée d'un fichier WAV en secondes (module standard `wave`), None sinon."""
    if not path.lower().endswith(".wav"):
        return None
    w = wave.open(path, "rb")   # pas de "with" : non supporté par wave en Python 2.7
    try:
        return w.getnframes() / float(w.getframerate())
    finally:
        w.close()


class FakeRobot(Robot):
    name = "fake"

    def __init__(self, log=None, verbose=False, speech_rate=14.0):
        Robot.__init__(self, log)
        self.verbose = verbose            # True : affiche aussi les LEDs
        self.speech_rate = speech_rate    # caractères "prononcés" par seconde
        self._awake = False
        self._posture = "Crouch"
        self._fall_callback = None
        # Un évènement par ressource : stop_xxx() le lève, l'action bloquante
        # correspondante se réveille et rend la main.
        self._motion_stop = threading.Event()
        self._audio_stop = threading.Event()
        self._speech_stop = threading.Event()

    # --- Connexion -----------------------------------------------------------------
    def connect(self):
        self.log("[FAKE] Robot simule pret (aucun materiel necessaire)")

    def close(self):
        self.log("[FAKE] Deconnexion")

    # --- Cycle de vie --------------------------------------------------------------
    def wake_up(self):
        self.log("[FAKE] wakeUp : moteurs actifs")
        time.sleep(0.5)
        self._awake = True

    def rest(self):
        self.log("[FAKE] rest : accroupi, moteurs relaches")
        time.sleep(0.8)
        self._awake = False
        self._posture = "Crouch"

    def go_to_posture(self, posture, speed):
        self.log("[FAKE] goToPosture(%s, %.1f)" % (posture, speed))
        time.sleep(0.8)
        self._awake = True
        self._posture = posture

    def is_awake(self):
        return self._awake

    # --- Mouvement -----------------------------------------------------------------
    def joint_limits(self, names):
        return dict((n, NAO_LIMITS.get(n)) for n in names)

    def move_to(self, names, angles, duration):
        self._motion_stop.clear()
        self.log("[FAKE] Pose de depart : %d articulations en %.1f s" % (len(names), duration))
        self._motion_stop.wait(duration)

    def play_motion(self, names, times, keys):
        self._motion_stop.clear()
        duration = max(t[-1] for t in times)
        self.log("[FAKE] Mouvement : %d articulations, %.1f s" % (len(names), duration))
        self._motion_stop.wait(duration)

    def stop_motion(self, names):
        self._motion_stop.set()

    # --- Musique -------------------------------------------------------------------
    def prepare_audio(self, local_path, robot_path=None, start=0.0):
        if not local_path or not os.path.isfile(local_path):
            raise RobotError("Music file not found: %s" % local_path)
        return {"path": local_path, "duration": wav_duration(local_path)}

    def play_audio(self, handle):
        if handle is None:
            return
        self._audio_stop.clear()
        path, duration = handle["path"], handle["duration"]
        self.log("[FAKE] Musique : %s" % os.path.basename(path))
        if winsound is not None and duration is not None:
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        # Durée inconnue (mp3) : on attend que le lecteur coupe la musique.
        self._audio_stop.wait(duration if duration is not None else 3600)
        if winsound is not None:
            winsound.PlaySound(None, 0)

    def stop_audio(self, handle):
        self._audio_stop.set()

    def release_audio(self, handle):
        pass

    # --- Expression ----------------------------------------------------------------
    def say(self, text):
        self._speech_stop.clear()
        self.log('[FAKE] NAO dit : "%s"' % text)
        self._speech_stop.wait(len(text) / self.speech_rate)

    def stop_speech(self):
        self._speech_stop.set()

    def set_leds(self, rgb, duration):
        if self.verbose:
            self.log("[FAKE] LEDs #%06X" % rgb)

    # --- État et sécurité ------------------------------------------------------------
    def status(self):
        return {
            "connected": True, "robot": "FakeRobot", "backend": "simulation",
            "battery": 100, "posture": self._posture, "awake": self._awake,
            "temperature": None,
        }

    def on_fall(self, callback):
        self._fall_callback = callback

    def simulate_fall(self):
        """Pour tester la gestion de chute sans robot (commande 'f' du menu clavier)."""
        self.log("[FAKE] Chute simulee !")
        self._awake = False
        self._posture = "LyingBack"
        if self._fall_callback is not None:
            self._fall_callback()
