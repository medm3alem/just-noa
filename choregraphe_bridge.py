# -*- coding: utf-8 -*-
"""
choregraphe_bridge.py - Passerelle Just Nao v3, à coller dans UNE boîte Python
Choregraphe (Python 2.7, classe MyClass(GeneratedClass)).

    Just Nao (PC, Python 3.12) --JSON/TCP--> cette boîte (sur NAO) --> services NAOqi

Quand Choregraphe est connecté au NAO physique, la boîte s'exécute SUR LE ROBOT :
elle écoute donc sur 0.0.0.0:8766 et l'application se connecte à IP_DU_NAO:8766.
Ne pas revenir à 127.0.0.1 : c'était la cause des confusions de la v1.

Protocole : une connexion = une ligne JSON {"cmd": ..., ...} -> une ligne JSON
{"ok": true, "result": ...} ou {"ok": false, "error": "..."}.

Nouveautés v3 (par rapport à la v2 "pong-physique-v2") :
- STOP JAMAIS BLOQUÉ : chaque connexion a son thread ; seules les commandes de
  mouvement longues (wake, rest, posture, move, play) se partagent un verrou,
  et stop / emergency_stop / audio_stop / stop_speech / status ne le prennent
  jamais. Un Stop pendant une danse de 66 s agit donc immédiatement.
- AUDIO : préchargement (audio_load), lecture dans un thread (audio_play),
  arrêt (audio_stop) ; une nouvelle lecture coupe toujours la précédente
  (pas de musiques superposées au "Rejouer").
- SÉCURITÉ : clients limités au réseau local (ALLOWED_CLIENTS), jambes refusées
  par défaut, mouvement refusé après une chute tant que "wake" n'est pas
  redemandé, transitions "move" d'au moins 0,3 s.
- Compatibilité v2 : "audio_play" sans paramètre joue DEFAULT_AUDIO_PATH.

Ce fichier fonctionne aussi en Python 3 (tests automatisés sur PC avec de faux
services NAOqi : tests/test_bridge.py).
"""
import json
import os
import select
import socket
import threading
import time

# --- Réglages ----------------------------------------------------------------------
BRIDGE_VERSION = "pong-physique-v3"
BIND_HOST = "0.0.0.0"
PORT = 8766
# Préfixes d'adresses IP autorisées à commander le robot (réseau local de la démo).
# () = tout le monde : à éviter, la passerelle fait bouger un vrai robot.
ALLOWED_CLIENTS = ("127.", "192.168.2.")
TTS_LANGUAGE = "English"
TTS_VOLUME = 0.85
DEFAULT_AUDIO_PATH = "/home/nao/music/macarena.mp3"   # compatibilité v2 (audio_play sans chemin)
ALLOW_LEG_MOTION = False          # mouvements des jambes refusés : danses haut du corps seulement
MIN_MOVE_DURATION = 0.3           # s minimum pour rejoindre une pose ("move")
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MOTION_LOCK_WAIT = 1.0            # s d'attente max si un autre mouvement est en cours
LEG_WORDS = ("Hip", "Knee", "Ankle")
MOTION_COMMANDS = ("wake", "rest", "posture", "move", "play")

try:
    TEXT_TYPE = unicode          # Python 2
except NameError:
    TEXT_TYPE = str              # Python 3 (tests)


def _native(obj):
    """Python 2 : json donne de l'unicode ; on rend des str classiques à NAOqi."""
    if TEXT_TYPE is not str:
        if isinstance(obj, TEXT_TYPE):
            return obj.encode("utf-8")
        if isinstance(obj, list):
            return [_native(x) for x in obj]
        if isinstance(obj, dict):
            return dict((_native(k), _native(v)) for k, v in obj.items())
    return obj


