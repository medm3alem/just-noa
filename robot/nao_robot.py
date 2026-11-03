# -*- coding: utf-8 -*-
"""
robot/nao_robot.py - Implémentation du contrat avec NAOqi (robot réel ou virtuel).

Différence avec ton test dans Choregraphe : une boîte Python de Choregraphe
s'exécute SUR le robot, donc ALProxy("ALMotion") suffit. Ici le programme
tourne sur le PC et parle au robot par le réseau : on ouvre une session vers
tcp://IP:port, puis chaque service (ALMotion, ALAudioPlayer...) est un
"proxy" dont chaque appel part sur le robot, s'y exécute, et renvoie le résultat.

Deux façons d'ouvrir la connexion, essayées dans cet ordre :
- qi.Session (NAOqi 2.x, V5/V6) : permet en plus d'écouter les évènements
  (détection de chute) ;
- ALProxy(nom, ip, port) (ancienne API, toujours présente) : de secours.

Toutes les méthodes bloquantes sont appelées depuis des threads distincts par
le lecteur (sync/player.py) : c'est ce qui permet de lancer la musique et le
mouvement en même temps, et de les arrêter depuis un autre thread.
"""
from __future__ import absolute_import, print_function

import os
import posixpath

import config
from robot.base import Robot, RobotError

TEMP_KEY = "Device/SubDeviceList/%s/Temperature/Sensor/Value"


