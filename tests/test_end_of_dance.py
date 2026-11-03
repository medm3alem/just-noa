# -*- coding: utf-8 -*-
"""
Fin de danse : musique coupée, NAO stable, score annoncé puis UNE pique, bilan
enregistré avec le texte, une seule annonce, "Skip", repos après la parole,
rien après une chute, voix désactivable. Robot simulé, session de jeu factice
(rapport fixé à l'avance) : pas de caméra, tests rapides et déterministes.
"""
import os
import random
import shutil
import tempfile
import threading
import time
import unittest
import wave

from tests.helpers import config, swing_choreo
from app.controller import ERREUR, PRET, REPOS, Controller
from evaluation.nao_personality import NaoPersonality
from evaluation.roast_library import NEUTRAL, ROASTS
from reports.session_store import SessionStore
from robot.choregraphe_robot import ChoregrapheRobot
from robot.fake_robot import FakeRobot


def wait_for(predicate, timeout):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


class Cfg(object):
    """Réglages modifiables par test (le contrôleur et la personnalité les relisent)."""
    NAO_SPEAKS = True
    ROAST_ENABLED = True
    ROAST_INTENSITY = "sarcastic"
    COMMENTARY_LENGTH = "short"
    ROAST_PAUSE = 0.2
    ANNOUNCE_INTERRUPTED = True


class RecordingRobot(FakeRobot):
    """FakeRobot qui note l'ordre des actions (parole, musique, repos, postures)."""

    def __init__(self):
        FakeRobot.__init__(self, log=lambda m: None, speech_rate=40.0)
        self.events = []
        self._ev_lock = threading.Lock()

    def note(self, *event):
        with self._ev_lock:
            self.events.append(event + (time.time(),))

    def kinds(self, kind):
        return [e for e in self.events if e[0] == kind]

    def stop_audio(self, handle):
        self.note("stop_audio")
        return FakeRobot.stop_audio(self, handle)

    def say(self, text):
        self.note("say", text)
        FakeRobot.say(self, text)
        self.note("said", text)

    def stop_speech(self):
        self.note("stop_speech")
        FakeRobot.stop_speech(self)

    def rest(self):
        self.note("rest")
        FakeRobot.rest(self)

    def go_to_posture(self, posture, speed):
        self.note("posture", posture)
        FakeRobot.go_to_posture(self, posture, speed)


class StubSession(object):
    """Session de jeu factice : renvoie le rapport prévu à la fin de la danse."""

    def __init__(self, report):
        self.report = report

    def snapshot(self):
        return {"score": None, "in_window": False}

    def finish(self, status):
        return dict(self.report, status=status)


def report(score=42, valid=True, delay=0.4):
    return {"title": "Test", "choreography": "test", "date": "2026-11-02T10:00:00",
            "score": score, "valid": valid, "category": "Needs work", "timing_offset_s": delay,
            "tracking_ratio": 0.95 if valid else 0.1, "activity": 0.95, "frames_analysed": 300,
            "evaluated_duration_s": 3.0 if valid else 0.0, "parts": {}, "advice": [],
            "timeline": []}


