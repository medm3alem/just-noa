# -*- coding: utf-8 -*-
"""
Chorégraphies composées (Macarena, NAO Party, Warm-up) et Calibration :
sécurité des trajectoires, rythme, compatibilité avec le score du joueur, Stop.

Tout est SIMULÉ (modèle géométrique de NAO, faux services NAOqi) : ces tests ne
valent pas un essai sur le robot physique (docs/DANCE_VALIDATION.md).
"""
import io
import json
import math
import os
import random
import shutil
import sys
import tempfile
import threading
import time
import unittest
import wave

from tests.helpers import LIBRARY, ROOT, config, fixture_choreo, library_choreo, make_choreo, play_session
from choreography.beatgrid import BeatGrid
from choreography.composer import Composer, bezier_keys, monotone_slopes
from choreography.kinematics import (arm_points, check_trajectory, head_pitch_range,
                                     min_clearance, pose_clearances)
from choreography.reference_pose import DEFAULT_POSE, JointTrack, ReferenceTimeline
from evaluation.pose_mapping import FEATURE_JOINTS, angle_deg, nao_features
from evaluation.scoring import ReferenceModel, evaluated_features
from robot.fake_robot import NAO_LIMITS

sys.path.insert(0, os.path.join(ROOT, "tools"))
import compose_choreographies as compose  # noqa: E402

COMPOSED = ("macarena", "nao_party", "echauffement", "mekassarat")
ALLOWED_JOINTS = set(["HeadYaw", "HeadPitch"] + [s + j for s in "LR" for j in
                     ("ShoulderPitch", "ShoulderRoll", "ElbowYaw", "ElbowRoll", "WristYaw", "Hand")])
MACARENA_ORDER = ["Right arm out", "Palms up", "Hands to shoulders", "Hands behind head",
                  "Hands on hips", "Hands behind hips", "Wiggle", "Ay!"]


def limits_for(choreo):
    return dict((n, NAO_LIMITS.get(n)) for n in choreo.names)


def peak_speed_ratio(choreo, step=0.005):
    tl = ReferenceTimeline(choreo)
    worst = {}
    for name, times in zip(choreo.names, choreo.times):
        track = tl.tracks[name]
        prev, best = track.value(times[0]), 0.0
        n = int((times[-1] - times[0]) / step)
        for k in range(1, n + 1):
            v = track.value(times[0] + k * step)
            best = max(best, abs(v - prev) / step)
            prev = v
        worst[name] = best / NAO_LIMITS[name][2]
    return worst


# =============================================================================
class TestKinematics(unittest.TestCase):

    def test_forward_kinematics_reference_values(self):
        pts = arm_points({}, "L")                     # bras gauche à zéro : tendu devant
        self.assertAlmostEqual(pts["tip"][0], 105 + 55.95 + 85, places=3)
        self.assertAlmostEqual(pts["tip"][1], 98 + 15, places=3)
        self.assertAlmostEqual(pts["palm"][2], -1.0, places=6)      # paume vers le bas
        down = arm_points({"LShoulderPitch": math.pi / 2}, "L")      # bras vers le bas
        self.assertLess(down["tip"][2], -100)

    def test_mirror_symmetry(self):
        left = {"LShoulderPitch": 0.3, "LShoulderRoll": 0.4, "LElbowYaw": -1.0, "LElbowRoll": -0.8,
                "LWristYaw": 0.5}
        right = {"RShoulderPitch": 0.3, "RShoulderRoll": -0.4, "RElbowYaw": 1.0, "RElbowRoll": 0.8,
                 "RWristYaw": -0.5}
        pl, pr = arm_points(left, "L"), arm_points(right, "R")
        for key in ("elbow", "wrist", "tip", "palm"):
            self.assertAlmostEqual(pl[key][0], pr[key][0], places=6)
            self.assertAlmostEqual(pl[key][1], -pr[key][1], places=6)
            self.assertAlmostEqual(pl[key][2], pr[key][2], places=6)

    def test_collision_model(self):
        self.assertGreater(min_clearance(DEFAULT_POSE)[0], 20)      # StandInit : libre
        # Main gauche plaquée contre le visage : collision détectée
        face = dict(DEFAULT_POSE, LShoulderPitch=-0.6, LShoulderRoll=-0.3, LElbowYaw=0.0,
                    LElbowRoll=-1.54)
        clear = pose_clearances(face)
        self.assertLess(min(v for k, v in clear.items() if "head" in k), 0)

    def test_head_envelope(self):
        lo0, hi0 = head_pitch_range(0.0)
        lo1, hi1 = head_pitch_range(1.4)
        self.assertLess(hi1, hi0)                     # tête tournée : moins d'amplitude
        self.assertGreater(lo1, lo0)
        errors, _, _ = check_trajectory(lambda t: dict(DEFAULT_POSE, HeadYaw=1.4, HeadPitch=0.4),
                                        0.0, 0.1, 0.05, arms=False)
        self.assertTrue(errors)


