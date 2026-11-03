# -*- coding: utf-8 -*-
"""
tools/download_model.py - Télécharge le modèle MediaPipe Pose Landmarker (une fois).

    python tools/download_model.py            # modèle "full" (recommandé)
    python tools/download_model.py --variante lite     # plus rapide, moins précis
    python tools/download_model.py --variante heavy    # plus précis, plus lent

Le fichier est rangé dans models/ ; "full" correspond à config.POSE_MODEL_PATH.
Pour une autre variante, modifier POSE_MODEL_PATH dans config.py.
Sans Internet : télécharger l'URL affichée sur un autre PC et copier le fichier.
"""
from __future__ import print_function

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, os.pardir)))
import config  # noqa: E402
from vision.pose_detector import MODEL_URLS  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Telecharge le modele de pose MediaPipe")
    parser.add_argument("--variante", choices=sorted(MODEL_URLS), default="full")
    args = parser.parse_args()
    url = MODEL_URLS[args.variante]
    folder = os.path.dirname(config.POSE_MODEL_PATH)
    target = (config.POSE_MODEL_PATH if args.variante == "full"
              else os.path.join(folder, "pose_landmarker_%s.task" % args.variante))
    if not os.path.isdir(folder):
        os.makedirs(folder)
    print("Telechargement de %s\n  -> %s" % (url, target))
    from urllib.request import urlopen
    tmp = target + ".part"
    try:
        with urlopen(url, timeout=60) as response, open(tmp, "wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = response.read(1 << 16)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if total:
                    sys.stdout.write("\r  %3d %%" % (100 * done // total))
                    sys.stdout.flush()
    except Exception as err:
        if os.path.exists(tmp):
            os.remove(tmp)
        sys.exit("\n[ERREUR] Telechargement impossible : %s\n"
                 "Telecharger l'URL ci-dessus avec un navigateur et copier le fichier en :\n  %s"
                 % (err, target))
    if os.path.getsize(tmp) < 1000000:
        os.remove(tmp)
        sys.exit("\n[ERREUR] Fichier trop petit : telechargement incomplet ou bloque.")
    os.replace(tmp, target)
    print("\n[OK] Modele pret (%.1f Mo)." % (os.path.getsize(target) / 1e6))
    if args.variante != "full":
        print("Pensez a mettre POSE_MODEL_PATH = %r dans config.py" % target)


if __name__ == "__main__":
    main()
