# -*- coding: utf-8 -*-
"""
choreography/beatgrid.py - Grille rythmique d'une chorégraphie (temps, mesures, phrases).

    grid = BeatGrid.load("choreography/library/macarena/beats.json")   # musique analysée
    grid = BeatGrid.regular(bpm=112, first_beat=1.0, count=64)          # danse sans musique

    grid.time(17)          # instant (s) du temps n°17
    grid.count(cycle, 1)   # instant du "1" du cycle n° `cycle` (16 temps par cycle)

beats.json est produit par tools/analyze_audio.py. Les temps sont en secondes
depuis le début du fichier audio, comme toutes les keyframes.
Python 2.7 et 3, sans dépendance.
"""
from __future__ import absolute_import, division

import io
import json


class BeatGrid(object):

    def __init__(self, beats, period, bar_phase=0, phrase_phase=0, phrase_length=16,
                 phrases=None, accents=None, source=None):
        self.beats = [float(b) for b in beats]
        self.period = float(period)
        self.bar_phase = int(bar_phase)
        self.phrase_phase = int(phrase_phase)
        self.phrase_length = int(phrase_length)
        self.phrases = phrases or []
        self.accents = set(accents or [])
        self.source = source

    @classmethod
    def load(cls, path):
        with io.open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(data["beats"], data["period"], data.get("bar_phase", 0),
                   data.get("phrase_phase", 0), data.get("phrase_length", 16),
                   data.get("phrases"), data.get("accents"), source=path)

    @classmethod
    def regular(cls, bpm, first_beat, count, bar_phase=0, phrase_phase=0, phrase_length=16):
        period = 60.0 / bpm
        beats = [first_beat + i * period for i in range(count)]
        return cls(beats, period, bar_phase, phrase_phase, phrase_length)

    @property
    def bpm(self):
        return 60.0 / self.period

    def time(self, index):
        """Instant du temps `index` ; extrapolé au tempo constant hors du fichier."""
        i = float(index)
        n = int(i // 1)
        frac = i - n
        if 0 <= n < len(self.beats):
            base = self.beats[n]
        elif n < 0:
            base = self.beats[0] + n * self.period
        else:
            base = self.beats[-1] + (n - len(self.beats) + 1) * self.period
        return base + frac * self.period

    def cycle_start(self, cycle):
        """Indice du premier temps du cycle n° `cycle` (0 = première phrase)."""
        return self.phrase_phase + cycle * self.phrase_length

    def count(self, cycle, count, offset=0.0):
        """Instant du temps `count` (1 = premier) du cycle `cycle`, + offset en temps."""
        return self.time(self.cycle_start(cycle) + count - 1 + offset)

    def n_cycles(self):
        return max(0, (len(self.beats) - self.phrase_phase) // self.phrase_length)

    def phrase_label(self, cycle):
        start = self.cycle_start(cycle)
        for p in self.phrases:
            if p["start_beat"] == start:
                return p.get("label")
        return None

    def nearest_beat(self, t):
        """(indice, écart en s) du temps le plus proche de l'instant t."""
        best = min(range(len(self.beats)), key=lambda i: abs(self.beats[i] - t))
        return best, t - self.beats[best]