class TestComposer(unittest.TestCase):

    def test_bezier_matches_monotone_hermite_without_overshoot(self):
        rnd = random.Random(4)
        times = [0.3]
        for _ in range(12):
            times.append(times[-1] + rnd.uniform(0.15, 0.8))
        values = [rnd.uniform(-1.0, 1.0) for _ in times]
        track = JointTrack(times, bezier_keys(times, values), True, 1)
        for i in range(len(times) - 1):
            lo, hi = sorted((values[i], values[i + 1]))
            for k in range(1, 20):
                v = track.value(times[i] + k * (times[i + 1] - times[i]) / 20.0)
                self.assertGreaterEqual(v, lo - 1e-3)        # jamais au-delà des clés
                self.assertLessEqual(v, hi + 1e-3)
        for t, v in zip(times, values):
            self.assertAlmostEqual(track.value(t), round(v, 4), places=3)

    def test_velocity_is_continuous_at_keys(self):
        times = [0.5, 1.0, 1.5, 2.0]
        values = [0.0, 0.4, 0.9, 1.0]                 # geste continu : pas d'arrêt à 1.0 et 1.5
        keys = bezier_keys(times, values)
        for k in keys[1:-1]:
            left_slope = k[1][2] / k[1][1]
            right_slope = k[2][2] / k[2][1]
            self.assertAlmostEqual(left_slope, right_slope, places=3)
            self.assertGreater(abs(right_slope), 0.1)
        self.assertEqual(monotone_slopes([0, 1, 2], [0.0, 1.0, 0.0])[1], 0.0)   # aller-retour : arrêt

    def test_arrive_respects_speed_budget(self):
        comp = Composer(["LShoulderPitch"])
        comp.key(1.0, {"LShoulderPitch": 1.4})
        comp.arrive(4.0, {"LShoulderPitch": -1.0}, NAO_LIMITS, max_ratio=0.5)
        names, times, keys = comp.to_motion()
        track = JointTrack(times[0], keys[0], True, 1)
        self.assertEqual(len(times[0]), 3)            # tenue, départ, arrivée
        self.assertAlmostEqual(track.value(2.5), 1.4)  # la pose précédente est tenue
        prev, peak = track.value(1.0), 0.0
        for k in range(1, 601):
            v = track.value(1.0 + k * 0.005)
            peak = max(peak, abs(v - prev) / 0.005)
            prev = v
        self.assertLessEqual(peak, 0.5 * NAO_LIMITS["LShoulderPitch"][2] + 1e-6)