def silent_wav(seconds=3.0):
    folder = tempfile.mkdtemp(prefix="jn_wav_")
    path = os.path.join(folder, "silence.wav")
    w = wave.open(path, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(8000)
    w.writeframes(b"\0\0" * int(8000 * seconds))
    w.close()
    return path


def short_choreo(seconds=2.5, audio=True):
    """2,5 s de bras + 3 s de "musique" : le lecteur doit couper la musique à la fin."""
    meta = {"end": seconds}
    if audio:
        meta["audio"] = silent_wav(seconds + 0.5)
    return swing_choreo(2.3, first=0.4, step=0.6, meta=meta)


class EndOfDanceBase(unittest.TestCase):
    rep = None

    def setUp(self):
        self.results = tempfile.mkdtemp(prefix="jn_end_")
        self.store = SessionStore(self.results)
        self.cfg = Cfg()
        self.robot = RecordingRobot()
        rep = self.rep or report()
        self.personality = NaoPersonality(self.cfg, rng=random.Random(5))
        self.ctrl = Controller(self.robot, {"test": short_choreo()},
                               lambda c, o, v: StubSession(rep), self.store,
                               personality=self.personality, cfg=self.cfg)

    def tearDown(self):
        self.ctrl.shutdown()
        shutil.rmtree(self.results, ignore_errors=True)

    def dance(self, stop_after=None):
        ok, message = self.ctrl.start()
        self.assertTrue(ok, message)
        if stop_after is not None:
            self.assertTrue(wait_for(lambda: self.ctrl.status()["state"] == "DANSE", 10))
            time.sleep(stop_after)
            self.ctrl.stop()
        self.assertTrue(wait_for(lambda: self.ctrl.status()["report_seq"] == 1, 20))
        self.assertTrue(wait_for(lambda: self.ctrl.status()["state"] in (PRET, ERREUR), 10))
        return self.ctrl.last_report()


class TestAnnouncement(EndOfDanceBase):

    def test_score_then_one_roast_after_the_music(self):
        rep = self.dance()
        self.assertEqual(self.ctrl.status()["message"], "Dance finished")
        self.assertTrue(wait_for(lambda: len(self.robot.kinds("said")) == 2, 10))
        comment = rep["nao_comment"]
        said = [e[1] for e in self.robot.kinds("say")]
        self.assertEqual(said, [comment["announce"], comment["roast"]])
        self.assertEqual(comment["announce"], "42 points.")
        self.assertIn(comment["roast"], ROASTS[comment["category"]]["sarcastic"])
        # Ordre : musique coupée, retour en posture, PUIS la parole.
        first_say = self.robot.kinds("say")[0][-1]
        self.assertLess(self.robot.kinds("stop_audio")[-1][-1], first_say)
        self.assertLess(self.robot.kinds("posture")[-1][-1], first_say)
        # Bilan enregistré AVEC le commentaire, une seule fois.
        sessions = self.store.list()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0][1]["nao_comment"]["lines"], comment["lines"])
        self.assertTrue(wait_for(lambda: not self.ctrl.status()["speaking"], 10))
        time.sleep(0.5)
        self.assertEqual(len(self.robot.kinds("say")), 2)          # pas d'annonce répétée
        self.ctrl._start_commentary(rep)                              # même bilan : refusé
        time.sleep(0.3)
        self.assertEqual(len(self.robot.kinds("say")), 2)

    def test_skip_commentary(self):
        self.robot.speech_rate = 4.0                                 # phrases longues
        self.dance()
        self.assertTrue(wait_for(lambda: len(self.robot.kinds("say")) == 1, 10))
        self.assertTrue(self.ctrl.status()["speaking"])
        ok, _ = self.ctrl.skip_commentary()
        self.assertTrue(ok)
        self.assertTrue(wait_for(lambda: not self.ctrl.status()["speaking"], 3))
        self.assertTrue(self.robot.kinds("stop_speech"))
        time.sleep(0.5)
        self.assertEqual(len(self.robot.kinds("say")), 1)            # la pique n'est pas dite
        self.assertFalse(self.ctrl.skip_commentary()[0])              # plus rien à passer

    def test_rest_waits_for_the_end_of_speech(self):
        self.robot.speech_rate = 15.0
        self.dance()
        self.assertTrue(wait_for(lambda: len(self.robot.kinds("say")) == 1, 10))
        ok, _ = self.ctrl.rest()
        self.assertTrue(ok)
        self.assertTrue(wait_for(lambda: self.ctrl.status()["state"] == REPOS, 20))
        last_said = self.robot.kinds("said")[-1][-1]
        self.assertEqual(len(self.robot.kinds("said")), 2)
        self.assertGreaterEqual(self.robot.kinds("rest")[-1][-1], last_said)

    def test_new_dance_cuts_the_comment(self):
        self.robot.speech_rate = 4.0
        self.dance()
        self.assertTrue(wait_for(lambda: self.ctrl.status()["speaking"], 5))
        ok, _ = self.ctrl.start()
        self.assertTrue(ok)
        self.assertTrue(wait_for(lambda: not self.ctrl.status()["speaking"], 3))
        self.ctrl.stop()
        self.assertTrue(wait_for(lambda: self.ctrl.status()["state"] == PRET, 10))

    def test_voice_off_keeps_the_text(self):
        self.cfg.NAO_SPEAKS = False
        rep = self.dance()
        time.sleep(0.6)
        self.assertEqual(self.robot.kinds("say"), [])
        self.assertIn("nao_comment", rep)

    def test_sarcasm_off(self):
        self.cfg.ROAST_ENABLED = False
        rep = self.dance()
        neutral = [line for lines in NEUTRAL.values() for line in lines]
        self.assertIn(rep["nao_comment"]["roast"], neutral)

    def test_interrupted_dance_is_announced_separately(self):
        rep = self.dance(stop_after=0.5)
        self.assertEqual(rep["status"], "interrompue")
        self.assertEqual(self.ctrl.status()["message"], "Dance stopped")
        self.assertEqual(rep["nao_comment"]["category"], "interrupted")
        self.assertTrue(wait_for(lambda: len(self.robot.kinds("said")) == 2, 10))
        self.assertEqual(self.robot.kinds("say")[0][1], "42 points, but you stopped early.")

    def test_interrupted_dance_can_stay_silent(self):
        self.cfg.ANNOUNCE_INTERRUPTED = False
        rep = self.dance(stop_after=0.5)
        time.sleep(0.6)
        self.assertNotIn("nao_comment", rep)
        self.assertEqual(self.robot.kinds("say"), [])


