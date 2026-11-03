# -*- coding: utf-8 -*-
"""
Passerelle Choregraphe v3 + backend ChoregrapheRobot, de bout en bout sur le PC.

La vraie passerelle (choregraphe_bridge.py) tourne avec de faux services NAOqi
(tests/fake_naoqi.py) ; l'application lui parle en TCP comme au vrai robot.
Ce qui est vérifié : format des commandes, Stop qui n'attend pas la fin d'une
danse, cycle de vie de l'audio, pas de musiques superposées, interruption de la
parole, sécurité (jambes, chute, clients), déconnexion, compatibilité v2, et
synchronisation musique/mouvement côté passerelle.

Ce ne sont PAS des essais sur le robot : voir docs/HARDWARE_TESTS.md.
Compatibilité Python 2.7 de la passerelle : définir JN_PY27=chemin\\python.exe
(Python 2.7) pour lancer aussi la passerelle dans un vrai interpréteur 2.7.
"""
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from tests.helpers import ROOT, make_choreo
from tests.fake_naoqi import FakeSession, load_bridge
from robot.base import RobotError
from robot.choregraphe_robot import ChoregrapheRobot
from sync.player import FINISHED, STOPPED, Player

BRIDGE = os.path.join(ROOT, "choregraphe_bridge.py")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait(predicate, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


class BridgeCase(unittest.TestCase):
    allowed = None
    audio_duration = 3.0

    def setUp(self):
        self.port = free_port()
        self.session = FakeSession(audio_duration=self.audio_duration)
        self.rec = self.session.rec
        self.box, self.ns = load_bridge(BRIDGE, self.session, self.port, self.allowed)
        self.box.onInput_onStart()
        self.assertTrue(wait(lambda: self.box.server is not None))
        self.robot = ChoregrapheRobot(log=lambda m: None, host="127.0.0.1", port=self.port)
        self.audio_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        self.audio_file.close()

    def tearDown(self):
        self.box.onUnload()
        os.remove(self.audio_file.name)

    def background(self, fn, *args):
        result = {}

        def run():
            try:
                result["value"] = fn(*args)
            except Exception as err:                # noqa: BLE001 - on veut tout voir
                result["error"] = err
        t = threading.Thread(target=run)
        t.daemon = True
        t.start()
        return t, result


class TestBridgeProtocol(BridgeCase):

    def test_connect_detects_v3_and_measures_latency(self):
        self.robot.connect()
        self.assertEqual(self.robot.bridge_version, "pong-physique-v3")
        self.assertTrue(self.robot.is_v3)
        self.assertIsNotNone(self.robot.latency_ms)
        st = self.robot.status()
        self.assertTrue(st["connected"])
        self.assertEqual(st["battery"], 77)
        self.assertFalse(st["fallen"])

    def test_stop_is_not_blocked_by_a_running_dance(self):
        self.robot.connect()
        names = ["LShoulderPitch", "RShoulderPitch"]
        t, res = self.background(self.robot.play_motion, names, [[30.0], [30.0]], [[0.5], [0.5]])
        self.assertTrue(wait(lambda: self.rec.find("angleInterpolation")))
        started = time.time()
        self.robot.stop_motion(names)                     # pendant une "danse" de 30 s
        self.assertLess(time.time() - started, 1.0)
        t.join(2.0)
        self.assertFalse(t.is_alive(), "le play aurait du se terminer apres stop")
        self.assertNotIn("error", res)

    def test_second_motion_is_refused_while_dancing(self):
        self.robot.connect()
        t, _ = self.background(self.robot.play_motion, ["HeadYaw"], [[30.0]], [[0.2]])
        self.assertTrue(wait(lambda: self.rec.find("angleInterpolation")))
        with self.assertRaises(RobotError) as ctx:
            self.robot.go_to_posture("StandInit", 0.5)
        self.assertIn("busy", str(ctx.exception))
        self.robot.stop_motion(["HeadYaw"])
        t.join(2.0)

    def test_audio_lifecycle_and_no_overlap(self):
        self.robot.connect()
        handle = self.robot.prepare_audio("local.wav", robot_path=self.audio_file.name)
        self.assertIsNotNone(handle["id"])
        started = time.time()
        self.robot.play_audio(handle)                     # ne bloque pas : NAO joue dans un thread
        self.assertLess(time.time() - started, 1.0)
        self.assertTrue(wait(lambda: self.rec.find("play")))
        self.assertTrue(self.box._audio_status()["playing"])
        # Rejouer : la première lecture est coupée avant la seconde
        handle2 = self.robot.prepare_audio("local.wav", robot_path=self.audio_file.name)
        self.robot.play_audio(handle2)
        self.assertTrue(wait(lambda: len(self.rec.find("play")) == 2))
        time.sleep(0.1)
        self.assertEqual(self.session.services["ALAudioPlayer"].max_playing, 1)
        self.robot.stop_audio(handle2)
        self.assertTrue(wait(lambda: not self.box._audio_status()["playing"], 2.0))

    def test_audio_start_position(self):
        self.robot.connect()
        handle = self.robot.prepare_audio("local.wav", robot_path=self.audio_file.name, start=48.0)
        self.robot.play_audio(handle)
        self.assertTrue(wait(lambda: self.rec.find("position")))
        self.assertEqual(self.rec.find("position")[0][3], (48.0,))
        self.robot.stop_audio(handle)

    def test_missing_audio_file_is_reported(self):
        self.robot.connect()
        with self.assertRaises(RobotError) as ctx:
            self.robot.prepare_audio("x.wav", robot_path="/home/nao/music/absent.wav")
        self.assertIn("not found on NAO", str(ctx.exception))
        with self.assertRaises(RobotError):
            self.robot.prepare_audio("x.wav", robot_path=None)   # pas de chemin robot

    def test_speech_can_be_interrupted(self):
        self.robot.connect()
        t, res = self.background(self.robot.say, "x" * 90)       # ~2,7 s de parole
        self.assertTrue(wait(lambda: self.rec.find("say")))
        started = time.time()
        self.robot.stop_speech()
        t.join(2.0)
        self.assertFalse(t.is_alive())
        self.assertLess(time.time() - started, 1.0)

    def test_leg_motion_is_refused(self):
        self.robot.connect()
        with self.assertRaises(RobotError) as ctx:
            self.robot.play_motion(["LKneePitch"], [[1.0]], [[0.5]])
        self.assertIn("leg motion disabled", str(ctx.exception))

    def test_fall_stops_everything_and_blocks_motion(self):
        self.robot.connect()
        fell = []
        self.robot.on_fall(lambda: fell.append(True))
        self.session.services["ALMemory"].subscribers["robotHasFallen"].trigger()
        self.assertTrue(self.rec.find("killAll"))
        st = self.robot.status()                         # le moniteur de l'appli lit l'état
        self.assertTrue(st["fallen"])
        self.assertEqual(fell, [True])
        with self.assertRaises(RobotError):
            self.robot.move_to(["HeadYaw"], [0.1], 0.5)
        self.robot.wake_up()                             # relevé par un humain, puis réveil
        self.robot.move_to(["HeadYaw"], [0.1], 0.3)

    def test_errors_are_reported_not_crashing(self):
        self.robot.connect()
        with self.assertRaises(RobotError) as ctx:
            self.robot._request("dance_badly")
        self.assertIn("unknown command", str(ctx.exception))
        s = socket.create_connection(("127.0.0.1", self.port))
        s.sendall(b"{pas du json\n")
        reply = s.recv(4096)
        s.close()
        self.assertIn(b'"ok": false', reply)
        self.assertTrue(self.robot.status()["connected"])   # la passerelle tourne toujours

    def test_emergency_stop(self):
        self.robot.connect()
        handle = self.robot.prepare_audio("l.wav", robot_path=self.audio_file.name)
        self.robot.play_audio(handle)
        self.robot.emergency_stop()
        self.assertTrue(self.rec.find("killAll"))
        self.assertTrue(self.rec.find("stopAll"))


class TestClientFilter(BridgeCase):
    allowed = ("10.99.",)                                # localhost n'est pas autorisé

    def test_unknown_client_is_rejected(self):
        with self.assertRaises(RobotError) as ctx:
            self.robot.connect()
        self.assertIn("not allowed", str(ctx.exception))
        self.assertFalse(self.rec.find("wakeUp"))


class TestSyncThroughBridge(BridgeCase):
    audio_duration = 30.0

    def choreo(self, audio_path):
        times = [[0.5, 1.0, 1.5, 2.0]] * 2
        keys = [[0.3, -0.5, 0.3, 0.6]] * 2
        return make_choreo(["LShoulderPitch", "RShoulderPitch"], times, keys,
                           {"end": 2.6, "audio": None, "audio_robot": audio_path})

    def test_music_and_motion_start_together_and_stop_at_end(self):
        self.robot.connect()
        player = Player(self.robot, log=lambda m: None)
        result = player.play(self.choreo(self.audio_file.name), threading.Event())
        self.assertEqual(result, FINISHED)
        audio_start = self.rec.find("play")[0][0]
        motion_start = [c for c in self.rec.find("angleInterpolation") if c[3][0] == ["LShoulderPitch", "RShoulderPitch"]]
        # 1er angleInterpolation = pose de départ ; le 2e = la danse
        dance_start = motion_start[1][0]
        self.assertLess(abs(audio_start - dance_start), 0.15)
        self.assertTrue(self.rec.find("stopAll"))           # musique coupée à 'end'
        self.assertTrue(wait(lambda: not self.box._audio_status()["playing"], 2.0))

    def test_stop_cuts_music_and_motion(self):
        self.robot.connect()
        player = Player(self.robot, log=lambda m: None)
        stop = threading.Event()
        threading.Timer(1.2, stop.set).start()
        result = player.play(self.choreo(self.audio_file.name), stop)
        self.assertEqual(result, STOPPED)
        self.assertTrue(self.rec.find("killTasksUsingResources"))
        self.assertTrue(wait(lambda: not self.box._audio_status()["playing"], 2.0))


class TestDisconnectionAndCompat(unittest.TestCase):

    def test_unreachable_bridge(self):
        robot = ChoregrapheRobot(log=lambda m: None, host="127.0.0.1", port=free_port())
        with self.assertRaises(RobotError):
            robot.connect()
        self.assertFalse(robot.status()["connected"])

    def test_v2_bridge_compatibility(self):
        robot = ChoregrapheRobot(log=lambda m: None)
        sent = []
        robot._request = lambda cmd, timeout=15, **p: sent.append((cmd, p)) or (
            "pong-physique-v2" if cmd == "ping" else {"awake": False})
        robot.connect()
        self.assertFalse(robot.is_v3)
        handle = robot.prepare_audio("m.wav", robot_path="/home/nao/music/macarena.mp3")
        robot.play_audio(handle)
        self.assertIn(("audio_play", {}), sent)                # v2 : sans paramètre
        self.assertNotIn("audio_load", [c for c, _ in sent])

    def test_v3_command_format(self):
        robot = ChoregrapheRobot(log=lambda m: None, volume=0.7)
        sent = []
        robot._request = lambda cmd, timeout=15, **p: sent.append((cmd, p)) or (
            "pong-physique-v3" if cmd == "ping" else {"id": 4, "duration": 66.0})
        robot.connect()
        handle = robot.prepare_audio("m.wav", robot_path="/home/nao/music/macarena_extrait.wav")
        robot.play_audio(handle)
        self.assertIn(("audio_load", {"path": "/home/nao/music/macarena_extrait.wav"}), sent)
        self.assertIn(("audio_play", {"id": 4, "path": "/home/nao/music/macarena_extrait.wav",
                                      "start": 0.0, "volume": 0.7}), sent)


@unittest.skipUnless(os.environ.get("JN_PY27"), "definir JN_PY27 pour tester la passerelle en Python 2.7")
class TestBridgePython27(unittest.TestCase):

    def test_bridge_runs_under_python27(self):
        port = free_port()
        proc = subprocess.Popen([os.environ["JN_PY27"], os.path.join(ROOT, "tests", "bridge_harness.py"),
                                 str(port)], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        try:
            line = proc.stdout.readline().decode()
            self.assertTrue(line.startswith("READY 2.7"), line)
            robot = ChoregrapheRobot(log=lambda m: None, host="127.0.0.1", port=port)
            robot.connect()
            self.assertEqual(robot.bridge_version, "pong-physique-v3")
            t = threading.Thread(target=robot.play_motion,
                                 args=(["LShoulderPitch"], [[20.0]], [[0.4]]))
            t.start()
            time.sleep(0.4)
            started = time.time()
            robot.stop_motion(["LShoulderPitch"])
            t.join(3.0)
            self.assertFalse(t.is_alive())
            self.assertLess(time.time() - started, 1.5)
            robot.say(u"Ninety-six points!")
            self.assertEqual(robot.status()["battery"], 77)
        finally:
            proc.stdin.close()
            proc.wait(5)
            proc.stdout.close()


if __name__ == "__main__":
    unittest.main()