class MyClass(GeneratedClass):

    def __init__(self):
        GeneratedClass.__init__(self)
        self.running = False
        self.server = None
        self.thread = None
        self._services = {}
        self._services_lock = threading.Lock()
        self._motion_lock = threading.Lock()
        self._audio_lock = threading.Lock()
        self._audio = {"task": None, "path": None, "playing": False, "started": None,
                       "generation": 0, "duration": None}
        self._fallen = False
        self._fall_sub = None
        self._fall_link = None
        self._stops = 0

    # =========================================================================
    # Cycle de vie de la boîte
    # =========================================================================
    def onLoad(self):
        pass

    def onUnload(self):
        self._shutdown()

    def onInput_onStart(self):
        if self.running:
            self.logger.info("Passerelle deja active")
            return
        self.running = True
        self._setup_robot()
        self.thread = threading.Thread(target=self.listen)
        self.thread.daemon = True
        self.thread.start()

    def onInput_onStop(self):
        self._shutdown()
        stopped = getattr(self, "onStopped", None)
        if stopped is not None:
            stopped()

    def _shutdown(self):
        self.running = False
        try:
            self._audio_stop()
        except Exception:
            pass
        if self.server is not None:
            try:
                self.server.close()
            except Exception:
                pass
        if self._fall_sub is not None and self._fall_link is not None:
            try:
                self._fall_sub.signal.disconnect(self._fall_link)
            except Exception:
                pass

    def service(self, name):
        with self._services_lock:
            if name not in self._services:
                self._services[name] = self.session().service(name)
            return self._services[name]

    def _setup_robot(self):
        try:
            tts = self.service("ALTextToSpeech")
            tts.setLanguage(TTS_LANGUAGE)
            tts.setVolume(TTS_VOLUME)
        except Exception as e:
            self.logger.info("Voix : reglage impossible (%s)" % e)
        try:
            self._fall_sub = self.service("ALMemory").subscriber("robotHasFallen")
            self._fall_link = self._fall_sub.signal.connect(self._on_fall)
        except Exception as e:
            self.logger.info("Detection de chute indisponible (%s)" % e)

    def _on_fall(self, value=None):
        # Chute : on coupe tout, et on refuse les mouvements jusqu'au prochain "wake".
        self._fallen = True
        self.logger.error("Chute detectee : arret de la danse et de la musique")
        self._emergency_stop()

    # =========================================================================
    # Serveur TCP
    # =========================================================================
    def listen(self):
        server = None
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((BIND_HOST, PORT))
            server.listen(16)
            server.setblocking(False)
            self.server = server
            self.logger.info("Just Nao bridge v3 pret : %s:%d" % (BIND_HOST, PORT))
            while self.running:
                ready, _, _ = select.select([server], [], [], 0.5)
                if not ready:
                    continue
                try:
                    client, addr = server.accept()
                except socket.error:
                    continue
                if ALLOWED_CLIENTS and not any(addr[0].startswith(p) for p in ALLOWED_CLIENTS):
                    self.logger.error("Client refuse : %s" % addr[0])
                    self._reply(client, {"ok": False, "error": "client not allowed: %s" % addr[0]})
                    continue
                t = threading.Thread(target=self.handle, args=(client,))
                t.daemon = True
                t.start()
        except Exception as e:
            if self.running:
                self.logger.error("Serveur : %s" % e)
        finally:
            self.running = False
            if server is not None:
                try:
                    server.close()
                except Exception:
                    pass
            self.server = None
            self.logger.info("Passerelle arretee")

    def handle(self, client):
        try:
            client.setblocking(True)
            client.settimeout(10.0)          # lecture de la requête seulement
            data = b""
            while b"\n" not in data:
                part = client.recv(8192)
                if not part:
                    raise ValueError("incomplete message")
                data += part
                if len(data) > MAX_REQUEST_BYTES:
                    raise ValueError("message too large")
            request = _native(json.loads(data.split(b"\n", 1)[0].decode("utf-8")))
            if not isinstance(request, dict):
                raise ValueError("JSON object expected")
            response = {"ok": True, "result": self.dispatch(request)}
        except Exception as e:
            self.logger.error("Commande : %s" % e)
            response = {"ok": False, "error": str(e)}
        self._reply(client, response)

    @staticmethod
    def _reply(client, response):
        try:
            client.sendall((json.dumps(response) + "\n").encode("utf-8"))
        except Exception:
            pass
        finally:
            try:
                client.close()
            except Exception:
                pass

    # =========================================================================
    # Commandes
    # =========================================================================
    def dispatch(self, req):
        cmd = req.get("cmd")
        if cmd in MOTION_COMMANDS:
            return self._with_motion_lock(cmd, req)
        handler = {
            "ping": lambda r: BRIDGE_VERSION,
            "status": self._status,
            "stop": self._stop,
            "emergency_stop": lambda r: self._emergency_stop(),
            "say": self._say,
            "stop_speech": self._stop_speech,
            "leds": self._leds,
            "audio_load": self._audio_load,
            "audio_play": self._audio_play,
            "audio_stop": lambda r: self._audio_stop(),
            "audio_status": lambda r: self._audio_status(),
        }.get(cmd)
        if handler is None:
            raise ValueError("unknown command: %s" % cmd)
        return handler(req)

    def _with_motion_lock(self, cmd, req):
        deadline = time.time() + MOTION_LOCK_WAIT
        while not self._motion_lock.acquire(False):     # Python 2 : pas de timeout natif
            if time.time() > deadline:
                raise RuntimeError("robot busy with another motion")
            time.sleep(0.02)
        try:
            return getattr(self, "_" + cmd)(req)
        finally:
            self._motion_lock.release()

    # --- Mouvement ----------------------------------------------------------------------
    def _check_motion_allowed(self, names):
        if self._fallen:
            raise RuntimeError("robot has fallen: put it back on its feet, then wake")
        if not ALLOW_LEG_MOTION:
            legs = [n for n in names if any(w in n for w in LEG_WORDS)]
            if legs:
                raise RuntimeError("leg motion disabled on the bridge: %s" % ", ".join(legs))

    def _wake(self, req):
        self._fallen = False
        self.service("ALMotion").wakeUp()
        return "OK"

    def _rest(self, req):
        self.service("ALMotion").rest()
        return "OK"

    def _posture(self, req):
        if self._fallen:
            raise RuntimeError("robot has fallen: put it back on its feet, then wake")
        ok = self.service("ALRobotPosture").goToPosture(req["posture"], float(req["speed"]))
        if not ok:
            raise RuntimeError("posture not reached: %s" % req["posture"])
        return "OK"

    def _move(self, req):
        names, angles = req["names"], [float(a) for a in req["angles"]]
        if len(names) != len(angles):
            raise ValueError("names and angles differ in length")
        self._check_motion_allowed(names)
        duration = max(MIN_MOVE_DURATION, float(req["duration"]))
        self.service("ALMotion").angleInterpolation(names, angles, duration, True)
        return "OK"

    def _play(self, req):
        names, times, keys = req["names"], req["times"], req["keys"]
        if not (len(names) == len(times) == len(keys)):
            raise ValueError("names, times and keys differ in length")
        self._check_motion_allowed(names)
        stops_before = self._stops
        motion = self.service("ALMotion")
        if keys and keys[0] and isinstance(keys[0][0], list):
            motion.angleInterpolationBezier(names, times, keys)
        else:
            motion.angleInterpolation(names, keys, times, True)
        return "stopped" if self._stops != stops_before else "OK"

    def _stop(self, req):
        # Jamais derrière le verrou de mouvement : interrompt le "play" en cours.
        self._stops += 1
        motion = self.service("ALMotion")
        names = req.get("names")
        if names:
            motion.killTasksUsingResources(names)
        else:
            motion.killAll()
        return "OK"

    def _emergency_stop(self):
        errors = []
        for action in (lambda: self._stop({}), self._audio_stop, lambda: self._stop_speech({})):
            try:
                action()
            except Exception as e:
                errors.append(str(e))
        return {"stopped": True, "errors": errors}

    # --- Parole et LEDs -------------------------------------------------------------------
    def _say(self, req):
        text = req.get("text") or ""
        if len(text) > 500:
            text = text[:500]
        self.service("ALTextToSpeech").say(text)      # bloquant : se termine avec la phrase
        return "OK"

    def _stop_speech(self, req):
        self.service("ALTextToSpeech").stopAll()
        return "OK"

    def _leds(self, req):
        self.service("ALLeds").fadeRGB("FaceLeds", int(req["rgb"]), float(req["duration"]))
        return "OK"

    # --- Audio -------------------------------------------------------------------------------
    def _audio_load(self, req):
        path = req["path"]
        if not os.path.isfile(path):
            raise RuntimeError("audio file not found on NAO: %s" % path)
        self._audio_stop()                              # jamais deux musiques à la fois
        player = self.service("ALAudioPlayer")
        task = player.loadFile(path)
        duration = None
        try:
            duration = float(player.getFileLength(task))
        except Exception:
            pass
        with self._audio_lock:
            self._audio.update(task=task, path=path, duration=duration, playing=False)
        return {"id": task, "duration": duration}

    def _audio_play(self, req):
        path = req.get("path")
        task = req.get("id")
        volume = float(req.get("volume", 0.8))
        start = float(req.get("start", 0.0))
        with self._audio_lock:
            loaded = self._audio["task"] if task is not None and task == self._audio["task"] else None
            loaded_path = self._audio["path"]
        if loaded is None:
            path = path or loaded_path or DEFAULT_AUDIO_PATH
            if not os.path.isfile(path):
                raise RuntimeError("audio file not found on NAO: %s" % path)
            self._audio_stop()
        else:
            path = loaded_path
            self._stop_playback_only()
        with self._audio_lock:
            self._audio["generation"] += 1
            generation = self._audio["generation"]
            self._audio.update(playing=True, started=time.time(), path=path)
        worker = threading.Thread(target=self._audio_worker,
                                  args=(generation, loaded, path, volume, start))
        worker.daemon = True
        worker.start()
        return {"playing": True, "id": loaded, "path": path}

    def _audio_worker(self, generation, task, path, volume, start):
        # Lecture dans un thread : la passerelle reste disponible pendant la musique
        # (proxy qi : pas de ".post" ; l'appel bloquant tourne ici).
        player = self.service("ALAudioPlayer")
        try:
            if task is not None and start <= 0:
                player.play(task, volume, 0.0)
            elif start > 0:
                player.playFileFromPosition(path, start, volume, 0.0)
            else:
                player.playFile(path, volume, 0.0)
        except Exception as e:
            self.logger.error("Audio : %s" % e)
        finally:
            with self._audio_lock:
                if self._audio["generation"] == generation:
                    self._audio["playing"] = False

    def _stop_playback_only(self):
        with self._audio_lock:
            self._audio["generation"] += 1
            self._audio["playing"] = False
        self.service("ALAudioPlayer").stopAll()

    def _audio_stop(self):
        with self._audio_lock:
            self._audio["generation"] += 1
            self._audio.update(playing=False, task=None)
        player = self.service("ALAudioPlayer")
        player.stopAll()
        try:
            player.unloadAllFiles()
        except Exception:
            pass
        return "OK"

    def _audio_status(self):
        with self._audio_lock:
            state = dict(self._audio)
        elapsed = time.time() - state["started"] if state["playing"] and state["started"] else None
        return {"playing": state["playing"], "path": state["path"], "elapsed": elapsed,
                "duration": state["duration"]}

    # --- État ----------------------------------------------------------------------------------
    def _status(self, req):
        st = {"version": BRIDGE_VERSION, "fallen": self._fallen,
              "motion_busy": self._motion_lock.locked(),
              "audio_playing": self._audio["playing"]}
        motion = self.service("ALMotion")
        st["awake"] = bool(motion.robotIsWakeUp())
        try:
            st["posture"] = self.service("ALRobotPosture").getPosture()
        except Exception:
            st["posture"] = None
        try:
            st["battery"] = int(self.service("ALBattery").getBatteryCharge())
        except Exception:
            st["battery"] = None
        return st