class NaoRobot(Robot):
    name = "nao"

    def __init__(self, ip, port, log=None):
        Robot.__init__(self, log)
        self.ip = ip
        self.port = port
        self.backend = None
        self._session = None
        self._get_service = None
        self._limits_cache = {}
        self._fall_callback = None
        self._fall_subscriber = None
        self._fall_link = None
        # Proxies vers les services du robot (None si absent)
        self.motion = self.posture = self.memory = None
        self.audio = self.tts = self.leds = self.battery = self.life = None

    # =========================================================================
    # Connexion
    # =========================================================================
    def connect(self):
        self._open_backend()
        # Indispensables : sans eux, pas de danse possible.
        self.motion = self._service("ALMotion", required=True)
        self.posture = self._service("ALRobotPosture", required=True)
        self.memory = self._service("ALMemory", required=True)
        # Facultatifs : le robot virtuel de Choregraphe n'a ni audio ni batterie.
        self.audio = self._service("ALAudioPlayer")
        self.tts = self._service("ALTextToSpeech")
        self.leds = self._service("ALLeds")
        self.battery = self._service("ALBattery")
        self.life = self._service("ALAutonomousLife")
        self._setup_speech()
        self._setup_autonomous_life()
        self._setup_fall_detection()

    def _open_backend(self):
        url = "tcp://%s:%d" % (self.ip, self.port)
        try:
            import qi
        except ImportError:
            qi = None

        if qi is not None:
            session = qi.Session()
            try:
                session.connect(url)
            except RuntimeError as err:
                raise RobotError("Cannot connect to %s: %s\n"
                                 "  -> Check the IP (press the chest button) and that the PC is on the same network."
                                 % (url, err))
            self._session = session
            self._get_service = session.service
            self.backend = "qi"
        else:
            try:
                from naoqi import ALProxy
            except ImportError:
                raise RobotError("Neither 'qi' nor 'naoqi' can be imported: NAOqi Python SDK missing, "
                                 "not on PYTHONPATH, or wrong Python (2.7 needed). "
                                 "Use --choregraphe with Python 3 instead.")
            self._get_service = lambda name: ALProxy(name, self.ip, self.port)
            self.backend = "ALProxy"
        self.log("[OK] Connecte a %s (API %s)" % (url, self.backend))

    def _service(self, name, required=False):
        try:
            return self._get_service(name)
        except Exception as err:   # RuntimeError si le service n'existe pas
            if required:
                raise RobotError("NAOqi service %s unavailable: %s" % (name, err))
            self.log("[INFO] Service %s absent (normal sur le robot virtuel)" % name)
            return None

    def _setup_speech(self):
        if self.tts is None:
            return
        try:
            self.tts.setLanguage(config.TTS_LANGUAGE)
            self.tts.setVolume(config.TTS_VOLUME)
        except Exception as err:
            self.log("[ATTENTION] Reglage de la voix impossible : %s" % err)

    def _setup_autonomous_life(self):
        # Autonomous Life fait bouger la tête et "respirer" NAO tout seul : ces
        # mouvements se mélangeraient à la chorégraphie. En le désactivant, NAO
        # se met au repos (accroupi) : c'est notre état de départ "REPOS".
        if self.life is None or not config.DISABLE_AUTONOMOUS_LIFE:
            return
        try:
            state = self.life.getState()
            if state != "disabled":
                self.log("[INFO] Autonomous Life '%s' -> 'disabled' (NAO se met au repos)" % state)
                self.life.setState("disabled")
        except Exception as err:
            self.log("[ATTENTION] Autonomous Life non modifiable : %s" % err)

    def _setup_fall_detection(self):
        # ALMotion publie l'évènement "robotHasFallen" dans ALMemory. Avec qi on
        # s'y abonne : la fonction est appelée dès que NAO tombe. Le "fall
        # manager" de NAO (protection réflexe) reste actif dans tous les cas.
        if self.backend != "qi":
            self.log("[ATTENTION] Detection de chute indisponible avec ALProxy "
                     "(le reflexe de protection de NAO reste actif).")
            return
        try:
            self._fall_subscriber = self.memory.subscriber("robotHasFallen")
            self._fall_link = self._fall_subscriber.signal.connect(self._on_fall_event)
        except Exception as err:
            self.log("[ATTENTION] Abonnement a robotHasFallen impossible : %s" % err)

    def _on_fall_event(self, value):
        # Appelé depuis un thread de qi, pas depuis le nôtre.
        if self._fall_callback is not None:
            self._fall_callback()

    def close(self):
        try:
            if self._fall_subscriber is not None and self._fall_link is not None:
                self._fall_subscriber.signal.disconnect(self._fall_link)
            if self._session is not None:
                self._session.close()
        except Exception:
            pass

    # =========================================================================
    # Cycle de vie
    # =========================================================================
    def wake_up(self):
        self.motion.wakeUp()

    def rest(self):
        self.motion.rest()

    def go_to_posture(self, posture, speed):
        if not self.posture.goToPosture(posture, speed):
            raise RobotError("Posture %s not reached (is NAO standing on a flat floor?)" % posture)

    def is_awake(self):
        try:
            return bool(self.motion.robotIsWakeUp())
        except Exception:
            return True   # dans le doute, on considère les moteurs actifs

    # =========================================================================
    # Mouvement
    # =========================================================================
    def joint_limits(self, names):
        result = {}
        for name in names:
            if name not in self._limits_cache:
                try:
                    # getLimits(nom) -> [[min, max, vitesse max, couple max]]
                    lim = self.motion.getLimits(name)[0]
                    self._limits_cache[name] = (lim[0], lim[1], lim[2])
                except Exception:
                    self._limits_cache[name] = None   # articulation inconnue
            result[name] = self._limits_cache[name]
        return result

    def move_to(self, names, angles, duration):
        # Même appel que dans ton test : une pose, un temps, angles absolus.
        self.motion.angleInterpolation(names, angles, duration, True)

    def play_motion(self, names, times, keys):
        if keys and isinstance(keys[0][0], list):
            # Export "Bezier" de Choregraphe : (noms, TEMPS, points de contrôle)
            self.motion.angleInterpolationBezier(names, times, keys)
        else:
            # Export "simplified" : attention, l'ordre est (noms, ANGLES, TEMPS, absolu)
            self.motion.angleInterpolation(names, keys, times, True)

    def stop_motion(self, names):
        # Tue les tâches de mouvement qui utilisent ces articulations : l'appel
        # bloquant de play_motion (dans un autre thread) se termine aussitôt.
        self.motion.killTasksUsingResources(names)

    # =========================================================================
    # Musique
    # =========================================================================
    def prepare_audio(self, local_path, robot_path=None, start=0.0):
        if self.audio is None:
            self.log("[INFO] Pas d'ALAudioPlayer : la danse sera jouee sans musique.")
            return None
        if start:
            self.log("[ATTENTION] Mode NAOqi direct : 'audio_start' ignore, lecture depuis 0 s.")
        remote = robot_path or posixpath.join(config.ROBOT_AUDIO_DIR, os.path.basename(local_path))
        try:
            # loadFile décode le fichier à l'avance : au moment du play(), le son
            # part sans délai de lecture disque. C'est clé pour la synchro.
            return self.audio.loadFile(remote)
        except Exception as err:
            raise RobotError("Music not found on the robot (%s): %s\n"
                             "  -> Copy it first: scp \"%s\" nao@%s:%s/"
                             % (remote, err, local_path, self.ip, config.ROBOT_AUDIO_DIR))

    def play_audio(self, handle):
        if handle is None or self.audio is None:
            return
        self.audio.play(handle, config.AUDIO_VOLUME, 0.0)   # bloquant jusqu'à la fin

    def stop_audio(self, handle):
        if self.audio is None:
            return
        try:
            if handle is not None:
                self.audio.stop(handle)
            else:
                self.audio.stopAll()
        except Exception:
            self.audio.stopAll()

    def release_audio(self, handle):
        if self.audio is not None and handle is not None:
            try:
                self.audio.unloadFile(handle)
            except Exception:
                pass

    # =========================================================================
    # Expression
    # =========================================================================
    def say(self, text):
        if self.tts is not None:
            self.tts.say(text)
        else:
            self.log('[INFO] (pas de voix) "%s"' % text)

    def stop_speech(self):
        if self.tts is not None:
            self.tts.stopAll()

    def set_leds(self, rgb, duration):
        if self.leds is not None:
            self.leds.fadeRGB("FaceLeds", rgb, duration)

    # =========================================================================
    # État et sécurité
    # =========================================================================
    def status(self):
        st = {"connected": True, "robot": "%s:%d" % (self.ip, self.port),
              "backend": self.backend, "battery": None, "posture": None,
              "awake": None, "temperature": None}
        try:
            st["posture"] = self.posture.getPosture()
        except Exception:
            st["connected"] = False   # le premier appel échoue : liaison perdue
            return st
        try:
            st["awake"] = bool(self.motion.robotIsWakeUp())
        except Exception:
            pass
        if self.battery is not None:
            try:
                st["battery"] = self.battery.getBatteryCharge()
            except Exception:
                pass
        try:
            values = self.memory.getListData([TEMP_KEY % j for j in config.TEMP_JOINTS])
            values = [v for v in values if isinstance(v, (int, float))]
            st["temperature"] = max(values) if values else None
        except Exception:
            pass
        return st

    def on_fall(self, callback):
        self._fall_callback = callback
