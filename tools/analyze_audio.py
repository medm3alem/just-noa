# -*- coding: utf-8 -*-
"""
tools/analyze_audio.py - Grille rythmique d'une musique : tempo, temps, mesures,
phrases, sections, accents. Résultat dans beats.json, utilisé pour composer et
vérifier les chorégraphies (choreography/beatgrid.py).

    python tools/analyze_audio.py choreography/library/macarena/macarena_extrait.wav
    python tools/analyze_audio.py musique.wav --bpm-min 90 --bpm-max 130 --out beats.json

Méthode (numpy seulement, pas de librosa) :
1. Spectrogramme (fenêtres de 46 ms, pas de 2,9 ms), énergie par bande.
2. Tempo : autocorrélation de l'enveloppe d'attaques, pic entre --bpm-min et --bpm-max.
3. Position des temps : sur la grosse caisse (bande 35-120 Hz). Dans la musique
   de danse "four on the floor", elle frappe chaque temps, alors que la
   charleston ouverte joue sur les contretemps : un détecteur généraliste peut
   se caler sur le contretemps (c'est ce que fait librosa sur la Macarena, 0,29 s
   trop tôt). Option --beat-band full pour une musique sans grosse caisse.
4. Affinage : moindres carrés sur les attaques de grosse caisse trouvées près
   de chaque temps prévu (tempo constant supposé, résidus affichés).
5. Mesures : changements d'harmonie (chroma) mesurés de temps en temps ; le
   1er temps de la mesure est celui où l'harmonie change le plus souvent.
   La force de la grosse caisse sur chaque temps de la mesure est aussi prise
   en compte. --bar-phase impose le résultat (vérifié à l'oreille).
6. Phrases de 16 temps : débuts de phrase = 1ers temps de mesure où le niveau
   change le plus de palier (4 temps avant / 4 temps après), où les voix
   montent et où l'harmonie change. --phrase-phase impose le résultat.
7. Sections : chaque phrase reçoit une étiquette A, B, C... ; deux phrases ont
   la même étiquette si leur harmonie moyenne (chroma) se ressemble. C'est une
   estimation grossière, utilisée seulement pour varier la danse.
8. Accents : temps dont l'attaque est parmi les 15 % les plus fortes.

Le résultat est une ESTIMATION à vérifier à l'oreille (tools/analyze_audio.py
--click produit un fichier avec un clic sur chaque temps, plus aigu au 1er temps
de la mesure).
"""
from __future__ import absolute_import, division, print_function

import argparse
import json
import os
import sys
import wave

import numpy as np

HOP = 64
N_FFT = 1024
SECTION_SIMILARITY = 0.4      # cosinus mini entre deux phrases de même étiquette


def read_wav(path):
    w = wave.open(path, "rb")
    try:
        sr, n, ch, width = w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    finally:
        w.close()
    if width != 2:
        raise ValueError("WAV 16 bits attendu (sampwidth=%d)" % width)
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


def spectrogram(x, sr):
    win = np.hanning(N_FFT).astype(np.float32)
    n_frames = 1 + (len(x) - N_FFT) // HOP
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n_frames)[:, None]
    frames = x[idx] * win
    spec = np.abs(np.fft.rfft(frames, axis=1)).astype(np.float32)        # frames x bins
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / sr)
    times = (np.arange(n_frames) * HOP + N_FFT / 2.0) / sr                # centre des fenêtres
    return spec, freqs, times


def band_flux(spec, freqs, lo, hi, gain=50.0):
    e = np.log1p(gain * spec[:, (freqs >= lo) & (freqs < hi)].sum(axis=1))
    return np.maximum(0.0, np.diff(e, prepend=e[0]))


def estimate_period(flux, frame_dt, bpm_min, bpm_max):
    f = flux - flux.mean()
    n = len(f)
    spec = np.fft.rfft(f, 2 * n)
    ac = np.fft.irfft(spec * np.conj(spec))[:n]
    lags = np.arange(n) * frame_dt
    lo, hi = 60.0 / bpm_max, 60.0 / bpm_min
    cand = np.where((lags >= lo) & (lags <= hi))[0]
    k = cand[np.argmax(ac[cand])]
    # Interpolation parabolique autour du pic
    a, b, c = ac[k - 1], ac[k], ac[k + 1]
    shift = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
    return (k + shift) * frame_dt


