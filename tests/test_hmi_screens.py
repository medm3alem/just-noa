# -*- coding: utf-8 -*-
"""
Écrans de la HMI sans jouer de danse complète (rapide) : résultats avec le
commentaire de NAO, Replay, historique et exports, fenêtre Settings, panne de
caméra, liaison robot perdue, et tous les textes affichés en anglais.
Nécessite Tkinter et un affichage (xvfb-run sous Linux) ; ignoré sinon.
"""
import csv
import io
import json
import os
import re
import shutil
import tempfile
import unittest

from tests.helpers import config, library_choreo

try:
    import tkinter
    from tkinter import ttk
    tkinter.Tk().destroy()
    HAS_DISPLAY = True
except Exception:
    HAS_DISPLAY = False

FRENCH = re.compile(u"[éèàùâêîôûçœ]|\\b(Danse|Danser|Arrêter|Rejouer|Réveiller|Repos|Historique|"
                    u"Paramètres|Joueur|Caméra|Vérifications|Commencer|Retour|Enregistrer|Annuler|"
                    u"Conseils|Exporter|Prêt|Erreur|partie|joueur|bras|coude)\\b")


def tmp_cfg(results_dir):
    """Copie des réglages de config.py, avec un dossier de résultats temporaire."""
    cfg = type("Cfg", (), {})()
    for key in dir(config):
        if key.isupper():
            setattr(cfg, key, getattr(config, key))
    cfg.RESULTS_DIR = results_dir
    return cfg


def sample_report(score=63):
    return {
        "title": "Warm-up (arms)", "choreography": "echauffement", "date": "2026-11-02T10:15:00",
        "status": "terminee", "valid": True, "score": score, "category": "Good",
        "tracking_ratio": 0.93, "correct_pose_ratio": 0.6, "timing_offset_s": 0.48,
        "evaluated_duration_s": 30.0, "frames_analysed": 400, "activity": 0.9,
        "mapping_mode": "miroir", "parts": {"bras_gauche": 66, "bras_droit": 60},
        "moves": {"reussis": 6, "total": 9, "details": []},
        "timeline": [{"t": 0.5 * i, "score": 60 + i % 10, "status": "ok"} for i in range(60)],
        "advice": ["Right arm: 60/100. Raise your right arm more clearly."],
        "nao_comment": {"lines": ["63 points!", "Respectable. Not legendary, but respectable!"],
                        "announce": "63 points!", "roast": "Respectable. Not legendary, but respectable!",
                        "fact": None, "category": "average", "intensity": "sarcastic",
                        "diagnostics": []},
    }


def all_texts(widget):
    """Tous les textes visibles d'un arbre de widgets Tk (labels, boutons, en-têtes)."""
    texts = []
    for child in widget.winfo_children():
        try:
            text = child.cget("text")
            if text:
                texts.append(str(text))
        except tkinter.TclError:
            pass
        if isinstance(child, ttk.Treeview):
            for col in child["columns"]:
                texts.append(str(child.heading(col)["text"]))
        texts.extend(all_texts(child))
    return texts


class AddressRobot(object):
    """Décorateur d'un FakeRobot qui accepte une nouvelle adresse (comme ChoregrapheRobot)."""
    address = None

    def set_address(self, host, port):
        AddressRobot.address = (host, port)


