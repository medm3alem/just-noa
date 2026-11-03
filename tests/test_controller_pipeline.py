# -*- coding: utf-8 -*-
"""
Contrôleur + robot simulé + session de jeu + chaîne vision, de bout en bout.
Durées réelles : ces tests prennent ~1 minute (le FakeRobot imite les temps du robot).
"""
import shutil
import tempfile
import threading
import time
import unittest

from tests.helpers import config, fixture_choreo, swing_choreo
from app.controller import ERREUR, PRET, REPOS, Controller
from app.game_session import GameSession
from reports.session_store import SessionStore
from robot.fake_robot import FakeRobot
from vision.pipeline import VisionPipeline, classify_detection
from vision.synthetic import SyntheticPlayer


def short_choreo(seconds=7.0):
    """Bras qui s'ouvrent et se ferment sur le côté, 7 s : assez pour être noté (> 5 s)."""
    return swing_choreo(seconds, first=0.6, step=0.8, meta={"end": seconds + 0.5})


class QuietFake(FakeRobot):
    def __init__(self):
        FakeRobot.__init__(self, log=lambda m: None)


def wait_for(predicate, timeout):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return False


class TestControllerGame(unittest.TestCase):

    def setUp(self):
        self.results = tempfile.mkdtemp(prefix="jn_ctrl_")
        self.choreo = short_choreo()
        self.store = SessionStore(self.results)
        factory = lambda c, origin, voice: GameSession(c, config, origin, voice)
        self.ctrl = Controller(QuietFake(), {"test": self.choreo}, factory, self.store)
        self.pipeline = VisionPipeline(
            config, synthetic_factory=lambda s: SyntheticPlayer(s.model, lag=0.3, noise=0.01),
            log=lambda m: None)
        self.ctrl.on_session = self.pipeline.set_session
        self.pipeline.start()

    def tearDown(self):
        self.pipeline.stop()
        self.ctrl.shutdown()
        shutil.rmtree(self.results, ignore_errors=True)

    def test_full_game_natural_end(self):
        self.assertEqual(self.ctrl.status()["state"], REPOS)
        ok, _ = self.ctrl.start()
        self.assertTrue(ok)
        self.assertTrue(wait_for(lambda: self.ctrl.status()["state"] == "DANSE", 10))
        self.assertTrue(wait_for(lambda: (self.ctrl.status()["game"] or {}).get("score") is not None, 8))
        self.assertTrue(wait_for(lambda: self.ctrl.status()["report_seq"] == 1, 20))
        self.assertTrue(wait_for(lambda: self.ctrl.status()["state"] == PRET, 10))
        report = self.ctrl.last_report()
        self.assertEqual(report["status"], "terminee")
        self.assertTrue(report["valid"])
        self.assertGreater(report["score"], 70)
        self.assertEqual(len(self.store.list()), 1)            # partie enregistrée
        self.assertIsNone(self.ctrl.current_session())        # vision débranchée

    def test_stop_during_dance_interrupts_session(self):
        self.ctrl.start()
        self.assertTrue(wait_for(lambda: self.ctrl.status()["state"] == "DANSE", 10))
        time.sleep(3.0)
        ok, _ = self.ctrl.stop()
        self.assertTrue(ok)
        self.assertTrue(wait_for(lambda: self.ctrl.status()["state"] == PRET, 10))
        report = self.ctrl.last_report()
        self.assertEqual(report["status"], "interrompue")
        self.assertEqual(self.store.best_scores(), {})         # pas de "meilleur score"

    def test_fall_gives_error_and_rest_recovers(self):
        self.ctrl.start()
        self.assertTrue(wait_for(lambda: self.ctrl.status()["state"] == "DANSE", 10))
        self.ctrl.robot.simulate_fall()
        self.assertTrue(wait_for(lambda: self.ctrl.status()["state"] == ERREUR, 5))
        self.assertEqual(self.ctrl.last_report()["status"], "interrompue")
        ok, _ = self.ctrl.rest()
        self.assertTrue(ok)
        self.assertTrue(wait_for(lambda: self.ctrl.status()["state"] == REPOS, 5))

    def test_commands_refused_when_impossible(self):
        self.assertFalse(self.ctrl.stop()[0])                  # rien à arrêter
        self.assertFalse(self.ctrl.rest()[0])                  # déjà au repos
        self.ctrl.start()
        self.assertFalse(self.ctrl.start()[0])                 # déjà en cours
        self.assertFalse(self.ctrl.select("test")[0])          # pas pendant une danse


class TestControllerWithoutGame(unittest.TestCase):
    """Sans fabrique de session (Python 2.7, ou pas de vision) : comportement d'origine."""

    def test_dance_without_session(self):
        ctrl = Controller(QuietFake(), {"test": short_choreo(3.0)})
        try:
            ctrl.start()
            self.assertTrue(wait_for(lambda: ctrl.status()["state"] == "DANSE", 10))
            self.assertIsNone(ctrl.status()["game"])
            self.assertTrue(wait_for(lambda: ctrl.status()["state"] == PRET, 15))
            self.assertIsNone(ctrl.last_report())
        finally:
            ctrl.shutdown()


class TestUnbalancedDanceRefused(unittest.TestCase):
    """La danse qui a fait tomber NAO (échauffement v4) ne peut plus être lancée."""

    def test_fallen_warmup_is_refused(self):
        robot = QuietFake()
        ctrl = Controller(robot, {"tombe": fixture_choreo("echauffement_v4_fell")})
        try:
            ok, message = ctrl.select("tombe")
            self.assertFalse(ok)
            self.assertIn("refused for safety", message)
            ok, _ = ctrl.start()
            self.assertFalse(ok)                     # rien de sélectionné : rien ne bouge
            self.assertEqual(ctrl.status()["state"] in ("DANSE", "PREPARATION"), False)
        finally:
            ctrl.shutdown()


class FakeCamera(object):
    """Caméra factice : renvoie des images noires horodatées."""
    def __init__(self):
        import numpy as np
        self.np = np
        self.seq = 0
        self.started = self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def status(self):
        return True, u"Caméra active"

    def latest(self):
        self.seq += 1
        return self.np.zeros((480, 640, 3), dtype=self.np.uint8), time.time(), self.seq


class TestPipeline(unittest.TestCase):

    def test_camera_without_detector_shows_video(self):
        cfg = type("Cfg", (), {"POSE_MODEL_PATH": "/introuvable.task", "VIDEO_SIZE": (320, 240)})()
        cam = FakeCamera()
        p = VisionPipeline(cfg, camera=cam, log=lambda m: None)
        p.start()
        try:
            self.assertTrue(wait_for(lambda: p.latest_display()[0] is not None, 5))
            frame, _ = p.latest_display()
            self.assertEqual(frame.shape, (240, 320, 3))
            st = p.status()
            self.assertFalse(st["detector_ok"])                # mode démonstration sans score
            self.assertEqual(st["detection"], "indisponible")
            self.assertIn(u"Pose model missing", st["detector_msg"])
        finally:
            p.stop()
        self.assertTrue(cam.stopped)                           # caméra libérée

    def test_stop_leaves_no_thread(self):
        before = threading.active_count()
        p = VisionPipeline(config, synthetic_factory=lambda s: None, log=lambda m: None)
        p.start()
        time.sleep(0.3)
        p.stop()
        time.sleep(0.2)
        self.assertLessEqual(threading.active_count(), before)

    def test_classify_detection(self):
        self.assertEqual(classify_detection(None, None, None), "absent")


if __name__ == "__main__":
    unittest.main()
