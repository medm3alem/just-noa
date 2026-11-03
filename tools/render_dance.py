# -*- coding: utf-8 -*-
"""
tools/render_dance.py - Images de contrôle d'une chorégraphie (pas de robot nécessaire).

    python tools/render_dance.py macarena                 # docs/img/macarena_poses.png + _curves.png
    python tools/render_dance.py macarena --cycle 2
    python tools/render_dance.py echauffement --times 2,4,6,8

1. Planche de poses : NAO vu de face ET de profil à chaque temps du cycle, avec
   le modèle de collision (tête, torse, bassin, cuisses, bras épaissis) et la
   distance libre minimale. Un bras orange = bras GAUCHE de NAO, bleu = DROIT ;
   la flèche noire = normale de la paume.
2. Courbes : angle de chaque articulation pendant le cycle, temps musicaux en
   pointillés (vérifier que les gestes arrivent sur les temps).

Nécessite matplotlib (outil de développement : pip install matplotlib).
"""
from __future__ import absolute_import, division, print_function

import argparse
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, os.pardir))
sys.path.insert(0, ROOT)

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, Rectangle  # noqa: E402

from choreography import kinematics as K  # noqa: E402
from choreography.beatgrid import BeatGrid  # noqa: E402
from choreography.choreography import Choreography  # noqa: E402
from choreography.reference_pose import ReferenceTimeline  # noqa: E402

LEFT, RIGHT = "#e8590c", "#1c7ed6"


def draw(ax, pose, view, title):
    def P(p):
        # De face, on regarde NAO : son bras gauche apparaît à DROITE de l'image.
        return (p[1], p[2]) if view == "front" else (p[0], p[2])
    ax.add_patch(Circle(P(K.HEAD_CENTER), K.HEAD_RADIUS, fc="#e9ecf5", ec="#a5aec9"))
    for box in (K.TORSO_BOX, K.PELVIS_BOX):
        x0, x1 = (box[1] if view == "front" else box[0])
        ax.add_patch(Rectangle((x0, box[2][0]), x1 - x0, box[2][1] - box[2][0], fc="#e9ecf5", ec="#a5aec9"))
    for side in "LR":
        h, k = K._thigh(side)
        a, b = P(h), P(k)
        ax.plot([a[0], b[0]], [a[1], b[1]], color="#d5d9e6", lw=13, solid_capstyle="round", zorder=1)
    for side, col in (("L", LEFT), ("R", RIGHT)):
        pts = K.arm_points(pose, side)
        for a, b, r in ((pts["shoulder"], pts["elbow"], K.R_UPPER), (pts["elbow"], pts["wrist"], K.R_FORE),
                        (pts["wrist"], pts["tip"], K.R_HAND)):
            A, B = P(a), P(b)
            ax.plot([A[0], B[0]], [A[1], B[1]], color=col, lw=r * 0.42, alpha=0.45, solid_capstyle="round", zorder=3)
            ax.plot([A[0], B[0]], [A[1], B[1]], color=col, lw=1.4, zorder=4)
        w, n = P(pts["wrist"]), pts["palm"]
        d = (n[1], n[2]) if view == "front" else (n[0], n[2])
        ax.arrow(w[0], w[1], 38 * d[0], 38 * d[1], head_width=9, color="#212529", zorder=5)
    yaw = pose.get("HeadYaw", 0.0)
    c = P(K.HEAD_CENTER)
    if view == "front":
        ax.plot([c[0], c[0] - 60 * math.sin(yaw)], [c[1], c[1]], color="#495057", lw=2)
    ax.set_xlim(-330, 330) if view == "front" else ax.set_xlim(-230, 330)
    ax.set_ylim(-210, 390)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(title, fontsize=9)


def pose_sheet(timeline, times, labels, path, cols=4):
    n = len(times)
    rows = int(math.ceil(n / float(cols)))
    fig, axes = plt.subplots(rows, 2 * cols, figsize=(4.0 * cols, 2.55 * rows))
    for i, (t, label) in enumerate(zip(times, labels)):
        r, c = divmod(i, cols)
        pose = timeline.pose_at(t)
        clear, _pair = K.min_clearance(pose)
        draw(axes[r][2 * c], pose, "front", label)
        draw(axes[r][2 * c + 1], pose, "side", "t=%.2f s, marge %d mm" % (t, clear))
    for j in range(n, rows * cols):
        r, c = divmod(j, cols)
        axes[r][2 * c].axis("off")
        axes[r][2 * c + 1].axis("off")
    plt.tight_layout()
    plt.savefig(path, dpi=70)
    plt.close(fig)


