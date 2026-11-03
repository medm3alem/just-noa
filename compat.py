# -*- coding: utf-8 -*-
"""
compat.py - Les petites différences entre Python 2.7 et Python 3, regroupées ici.

Le projet doit tourner en Python 2.7 (imposé par le SDK NAOqi). Le mode
--fake tourne aussi en Python 3 : pratique pour développer la HMI sur
n'importe quel PC. Plutôt que de semer des "if PY2" partout, on les met ici.
"""
from __future__ import absolute_import, print_function

import sys
import time

PY2 = sys.version_info[0] == 2

if PY2:
    input_text = raw_input  # noqa: F821  (raw_input n'existe qu'en Python 2)
else:
    input_text = input


# ---------------------------------------------------------------------------
# Horloge précise
# ---------------------------------------------------------------------------
# La synchronisation compte en millisecondes. Or en Python 2.7 sous Windows,
# time.time() n'avance que par pas de ~15 ms. time.clock() y est une horloge
# haute résolution (QueryPerformanceCounter). Sous Linux/macOS, time.clock()
# mesure le temps CPU (faux ici) : on garde time.time(). En Python 3,
# time.perf_counter() est la bonne réponse partout.
if hasattr(time, "perf_counter"):
    now = time.perf_counter
elif sys.platform == "win32":
    now = time.clock
else:
    now = time.time


# Sous Windows, time.sleep(0.001) peut durer jusqu'à ~15 ms : on termine
# l'attente "activement" (boucle) sur une fenêtre plus large.
_SPIN = 0.02 if sys.platform == "win32" else 0.002


def sleep_until(target, halt=None):
    """
    Attend jusqu'à l'instant `target` (mesuré avec now()).
    Retourne True à l'heure dite, False si l'évènement `halt` a été levé avant.

    Pourquoi pas halt.wait(timeout) ? En Python 2.7, Event.wait(timeout) dort par
    paliers croissants jusqu'à 50 ms : on raterait le départ de la musique de
    plusieurs dizaines de millisecondes. Ici on dort par petits pas, puis on
    attend activement les dernières millisecondes. Mesuré : < 1 ms d'erreur.
    """
    while True:
        if halt is not None and halt.is_set():
            return False
        remaining = target - now()
        if remaining <= 0:
            return True
        if remaining > _SPIN:
            time.sleep(min(remaining - _SPIN, 0.01))


# ---------------------------------------------------------------------------
# Chaînes de caractères
# ---------------------------------------------------------------------------
def to_native(obj):
    """
    En Python 2, json.load() renvoie des chaînes `unicode` (u"HeadYaw").
    NAOqi attend des `str` classiques : on convertit récursivement en UTF-8.
    En Python 3, les chaînes sont déjà natives : on ne touche à rien.
    """
    if not PY2:
        return obj
    if isinstance(obj, unicode):  # noqa: F821
        return obj.encode("utf-8")
    if isinstance(obj, list):
        return [to_native(x) for x in obj]
    if isinstance(obj, dict):
        return dict((to_native(k), to_native(v)) for k, v in obj.items())
    return obj


def to_text(value):
    """Inverse, pour l'affichage Tkinter : renvoie toujours du texte unicode."""
    if value is None:
        return u""
    if isinstance(value, bytes):   # en Python 2, bytes est le type str
        return value.decode("utf-8", "replace")
    return value
