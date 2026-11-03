# -*- coding: utf-8 -*-
"""
vision/pipeline.py - La chaîne vision complète, dans son propre thread.

    caméra (thread) --> image + instant de capture
         |
    VisionPipeline (thread) :
         détection MediaPipe -> lissage -> caractéristiques -> session de jeu
         -> squelette dessiné -> image d'affichage prête (RGB, bonne taille)
         |
    HMI (thread Tkinter) : lit la dernière image d'affichage toutes les 40 ms

Le thread Tkinter ne fait jamais de capture, de détection ni de calcul de
score : il ne fait qu'afficher. Si l'analyse est plus lente que la caméra,
les images intermédiaires sont sautées (on traite toujours la plus récente).

Sans caméra ou sans MediaPipe, la chaîne reste utilisable : vidéo seule
("mode démonstration sans score"), ou joueur simulé (--joueur-simule).
"""
from __future__ import absolute_import, division, print_function

import threading
import time

from compat import now
from vision.overlay import draw_overlay
from vision.pose_detector import MediaPipePoseDetector, detector_status
from vision.pose_features import extract_features
from vision.pose_filter import PoseFilter

ARMS = {"L_upper", "R_upper"}


def classify_detection(sample, features, required):
    """'absent' | 'partiel' | 'bord' | 'ok' (alimente le feedback et les indicateurs)."""
    if sample is None or features is None:
        return "absent"
    needed = required or ARMS
    # "partiel" seulement si moins de la moitié de ce qui est noté est visible :
    # un poignet caché un instant derrière la tête (Macarena) n'est pas une alerte.
    if len(needed & features.valid) * 2 < len(needed):
        return "partiel"
    if features.border:
        return "bord"
    return "ok"


class VisionPipeline(object):

    def __init__(self, cfg, camera=None, synthetic_factory=None, log=print):
        """
        camera            : CameraSource, ou None
        synthetic_factory : fonction(session) -> SyntheticPlayer (mode joueur simulé)
        """
        self.cfg = cfg
        self.camera = camera
        self.synthetic_factory = synthetic_factory
        self.log = log
        self.mirror = getattr(cfg, "CAMERA_MIRROR", True)
        self.display_size = getattr(cfg, "VIDEO_SIZE", (480, 360))
        self.max_fps = getattr(cfg, "VISION_MAX_FPS", 20)
        self.vis_min = getattr(cfg, "LANDMARK_VISIBILITY_MIN", 0.5)
        self.use_depth = getattr(cfg, "EVAL_DEPTH", True)
        self.filter = PoseFilter(getattr(cfg, "FILTER_MIN_CUTOFF", 1.2),
                                 getattr(cfg, "FILTER_BETA", 0.4))
        self._lock = threading.Lock()
        self._sink = None
        self._synthetic = None
        self._display, self._display_seq = None, 0
        self._detection = "absent"
        self._fps = 0.0
        self._detector = None
        self._detector_ok, self._detector_msg = False, u"Pose detection not started"
        self._running = False
        self._thread = None

    # --- Pilotage ------------------------------------------------------------------------
    def start(self):
        if self._running:
            return
        self._running = True
        if self.camera is not None:
            self.camera.start()
        self._thread = threading.Thread(target=self._loop, name="vision")
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(3.0)
            self._thread = None
        if self.camera is not None:
            self.camera.stop()
        if self._detector is not None:
            self._detector.close()
            self._detector = None

    def retry_camera(self):
        if self.camera is not None:
            self.camera.stop()
            self.camera.start()

    def set_session(self, session):
        """Branche (ou débranche avec None) la session de jeu qui reçoit les poses."""
        with self._lock:
            self._sink = session
            self.filter.reset()
            self._synthetic = (self.synthetic_factory(session)
                               if session is not None and self.synthetic_factory else None)

    # --- Lecture par la HMI ---------------------------------------------------------------------
    def latest_display(self):
        """(image RVB prête à afficher, numéro) ; None tant qu'aucune image."""
        with self._lock:
            return self._display, self._display_seq

    def status(self):
        cam_ok, cam_msg = (self.camera.status() if self.camera is not None
                           else (self.synthetic_factory is not None, u"Simulated player (no camera)"
                                 if self.synthetic_factory else u"No camera configured"))
        return {
            "camera_ok": cam_ok, "camera_msg": cam_msg,
            "detector_ok": self._detector_ok or self.synthetic_factory is not None,
            "detector_msg": u"Simulated player" if self.synthetic_factory else self._detector_msg,
            "detection": self._detection,
            "fps": round(self._fps, 1),
            "simulated": self.synthetic_factory is not None,
        }

    # --- Thread vision -------------------------------------------------------------------------
    def _init_detector(self):
        path = getattr(self.cfg, "POSE_MODEL_PATH", "")
        ok, msg = detector_status(path)
        if ok:
            try:
                self._detector = MediaPipePoseDetector(path)
                msg = u"MediaPipe running"
            except Exception as err:            # modèle abîmé, DLL manquante...
                ok, msg = False, u"MediaPipe failed to start: %s" % err
        self._detector_ok, self._detector_msg = ok, msg
        self.log("[VISION] %s" % msg.split("\n")[0])

    def _loop(self):
        if self.synthetic_factory is None:
            self._init_detector()
        last_seq, period = 0, 1.0 / max(1, self.max_fps)
        while self._running:
            started = now()
            try:
                if self.synthetic_factory is not None:
                    self._step_synthetic()
                else:
                    last_seq = self._step_camera(last_seq)
            except Exception as err:                # une image fautive ne tue pas le thread
                self.log("[VISION] Erreur : %s" % err)
                time.sleep(0.2)
            elapsed = now() - started
            if elapsed > 0:
                self._fps += 0.1 * (min(self.max_fps, 1.0 / max(elapsed, period)) - self._fps)
            time.sleep(max(0.002, period - elapsed))

    def _step_camera(self, last_seq):
        frame, t, seq = self.camera.latest() if self.camera is not None else (None, None, 0)
        if frame is None or seq == last_seq:
            return last_seq
        with self._lock:
            sink = self._sink
        sample = self._detector.detect(frame, t) if self._detector is not None else None
        self._process(frame, t, sample, sink, self._detector is not None)
        return seq

    def _step_synthetic(self):
        import numpy as np
        with self._lock:
            sink, player = self._sink, self._synthetic
        t = now()
        sample = None
        if player is not None and sink.origin_fn() is not None:
            tau = t - sink.origin_fn() - sink.latency
            sample = player.sample(t, max(0.0, tau))
        else:
            from vision.synthetic import idle_sample
            sample = idle_sample(t)              # joueur simulé immobile avant la danse
        h, w = 480, 640
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:] = (48, 40, 34)
        self._process(frame, t, sample, sink, True)

    def _process(self, frame, t, sample, sink, can_detect):
        import cv2
        sample = self.filter(sample) if sample is not None else None
        if sample is None:
            self.filter.reset()
        features = extract_features(sample, self.vis_min, self.use_depth) if sample else None
        required = sink.required_features() if sink is not None else None
        detection = classify_detection(sample, features, required) if can_detect else "indisponible"
        parts = None
        if sink is not None and can_detect:
            sink.add_sample(t, features, detection)
            parts = sink.live_parts()
        image = draw_overlay(frame, sample, parts, self.mirror, self.vis_min,
                             detected=(detection == "ok") if can_detect else None)
        image = cv2.resize(image, tuple(self.display_size), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        with self._lock:
            self._display, self._display_seq = rgb, self._display_seq + 1
            self._detection = detection