# =============================================================================
class TestLibrarySafety(unittest.TestCase):
    """Butées, vitesses, collisions, tête, articulations interdites : sur TOUTE la trajectoire."""

    def test_full_validation_passes(self):
        for cid in COMPOSED + ("calibration",):
            c = library_choreo(cid)
            errors, warnings = c.validate(limits_for(c), collision_step=0.01)
            self.assertEqual(errors, [], cid)
            self.assertFalse([w for w in warnings if "marge" in w or "collision" in w], cid)

    def test_peak_speed_below_55_percent(self):
        for cid in COMPOSED:
            ratios = peak_speed_ratio(library_choreo(cid))
            worst = max(ratios, key=ratios.get)
            self.assertLessEqual(ratios[worst], 0.55, "%s %s %.2f" % (cid, worst, ratios[worst]))

    def test_no_forbidden_joint(self):
        for cid in COMPOSED + ("calibration",):
            c = library_choreo(cid)
            self.assertTrue(set(c.names) <= ALLOWED_JOINTS, (cid, set(c.names) - ALLOWED_JOINTS))
            self.assertFalse([n for n in c.names if any(w in n for w in ("Hip", "Knee", "Ankle"))])

    def test_keys_inside_limits_with_margin(self):
        for cid in COMPOSED:
            c = library_choreo(cid)
            for name, keys in zip(c.names, c.keys):
                lo, hi, _ = NAO_LIMITS[name]
                margin = 0.0 if name.endswith("Hand") else 0.03
                for k in keys:
                    self.assertTrue(lo + margin - 1e-6 <= c.angle(k) <= hi - margin + 1e-6, (cid, name, k[0]))

    def test_trajectory_format(self):
        for cid in COMPOSED:
            c = library_choreo(cid)
            self.assertTrue(c.bezier, cid)
            firsts = set(t[0] for t in c.times)
            self.assertEqual(len(firsts), 1, "%s : toutes les articulations partent de la meme pose" % cid)
            self.assertGreater(min(firsts), 0.0)
            self.assertGreaterEqual(c.end, c.last_key_time)
            for times, keys in zip(c.times, c.keys):
                for i, k in enumerate(keys):
                    self.assertEqual((k[1][0], k[2][0]), (3, 3))
                    self.assertLessEqual(k[1][1], 0.0)
                    self.assertGreaterEqual(k[2][1], 0.0)
                    if 0 < i < len(times) - 1:
                        self.assertAlmostEqual(-k[1][1], (times[i] - times[i - 1]) / 3.0, places=3)
                        self.assertAlmostEqual(k[2][1], (times[i + 1] - times[i]) / 3.0, places=3)

    def test_gesture_durations_and_no_long_stillness(self):
        for cid, max_still in (("macarena", 0.8), ("nao_party", 1.5), ("echauffement", 1.5),
                               ("mekassarat", 1.2)):
            c = library_choreo(cid)
            tl = ReferenceTimeline(c)
            arms = [n for n in c.names if n[1:] in ("ShoulderPitch", "ShoulderRoll", "ElbowYaw", "ElbowRoll")]
            # chaque geste (entre deux clés de valeurs différentes) dure au moins 0,15 s
            for name, times, keys in zip(c.names, c.times, c.keys):
                for (t0, k0), (t1, k1) in zip(zip(times, keys), zip(times[1:], keys[1:])):
                    if abs(k1[0] - k0[0]) > 0.05 and not name.endswith("Hand"):
                        self.assertGreaterEqual(t1 - t0, 0.15, (cid, name, t0))
            # pas d'immobilité injustifiée des bras pendant la danse
            still, longest, dt = 0.0, 0.0, 0.02
            prev = tl.pose_at(tl.first_key_time)
            t = tl.first_key_time + dt
            while t < tl.last_key_time - 1.0:          # le final tenu est voulu
                pose = tl.pose_at(t)
                moving = max(abs(pose[n] - prev[n]) / dt for n in arms) > 0.08
                still = 0.0 if moving else still + dt
                longest = max(longest, still)
                prev, t = pose, t + dt
            self.assertLessEqual(longest, max_still, cid)

    def test_generator_and_library_are_in_sync(self):
        """motion.json correspond exactement à tools/compose_choreographies.py."""
        for cid in COMPOSED:
            folder = os.path.join(LIBRARY, cid)
            if cid == "macarena":
                comp = compose.macarena(BeatGrid.load(os.path.join(folder, "beats.json")))
            elif cid == "nao_party":
                comp, _ = compose.nao_party()
            elif cid == "mekassarat":
                comp = compose.mekassarat(BeatGrid.load(os.path.join(folder, "beats.json")))
            else:
                comp, _ = compose.warmup()
            names, times, keys = comp.to_motion()
            c = library_choreo(cid)
            self.assertEqual(names, c.names, cid)
            self.assertEqual(times, c.times, cid)
            self.assertEqual([[k[0] for k in j] for j in keys], [[k[0] for k in j] for j in c.keys], cid)


