# -*- coding: utf-8 -*-
"""
Personnalité de NAO (coach sarcastique) : choix du commentaire de fin.

Tout est déterministe : le hasard vient d'un random.Random(graine).
Aucun robot ni caméra : on fabrique des rapports de partie à la main.
"""
import os
import random
import re
import shutil
import tempfile
import unittest

from tests.helpers import config  # noqa: F401  (chemin du projet)
from evaluation.nao_personality import NaoPersonality, diagnose
from evaluation.roast_library import FACTS, INTENSITIES, NEUTRAL, ROASTS, all_lines

BANDS = ("poor", "weak", "average", "good", "excellent")
DIAGNOSTICS = ("barely_moves", "late", "early", "arms_wrong", "arms_asymmetric", "rigid",
               "out_of_frame", "great_sync")
# Mots interdits : rien sur le corps, l'apparence ou l'identité du joueur ; pas de jambes
# (les chorégraphies actuelles n'évaluent que les bras).
FORBIDDEN = (r"\blegs?\b", r"\bknees?\b", r"\bfeet\b", r"\bfoot\b", r"\bhips?\b",
             r"\bweight", r"\bfat\b", r"\bugly\b", r"\bfaces?\b", r"\bhair", r"\bclothes\b",
             r"\boutfit", r"\bskin\b", r"\bage\b", r"\bold (man|woman|person)\b", r"\bgirls?\b",
             r"\bboys?\b", r"\bstupid", r"\bidiot", r"\bdumb\b", r"\bloser", r"\bkill",
             r"\bdie\b", r"\bdisab", r"\brace\b", r"\breligio", r"\bbody\b", r"\bshort\b",
             r"\btall\b")


class Cfg(object):
    ROAST_ENABLED = True
    ROAST_INTENSITY = "sarcastic"
    COMMENTARY_LENGTH = "short"


def report(score=60, valid=True, status="terminee", delay=0.4, tracking=0.95, activity=0.95,
           left=None, right=None, flex=None):
    rep = {"score": score, "valid": valid, "status": status, "timing_offset_s": delay,
           "tracking_ratio": tracking, "activity": activity, "frames_analysed": 500,
           "parts": {"bras_gauche": score if left is None else left,
                     "bras_droit": score if right is None else right},
           "moves": {"reussis": 7, "total": 10}, "mean_diffs": {}}
    if flex is not None:
        rep["mean_diffs"] = {"L_flex": [flex], "R_flex": [flex]}
    return rep


def nao(seed=1, **cfg):
    c = Cfg()
    for k, v in cfg.items():
        setattr(c, k, v)
    return NaoPersonality(c, rng=random.Random(seed))


def words(lines):
    return sum(len(line.split()) for line in lines)


class TestLibrary(unittest.TestCase):

    def test_at_least_fifty_unique_roasts(self):
        lines = all_lines()
        self.assertGreaterEqual(len(lines), 50)
        self.assertEqual(len(lines), len(set(lines)), "phrases en double")

    def test_every_category_has_every_intensity(self):
        for category in BANDS + DIAGNOSTICS + ("unevaluable", "interrupted"):
            for intensity in INTENSITIES:
                self.assertTrue(ROASTS[category].get(intensity), (category, intensity))

    def test_lines_are_short_english_and_about_the_dance_only(self):
        for line in all_lines() + [l for v in NEUTRAL.values() for l in v] + list(FACTS.values()):
            low = line.lower()
            for pattern in FORBIDDEN:
                self.assertIsNone(re.search(pattern, low), "%r contient %r" % (line, pattern))
            self.assertLessEqual(len(line.split()), 26, line)        # ~3 a 9 s a voix haute
            self.assertTrue(all(ord(ch) < 128 for ch in line), line)   # anglais, TTS sans surprise
            self.assertIsNone(re.search(u"[éèàùçê]", line), line)


class TestDiagnostics(unittest.TestCase):

    def test_measured_issues_only(self):
        self.assertEqual(diagnose(report(60)), [])
        self.assertIn("late", diagnose(report(60, delay=1.0)))
        self.assertIn("early", diagnose(report(60, delay=-0.4)))
        self.assertIn("barely_moves", diagnose(report(30, activity=0.4)))
        self.assertIn("out_of_frame", diagnose(report(60, tracking=0.6)))
        self.assertIn("arms_wrong", diagnose(report(40)))
        self.assertIn("arms_asymmetric", diagnose(report(60, left=80, right=45)))
        self.assertIn("rigid", diagnose(report(60, flex=30)))
        self.assertIn("great_sync", diagnose(report(85, delay=0.2)))

    def test_no_diagnostic_without_measurement(self):
        rep = report(40)
        rep["timing_offset_s"] = None
        rep["activity"] = None
        rep["parts"] = {}
        self.assertEqual(diagnose(rep), [])                       # rien de mesuré : rien d'inventé
        self.assertEqual(diagnose(report(10, valid=False)), [])  # partie non évaluable
        # Retard peu fiable si le joueur a été mal suivi : on ne le reproche pas.
        self.assertNotIn("late", diagnose(report(60, delay=1.0, tracking=0.5)))


