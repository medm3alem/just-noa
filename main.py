# -*- coding: utf-8 -*-
"""
main.py - Point d'entrée de Just Nao.

    python main.py --choregraphe --ui hmi             NAO physique via la passerelle
                                                      Choregraphe (IP/port : config.py
                                                      ou fenêtre Settings)
    python main.py --choregraphe --ip 192.168.2.121 --bridge-port 8766 --ui hmi
    python main.py --fake --ui hmi                    jeu complet sans robot (webcam 0)
    python main.py --fake --ui hmi --joueur-simule    jeu complet sans robot NI caméra
    python main.py --ip 192.168.2.121 --ui hmi        NAOqi direct (SDK Python 2.7)
    python main.py --fake                             interface clavier
    python main.py --fake --valider                   vérifie toutes les chorégraphies

Priorité des réglages : ligne de commande > results/settings.json (fenêtre
Settings) > config.py.

C'est le seul fichier qui choisit le robot (FakeRobot, NaoRobot...), l'interface
et la source vidéo : passer de la simulation au robot ne change rien ailleurs.

Jeu interactif (score, squelette, bilans) : Python 3 + requirements.txt.
En Python 2.7 (SDK NAOqi direct), l'application fonctionne comme avant, sans jeu.
"""
from __future__ import absolute_import, print_function

import argparse
import sys

import config
from choreography.loader import load_library
from compat import PY2
from robot.base import RobotError


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Just Nao: NAO dances, you copy it")
    p.add_argument("--choregraphe", action="store_true",
                   help="NAO (physical or virtual) through the Choregraphe bridge (--ip, --bridge-port)")
    p.add_argument("--bridge-port", type=int, default=config.BRIDGE_PORT,
                   help="Choregraphe bridge port (default: settings / config.py = %(default)s)")
    p.add_argument("--fake", action="store_true",
                   help="simulated robot: no hardware or SDK needed")
    p.add_argument("--ip", default=config.NAO_IP,
                   help="robot IP address (default: settings / config.py = %(default)s)")
    p.add_argument("--port", type=int, default=config.NAO_PORT, help="NAOqi port (direct SDK mode)")
    p.add_argument("--ui", choices=["clavier", "hmi"], default="clavier",
                   help="interface: clavier (console) or hmi (game window)")
    p.add_argument("--video", default=None,
                   help="video source: webcam number, URL, or 'none'")
    p.add_argument("--joueur-simule", action="store_true",
                   help="HMI: simulated player instead of the camera (demo and tests)")
    p.add_argument("--valider", action="store_true",
                   help="check every choreography (joint limits, speeds) then quit")
    p.add_argument("--speed", type=float, default=1.0,
                   help="play every dance slower for first robot trials, e.g. 0.5 (no music)")
    return p.parse_args(argv)


def make_robot(args):
    # Imports locaux : en mode --fake, le SDK NAOqi n'est jamais importé.
    if args.choregraphe:
        from robot.choregraphe_robot import ChoregrapheRobot
        return ChoregrapheRobot(host=args.ip, port=args.bridge_port, volume=config.AUDIO_VOLUME)
    if args.fake:
        from robot.fake_robot import FakeRobot
        return FakeRobot()
    from robot.nao_robot import NaoRobot
    return NaoRobot(args.ip, args.port)


def video_source(arg):
    if arg is None:
        return config.VIDEO_SOURCE
    if arg.lower() in ("aucune", "none", "off", ""):
        return None
    return int(arg) if arg.isdigit() else arg


def validate_all(robot, library):
    all_ok = True
    print("\n%-14s %-34s %8s  %s" % ("dossier", "titre", "duree", "verdict"))
    for c in library.values():
        errors, warnings = c.validate(robot.joint_limits(c.names),
                                      config.SPEED_WARN_RATIO, config.LIMIT_TOLERANCE)
        print("%-14s %-34s %7.1fs  %s" % (c.id, c.title[:34], c.end,
                                          "REFUSEE" if errors else "OK"))
        for e in errors:
            print("    [ERREUR] " + e)
        for w in warnings:
            print("    [ATTENTION] " + w)
        all_ok = all_ok and not errors
    return 0 if all_ok else 1


