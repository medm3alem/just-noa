# -*- coding: utf-8 -*-
"""
HMI de jeu de bout en bout (nécessite Tkinter et un affichage ; ignoré sinon) :
menu -> préparation -> compte à rebours -> jeu -> résultats -> historique.
Robot simulé + joueur simulé : aucune caméra ni robot nécessaires.

Pour enregistrer des captures d'écran : JN_SCREENSHOTS=dossier (sous Linux,
avec ImageMagick "import" et un serveur X, par ex. xvfb-run).
"""
import gc
import os
import shutil
import subprocess
import tempfile
import time
import unittest

from tests.helpers import config, library_choreo

try:
    import tkinter
    tkinter.Tk().destroy()
    HAS_DISPLAY = True
except Exception:
    HAS_DISPLAY = False


@unittest.skipUnless(HAS_DISPLAY, "Tkinter ou affichage indisponible")
class TestHMIFlow(unittest.TestCase):

    def test_full_flow(self):
        import random
        from app.controller import Controller
        from app.game_session import GameSession
        from evaluation.nao_personality import NaoPersonality
        from reports.session_store import SessionStore
        from robot.fake_robot import FakeRobot
        from ui.hmi import HMI
        from vision.pipeline import VisionPipeline
        from vision.synthetic import SyntheticPlayer

        results = tempfile.mkdtemp(prefix="jn_hmi_")
        shots = os.environ.get("JN_SCREENSHOTS")
        store = SessionStore(results)
        library = {"echauffement": library_choreo("echauffement")}
        ctrl = Controller(FakeRobot(log=lambda m: None), library,
                          lambda c, o, v: GameSession(c, config, o, v), store,
                          personality=NaoPersonality(config, rng=random.Random(3)))
        pipeline = VisionPipeline(config, synthetic_factory=lambda s: SyntheticPlayer(
            s.model, lag=0.35, noise=0.012), log=lambda m: None)
        ctrl.on_session = pipeline.set_session
        hmi = HMI(ctrl, pipeline, store, config)
        seen = []

        def shot(name):
            hmi.root.update()
            seen.append((name, hmi._screen, ctrl.status()["state"]))
            if shots:
                subprocess.call(["import", "-window", "root", os.path.join(shots, name + ".png")])

        def wait_report():
            if ctrl.status()["report_seq"] >= 1 and hmi._screen == "results":
                hmi.root.after(500, lambda: shot("4_resultats"))
                hmi.root.after(550, lambda: seen.append(("nao_text", hmi.screens["results"].nao_text.cget("text"),
                                                         ctrl.status()["speaking"])))
                hmi.root.after(1000, lambda: hmi.show_history())
                hmi.root.after(1600, lambda: shot("5_historique"))
                hmi.root.after(1800, lambda: hmi.open_settings())
                hmi.root.after(2400, lambda: shot("6_parametres"))
                hmi.root.after(2600, lambda: [w.destroy() for w in hmi.root.winfo_children()
                                              if isinstance(w, tkinter.Toplevel)])
                hmi.root.after(2700, gc.collect)    # variables Tk libérées dans le bon thread
                hmi.root.after(2800, hmi.close)
            else:
                hmi.root.after(300, wait_report)

        hmi.root.after(1200, lambda: shot("1_menu"))
        hmi.root.after(1400, lambda: hmi.prepare("echauffement"))
        hmi.root.after(2600, lambda: shot("2_preparation"))
        hmi.root.after(2800, lambda: hmi.screens["prepare"].start_countdown())
        hmi.root.after(14000, lambda: shot("3_jeu"))
        hmi.root.after(15000, wait_report)
        hmi.root.after(90000, hmi.close)              # garde-fou
        started = time.time()
        hmi.run()
        ctrl.shutdown()
        shutil.rmtree(results, ignore_errors=True)

        names = [s[0] for s in seen]
        self.assertEqual(names[:3], ["1_menu", "2_preparation", "3_jeu"])
        self.assertEqual(seen[2][1], "game")
        self.assertIn("4_resultats", names, "l'écran de résultats ne s'est pas affiché")
        self.assertLess(time.time() - started, 85)
        report = ctrl.last_report()
        self.assertEqual(report["status"], "terminee")
        self.assertTrue(report["valid"])
        self.assertGreater(report["score"], 75)
        # Le commentaire de NAO est affiché sur l'écran de résultats.
        nao_text = [s for s in seen if s[0] == "nao_text"][0][1]
        self.assertIn(report["nao_comment"]["roast"], nao_text)
        self.assertIn(report["nao_comment"]["announce"], nao_text)


if __name__ == "__main__":
    unittest.main()
