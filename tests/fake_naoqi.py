# -*- coding: utf-8 -*-
"""
Faux services NAOqi et fausse GeneratedClass pour exécuter choregraphe_bridge.py
SUR LE PC (Python 3 ou 2.7), sans Choregraphe ni robot.

Les fausses commandes bloquantes se comportent comme sur NAO : angleInterpolation
dure le temps de la trajectoire sauf si killAll/killTasksUsingResources l'arrête,
ALAudioPlayer.play dure le temps du fichier sauf stopAll, say dure le temps de la
phrase sauf stopAll. Chaque appel est horodaté (journal `calls`) pour les tests.
"""
from __future__ import print_function

import os
import threading
import time


class Recorder(object):
    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()

    def add(self, service, method, *args):
        with self.lock:
            self.calls.append((time.time(), service, method, args))

    def find(self, method):
        with self.lock:
            return [c for c in self.calls if c[2] == method]


class FakeMotion(object):
    def __init__(self, rec):
        self.rec = rec
        self.kill = threading.Event()
        self.awake = False

    def wakeUp(self):
        self.rec.add("ALMotion", "wakeUp")
        self.awake = True

    def rest(self):
        self.rec.add("ALMotion", "rest")
        self.awake = False

    def robotIsWakeUp(self):
        return self.awake

    def _block(self, duration):
        self.kill.clear()
        self.kill.wait(duration)

    def angleInterpolation(self, names, angles, times, absolute):
        self.rec.add("ALMotion", "angleInterpolation", names)
        duration = times if isinstance(times, (int, float)) else max(t[-1] for t in times)
        self._block(duration)
        self.rec.add("ALMotion", "angleInterpolation_end", names)

    def angleInterpolationBezier(self, names, times, keys):
        self.rec.add("ALMotion", "angleInterpolationBezier", names)
        self._block(max(t[-1] for t in times))

    def killTasksUsingResources(self, names):
        self.rec.add("ALMotion", "killTasksUsingResources", names)
        self.kill.set()

    def killAll(self):
        self.rec.add("ALMotion", "killAll")
        self.kill.set()


class FakePosture(object):
    def __init__(self, rec):
        self.rec = rec
        self.posture = "Crouch"

    def goToPosture(self, name, speed):
        self.rec.add("ALRobotPosture", "goToPosture", name, speed)
        time.sleep(0.05)
        self.posture = name
        return True

    def getPosture(self):
        return self.posture


class FakeTTS(object):
    def __init__(self, rec):
        self.rec = rec
        self.stop = threading.Event()

    def setLanguage(self, lang):
        self.rec.add("ALTextToSpeech", "setLanguage", lang)

    def setVolume(self, v):
        pass

    def say(self, text):
        self.rec.add("ALTextToSpeech", "say", text)
        self.stop.clear()
        self.stop.wait(min(3.0, 0.03 * len(text)))
        self.rec.add("ALTextToSpeech", "say_end", text)

    def stopAll(self):
        self.rec.add("ALTextToSpeech", "stopAll")
        self.stop.set()


class FakeAudio(object):
    def __init__(self, rec, duration=3.0):
        self.rec = rec
        self.duration = duration
        self.stop = threading.Event()
        self.playing = 0
        self.max_playing = 0
        self.tasks = {}
        self.lock = threading.Lock()

    def loadFile(self, path):
        if not os.path.isfile(path):
            raise RuntimeError("file not found")
        task = len(self.tasks) + 1
        self.tasks[task] = path
        self.rec.add("ALAudioPlayer", "loadFile", path)
        return task

    def getFileLength(self, task):
        return self.duration

    def _play(self, label):
        with self.lock:
            self.playing += 1
            self.max_playing = max(self.max_playing, self.playing)
        self.rec.add("ALAudioPlayer", label)
        self.stop.clear()
        self.stop.wait(self.duration)
        with self.lock:
            self.playing -= 1
        self.rec.add("ALAudioPlayer", label + "_end")

    def play(self, task, volume=1.0, pan=0.0):
        self._play("play")

    def playFile(self, path, volume=1.0, pan=0.0):
        self._play("playFile")

    def playFileFromPosition(self, path, position, volume=1.0, pan=0.0):
        self.rec.add("ALAudioPlayer", "position", position)
        self._play("playFileFromPosition")

    def stopAll(self):
        self.rec.add("ALAudioPlayer", "stopAll")
        self.stop.set()

    def unloadAllFiles(self):
        self.tasks = {}


class FakeLeds(object):
    def __init__(self, rec):
        self.rec = rec

    def fadeRGB(self, name, rgb, duration):
        self.rec.add("ALLeds", "fadeRGB", rgb)


class FakeBattery(object):
    def getBatteryCharge(self):
        return 77


class FakeSignal(object):
    def __init__(self):
        self.callbacks = {}

    def connect(self, cb):
        self.callbacks[1] = cb
        return 1

    def disconnect(self, link):
        self.callbacks.pop(link, None)


class FakeSubscriber(object):
    def __init__(self):
        self.signal = FakeSignal()

    def trigger(self, value=1):
        for cb in list(self.signal.callbacks.values()):
            cb(value)


class FakeMemory(object):
    def __init__(self):
        self.subscribers = {}

    def subscriber(self, name):
        self.subscribers[name] = FakeSubscriber()
        return self.subscribers[name]


class FakeSession(object):
    def __init__(self, audio_duration=3.0):
        self.rec = Recorder()
        self.services = {
            "ALMotion": FakeMotion(self.rec), "ALRobotPosture": FakePosture(self.rec),
            "ALTextToSpeech": FakeTTS(self.rec), "ALAudioPlayer": FakeAudio(self.rec, audio_duration),
            "ALLeds": FakeLeds(self.rec), "ALBattery": FakeBattery(), "ALMemory": FakeMemory(),
        }

    def service(self, name):
        if name not in self.services:
            raise RuntimeError("service %s absent" % name)
        return self.services[name]


class Logger(object):
    def __init__(self):
        self.lines = []

    def info(self, msg):
        self.lines.append(("info", msg))

    def error(self, msg):
        self.lines.append(("error", msg))


def make_generated_class(session):
    class GeneratedClass(object):
        def __init__(self):
            self.logger = Logger()

        def session(self):
            return session
    return GeneratedClass


def load_bridge(bridge_path, session, port, allowed=None):
    """Charge choregraphe_bridge.py comme le fait Choregraphe ; renvoie (box, namespace)."""
    ns = {"GeneratedClass": make_generated_class(session), "__name__": "choregraphe_box"}
    with open(bridge_path) as f:
        source = f.read()
    exec(compile(source, bridge_path, "exec"), ns)
    ns["PORT"] = port
    if allowed is not None:
        ns["ALLOWED_CLIENTS"] = allowed
    box = ns["MyClass"]()
    return box, ns