def curves(timeline, names, t0, t1, beats, path):
    fig, axes = plt.subplots(3, 1, figsize=(13, 8), sharex=True)
    groups = [("Bras gauche", [n for n in names if n.startswith("L")]),
              ("Bras droit", [n for n in names if n.startswith("R")]),
              ("Tete", [n for n in names if n.startswith("Head")])]
    ts = [t0 + k * 0.01 for k in range(int((t1 - t0) / 0.01))]
    for ax, (title, group) in zip(axes, groups):
        for name in group:
            track = timeline.tracks[name]
            ax.plot(ts, [track.value(t) for t in ts], label=name[1:] if title != "Tete" else name, lw=1.3)
        for b in beats:
            if t0 <= b <= t1:
                ax.axvline(b, color="#adb5bd", lw=0.6, ls=":")
        ax.set_ylabel("%s (rad)" % title)
        ax.legend(loc="upper right", fontsize=7, ncol=6)
    axes[-1].set_xlabel("temps (s) - pointilles : temps musicaux")
    plt.tight_layout()
    plt.savefig(path, dpi=70)
    plt.close(fig)


def main(argv=None):
    p = argparse.ArgumentParser(description="Images de controle d'une choregraphie")
    p.add_argument("which")
    p.add_argument("--cycle", type=int, default=1, help="cycle de 16 temps a dessiner (Macarena)")
    p.add_argument("--times", help="instants a dessiner, ex. 2,4,6 (sinon : chaque temps du cycle)")
    p.add_argument("--out", default=os.path.join(ROOT, "docs", "img"))
    args = p.parse_args(argv)
    folder = os.path.join(ROOT, "choreography", "library", args.which)
    choreo = Choreography(folder)
    timeline = ReferenceTimeline(choreo)
    beats_file = os.path.join(folder, "beats.json")
    if not os.path.isdir(args.out):
        os.makedirs(args.out)
    if args.times:
        times = [float(x) for x in args.times.split(",")]
        labels = ["t=%.2f s" % t for t in times]
        beats, t0, t1 = [], min(times) - 0.5, max(times) + 0.5
    elif os.path.isfile(beats_file):
        grid = BeatGrid.load(beats_file)
        start = grid.cycle_start(args.cycle)
        times = [grid.time(start + k) for k in range(16)]
        labels = []
        for k, t in enumerate(times):
            starting = [m["name"] for m in choreo.moves if abs(m["start"] - t) < 0.02]
            labels.append("%d  %s" % (k + 1, starting[0] if starting else ""))
        beats, t0, t1 = grid.beats, grid.time(start - 1), grid.time(start + 16)
    else:
        # Danse sans musique : tempo et 1er temps écrits par compose_choreographies.py
        import io
        import json
        with io.open(os.path.join(folder, "meta.json"), encoding="utf-8") as f:
            info = json.load(f).get("composer") or {}
        t0 = min(t[0] for t in choreo.times)
        t1 = choreo.last_key_time
        period = 60.0 / info["bpm"] if info.get("bpm") else 1.0
        times, labels = [], []
        for m in choreo.moves:
            for k, suffix in ((1, ""), (2, " (+1)")):
                times.append(m["start"] + k * period)
                labels.append(m["name"] + suffix)
        if not times:
            times, labels = [t0, t1], ["debut", "fin"]
        first = info.get("first_beat", t0)
        beats = [first + k * period for k in range(int((t1 - first) / period) + 2)] if info else []
    pose_sheet(timeline, times, labels, os.path.join(args.out, "%s_poses.png" % args.which))
    curves(timeline, choreo.names, t0, t1, beats, os.path.join(args.out, "%s_curves.png" % args.which))
    print("-> %s" % os.path.join(args.out, "%s_poses.png" % args.which))
    print("-> %s" % os.path.join(args.out, "%s_curves.png" % args.which))
    return 0


if __name__ == "__main__":
    sys.exit(main())
