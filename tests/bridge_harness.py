# -*- coding: utf-8 -*-
"""
Lance la VRAIE passerelle (choregraphe_bridge.py) avec de faux services NAOqi,
dans un processus séparé : sert à vérifier la compatibilité Python 2.7.

    python2.7 tests/bridge_harness.py <port>
Affiche "READY" puis tourne jusqu'à la fermeture de l'entrée standard.
"""
from __future__ import print_function

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fake_naoqi import FakeSession, load_bridge  # noqa: E402


def main():
    port = int(sys.argv[1])
    session = FakeSession(audio_duration=2.0)
    box, _ns = load_bridge(os.path.join(HERE, os.pardir, "choregraphe_bridge.py"), session, port)
    box.onInput_onStart()
    import time
    for _ in range(100):
        if box.server is not None:
            break
        time.sleep(0.05)
    print("READY %s" % sys.version.split()[0])
    sys.stdout.flush()
    sys.stdin.read()
    box.onUnload()


if __name__ == "__main__":
    main()