@unittest.skipUnless(HAS_DISPLAY, "Tkinter ou affichage indisponible")
class TestScreens(unittest.TestCase):

    def setUp(self):
        from app.controller import Controller
        from reports.session_store import SessionStore
        from robot.fake_robot import FakeRobot
        from ui.hmi import HMI
        from vision.pipeline import VisionPipeline
        from vision.synthetic import SyntheticPlayer

        class Robot(AddressRobot, FakeRobot):
            pass

        self.results = tempfile.mkdtemp(prefix="jn_screens_")
        self.cfg = tmp_cfg(self.results)
        self.store = SessionStore(self.results)
        self.store.save(sample_report())
        library = {"echauffement": library_choreo("echauffement")}
        self.ctrl = Controller(Robot(log=lambda m: None), library, store=self.store)
        self.pipeline = VisionPipeline(self.cfg, synthetic_factory=lambda s: SyntheticPlayer(s.model),
                                       log=lambda m: None)
        self.hmi = HMI(self.ctrl, self.pipeline, self.store, self.cfg)
        self.hmi.root.update()

    def tearDown(self):
        import gc
        gc.collect()                      # variables et images Tk libérées dans le thread Tk
        try:
            self.hmi.close()
        except tkinter.TclError:
            pass
        gc.collect()
        self.ctrl.shutdown()
        shutil.rmtree(self.results, ignore_errors=True)

    def pump(self, n=5):
        for _ in range(n):
            self.hmi.root.update()

    def test_results_screen_shows_nao_comment_and_replay(self):
        self.hmi.show_results(sample_report())
        self.pump()
        screen = self.hmi.screens["results"]
        text = screen.nao_text.cget("text")
        self.assertIn(u"63 points!", text)
        self.assertIn(u"Respectable. Not legendary, but respectable!", text)
        self.assertEqual(screen.nao_title.cget("text"), u"NAO says")
        self.assertIn("disabled", screen.skip_btn.state())          # NAO ne parle pas
        self.assertEqual(screen.category.cget("text"), u"Good")
        screen._replay()
        self.pump()
        self.assertEqual(self.hmi._screen, "prepare")
        self.assertEqual(self.ctrl.status()["selected"], "echauffement")

    def test_results_without_comment(self):
        rep = sample_report()
        rep.pop("nao_comment")
        self.hmi.show_results(rep, from_history=True)
        self.pump()
        self.assertIn(u"no comment", self.hmi.screens["results"].nao_text.cget("text"))

    def test_history_and_exports(self):
        self.hmi.show_history()
        self.pump()
        screen = self.hmi.screens["history"]
        items = screen.tree.get_children()
        self.assertEqual(len(items), 1)
        values = screen.tree.item(items[0])["values"]
        self.assertEqual(str(values[2]), u"63")
        self.assertIn(u"Respectable", values[6])
        screen._export_selected()                                   # rien de choisi
        self.assertIn(u"Select a dance", screen.empty.cget("text"))
        screen.tree.selection_set(items[0])
        screen._export_selected()
        exports = os.listdir(os.path.join(self.results, "exports"))
        self.assertTrue(any(n.endswith(".csv") for n in exports))
        self.assertTrue(any(n.endswith(".json") for n in exports))
        screen._export_all()
        history = [n for n in os.listdir(os.path.join(self.results, "exports")) if n.startswith("history_")]
        self.assertEqual(len(history), 1)
        with io.open(os.path.join(self.results, "exports", history[0]), encoding="utf-8") as f:
            rows = list(csv.reader(f, delimiter=";"))
        self.assertEqual(rows[0][0], "date")
        self.assertIn(u"Respectable", rows[1][-1])
        screen._open()
        self.pump()
        self.assertEqual(self.hmi._screen, "results")
        self.assertEqual(self.hmi.screens["results"].nao_title.cget("text"), u"NAO said")

    def test_settings_dialog_saves_voice_personality_robot_and_camera(self):
        from ui.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self.hmi)
        self.pump()
        dialog.speaks.set(False)
        dialog.sarcasm.set(True)
        dialog.intensity.set("savage")
        dialog.length.set("long")
        dialog.source.set("1")
        dialog.ip.set("192.168.2.130")
        dialog.port.set("8770")
        dialog._save()
        self.pump()
        self.assertFalse(self.cfg.NAO_SPEAKS)
        self.assertEqual(self.cfg.ROAST_INTENSITY, "savage")
        self.assertEqual(self.cfg.COMMENTARY_LENGTH, "long")
        self.assertEqual(self.cfg.VIDEO_SOURCE, 1)
        self.assertEqual((self.cfg.NAO_IP, self.cfg.BRIDGE_PORT), ("192.168.2.130", 8770))
        self.assertEqual(AddressRobot.address, ("192.168.2.130", 8770))   # appliqué à chaud
        with io.open(os.path.join(self.results, "settings.json"), encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["ROAST_INTENSITY"], "savage")
        self.assertEqual(saved["NAO_IP"], "192.168.2.130")
        # Relecture au démarrage suivant (app/settings.py)
        from app import settings
        fresh = tmp_cfg(self.results)
        settings.load(fresh)
        self.assertEqual((fresh.ROAST_INTENSITY, fresh.BRIDGE_PORT, fresh.NAO_SPEAKS), ("savage", 8770, False))

    def test_settings_dialog_rejects_bad_robot_address(self):
        from ui.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self.hmi)
        self.pump()
        dialog.ip.set("192.168.2.999")
        dialog._save()
        self.assertIn(u"Robot", dialog.error.cget("text"))
        dialog.destroy()

    def test_every_screen_is_in_english(self):
        from ui.settings_dialog import SettingsDialog
        self.hmi.show_results(sample_report())
        self.hmi.prepare("echauffement")
        self.pump()
        self.hmi.show_history()
        self.pump()
        dialog = SettingsDialog(self.hmi)
        self.pump()
        texts = all_texts(self.hmi.root)
        self.assertGreater(len(texts), 60)
        french = [t for t in texts if FRENCH.search(t)]
        self.assertEqual(french, [])
        dialog.destroy()

    def test_robot_connection_lost_is_shown(self):
        self.ctrl.robot.connected = False
        original = self.ctrl.robot.status
        self.ctrl.robot.status = lambda: dict(original(), connected=False)
        self.ctrl._robot_status = dict(self.ctrl._robot_status, connected=False) \
            if hasattr(self.ctrl, "_robot_status") else None
        self.hmi.prepare("echauffement")
        self.pump()
        st = self.ctrl.status()
        st["robot"] = dict(st["robot"], connected=False)
        self.hmi._update_status_bar(st)
        self.hmi.screens["prepare"].refresh(st)
        self.assertIn(u"connection lost", self.hmi.status_labels["robot"].cget("text"))
        detail = self.hmi.screens["prepare"].checks["robot"][1].cget("text")
        self.assertIn(u"No connection to NAO", detail)
        self.assertIn("disabled", self.hmi.screens["prepare"].go.state())


