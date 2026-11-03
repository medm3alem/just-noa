# -*- coding: utf-8 -*-
"""
vision/camera.py - Capture vidéo dans un thread, image la plus récente seulement.

- Chaque image est HORODATÉE à la capture (compat.now()) : c'est l'heure du
  geste du joueur, pas celle où l'analyse se termine.
- Seule la dernière image est gardée (tampon de taille 1) : si l'analyse prend
  du retard, on saute des images au lieu d'accumuler un retard croissant.
- La caméra est rouverte automatiquement si elle se déconnecte ; l'état est
  lisible à tout moment (status()) pour l'afficher dans la HMI.
- Sous Windows, une webcam (source numérique) est ouverte avec DirectShow,
  beaucoup plus rapide à démarrer que le pilote par défaut ; repli automatique.
"""
from __future__ import absolute_import, division, print_function

import sys
import threading
import time

from compat import now


class CameraSource(object):

    def __init__(self, source=0, size=(640, 480), log=print):
        self.source = source
        self.size = size
        self.log = log
        self._lock = threading.Lock()
        self._frame, self._t, self._seq = None, None, 0
        self._running = False
        self._thread = None
        self._status = u"Camera stopped"
        self._ok = False

    # --- Pilotage ----------------------------------------------------------------------------
    def start(self):
        if self._running:
            return
        self._running = True
        self._status = u"Opening the camera..."
        self._thread = threading.Thread(target=self._loop, name="camera")
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(3.0)
            self._thread = None

    def latest(self):
        """(image BGR, instant de capture, numéro) de la dernière image, ou (None, None, 0)."""
        with self._lock:
            return self._frame, self._t, self._seq

    def status(self):
        return self._ok, self._status

    # --- Thread de capture -----------------------------------------------------------------
    def _open(self):
        import cv2
        if isinstance(self.source, int) and sys.platform == "win32":
            cap = cv2.VideoCapture(self.source, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(self.source)
        else:
            cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            cap.release()
            return None
        if isinstance(self.source, int):
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.size[0])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.size[1])
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _loop(self):
        try:
            import cv2  # noqa: F401
        except ImportError:
            self._status = u"OpenCV missing: pip install -r requirements.txt"
            self._running = False
            return
        cap, failures = None, 0
        while self._running:
            if cap is None:
                cap = self._open()
                if cap is None:
                    self._ok = False
                    self._status = (u"Camera %s unavailable (plugged in? used by another app? "
                                    u"allowed in Windows privacy settings?)" % (self.source,))
                    time.sleep(1.5)
                    continue
                self._status, failures = u"Camera on", 0
            ok, frame = cap.read()
            t = now()
            if not ok or frame is None:
                failures += 1
                if failures > 10:              # flux perdu : on rouvre
                    cap.release()
                    cap = None
                    self._ok = False
                    self._status = u"Video lost, reconnecting..."
                time.sleep(0.05)
                continue
            failures = 0
            with self._lock:
                self._frame, self._t, self._seq = frame, t, self._seq + 1
            self._ok = True
            if not isinstance(self.source, int):
                time.sleep(0.001)              # fichier vidéo : ne pas boucler à vide
        if cap is not None:
            cap.release()
        self._ok = False
        self._status = u"Camera stopped"