# =============================================================================
class TestMacarenaRhythm(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.choreo = library_choreo("macarena")
        cls.grid = BeatGrid.load(os.path.join(LIBRARY, "macarena", "beats.json"))
        cls.timeline = ReferenceTimeline(cls.choreo)

    def test_beat_grid(self):
        g = self.grid
        self.assertTrue(102.5 < g.bpm < 103.8, g.bpm)
        self.assertTrue(0.18 < g.beats[0] < 0.28, g.beats[0])     # grosse caisse, pas le contretemps
        self.assertEqual(g.phrase_phase, 1)
        self.assertEqual(g.n_cycles(), 7)
        self.assertLess(g.time(g.cycle_start(7) - 1), 66.0)

    def test_named_moves_follow_the_macarena_and_start_on_beats(self):
        moves = self.choreo.moves
        self.assertEqual(len(moves), 7 * 8)
        self.assertEqual([m["name"] for m in moves[:8]], MACARENA_ORDER)
        for m in moves:
            index, error = self.grid.nearest_beat(m["start"])
            self.assertLess(abs(error), 0.005, m)

    def test_poses_arrive_on_the_beat(self):
        """Sur chaque temps 1 à 12, le bras qui vient de bouger est arrivé (vitesse ~0)."""
        side_of = {1: "R", 2: "L", 3: "R", 4: "L", 5: "R", 6: "L", 7: "R", 8: "L",
                   9: "R", 10: "L", 11: "R", 12: "L"}
        for cycle in range(self.grid.n_cycles()):
            for count, side in side_of.items():
                t = self.grid.count(cycle, count)
                a, b = self.timeline.pose_at(t - 0.01), self.timeline.pose_at(t + 0.01)
                for j in ("ShoulderPitch", "ShoulderRoll", "ElbowRoll"):
                    speed = abs(b[side + j] - a[side + j]) / 0.02
                    self.assertLess(speed, 0.6, (cycle, count, side + j, speed))

    def test_recognisable_macarena_poses(self):
        for cycle in range(self.grid.n_cycles()):
            def at(count):
                p = self.timeline.pose_at(self.grid.count(cycle, count))
                return arm_points(p, "L"), arm_points(p, "R"), p
            L, R, _ = at(1)
            self.assertGreater(R["tip"][0], 200)                     # 1 : bras droit devant
            self.assertLess(R["palm"][2], -0.7)                      #     paume vers le bas
            L, R, _ = at(2)
            self.assertGreater(L["tip"][0], 200)
            L, R, _ = at(4)
            self.assertGreater(R["palm"][2], 0.7)                    # 3-4 : paumes vers le haut
            self.assertGreater(L["palm"][2], 0.7)
            L, R, _ = at(5)
            self.assertGreater(R["tip"][1], 0)                       # 5 : main droite vers l'épaule gauche
            L, R, _ = at(6)
            self.assertLess(L["tip"][1], 0)                          # 6 : main gauche vers l'épaule droite
            self.assertGreater(R["tip"][2] - L["tip"][2], 55)       #     sous le bras droit, qui monte
            L, R, _ = at(7)
            self.assertGreater(R["tip"][2], 250)                     # 7-8 : main à la tête
            L, R, _ = at(8)
            self.assertGreater(L["tip"][2], 250)
            L, R, _ = at(10)
            self.assertLess(max(L["tip"][2], R["tip"][2]), -60)      # 9-10 : mains aux hanches
            self.assertGreater(min(L["tip"][0], R["tip"][0]), 20)
            L, R, _ = at(12)
            self.assertLess(max(L["tip"][0], R["tip"][0]), 0)        # 11-12 : derrière les hanches
            L, R, pose = at(16)
            self.assertLess(pose["RShoulderPitch"], -0.3)            # 16 : "Ay !" poing droit levé
            self.assertGreater(R["tip"][2], 200)
            self.assertGreater(pose["LShoulderRoll"], 1.0)           #      bras gauche ouvert sur le côté

    def test_cycles_vary(self):
        """La danse ne se répète pas à l'identique : la tête et l'amplitude varient."""
        signatures = set()
        for cycle in range(self.grid.n_cycles()):
            sig = tuple(round(self.timeline.pose_at(self.grid.count(cycle, n) + 0.3)[j], 2)
                        for n in (1, 2, 3, 5, 9) for j in ("HeadYaw", "HeadPitch", "RShoulderPitch"))
            signatures.add(sig)
        self.assertGreaterEqual(len(signatures), 3)

    def test_music_and_motion_fit_the_excerpt(self):
        path = os.path.join(LIBRARY, "macarena", "macarena_extrait.wav")
        w = wave.open(path, "rb")
        duration = w.getnframes() / float(w.getframerate())
        w.close()
        self.assertLessEqual(self.choreo.last_key_time, duration)
        self.assertLessEqual(self.choreo.end, duration + 0.1)
        self.assertEqual(self.choreo.audio_robot, "/home/nao/music/macarena_extrait.wav")
        self.assertEqual(self.choreo.sync_offset, 0.0)


class TestAudioAnalysis(unittest.TestCase):

    def test_synthetic_four_on_the_floor(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy absent")
        import analyze_audio
        sr, bpm, first = 22050, 100.0, 0.47
        period = 60.0 / bpm
        n = int(20 * sr)
        x = np.zeros(n, dtype=np.float32)
        t = np.arange(int(0.12 * sr)) / float(sr)
        kick = (np.sin(2 * np.pi * 60 * t) * np.exp(-t * 30)).astype(np.float32)
        hat = (np.random.RandomState(0).randn(int(0.04 * sr)) * np.exp(-np.arange(int(0.04 * sr)) / 200.0)
               ).astype(np.float32) * 0.3
        k = 0
        while first + k * period < 19.5:
            s = int((first + k * period) * sr)
            x[s:s + len(kick)] += kick
            h = int((first + (k + 0.5) * period) * sr)        # charleston sur le contretemps
            x[h:h + len(hat)] += hat
            k += 1
        folder = tempfile.mkdtemp(prefix="jn_beats_")
        try:
            path = os.path.join(folder, "beat.wav")
            wf = wave.open(path, "wb")
            wf.setnchannels(1), wf.setsampwidth(2), wf.setframerate(sr)
            wf.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
            wf.close()
            grid = analyze_audio.analyse(path, 70, 180)
            self.assertAlmostEqual(grid["bpm"], bpm, delta=0.3)
            self.assertAlmostEqual(grid["first_beat"], first, delta=0.02)   # sur la grosse caisse
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class TestCalibrationStaysPrecise(unittest.TestCase):

    def test_arm_hits_on_every_click(self):
        c = library_choreo("calibration")
        w = wave.open(c.audio_path, "rb")
        sr = w.getframerate()
        raw = w.readframes(w.getnframes())
        w.close()
        import struct
        samples = struct.unpack("<%dh" % (len(raw) // 2), raw)
        clicks, last = [], -1.0
        for i, s in enumerate(samples):
            if abs(s) > 8000 and i / float(sr) - last > 0.2:
                last = i / float(sr)
                clicks.append(last)
        tl = ReferenceTimeline(c)
        hits = [t for t, k in zip(c.times[0], c.keys[0]) if abs(c.angle(k) - 0.6) < 1e-6]
        self.assertGreaterEqual(len(clicks), 16)
        self.assertEqual(len(hits), len(clicks))
        for h, k in zip(hits, clicks):
            self.assertLess(abs(h - k), 0.01)
        self.assertEqual(c.names, ["RShoulderPitch"])                   # un seul geste, simple


# =============================================================================
class TestScoringCompatibility(unittest.TestCase):

    def test_wrists_and_hands_are_never_scored(self):
        for joints in FEATURE_JOINTS.values():
            self.assertFalse([j for j in joints if "Wrist" in j or "Hand" in j])
        # Paume vers le bas ou vers le haut : la pose attendue du joueur ne change
        # presque pas (coude quasi tendu), bien moins que la tolérance sans pénalité.
        tl = ReferenceTimeline(library_choreo("macarena"))
        g = BeatGrid.load(os.path.join(LIBRARY, "macarena", "beats.json"))
        down = nao_features(tl.pose_at(g.count(1, 2)))
        up = nao_features(tl.pose_at(g.count(1, 4)))
        free_fore = config.SCORE_TOLERANCES["fore"][0]
        for f in ("L_upper", "R_upper"):
            self.assertLess(angle_deg(down[f], up[f]), 1.0, f)
        for f in ("L_fore", "R_fore"):
            self.assertLess(angle_deg(down[f], up[f]), free_fore / 3.0, f)

    def test_main_gestures_are_distinct_for_the_camera(self):
        tl = ReferenceTimeline(library_choreo("macarena"))
        g = BeatGrid.load(os.path.join(LIBRARY, "macarena", "beats.json"))
        poses = dict((n, nao_features(tl.pose_at(g.count(1, n)))) for n in (2, 6, 8, 10, 16))
        names = sorted(poses)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                diff = max(angle_deg(poses[a][f], poses[b][f]) for f in ("L_upper", "R_upper", "L_fore", "R_fore"))
                self.assertGreater(diff, 25.0, "temps %d et %d trop proches" % (a, b))

    def test_macarena_scores_good_still_and_wrong_players(self):
        c = library_choreo("macarena")
        self.assertEqual(evaluated_features(ReferenceTimeline(c)), {"L_upper", "L_fore", "R_upper", "R_fore"})
        good = play_session(c, mode="miroir", lag=0.35, noise=0.01, fps=8)
        still = play_session(c, static=True, fps=8)
        self.assertTrue(good["valid"])
        self.assertGreaterEqual(good["score"], 85)
        self.assertLess(still["score"], 35)
        self.assertEqual(good["moves"]["total"], 56)
        self.assertEqual(good["moves"]["details"][0]["name"], "Right arm out")
        self.assertGreaterEqual(good["moves"]["reussis"], 50)

    def test_missed_moves_are_named_in_tips(self):
        c = library_choreo("macarena")
        late = play_session(c, mode="miroir", lag=1.3, noise=0.02, fps=8)
        tips = " ".join(late["advice"])
        if late["moves"]["reussis"] < late["moves"]["total"]:
            self.assertIn("Moves to practice", tips)
            self.assertTrue(any(name in tips for name in MACARENA_ORDER), tips)

    def test_other_dances_score(self):
        for cid in ("echauffement", "nao_party", "mekassarat"):
            c = library_choreo(cid)
            good = play_session(c, mode="miroir", lag=0.35, noise=0.01, fps=8)
            still = play_session(c, static=True, fps=8)
            self.assertGreaterEqual(good["score"], 85, cid)
            # L'échauffement "équilibre" a de nouveau des gestes assez amples pour
            # distinguer un joueur immobile (la version très lente ne le pouvait pas).
            self.assertLess(still["score"], 35, cid)
            self.assertTrue(all(d["name"] for d in good["moves"]["details"]), cid)


# =============================================================================
class TestStopDuringMacarena(unittest.TestCase):
    """La vraie Macarena envoyée à la vraie passerelle (faux NAOqi), Stop au milieu."""

    def test_stop_mid_dance(self):
        from tests.fake_naoqi import FakeSession, load_bridge
        from tests.test_bridge import free_port, wait
        from robot.choregraphe_robot import ChoregrapheRobot
        from sync.player import STOPPED, Player
        port = free_port()
        session = FakeSession(audio_duration=66.0)
        box, _ns = load_bridge(os.path.join(ROOT, "choregraphe_bridge.py"), session, port)
        box.onInput_onStart()
        audio = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        audio.close()
        try:
            self.assertTrue(wait(lambda: box.server is not None))
            robot = ChoregrapheRobot(log=lambda m: None, host="127.0.0.1", port=port)
            robot.connect()
            choreo = library_choreo("macarena")
            choreo.audio_robot = audio.name                # fichier présent "sur le robot"
            player = Player(robot, log=lambda m: None)
            stop = threading.Event()
            stopped_at = {}

            def press_stop():
                stopped_at["t"] = time.time()
                stop.set()
            threading.Timer(3.5, press_stop).start()
            result = player.play(choreo, stop)
            returned = time.time()
            self.assertEqual(result, STOPPED)
            self.assertLess(returned - stopped_at["t"], 1.0)
            calls = session.rec.find("angleInterpolationBezier")
            self.assertTrue(calls)
            self.assertEqual(sorted(calls[0][3][0]), sorted(choreo.names))
            self.assertTrue(session.rec.find("killTasksUsingResources"))
            self.assertTrue(wait(lambda: not box._audio_status()["playing"], 2.0))
            payload = json.dumps({"cmd": "play", "names": choreo.names, "times": choreo.times,
                                  "keys": choreo.keys})
            self.assertLess(len(payload), 1024 * 1024)
        finally:
            box.onUnload()
            os.remove(audio.name)


if __name__ == "__main__":
    unittest.main()


class TestReducedSpeed(unittest.TestCase):
    """main.py --speed 0.5 : premiers essais sur le robot, danse ralentie, sans musique."""

    def test_half_speed_copy(self):
        c = library_choreo("macarena")
        slow = c.scaled(0.5)
        self.assertIsNone(slow.audio_path)
        self.assertIsNone(slow.audio_robot)
        self.assertAlmostEqual(slow.end, 2 * c.end)
        self.assertAlmostEqual(slow.moves[3]["start"], 2 * c.moves[3]["start"])
        self.assertIn("50 % speed", slow.title)
        fast = peak_speed_ratio(c)
        half = peak_speed_ratio(slow)
        for name in ("LShoulderPitch", "RElbowYaw"):
            self.assertAlmostEqual(half[name], fast[name] / 2, delta=0.02)
        errors, _ = slow.validate(limits_for(slow), collision_step=0.05)
        self.assertEqual(errors, [])
        tl_fast, tl_slow = ReferenceTimeline(c), ReferenceTimeline(slow)
        for t in (5.0, 12.3, 40.0):
            self.assertAlmostEqual(tl_fast.pose_at(t)["RShoulderPitch"],
                                   tl_slow.pose_at(2 * t)["RShoulderPitch"], places=3)
        self.assertEqual(c.audio_robot, "/home/nao/music/macarena_extrait.wav")   # original intact
        with self.assertRaises(ValueError):
            c.scaled(2.0)


# =============================================================================
class TestBalance(unittest.TestCase):
    """
    Équilibre estimé (ZMP, choreography/kinematics.py). Repère réel : l'échauffement
    v4 a fait TOMBER NAO (tests/fixtures/echauffement_v4_fell). Estimation seulement.
    """

    def summary(self, choreo):
        from choreography.kinematics import balance_summary
        tl = ReferenceTimeline(choreo)
        return balance_summary(tl.pose_at, tl.first_key_time, tl.last_key_time, step=0.02)

    def test_composed_dances_stay_well_below_the_fall(self):
        from choreography.kinematics import BALANCE_LIMITS
        fell = self.summary(fixture_choreo("echauffement_v4_fell"))
        for cid in COMPOSED:
            b = self.summary(library_choreo(cid))
            for key in ("dyn", "back", "fwd", "lat"):
                self.assertLessEqual(b[key], BALANCE_LIMITS[key][0], "%s %s %.1f mm" % (cid, key, b[key]))
            self.assertLess(b["dyn"], 0.5 * fell["dyn"], cid)    # moins de la moitié de la chute

    def test_the_warm_up_that_fell_would_now_be_refused(self):
        c = fixture_choreo("echauffement_v4_fell")
        errors, _ = c.validate(limits_for(c), collision_step=None)
        self.assertTrue([e for e in errors if "equilibre" in e], errors)

    def test_meds_first_test_passes(self):
        c = fixture_choreo("nao_party_v1")              # joué sur le robot sans problème
        errors, warnings = c.validate(limits_for(c), collision_step=None)
        self.assertFalse([m for m in errors + warnings if "equilibre" in m])

    def test_holding_a_pose_is_not_dynamic(self):
        from choreography.kinematics import balance_summary
        pose = dict(DEFAULT_POSE)
        for side, sign in (("L", 1), ("R", -1)):
            pose.update({side + "ShoulderPitch": 0.0, side + "ShoulderRoll": sign * 0.2,
                         side + "ElbowRoll": sign * -0.05})
        b = balance_summary(lambda t: pose, 0.0, 1.0, step=0.02)
        self.assertLess(b["dyn"], 0.1)                    # bras tenus devant : pas d'élan
        self.assertGreater(b["fwd"], 8.0)                 # mais le centre de masse avance
        self.assertLess(b["fwd"], 18.0)


class TestMekassarat(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.choreo = library_choreo("mekassarat")
        cls.grid = BeatGrid.load(os.path.join(LIBRARY, "mekassarat", "beats.json"))
        cls.timeline = ReferenceTimeline(cls.choreo)

    def test_excerpt_and_beat_grid(self):
        path = os.path.join(LIBRARY, "mekassarat", "mekassarat_extrait.wav")
        w = wave.open(path, "rb")
        duration = w.getnframes() / float(w.getframerate())
        w.close()
        self.assertAlmostEqual(duration, 48.45, delta=0.05)
        g = self.grid
        self.assertTrue(109.5 < g.bpm < 110.5, g.bpm)
        self.assertLess(g.beats[0], 0.1)                 # l'extrait commence sur un temps fort
        self.assertEqual((g.bar_phase, g.phrase_phase), (0, 0))
        self.assertEqual(len(g.beats), 89)
        self.assertLessEqual(self.choreo.last_key_time, duration)
        self.assertLessEqual(self.choreo.end, duration + 0.05)
        self.assertEqual(self.choreo.audio_robot, "/home/nao/music/mekassarat_extrait.wav")

    def test_moves_on_beats_and_phrases(self):
        names = [m["name"] for m in self.choreo.moves]
        self.assertEqual(names[0], "Hand twirls")
        self.assertEqual(names[-1], "Big finish")
        self.assertEqual(len(names), 11)
        for m in self.choreo.moves:
            index, error = self.grid.nearest_beat(m["start"])
            self.assertLess(abs(error), 0.005, m)
            self.assertEqual(index % 8, 0, m)            # chaque mouvement commence une demi-phrase

    def test_final_hit(self):
        pose = self.timeline.pose_at(self.grid.time(88))
        self.assertGreater(pose["LShoulderRoll"], 1.0)   # bras ouverts sur le coup final
        self.assertLess(pose["RShoulderRoll"], -1.0)

    def test_wrist_twirls_in_the_intro(self):
        """Montée (temps 0-15) : les poignets tournent, les bras bougent peu (non noté)."""
        values = [self.timeline.pose_at(self.grid.time(n))["LWristYaw"] for n in range(3, 15)]
        self.assertGreater(max(values) - min(values), 2.0)
