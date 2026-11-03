# -*- coding: utf-8 -*-
"""Session de jeu, feedback, sauvegarde, historique et exports."""
import csv
import io
import json
import os
import shutil
import tempfile
import unittest

from tests.helpers import config, library_choreo, play_session
from app.game_session import GameSession
from evaluation.feedback import LATE, PRAISE_TOP, FeedbackEngine, advice_from_summary, correction_for
from reports.session_store import SessionStore


class TestFeedback(unittest.TestCase):

    def test_messages_follow_detection_and_score(self):
        fb = FeedbackEngine(config)
        self.assertEqual(fb.update(0.0, "absent", True, None)[0], u"Come back into the camera frame!")
        self.assertIn(u"Step back", fb.update(0.1, "partiel", True, None)[0])
        self.assertEqual(fb.update(0.2, "bord", True, None)[0], u"Step back so I can see your whole upper body!")
        self.assertEqual(fb.update(2.0, "bord", True, None)[0], u"Move to the center of the frame!")
        self.assertEqual(fb.update(4.0, "ok", False, None)[0], u"Get ready... copy NAO!")
        fb = FeedbackEngine(config)
        msg = fb.update(5.0, "ok", True, {"score": 92, "activity": 1.0, "delay": 0.3, "match": None})
        self.assertIn(msg[0], PRAISE_TOP)
        first = msg[0]
        # Maintien minimal : un message différent n'apparaît pas immédiatement
        msg = fb.update(5.2, "ok", True, {"score": 40, "activity": 1.0, "delay": 0.3, "match": None})
        self.assertEqual(msg[0], first)
        msg = fb.update(7.0, "ok", True, {"score": 40, "activity": 0.3, "delay": 0.3, "match": None})
        self.assertEqual(msg[0], u"Don't stop now!")
        msg = fb.update(9.0, "ok", True, {"score": 40, "activity": 1.0, "delay": 0.9, "match": None})
        self.assertIn(msg[0], LATE)

    def test_corrections(self):
        self.assertEqual(correction_for("L_upper", (0.0, 0.0, 0.8)), u"Raise your left arm!")
        self.assertEqual(correction_for("R_upper", (0.0, 0.0, -0.8)), u"Lower your right arm!")
        self.assertEqual(correction_for("R_upper", (0.0, -0.9, 0.1)), u"Spread your right arm out!")
        self.assertEqual(correction_for("L_upper", (0.0, -0.9, 0.1)), u"Bring your left arm in!")
        self.assertEqual(correction_for("L_upper", (0.9, 0.0, 0.1)), u"Reach forward with your left arm!")
        self.assertEqual(correction_for("L_fore", (0.1, 0.1, 0.1), flex=40), u"Bend your left elbow!")
        self.assertEqual(correction_for("R_fore", (0.1, 0.1, 0.1), flex=-40), u"Straighten your right arm!")

    def test_voice_is_rare_and_optional(self):
        class Cfg(object):
            VOICE_FEEDBACK = True
            VOICE_MIN_INTERVAL = 10.0
        fb = FeedbackEngine(Cfg())
        live = {"score": 95, "activity": 1.0, "delay": 0.2, "match": None}
        voices = [fb.update(t * 0.1, "ok", True, live)[2] for t in range(200)]   # 20 s
        self.assertEqual(len([v for v in voices if v]), 2)
        fb_off = FeedbackEngine(config)                                          # désactivé
        self.assertFalse(any(fb_off.update(t * 0.1, "ok", True, live)[2] for t in range(100)))

    def test_advice_for_invalid_session(self):
        tips = advice_from_summary({"valid": False, "invalid_reason": u"Joueur trop peu détecté."})
        self.assertIn(u"Joueur trop peu détecté.", tips)


class TestSessionLifecycle(unittest.TestCase):

    def test_no_score_before_music_starts(self):
        c = library_choreo("echauffement")
        s = GameSession(c, config, origin_fn=lambda: None)
        s.add_sample(1.0, None, "absent")
        snap = s.snapshot()
        self.assertIsNone(snap["score"])
        self.assertEqual(snap["detection"], "absent")
        report = s.finish("interrompue")
        self.assertEqual(report["evaluated_duration_s"], 0)
        self.assertFalse(report["valid"])

    def test_finish_is_idempotent_and_freezes(self):
        r = play_session(library_choreo("echauffement"), lag=0.35, fps=8)
        self.assertEqual(r["status"], "terminee")
        self.assertGreater(r["frames_analysed"], 100)


class TestStore(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="jn_results_")
        self.store = SessionStore(self.dir)
        self.report = play_session(library_choreo("echauffement"), lag=0.35, fps=8)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_save_load_list_best(self):
        p1 = self.store.save(self.report)
        bad = dict(self.report, score=99.0, status="interrompue")
        p2 = self.store.save(bad)
        self.assertNotEqual(p1, p2)
        with io.open(p1, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["choreography"], "echauffement")
        self.assertEqual(len(self.store.list()), 2)
        # Une partie interrompue ne compte pas pour le meilleur score
        self.assertEqual(self.store.best_scores(), {"echauffement": self.report["score"]})

    def test_corrupted_file_is_ignored(self):
        self.store.save(self.report)
        with open(os.path.join(self.store.sessions_dir, "session_29990101_000000.json"), "w") as f:
            f.write("{pas du json")
        self.assertEqual(len(self.store.list()), 1)

    def test_exports(self):
        path = self.store.export_csv(self.report)
        with io.open(path, encoding="utf-8") as f:
            rows = list(csv.reader(f, delimiter=";"))
        header = rows.index(["t_s", "score", "statut"])
        self.assertEqual(len(rows) - header - 1, len(self.report["timeline"]))
        self.assertTrue(os.path.isfile(self.store.export_json(self.report)))


if __name__ == "__main__":
    unittest.main()