def comb_score(flux, times, period, phase, n_beats, half_window=0.012):
    total = 0.0
    for n in range(n_beats):
        c = phase + n * period
        i0, i1 = np.searchsorted(times, [c - half_window, c + half_window])
        if i1 > i0:
            total += flux[i0:i1].max()
    return total


def fit_grid(flux, times, period, phase, n_beats, search=0.06):
    """Moindres carrés sur les attaques trouvées près de chaque temps prévu."""
    for _ in range(3):
        ns, ts, ws = [], [], []
        for n in range(n_beats):
            c = phase + n * period
            i0, i1 = np.searchsorted(times, [c - search, c + search])
            if i1 - i0 < 3:
                continue
            i = i0 + int(np.argmax(flux[i0:i1]))
            ns.append(n), ts.append(times[i]), ws.append(flux[i])
        ns, ts, ws = map(np.asarray, (ns, ts, ws))
        keep = ws >= np.percentile(ws, 25)            # attaques franches seulement
        A = np.vstack([ns[keep], np.ones(keep.sum())]).T
        (period, phase), _, _, _ = np.linalg.lstsq(A, ts[keep], rcond=None)
        resid = ts[keep] - (period * ns[keep] + phase)
        search = max(0.03, 3 * resid.std())
    return period, phase, resid


def chroma_per_beat(spec, freqs, frame_times, beats):
    sel = (freqs >= 55) & (freqs <= 2000)
    pitch = np.round(12 * np.log2(freqs[sel] / 440.0)).astype(int) % 12
    logspec = np.log1p(10 * spec[:, sel])
    chroma = np.zeros((len(frame_times), 12), dtype=np.float32)
    for pc in range(12):
        chroma[:, pc] = logspec[:, pitch == pc].sum(axis=1)
    edges = np.searchsorted(frame_times, np.append(beats, beats[-1] + np.median(np.diff(beats))))
    out = np.array([chroma[a:b].mean(axis=0) if b > a else np.zeros(12) for a, b in zip(edges[:-1], edges[1:])])
    return out / (np.linalg.norm(out, axis=1, keepdims=True) + 1e-9)


def per_beat_mean(values, frame_times, beats, period):
    out = []
    for b in beats:
        i0, i1 = np.searchsorted(frame_times, [b, b + period])
        out.append(values[i0:i1].mean() if i1 > i0 else 0.0)
    return np.array(out)


