# -*- coding: utf-8 -*-
"""
ui/video_panel.py - Panneau Tkinter qui affiche un flux vidéo dans la HMI.

Source (config.VIDEO_SOURCE ou --video) :
- un numéro (0, 1...) : webcam du PC, pour tester tout de suite ;
- une URL (ex. http://localhost:8080/stream.mjpg) : le flux annoté produit
  par l'algorithme du groupe 2. C'est le "contrat" à fixer avec eux.

Deux règles Tkinter guident ce code :
1. Tkinter n'est pas thread-safe : seul le thread principal touche aux widgets.
   Un thread de capture lit les images et les dépose dans `_frame` ; le thread
   principal vient les chercher toutes les 40 ms avec `after()`.
2. Il faut garder une référence Python vers l'image affichée
   (self.label.image = photo), sinon elle est libérée et Tk affiche du vide.

Dépendances facultatives : opencv-python et Pillow. Sans elles, le panneau
affiche un message et tout le reste de la HMI fonctionne.
"""
from __future__ import absolute_import, division, print_function

import threading
import time

try:
    import Tkinter as tk
except ImportError:
    import tkinter as tk

try:
    import cv2
except ImportError:
    cv2 = None
try:
    from PIL import Image, ImageTk
except ImportError:
    Image = ImageTk = None


class VideoPanel(tk.Frame):

    def __init__(self, master, source, size=(480, 360), fps=25):
        tk.Frame.__init__(self, master, width=size[0], height=size[1], bg="#1e1e1e")
        self.pack_propagate(False)          # taille fixe, quelle que soit l'image
        self.size = size
        self.period_ms = int(1000 / fps)
        self.source = source
        self.label = tk.Label(self, bg="#1e1e1e", fg="#d0d0d0", font=("Helvetica", 11),
                              wraplength=size[0] - 40, justify="center")
        self.label.pack(fill="both", expand=True)
        self.label.image = None
        self._frame = None
        self._lock = threading.Lock()
        self._running = False
        self._status = u"Connecting to the video stream..."

        if source is None:
            self._show_text(u"Video off\n(config.VIDEO_SOURCE = None)")
        elif cv2 is None or Image is None:
            self._show_text(u"Video unavailable: install opencv-python and Pillow\n"
                            u"(the rest of the interface works normally)")
        else:
            self.start()

    def start(self):
        self._running = True
        t = threading.Thread(target=self._capture_loop)
        t.daemon = True
        t.start()
        self.after(self.period_ms, self._refresh)

    def stop(self):
        self._running = False

    # --- Thread de capture (aucun appel Tkinter ici) ----------------------------
    def _capture_loop(self):
        cap = None
        while self._running:
            if cap is None:
                cap = cv2.VideoCapture(self.source)
                if not cap.isOpened():
                    cap = None
                    self._status = u"Video source unreachable: %s\nretrying..." % (self.source,)
                    time.sleep(1.0)
                    continue
            ok, frame = cap.read()
            if not ok:                      # flux coupé : on se reconnecte
                cap.release()
                cap = None
                time.sleep(0.5)
                continue
            with self._lock:
                self._frame = frame
        if cap is not None:
            cap.release()

    # --- Thread principal Tkinter -------------------------------------------------
    def _refresh(self):
        if not self._running:
            return
        with self._lock:
            frame, self._frame = self._frame, None
        if frame is not None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)   # OpenCV donne du BGR
            image = Image.fromarray(rgb)
            image.thumbnail(self.size)                      # garde les proportions
            photo = ImageTk.PhotoImage(image)
            self.label.configure(image=photo, text="")
            self.label.image = photo                        # règle n°2 ci-dessus
        elif self.label.image is None:
            self.label.configure(text=self._status)
        self.after(self.period_ms, self._refresh)

    def _show_text(self, text):
        self.label.image = None
        self.label.configure(image="", text=text)
