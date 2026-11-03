# -*- coding: utf-8 -*-
"""
robot/choregraphe_robot.py - NAO (physique ou virtuel) piloté via la passerelle
Choregraphe (choregraphe_bridge.py), en JSON sur TCP.

    Just Nao (PC) --une connexion par commande--> IP_DU_NAO:8766 --> NAOqi

Chaque commande ouvre sa propre connexion : une commande longue ("play" d'une
danse de 66 s) n'empêche jamais "stop" ou "audio_stop" de passer. Pas d'état
de connexion à maintenir : si la passerelle redémarre, la commande suivante
réussit à nouveau (reconnexion automatique).

Audio : la musique est lue PAR NAO (haut-parleurs du robot). Le fichier doit
déjà être sur le robot (scp, voir docs/AUDIO_MACARENA.md). Le chemin sur le
robot vient du meta.json de la chorégraphie ("audio_robot").

Compatibilité : passerelle v3 ("pong-physique-v3", préchargement, lecture d'un
fichier précis, statut complet) ou v2 ("pong-physique-v2" : "audio_play" sans
paramètre, qui joue le morceau configuré dans la boîte).
"""
from __future__ import absolute_import, print_function

import json
import socket
import time

from robot.base import Robot, RobotError
from robot.fake_robot import NAO_LIMITS