def analyse(path, bpm_min=70.0, bpm_max=180.0, beat_band="low", forced_bar=None, forced_phrase=None):
    x, sr = read_wav(path)
    duration = len(x) / float(sr)
    spec, freqs, times = spectrogram(x, sr)
    dt = HOP / float(sr)
    full = band_flux(spec, freqs, 30, 8000)
    low = band_flux(spec, freqs, 35, 120)
    high = band_flux(spec, freqs, 6000, 11000)
    beat_flux = low if beat_band == "low" else full

    period = estimate_period(full, dt, bpm_min, bpm_max)
    n_beats = int(duration / period) + 1
    phases = np.arange(0.0, period, 0.002)
    scores = np.array([comb_score(beat_flux, times, period, p, n_beats) for p in phases])
    phase = phases[int(np.argmax(scores))]
    period, phase, resid = fit_grid(beat_flux, times, period, phase, n_beats)
    while phase - period > 0:
        phase -= period
    if phase < 0:
        phase += period
    beats = phase + period * np.arange(int((duration - phase) / period) + 1)
    beats = beats[beats < duration - 0.05]
    on = comb_score(beat_flux, times, period, phase, len(beats))
    off = comb_score(beat_flux, times, period, phase + period / 2, len(beats))
    hats_on = comb_score(high, times, period, phase, len(beats))
    hats_off = comb_score(high, times, period, phase + period / 2, len(beats))

    # Mesures : changement d'harmonie entre deux temps consécutifs
    chroma = chroma_per_beat(spec, freqs, times, beats)
    change = np.r_[0.0, 1.0 - np.sum(chroma[1:] * chroma[:-1], axis=1)]
    fold4 = np.array([change[i::4].mean() for i in range(4)])
    # + force de la grosse caisse : dans beaucoup de musiques (pop orientale,
    # maqsoum...) elle marque le 1er temps plus nettement que l'harmonie
    kick_beat = np.array([low[np.searchsorted(times, b - 0.03):np.searchsorted(times, b + 0.05)].max()
                          for b in beats])
    kick4 = np.array([kick_beat[i::4].mean() for i in range(4)])

    def z(v):
        return (v - v.mean()) / (v.std() + 1e-9)
    bar_score = z(fold4) + z(kick4)
    bar_phase = int(np.argmax(bar_score)) if forced_bar is None else int(forced_bar) % 4

    # Phrases de 16 temps : là où l'énergie (et les voix) changent de palier
    mid = spec[:, (freqs >= 300) & (freqs < 3500)].sum(axis=1)
    mid_beat = per_beat_mean(np.log1p(mid), times, beats, period)
    level = per_beat_mean(np.log1p(spec.sum(axis=1)), times, beats, period)
    rise = np.r_[0.0, np.maximum(0.0, np.diff(mid_beat))]

    def jump(i):
        before, after = level[max(0, i - 4):i], level[i:i + 4]
        return abs(after.mean() - before.mean()) if len(before) and len(after) else 0.0
    cands = [bar_phase + 4 * k for k in range(4)]
    phrase_scores = []
    for c in cands:
        starts = list(range(c, len(beats), 16))
        phrase_scores.append(np.mean([jump(i) for i in starts]) / (level.std() + 1e-9)
                             + rise[c::16].mean() / (rise.std() + 1e-9) * 0.5
                             + change[c::16].mean() / (change.std() + 1e-9) * 0.5)
    phrase_phase = cands[int(np.argmax(phrase_scores))] % 16
    if forced_phrase is not None:
        phrase_phase = int(forced_phrase) % 16

    # Sections : ressemblance harmonique des phrases (chroma moyen, centré)
    phrase_starts = list(range(phrase_phase, len(beats), 16))
    phrases = [(s, min(s + 16, len(beats))) for s in phrase_starts if min(s + 16, len(beats)) - s >= 8]
    z = (chroma - chroma.mean(axis=0)) / (chroma.std(axis=0) + 1e-9)
    pvec = np.array([z[s:e].mean(axis=0) for s, e in phrases])
    pvec = pvec - pvec.mean(axis=0)
    pvec = pvec / (np.linalg.norm(pvec, axis=1, keepdims=True) + 1e-9)
    sim = pvec @ pvec.T
    labels, protos = [], []
    for i in range(len(phrases)):
        sims = [float(sim[i, j]) for j in protos]
        if sims and max(sims) >= SECTION_SIMILARITY:
            labels.append(labels[protos[int(np.argmax(sims))]])
        else:
            protos.append(i)
            labels.append(chr(ord("A") + len(protos) - 1))
    rms = np.sqrt(np.convolve(x * x, np.ones(HOP) / HOP, mode="same")[::HOP])
    rms_t = np.arange(len(rms)) * HOP / float(sr)
    energy = []
    for s, e in phrases:
        i0, i1 = np.searchsorted(rms_t, [beats[s], beats[e - 1] + period])
        energy.append(round(float(20 * np.log10(rms[i0:i1].mean() + 1e-9)), 1))
    sections = []
    for (s, e), lab in zip(phrases, labels):
        if sections and sections[-1]["label"] == lab and sections[-1]["end_beat"] == s:
            sections[-1]["end_beat"] = e
        else:
            sections.append({"label": lab, "start_beat": s, "end_beat": e})

    strength = np.array([full[np.searchsorted(times, b - 0.03):np.searchsorted(times, b + 0.05)].max()
                         for b in beats])
    accents = [int(i) for i in np.where(strength >= np.percentile(strength, 85))[0]]

    return {
        "file": os.path.basename(path),
        "duration": round(duration, 3),
        "bpm": round(60.0 / period, 3),
        "period": round(float(period), 5),
        "first_beat": round(float(phase), 4),
        "beats": [round(float(b), 4) for b in beats],
        "bar_phase": bar_phase,
        "downbeats": [int(i) for i in range(bar_phase, len(beats), 4)],
        "phrase_length": 16,
        "phrase_phase": phrase_phase,
        "phrases": [{"start_beat": s, "end_beat": e, "label": lab, "energy_db": en}
                    for (s, e), lab, en in zip(phrases, labels, energy)],
        "sections": sections,
        "accents": accents,
        "quality": {
            "beat_band": beat_band,
            "kick_on_vs_offbeat": round(float(on / max(off, 1e-9)), 2),
            "hats_on_vs_offbeat": round(float(hats_on / max(hats_off, 1e-9)), 2),
            "fit_residual_ms": round(float(1000 * resid.std()), 1),
            "downbeat_contrast": [round(float(v), 3) for v in fold4],
            "downbeat_kick": [round(float(v), 1) for v in kick4],
            "phrase_scores": [round(float(v), 2) for v in phrase_scores],
            "forced": {"bar_phase": forced_bar, "phrase_phase": forced_phrase},
        },
        "method": "tools/analyze_audio.py (numpy): kick-drum beat grid, constant tempo",
    }


