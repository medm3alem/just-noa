# -*- coding: utf-8 -*-
"""
tools/make_calibration.py - Génère la chorégraphie "calibration" (mesure de la synchro).

Elle contient :
- click.wav : un métronome (clic aigu sur le 1er temps de chaque mesure) ;
- motion.json : le bras droit "frappe" vers le bas exactement sur chaque clic ;
- meta.json : les yeux flashent aussi sur chaque clic.

On filme le robot (au ralenti si possible) et on compare l'instant où le bras
est au plus bas avec le clic : l'écart mesuré se reporte dans "sync_offset"
des autres chorégraphies (procédure dans le README).

    python tools/make_calibration.py            # 90 BPM, 16 temps
    python tools/make_calibration.py --bpm 120

Uniquement la bibliothèque standard (wave, struct, math) : Python 2.7 et 3.
"""
from __future__ import print_function, division

import argparse
import math
import os
import struct
import sys
import wave
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, os.pardir))
sys.path.insert(0, ROOT)   # pour importer les modules du projet depuis tools/
from choreography.choreography import save_meta, save_motion  # noqa: E402

OUT_DIR = os.path.join(ROOT, "choreography", "library", "calibration")

RATE = 22050        # échantillons par seconde (suffisant pour un clic)
LEAD = 2.0          # s de silence avant le premier clic
ARM_DOWN = 0.6      # RShoulderPitch : bras vers le bas-avant (instant du "clic")
ARM_UP = 0.2        # RShoulderPitch : bras levé à mi-temps. 0.2 (au lieu de -0.2 avant
                    # 2026-11-02) : geste deux fois plus petit, pour l'équilibre de NAO ;
                    # le point bas reste exactement sur chaque clic.
ARM_REST = 1.2      # fin : bras redescendu le long du corps


def write_click_track(path, bpm, beats):
    beat = 60.0 / bpm
    total = LEAD + beats * beat + 1.0
    samples = [0.0] * int(total * RATE)
    for b in range(beats):
        start = int((LEAD + b * beat) * RATE)
        freq = 1600.0 if b % 4 == 0 else 1000.0       # temps fort plus aigu
        for i in range(int(0.03 * RATE)):            # clic de 30 ms qui décroît
            t = i / RATE
            samples[start + i] = 0.8 * math.sin(2 * math.pi * freq * t) * math.exp(-t * 120)
    w = wave.open(path, "wb")
    try:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(s * 32767)) for s in samples))
    finally:
        w.close()
    return total


def build_motion(bpm, beats):
    beat = 60.0 / bpm
    times, keys = [], []
    t = LEAD - beat / 2                     # pose de départ : bras levé
    times.append(round(t, 4))
    keys.append(ARM_UP)
    for b in range(beats):
        hit = LEAD + b * beat
        times.append(round(hit, 4))
        keys.append(ARM_DOWN)               # point bas = instant du clic
        if b < beats - 1:
            times.append(round(hit + beat / 2, 4))
            keys.append(ARM_UP)
    times.append(round(LEAD + beats * beat + 0.5, 4))
    keys.append(ARM_REST)
    return {"names": ["RShoulderPitch"], "times": [times], "keys": [keys]}


def build_meta(bpm, beats, end):
    # OrderedDict : en Python 2 un dict n'a pas d'ordre, le fichier serait illisible.
    beat = 60.0 / bpm
    events = []
    for b in range(beats):
        events.append(OrderedDict([("t", round(LEAD + b * beat, 4)), ("type", "leds"),
                                   ("color", "#FF0000" if b % 4 == 0 else "#0000FF"),
                                   ("duration", 0.05)]))
    return OrderedDict([
        ("title", "Sync calibration (%d BPM)" % bpm),
        ("description", "NAO's right arm hits on every click: film it to measure the audio/motion offset."),
        ("audio", "click.wav"),
        ("audio_robot", "/home/nao/music/click.wav"),
        ("audio_start", 0.0),
        ("sync_offset", 0.0),
        ("countdown", False),
        ("end", round(end, 2)),
        ("events", events),
    ])


def main():
    parser = argparse.ArgumentParser(description="Genere la choregraphie de calibration")
    parser.add_argument("--bpm", type=int, default=90)
    parser.add_argument("--beats", type=int, default=16)
    args = parser.parse_args()

    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    end = write_click_track(os.path.join(OUT_DIR, "click.wav"), args.bpm, args.beats)
    motion = build_motion(args.bpm, args.beats)
    save_motion(os.path.join(OUT_DIR, "motion.json"), motion["names"], motion["times"], motion["keys"])
    save_meta(os.path.join(OUT_DIR, "meta.json"), build_meta(args.bpm, args.beats, end))
    print("Calibration ecrite dans %s (%d BPM, %d temps, %.1f s)"
          % (os.path.normpath(OUT_DIR), args.bpm, args.beats, end))


if __name__ == "__main__":
    main()