class ChoregrapheRobot(Robot):
    name = "choregraphe"

    def __init__(self, log=None, host="192.168.2.121", port=8766, volume=0.8):
        Robot.__init__(self, log)
        self.host, self.port = host, port
        self.volume = volume
        self.bridge_version = None
        self.latency_ms = None
        self._fall_callback = None
        self._fall_reported = False
        self._last_status = {}

    def set_address(self, host, port):
        """Nouvelle adresse de la passerelle (fenêtre Settings) : prise en compte
        dès la commande suivante, puisque chaque commande ouvre sa connexion."""
        self.host, self.port = host, int(port)
        self.log("[ROBOT] Passerelle Choregraphe : %s:%d" % (self.host, self.port))

    # =========================================================================
    # Transport
    # =========================================================================
    def _request(self, command, timeout=15, **params):
        request = dict(params, cmd=command)
        payload = (json.dumps(request, ensure_ascii=True, separators=(",", ":")) + "\n").encode("ascii")
        try:
            s = socket.create_connection((self.host, self.port), 3)
            try:
                s.settimeout(timeout)
                s.sendall(payload)
                data = bytearray()
                while b"\n" not in data:
                    chunk = s.recv(4096)
                    if not chunk:
                        raise RobotError("Bridge closed without answering (%s)" % command)
                    data.extend(chunk)
                    if len(data) > 1024 * 1024:
                        raise RobotError("Bridge answer too large")
                result = json.loads(bytes(data).split(b"\n", 1)[0].decode("utf-8"))
            finally:
                s.close()
        except (socket.error, ValueError) as exc:
            raise RobotError("No answer from the Choregraphe bridge %s:%d (%s): %s"
                             % (self.host, self.port, command, exc))
        if not result.get("ok"):
            raise RobotError("NAO (%s): %s" % (command, result.get("error", "unknown error")))
        return result.get("result")

    @property
    def is_v3(self):
        return bool(self.bridge_version) and not self.bridge_version.endswith("v2") \
            and self.bridge_version != "pong"

    # =========================================================================
    # Connexion
    # =========================================================================
    def connect(self):
        rtts = []
        for _ in range(3):
            t0 = time.time()
            version = self._request("ping", timeout=5)
            rtts.append(1000.0 * (time.time() - t0))
        self.bridge_version = str(version)
        self.latency_ms = sorted(rtts)[len(rtts) // 2]
        st = self._request("status", timeout=5)
        self._last_status = st or {}
        self.log("[OK] Passerelle %s sur %s:%d (aller-retour %.0f ms)"
                 % (self.bridge_version, self.host, self.port, self.latency_ms))
        if not self.is_v3:
            self.log("[ATTENTION] Passerelle ancienne (%s) : audio_play joue le morceau fixe de la "
                     "boite, Stop peut attendre la fin d'un mouvement. Installer la v3." % self.bridge_version)

    def close(self):
        pass

    # =========================================================================
    # Cycle de vie
    # =========================================================================
    def wake_up(self):
        self._fall_reported = False
        self._request("wake", timeout=35)

    def rest(self):
        self._request("rest", timeout=35)

    def go_to_posture(self, posture, speed):
        self._request("posture", posture=posture, speed=speed, timeout=35)

    def is_awake(self):
        return bool((self._request("status", timeout=5) or {}).get("awake"))

    # =========================================================================
    # Mouvement
    # =========================================================================
    def joint_limits(self, names):
        return dict((n, NAO_LIMITS.get(n)) for n in names)

    def move_to(self, names, angles, duration):
        self._request("move", names=names, angles=angles, duration=duration,
                      timeout=max(15, duration + 15))

    def play_motion(self, names, times, keys):
        duration = max([t[-1] for t in times if t] or [0])
        self._request("play", names=names, times=times, keys=keys, timeout=max(15, duration + 20))

    def stop_motion(self, names):
        self._request("stop", names=names, timeout=5)

    # =========================================================================
    # Musique (jouée par NAO)
    # =========================================================================
    def prepare_audio(self, local_path, robot_path=None, start=0.0):
        """
        Précharge la musique sur NAO (v3). `robot_path` : chemin du fichier SUR le
        robot (meta.json "audio_robot"). Sans chemin robot, pas de musique : on le
        signale au lieu de jouer un mauvais morceau.
        """
        if not robot_path:
            raise RobotError("No music file on NAO for %s: add \"audio_robot\" to meta.json "
                             "and copy the file to the robot (docs/AUDIO_MACARENA.md)" % local_path)
        handle = {"path": robot_path, "start": float(start or 0.0), "id": None}
        if self.is_v3:
            loaded = self._request("audio_load", path=robot_path, timeout=20) or {}
            handle["id"] = loaded.get("id")
            handle["duration"] = loaded.get("duration")
            self.log("[AUDIO] Prechargee sur NAO : %s (%s s)" % (robot_path, handle.get("duration")))
        return handle

    def play_audio(self, handle):
        if handle is None:
            return
        if self.is_v3:
            self._request("audio_play", id=handle.get("id"), path=handle["path"],
                          start=handle.get("start", 0.0), volume=self.volume, timeout=10)
        else:
            self._request("audio_play", timeout=10)        # v2 : morceau fixe de la boîte
        self.log("[AUDIO] Lecture lancee sur NAO")

    def stop_audio(self, handle):
        self._request("audio_stop", timeout=5)

    def release_audio(self, handle):
        pass                    # la passerelle libère le fichier à l'arrêt

    # =========================================================================
    # Expression
    # =========================================================================
    def say(self, text):
        self._request("say", text=text, timeout=max(15, len(text) / 8.0 + 10))

    def stop_speech(self):
        self._request("stop_speech", timeout=5)

    def set_leds(self, rgb, duration):
        self._request("leds", rgb=rgb, duration=duration, timeout=5)

    def emergency_stop(self):
        """Mouvement + musique + parole coupés d'un coup (v3), sinon une à une."""
        if self.is_v3:
            self._request("emergency_stop", timeout=5)
            return
        for cmd in ("stop", "audio_stop", "stop_speech"):
            try:
                self._request(cmd, timeout=5, **({"names": []} if cmd == "stop" else {}))
            except RobotError:
                pass

    # =========================================================================
    # État
    # =========================================================================
    def status(self):
        try:
            st = self._request("status", timeout=5) or {}
        except Exception:
            return dict(connected=False, robot="NAO %s:%d" % (self.host, self.port),
                        backend="choregraphe-tcp", battery=None, posture=None, awake=None,
                        temperature=None)
        self._last_status = st
        if st.get("fallen") and not self._fall_reported and self._fall_callback is not None:
            self._fall_reported = True
            self._fall_callback()
        return dict(connected=True, robot="NAO %s:%d" % (self.host, self.port),
                    backend="choregraphe %s" % (self.bridge_version or "?"),
                    battery=st.get("battery"), posture=st.get("posture"), awake=st.get("awake"),
                    temperature=None, fallen=st.get("fallen"))

    def on_fall(self, callback):
        self._fall_callback = callback