def click_track(path, grid, out):
    """WAV de contrôle : la musique + un clic sur chaque temps (aigu au 1er temps)."""
    x, sr = read_wav(path)
    y = 0.6 * x
    down = set(grid["downbeats"])
    for i, b in enumerate(grid["beats"]):
        f = 1800.0 if i in down else 1000.0
        n = int(0.03 * sr)
        t = np.arange(n) / float(sr)
        s = int(b * sr)
        if s + n < len(y):
            y[s:s + n] += 0.5 * np.sin(2 * np.pi * f * t) * np.exp(-t * 120)
    y = np.clip(y, -1, 1)
    w = wave.open(out, "wb")
    w.setnchannels(1), w.setsampwidth(2), w.setframerate(sr)
    w.writeframes((y * 32767).astype("<i2").tobytes())
    w.close()


def main(argv=None):
    p = argparse.ArgumentParser(description="Tempo, temps, mesures et sections d'un WAV")
    p.add_argument("wav")
    p.add_argument("--out", help="fichier JSON (defaut : beats.json a cote du WAV)")
    p.add_argument("--bpm-min", type=float, default=70.0)
    p.add_argument("--bpm-max", type=float, default=180.0)
    p.add_argument("--beat-band", choices=("low", "full"), default="low")
    p.add_argument("--click", help="ecrit aussi un WAV avec un clic sur chaque temps")
    p.add_argument("--bar-phase", type=int, help="impose le 1er temps de mesure (verifie a l'oreille)")
    p.add_argument("--phrase-phase", type=int, help="impose le debut des phrases de 16 temps")
    args = p.parse_args(argv)
    grid = analyse(args.wav, args.bpm_min, args.bpm_max, args.beat_band, args.bar_phase, args.phrase_phase)
    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.wav)), "beats.json")
    with open(out, "w") as f:
        json.dump(grid, f, indent=1)
        f.write("\n")
    q = grid["quality"]
    print("%s : %.2f BPM, 1er temps %.3f s, %d temps, 1er temps de mesure = temps n°%d, "
          "phrases de 16 temps a partir du temps n°%d"
          % (grid["file"], grid["bpm"], grid["first_beat"], len(grid["beats"]), grid["bar_phase"],
             grid["phrase_phase"]))
    print("sections : " + ", ".join("%s %d-%d" % (s["label"], s["start_beat"], s["end_beat"] - 1)
                                     for s in grid["sections"]))
    print("qualite : grosse caisse temps/contretemps %.2f, charleston %.2f, residus %.1f ms"
          % (q["kick_on_vs_offbeat"], q["hats_on_vs_offbeat"], q["fit_residual_ms"]))
    print("-> %s" % out)
    if args.click:
        click_track(args.wav, grid, args.click)
        print("-> %s (musique + clics)" % args.click)
    return 0


if __name__ == "__main__":
    sys.exit(main())
