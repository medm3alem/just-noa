# -*- coding: utf-8 -*-
"""
app/settings.py - Réglages modifiables depuis la HMI (fenêtre Settings).

Ils surchargent les valeurs de config.py et sont enregistrés dans
results/settings.json, relu au démarrage (avant la lecture de la ligne de
commande : un --ip explicite reste prioritaire). Seule une liste fermée de
réglages est concernée : un fichier abîmé ou une valeur invalide est
simplement ignoré.
"""
from __future__ import absolute_import, division, print_function

import io
import json
import os
import re

try:
    TEXT = (str, unicode)    # noqa: F821  (Python 2)
except NameError:
    TEXT = (str,)


def check_ip(value):
    """Adresse IPv4 ou nom d'hôte simple ; None si invalide."""
    value = (value or u"").strip()
    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", value):
        return str(value) if all(0 <= int(p) <= 255 for p in value.split(".")) else None
    if re.match(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$", value):
        return str(value)
    return None


def check_port(value):
    try:
        port = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return port if 1 <= port <= 65535 else None


def _video(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, TEXT) and v.strip():
        return int(v) if v.strip().isdigit() else v.strip()
    return None


EDITABLE = {
    "MAPPING_MODE": lambda v: v if v in ("auto", "miroir", "meme_cote") else None,
    "CAMERA_MIRROR": lambda v: bool(v),
    "EVAL_DEPTH": lambda v: bool(v),
    "VOICE_FEEDBACK": lambda v: bool(v),
    "ROBOT_LATENCY": lambda v: float(v) if 0.0 <= float(v) <= 1.0 else None,
    "CAMERA_LATENCY": lambda v: float(v) if 0.0 <= float(v) <= 1.0 else None,
    "VIDEO_SOURCE": _video,
    # Voix et personnalité de NAO
    "NAO_SPEAKS": lambda v: bool(v),
    "ROAST_ENABLED": lambda v: bool(v),
    "ROAST_INTENSITY": lambda v: v if v in ("friendly", "sarcastic", "savage") else None,
    "COMMENTARY_LENGTH": lambda v: v if v in ("short", "long") else None,
    # Connexion au robot
    "NAO_IP": check_ip,
    "BRIDGE_PORT": check_port,
}


def settings_path(cfg):
    return os.path.join(cfg.RESULTS_DIR, "settings.json")


def load(cfg, log=print):
    path = settings_path(cfg)
    if not os.path.isfile(path):
        return
    try:
        with io.open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (ValueError, OSError, IOError) as err:
        log("[ATTENTION] Parametres ignores (%s) : %s" % (path, err))
        return
    if not isinstance(data, dict):
        return
    for key, check in EDITABLE.items():
        if key in data and data[key] is not None:
            try:
                value = check(data[key])
            except (TypeError, ValueError):
                value = None
            if value is not None:
                setattr(cfg, key, value)


def save(cfg):
    path = settings_path(cfg)
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    data = dict((key, getattr(cfg, key, None)) for key in EDITABLE)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2))
    return path
