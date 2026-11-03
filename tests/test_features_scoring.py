# -*- coding: utf-8 -*-
"""Caractéristiques du joueur, comparaison et score sur des parties simulées."""
import unittest

from tests.helpers import fixture_choreo, config, library_choreo, play_session
from evaluation.comparator import Comparator, linear_score
from evaluation.pose_mapping import angle_deg
from evaluation.scoring import ReferenceModel, category_for
from vision.pose_features import PoseSample, extract_features
from vision.synthetic import SyntheticPlayer


class TestFeatures(unittest.TestCase):

    def setUp(self):
        # Chorégraphie figée (échauffement v4) : bras levés à 7 s, bras tendus vers la
        # caméra à 10,5 s. Ne bouge plus quand on retouche les danses de la bibliothèque.
        self.model = ReferenceModel(fixture_choreo("echauffement_v4_fell"), config)

    def features(self, **kw):
        player = SyntheticPlayer(self.model, noise=0.0, **kw)
        return extract_features(player.sample(0.0, 7.0)), self.model.expected("miroir", 7.0)

    def test_features_match_expected(self):
        feats, expected = self.features(lag=0.0)
        for name in ("L_upper", "R_upper", "L_fore", "R_fore"):
            self.assertLess(angle_deg(feats.values[name], expected[name]), 1.0, name)

    def test_invariant_to_size_rotation(self):
        ref, _ = self.features(lag=0.0)
        big, _ = self.features(lag=0.0, scale=1.3, yaw_deg=30)
        for name in ("L_upper", "R_upper"):
            self.assertLess(angle_deg(ref.values[name], big.values[name]), 1.0)

    def test_hidden_points_are_invalid_not_wrong(self):
        feats, _ = self.features(lag=0.0, hide=["L_arm"])
        self.assertNotIn("L_upper", feats.valid)
        self.assertIn("R_upper", feats.valid)

    def test_nan_and_missing_shoulders(self):
        image = {"left_shoulder": (float("nan"), 0.3, 0.9), "right_shoulder": (0.4, 0.3, 0.9)}
        self.assertEqual(extract_features(PoseSample(0.0, image)).valid, set())
        self.assertEqual(extract_features(None).valid, set())

    def test_2d_mode_without_depth(self):
        player = SyntheticPlayer(self.model, noise=0.0, lag=0.0)
        cmp2d = Comparator(use_depth=False)
        feats_set = self.model.feature_sets["miroir"]
        # Bras levés (pose "haut", t = 7 s) : lisibles de face -> note valide et haute
        sample = player.sample(0.0, 7.0)
        sample.world = None                                   # fournisseur 2D seulement
        feats = extract_features(sample)
        self.assertFalse(feats.has_depth)
        match = cmp2d.compare(self.model.expected("miroir", 7.0), feats, feats_set)
        self.assertGreater(match.overall, 0.9)
        # Bras tendus vers la caméra (pose "devant", t = 10,5 s) : illisibles en 2D
        # -> pose "insuffisante" (ni réussie ni ratée), pas une erreur
        sample = player.sample(0.0, 10.5)
        sample.world = None
        match = cmp2d.compare(self.model.expected("miroir", 10.5), extract_features(sample), feats_set)
        self.assertIsNone(match.overall)


class TestComparator(unittest.TestCase):

    def test_linear_score(self):
        self.assertEqual(linear_score(10, 20, 60), 1.0)
        self.assertEqual(linear_score(70, 20, 60), 0.0)
        self.assertAlmostEqual(linear_score(40, 20, 60), 0.5)

    def test_categories(self):
        self.assertEqual(category_for(95), u"Excellent")
        self.assertEqual(category_for(80), u"Great")
        self.assertEqual(category_for(60), u"Good")
        self.assertEqual(category_for(40), u"Needs work")
        self.assertEqual(category_for(10), u"Try again")


