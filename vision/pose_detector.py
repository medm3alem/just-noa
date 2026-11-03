# -*- coding: utf-8 -*-
"""
vision/pose_detector.py - Détection du squelette du joueur avec MediaPipe.

API utilisée : MediaPipe Tasks, "Pose Landmarker". L'ancienne API
`mediapipe.solutions.pose` n'existe plus depuis MediaPipe 0.10.30 : ne pas
installer une vieille version pour la retrouver.

Le Pose Landmarker a besoin d'un fichier modèle (.task) téléchargé une fois :
    python tools/download_model.py            (modèle "full", ~9 Mo)
Il est rangé dans models/ (chemin : config.POSE_MODEL_PATH).

Mode VIDEO : le modèle suit le joueur d'une image à l'autre (plus stable et
plus rapide qu'une détection indépendante par image). Il exige des
horodatages en millisecondes strictement croissants.

Pour brancher un autre détecteur (module du groupe 2...), il suffit d'un objet
ayant la même méthode detect(image_bgr, t) -> PoseSample ou None, et close().
"""
from __future__ import absolute_import, division, print_function

import os

from vision.pose_features import LANDMARK_INDEX, PoseSample

MODEL_URLS = {
    "lite": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
            "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
    "full": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
            "pose_landmarker_full/float16/latest/pose_landmarker_full.task",
    "heavy": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
             "pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task",
}


def detector_status(model_path):
    """(disponible, message) : explique précisément ce qui manque."""
    try:
        import mediapipe  # noqa: F401
        from mediapipe.tasks.python import vision  # noqa: F401
    except ImportError as err:
        return False, u"MediaPipe missing (pip install -r requirements.txt): %s" % err
    try:
        import cv2  # noqa: F401
    except ImportError:
        return False, u"OpenCV missing (pip install -r requirements.txt)"
    if not os.path.isfile(model_path):
        return False, (u"Pose model missing: %s\nRun: python tools/download_model.py"
                       % model_path)
    return True, u"MediaPipe ready"


class MediaPipePoseDetector(object):
    """Détecteur MediaPipe Pose Landmarker (mode vidéo, une personne)."""

    def __init__(self, model_path, min_detection=0.5, min_presence=0.5, min_tracking=0.5):
        import mediapipe as mp
        from mediapipe.tasks import python as mp_tasks
        from mediapipe.tasks.python import vision as mp_vision
        self._mp = mp
        options = mp_vision.PoseLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=model_path),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=min_detection,
            min_pose_presence_confidence=min_presence,
            min_tracking_confidence=min_tracking,
            output_segmentation_masks=False)
        self._landmarker = mp_vision.PoseLandmarker.create_from_options(options)
        self._last_ms = -1

    def detect(self, image_bgr, t):
        """Image BGR (OpenCV) capturée à l'instant t -> PoseSample ou None."""
        import cv2
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        ms = int(t * 1000)
        if ms <= self._last_ms:                 # horodatage strictement croissant exigé
            ms = self._last_ms + 1
        self._last_ms = ms
        result = self._landmarker.detect_for_video(image, ms)
        if not result.pose_landmarks:
            return None
        lms = result.pose_landmarks[0]
        world_lms = result.pose_world_landmarks[0] if result.pose_world_landmarks else None
        image_pts, world_pts = {}, {} if world_lms else None
        for name, i in LANDMARK_INDEX.items():
            p = lms[i]
            vis = getattr(p, "visibility", None)
            presence = getattr(p, "presence", None)
            # On combine visibilité (point non masqué) et présence (point dans l'image).
            conf = min(v for v in (vis, presence, 1.0) if v is not None)
            image_pts[name] = (p.x, p.y, conf)
            if world_lms:
                w = world_lms[i]
                world_pts[name] = (w.x, w.y, w.z)
        h, w = image_bgr.shape[:2]
        return PoseSample(t, image_pts, world_pts, w / float(h))

    def close(self):
        try:
            self._landmarker.close()
        except Exception:
            pass