@unittest.skipUnless(HAS_DISPLAY, "Tkinter ou affichage indisponible")
class TestCameraFailure(unittest.TestCase):

    def test_missing_camera_means_demo_mode(self):
        from app.controller import Controller
        from robot.fake_robot import FakeRobot
        from ui.hmi import HMI
        from vision.camera import CameraSource
        from vision.pipeline import VisionPipeline

        results = tempfile.mkdtemp(prefix="jn_cam_")
        cfg = tmp_cfg(results)
        camera = CameraSource(os.path.join(results, "no_such_camera.mp4"), (320, 240), log=lambda m: None)
        pipeline = VisionPipeline(cfg, camera=camera, log=lambda m: None)
        ctrl = Controller(FakeRobot(log=lambda m: None), {"echauffement": library_choreo("echauffement")})
        hmi = HMI(ctrl, pipeline, None, cfg)
        try:
            hmi.prepare("echauffement")
            deadline = 0
            while deadline < 60 and pipeline.status()["camera_msg"] in (u"Camera stopped",
                                                                       u"Opening the camera..."):
                hmi.root.after(100)
                hmi.root.update()
                deadline += 1
            for _ in range(5):
                hmi.root.after(120)
                hmi.root.update()
            st = pipeline.status()
            self.assertFalse(st["camera_ok"])
            self.assertIn(u"unavailable", st["camera_msg"])
            prepare = hmi.screens["prepare"]
            self.assertEqual(prepare.go.cget("text"), u"Dance without score")
            self.assertIn(u"demo mode", prepare.hint.cget("text"))
            self.assertIn(u"unavailable", hmi.status_labels["camera"].cget("text"))
            self.assertFalse(hmi.scoring_possible())
        finally:
            hmi.close()
            ctrl.shutdown()
            shutil.rmtree(results, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
