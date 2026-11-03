# -*- coding: utf-8 -*-
"""Pose de référence : chargement, interpolation, Bezier, cinématique NAO."""
import math
import unittest

from tests.helpers import fixture_choreo, library_choreo, make_choreo
from choreography.reference_pose import DEFAULT_POSE, JointTrack, ReferenceTimeline
from evaluation.pose_mapping import (angle_deg, evaluated_features, expected_player_features,
                                     map_feature_names, nao_arm_vectors, nao_features)


class TestInterpolation(unittest.TestCase):

    def test_simple_track_passes_through_keys_and_holds(self):
        tr = JointTrack([1.0, 2.0, 3.0], [0.0, 1.0, 1.0])
        self.assertAlmostEqual(tr.value(0.0), 0.0)          # avant : première clé
        self.assertAlmostEqual(tr.value(1.0), 0.0)
        self.assertAlmostEqual(tr.value(2.0), 1.0)
        self.assertAlmostEqual(tr.value(2.5), 1.0)          # palier : aucun dépassement
        self.assertAlmostEqual(tr.value(9.0), 1.0)          # après : dernière clé
        mid = tr.value(1.5)
        self.assertTrue(0.0 < mid < 1.0)

    def test_monotone_no_overshoot(self):
        tr = JointTrack([1, 2, 3, 4], [0.0, 1.0, 1.05, 0.0])
        values = [tr.value(1 + i / 100.0) for i in range(301)]
        self.assertLessEqual(max(values), 1.05 + 1e-9)
        self.assertGreaterEqual(min(values), -1e-9)

    def test_bezier_choregraphe_handles(self):
        # Export Choregraphe : [angle, [3, -dt, 0], [3, +dt, 0]] (temps d'abord)
        keys = [[0.0, [3, -0.3, 0.0], [3, 0.3, 0.0]], [1.0, [3, -0.3, 0.0], [3, 0.3, 0.0]]]
        tr = JointTrack([1.0, 2.0], keys, bezier=True, time_index=1)
        self.assertAlmostEqual(tr.value(1.0), 0.0)
        self.assertAlmostEqual(tr.value(2.0), 1.0)
        self.assertAlmostEqual(tr.value(1.5), 0.5, places=3)   # courbe symétrique
        self.assertLess(tr.value(1.1), 0.1)                     # départ en douceur

    def test_bezier_handle_order_detection(self):
        c = make_choreo(["HeadYaw"], [[1.0, 2.0]],
                        [[[0.0, [3, 0.0, -0.3], [3, 0.0, 0.3]], [1.0, [3, 0.0, -0.3], [3, 0.0, 0.3]]]])
        tl = ReferenceTimeline(c)
        self.assertAlmostEqual(tl.pose_at(1.5)["HeadYaw"], 0.5, places=3)


class TestKinematics(unittest.TestCase):

    def pose(self, **kw):
        p = dict(DEFAULT_POSE)
        p.update(kw)
        return p

    def test_shoulder_directions(self):
        down = nao_arm_vectors(self.pose(LShoulderPitch=math.pi / 2, LShoulderRoll=0.0), "L")[0]
        front = nao_arm_vectors(self.pose(LShoulderPitch=0.0, LShoulderRoll=0.0), "L")[0]
        up = nao_arm_vectors(self.pose(LShoulderPitch=-math.pi / 2, LShoulderRoll=0.0), "L")[0]
        side = nao_arm_vectors(self.pose(LShoulderPitch=0.0, LShoulderRoll=math.pi / 2), "L")[0]
        rside = nao_arm_vectors(self.pose(RShoulderPitch=0.0, RShoulderRoll=-math.pi / 2), "R")[0]
        for got, want in ((down, (0, 0, -1)), (front, (1, 0, 0)), (up, (0, 0, 1)),
                          (side, (0, 1, 0)), (rside, (0, -1, 0))):
            self.assertLess(angle_deg(got, want), 1e-6)

    def test_standinit_forearms_point_forward(self):
        for side in ("L", "R"):
            fore = nao_arm_vectors(self.pose(), side)[1]
            self.assertGreater(fore[0], 0.8)          # mains devant le bassin

    def test_mirror_mapping(self):
        nao = nao_features(self.pose(LShoulderPitch=0.0, LShoulderRoll=math.pi / 2))
        mirror = expected_player_features(nao, "miroir")
        same = expected_player_features(nao, "meme_cote")
        # NAO lève son bras GAUCHE sur le côté -> en miroir, le joueur lève son bras DROIT
        self.assertLess(angle_deg(mirror["R_upper"], (0, -1, 0)), 1e-6)
        self.assertLess(angle_deg(same["L_upper"], (0, 1, 0)), 1e-6)
        self.assertEqual(map_feature_names({"L_upper"}, "miroir"), {"R_upper"})


class TestLibrary(unittest.TestCase):

    def test_pose_at_uses_real_data(self):
        c = fixture_choreo("nao_party_v1")
        tl = ReferenceTimeline(c)
        # Première keyframe de HeadYaw : 0.35 rad à 6,8 s (pose 1 du test de Med)
        self.assertAlmostEqual(tl.pose_at(6.8)["HeadYaw"], 0.35)
        self.assertAlmostEqual(tl.pose_at(10.0)["LShoulderPitch"], 0.8)
        # Articulation non pilotée : valeur StandInit par défaut
        self.assertAlmostEqual(tl.pose_at(10.0)["LElbowYaw"], DEFAULT_POSE["LElbowYaw"])

    def test_evaluated_features_follow_driven_joints(self):
        self.assertEqual(evaluated_features(ReferenceTimeline(library_choreo("calibration"))),
                         {"R_upper"})
        self.assertEqual(evaluated_features(ReferenceTimeline(fixture_choreo("nao_party_v1"))),
                         {"L_upper", "L_fore", "R_upper", "R_fore"})

    def test_move_segments(self):
        moves = ReferenceTimeline(fixture_choreo("nao_party_v1")).move_segments()
        self.assertEqual(len(moves), 12)                  # 3 tours x 4 poses
        self.assertEqual(moves[0], (6.8, 8.5))
        self.assertTrue(all(b - a >= 1.0 for a, b in moves))

    def test_duration(self):
        self.assertAlmostEqual(fixture_choreo("nao_party_v1").end, 41.5)


if __name__ == "__main__":
    unittest.main()