def build_game(args):
    """
    Python 3 + HMI : chaîne vision, fabrique de sessions de jeu, stockage des
    bilans. Renvoie (fabrique, stockage, chaîne) ; (None, None, None) si le jeu
    n'est pas disponible : l'application fonctionne alors comme avant.
    """
    if PY2 or args.ui != "hmi":
        return None, None, None
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
        from app.game_session import GameSession
        from reports.session_store import SessionStore
        from vision.camera import CameraSource
        from vision.pipeline import VisionPipeline
    except ImportError as err:
        print("[ATTENTION] Jeu indisponible (%s) : pip install -r requirements.txt" % err)
        return None, None, None
    store = SessionStore(config.RESULTS_DIR)

    def factory(choreo, origin_fn, on_voice):
        return GameSession(choreo, config, origin_fn, on_voice)

    if args.joueur_simule:
        from vision.synthetic import SyntheticPlayer
        pipeline = VisionPipeline(config, synthetic_factory=lambda session: SyntheticPlayer(
            session.model, mode="miroir", lag=0.35, noise=0.012))
    else:
        source = video_source(args.video)
        camera = CameraSource(source, config.CAMERA_SIZE) if source is not None else None
        pipeline = VisionPipeline(config, camera=camera)
    return factory, store, pipeline


def make_personality():
    """NAO coach sarcastique : texte du commentaire de fin (lu dans config à chaque partie)."""
    import os
    from evaluation.nao_personality import NaoPersonality
    return NaoPersonality(config, history_path=os.path.join(config.RESULTS_DIR, "roast_history.json"))


def main():
    if not PY2:
        from app import settings
        settings.load(config)          # réglages enregistrés depuis la HMI (avant les options)
    args = parse_args()
    if args.fake and args.choregraphe:
        print("[ERREUR] Choisir soit --fake, soit --choregraphe")
        return 2
    config.NAO_IP, config.BRIDGE_PORT = args.ip, args.bridge_port
    robot = make_robot(args)
    try:
        robot.connect()
    except RobotError as err:
        print("[ERROR] %s" % err)
        if args.choregraphe:
            print("  -> Is the Just Nao bridge box running in Choregraphe, connected to NAO %s?\n"
                  "     Expected log line: 'Just Nao bridge v3 pret : 0.0.0.0:%d' "
                  "(docs/CHOREGRAPHE.md, Troubleshooting)." % (args.ip, args.bridge_port))
        return 1

    library = load_library(config.LIBRARY_DIR)
    if args.speed != 1.0:
        if not 0.1 <= args.speed <= 1.0:
            print("[ERROR] --speed must be between 0.1 and 1.0")
            robot.close()
            return 2
        # Essais progressifs sur le robot : danses ralenties, sans musique
        library = type(library)((cid, c.scaled(args.speed)) for cid, c in library.items())
        print("[ATTENTION] Danses a %d %% de leur vitesse, sans musique (essais)" % round(100 * args.speed))
    if args.valider:
        code = validate_all(robot, library)
        robot.close()
        return code
    if not library:
        print("[ERREUR] Aucune choregraphie valide dans %s" % config.LIBRARY_DIR)
        robot.close()
        return 1

    from app.controller import Controller
    factory, store, pipeline = build_game(args)
    ctrl = Controller(robot, library, factory, store, personality=make_personality())
    if pipeline is not None:
        pipeline.log = ctrl.log
        ctrl.on_session = pipeline.set_session
    try:
        if args.ui == "hmi" and PY2:
            from ui.hmi_classic import HMI as ClassicHMI
            ClassicHMI(ctrl, video_source(args.video)).run()
        elif args.ui == "hmi":
            from ui.hmi import HMI
            HMI(ctrl, pipeline, store, config).run()
        else:
            from ui import keyboard_ui
            keyboard_ui.run(ctrl)
    except KeyboardInterrupt:
        print("\nInterruption (Ctrl+C)")
    finally:
        # Quoi qu'il arrive : caméra libérée, danse arrêtée, NAO au repos, connexion fermée.
        if pipeline is not None:
            pipeline.stop()
        ctrl.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