class TestComments(unittest.TestCase):

    def test_score_bands(self):
        for score, band in ((10, "poor"), (30, "poor"), (31, "weak"), (50, "weak"), (51, "average"),
                            (70, "average"), (71, "good"), (89, "good"), (90, "excellent"),
                            (100, "excellent")):
            n = nao()
            self.assertEqual(n.band(score), band)
            rep = report(score, delay=0.5)                       # pas de diagnostic particulier
            rep["parts"] = {}
            c = n.comment(rep)
            self.assertEqual(c["category"], band, score)
            self.assertIn(c["roast"], ROASTS[band]["sarcastic"])
            self.assertTrue(c["announce"].startswith("%d points" % score))
            self.assertEqual(c["lines"], [c["announce"], c["roast"]])

    def test_diagnostic_line_for_weak_dance(self):
        c = nao().comment(report(45, delay=1.0))
        self.assertEqual(c["category"], "late")
        self.assertIn(c["roast"], ROASTS["late"]["sarcastic"])
        c = nao().comment(report(25, activity=0.3))
        self.assertEqual(c["category"], "barely_moves")

    def test_intensities(self):
        for intensity in INTENSITIES:
            rep = report(20)
            rep["parts"] = {}
            c = nao(ROAST_INTENSITY=intensity).comment(rep)
            self.assertIn(c["roast"], ROASTS["poor"][intensity])
            self.assertEqual(c["intensity"], intensity)
        c = nao(ROAST_INTENSITY="nonsense").comment(report(20))
        self.assertEqual(c["intensity"], "sarcastic")

    def test_sarcasm_off_gives_kind_comment(self):
        neutral = [l for v in NEUTRAL.values() for l in v]
        for score in (10, 60, 95):
            c = nao(ROAST_ENABLED=False).comment(report(score))
            self.assertIn(c["roast"], neutral)
            self.assertEqual(c["intensity"], "off")

    def test_no_repetition(self):
        n = nao(seed=3)
        rep = report(20)
        rep["parts"] = {}
        said = [n.comment(rep)["roast"] for _ in range(len(ROASTS["poor"]["sarcastic"]))]
        self.assertEqual(len(said), len(set(said)), said)

    def test_history_survives_restart(self):
        folder = tempfile.mkdtemp(prefix="jn_roast_")
        try:
            path = os.path.join(folder, "roast_history.json")
            rep = report(20)
            rep["parts"] = {}
            first = NaoPersonality(Cfg(), random.Random(1), history_path=path)
            said = set(first.comment(rep)["roast"] for _ in range(5))
            second = NaoPersonality(Cfg(), random.Random(1), history_path=path)
            for _ in range(3):
                self.assertNotIn(second.comment(rep)["roast"], said)
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_seed_makes_it_reproducible(self):
        a, b = nao(seed=42), nao(seed=42)
        reps = [report(s) for s in (12, 44, 63, 80, 97)]
        self.assertEqual([a.comment(r)["lines"] for r in reps], [b.comment(r)["lines"] for r in reps])

    def test_unevaluable_session(self):
        c = nao().comment(report(0, valid=False, tracking=0.1))
        self.assertEqual(c["category"], "unevaluable")
        self.assertEqual(c["announce"], "No score this time.")
        self.assertIn(c["roast"], ROASTS["unevaluable"]["sarcastic"])
        self.assertIsNone(c["fact"])

    def test_missing_score(self):
        rep = report(0, valid=False)
        rep.pop("score")
        c = nao().comment(rep)
        self.assertEqual(c["category"], "unevaluable")
        rep = {"status": "terminee"}                              # rapport minimal
        self.assertEqual(nao().comment(rep)["category"], "unevaluable")

    def test_interrupted_session(self):
        c = nao().comment(report(55, status="interrompue"))
        self.assertEqual(c["category"], "interrupted")
        self.assertEqual(c["announce"], "55 points, but you stopped early.")
        self.assertIn(c["roast"], ROASTS["interrupted"]["sarcastic"])
        c = nao().comment(report(0, valid=False, status="interrompue"))
        self.assertEqual(c["announce"], "Dance stopped.")

    def test_long_mode_adds_a_measured_fact(self):
        c = nao(COMMENTARY_LENGTH="long").comment(report(45, delay=1.0))
        self.assertEqual(c["fact"], "You were about 1.0 seconds behind me.")
        self.assertEqual(len(c["lines"]), 3)
        c = nao(COMMENTARY_LENGTH="long").comment(report(60, left=80, right=45))
        self.assertEqual(c["fact"], "Your left arm did much better than your right arm.")
        c = nao(COMMENTARY_LENGTH="long").comment(report(60))
        self.assertEqual(c["fact"], "You got 7 of 10 moves right.")

    def test_comment_length_fits_5_to_15_seconds(self):
        # ~2.5 mots/s pour la synthèse vocale de NAO + pause de 0,7 s après le score.
        for length in ("short", "long"):
            for intensity in INTENSITIES:
                n = nao(seed=7, COMMENTARY_LENGTH=length, ROAST_INTENSITY=intensity)
                for score in range(0, 101, 7):
                    for rep in (report(score), report(score, delay=1.0), report(score, valid=False)):
                        lines = n.comment(rep)["lines"]
                        seconds = words(lines) / 2.5 + 0.7
                        self.assertLessEqual(seconds, 15.0, lines)
                        self.assertGreaterEqual(seconds, 2.5, lines)


if __name__ == "__main__":
    unittest.main()