class TestSessionScores(unittest.TestCase):
    """Scénarios exigés : correct, faux, immobile, retard, partiel, absent, morphologies."""

    @classmethod
    def setUpClass(cls):
        cls.choreo = library_choreo("echauffement")
        cls.good = play_session(cls.choreo, mode="miroir", lag=0.35, noise=0.01)

    def test_good_player_scores_high(self):
        self.assertTrue(self.good["valid"])
        self.assertGreaterEqual(self.good["score"], 90)
        self.assertEqual(self.good["mapping_mode"], "miroir")
        # Échauffement : gestes lents et longues poses tenues, le retard se mesure moins
        # finement (0,25 s mesuré pour 0,35 s) ; la précision est vérifiée plus bas sur
        # des danses aux gestes nets.
        self.assertAlmostEqual(self.good["timing_offset_s"], 0.35, delta=0.12)
        self.assertGreaterEqual(self.good["moves"]["reussis"], self.good["moves"]["total"] - 1)

    def test_timing_offset_measured_precisely(self):
        # Milieu du plateau de la corrélation (2026-11-02) : retard exact au pas près
        for name in ("mekassarat", "nao_party"):
            r = play_session(library_choreo(name), mode="miroir", lag=0.35, noise=0.01)
            self.assertAlmostEqual(r["timing_offset_s"], 0.35, delta=0.06, msg=name)

    def test_same_side_player_detected_in_auto_mode(self):
        r = play_session(self.choreo, mode="meme_cote", lag=0.35, noise=0.01)
        self.assertEqual(r["mapping_mode"], "meme_cote")
        self.assertGreaterEqual(r["score"], 90)

    def test_immobile_player_scores_low(self):
        r = play_session(self.choreo, static=True)
        self.assertTrue(r["valid"])
        self.assertLess(r["score"], 35)
        self.assertLess(r["activity"], 0.8)

    def test_wrong_moves_score_low(self):
        r = play_session(self.choreo, wrong=True, lag=0.3)
        self.assertLess(r["score"], 60)
        self.assertLess(r["score"], self.good["score"] - 30)

    def test_late_player_is_not_perfect(self):
        r = play_session(self.choreo, lag=1.2, noise=0.01)
        self.assertLess(r["score"], self.good["score"] - 10)
        self.assertGreaterEqual(r["timing_offset_s"], 0.8)
        self.assertTrue(any(u"late" in a for a in r["advice"]))

    def test_absent_player_has_no_valid_score(self):
        r = play_session(self.choreo, absent=True)
        self.assertFalse(r["valid"])
        self.assertEqual(r["tracking_ratio"], 0.0)
        self.assertEqual(r["category"], u"Not scored")

    def test_partially_visible_player(self):
        r = play_session(self.choreo, lag=0.35, hide=["L_arm"])
        self.assertTrue(r["valid"])
        self.assertIsNone(r["parts"]["bras_gauche"])         # non noté, pas compté faux
        self.assertGreaterEqual(r["parts"]["bras_droit"], 90)

    def test_other_morphologies(self):
        for scale, yaw in ((0.8, 0), (1.25, 25)):
            r = play_session(self.choreo, lag=0.35, scale=scale, yaw_deg=yaw, noise=0.01)
            self.assertGreaterEqual(r["score"], 88, (scale, yaw))

    def test_leaving_the_frame_reduces_coverage(self):
        # Le joueur danse bien la première moitié puis disparaît : score réduit, pas à 0
        model = ReferenceModel(self.choreo, config)
        half = (model.eval_start + model.eval_end) / 2
        r1 = play_session(self.choreo, lag=0.35, stop_at=half)
        self.assertGreater(r1["evaluated_duration_s"], 0)

    def test_report_structure(self):
        for key in ("score", "performance", "tracking_ratio", "correct_pose_ratio", "parts",
                    "timeline", "moves", "advice", "category", "algorithm_version", "date",
                    "mapping_mode", "status"):
            self.assertIn(key, self.good)
        statuses = set(row["status"] for row in self.good["timeline"])
        self.assertEqual(statuses, {"ok"})

    def test_interrupted_session_scores_only_danced_part(self):
        r = play_session(self.choreo, lag=0.35, status="interrompue", stop_at=10.0)
        self.assertEqual(r["status"], "interrompue")
        self.assertLessEqual(r["evaluated_duration_s"], 10.0)        # pas les 29 s de la danse
        self.assertGreaterEqual(r["score"], 85)


class TestLowAmplitudeChoreography(unittest.TestCase):
    """nao_party : poses proches -> score moins discriminant, mais immobile reste faible."""

    def test_nao_party(self):
        c = fixture_choreo("nao_party_v1")
        good = play_session(c, lag=0.35, fps=10)
        still = play_session(c, static=True, fps=10)
        self.assertGreaterEqual(good["score"], 90)
        self.assertLess(still["score"], 30)


if __name__ == "__main__":
    unittest.main()