class TestNoAnnouncementAfterFall(EndOfDanceBase):

    def test_fall(self):
        self.ctrl.start()
        self.assertTrue(wait_for(lambda: self.ctrl.status()["state"] == "DANSE", 10))
        self.robot.simulate_fall()
        self.assertTrue(wait_for(lambda: self.ctrl.status()["state"] == ERREUR, 5))
        self.assertTrue(wait_for(lambda: self.ctrl.status()["report_seq"] == 1, 5))
        time.sleep(0.6)
        self.assertEqual(self.robot.kinds("say"), [])
        self.assertNotIn("nao_comment", self.ctrl.last_report())
        self.assertIn("fell", self.ctrl.status()["message"])
        # Pas de relevé automatique : il faut une action de l'opérateur.
        self.assertEqual(self.ctrl.status()["state"], ERREUR)


class TestUnevaluable(EndOfDanceBase):
    rep = report(0, valid=False)

    def test_fair_camera_comment(self):
        rep = self.dance()
        self.assertEqual(rep["nao_comment"]["category"], "unevaluable")
        self.assertTrue(wait_for(lambda: len(self.robot.kinds("said")) == 2, 10))
        self.assertEqual(self.robot.kinds("say")[0][1], "No score this time.")
        self.assertEqual(self.store.list(), [])          # rien de noté : pas de bilan enregistré


class TestNoVision(unittest.TestCase):

    def test_no_session_no_comment(self):
        robot = RecordingRobot()
        ctrl = Controller(robot, {"test": short_choreo()}, personality=NaoPersonality(Cfg()), cfg=Cfg())
        try:
            ctrl.start()
            self.assertTrue(wait_for(lambda: ctrl.status()["state"] == "DANSE", 10))
            self.assertTrue(wait_for(lambda: ctrl.status()["state"] == PRET, 15))
            time.sleep(0.5)
            self.assertEqual(robot.kinds("say"), [])
        finally:
            ctrl.shutdown()


class TestRobotDisconnected(unittest.TestCase):
    """Passerelle injoignable : messages clairs en anglais, pas de blocage."""

    def test_unreachable_bridge(self):
        import socket
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()                                        # port libre : personne n'écoute
        robot = ChoregrapheRobot(log=lambda m: None, host="127.0.0.1", port=port)
        st = robot.status()
        self.assertFalse(st["connected"])
        logs = []
        ctrl = Controller(robot, {"test": short_choreo()}, cfg=Cfg())
        ctrl.on_log = logs.append
        try:
            ok, _ = ctrl.start()
            self.assertTrue(ok)
            self.assertTrue(wait_for(lambda: ctrl.status()["state"] == ERREUR, 15))
            message = ctrl.status()["message"]
            self.assertTrue(message.startswith("Robot error: No answer from the Choregraphe bridge"),
                            message)
            self.assertTrue(all(ord(ch) < 128 for ch in message))
        finally:
            ctrl.shutdown()


if __name__ == "__main__":
    unittest.main()
