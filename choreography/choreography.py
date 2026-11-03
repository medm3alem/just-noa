# -*- coding: utf-8 -*-
"""
choreography/choreography.py - Une chorégraphie = un dossier de DONNÉES.

    library/ymca/
        meta.json     titre, musique, décalage de synchro, évènements (parole, LEDs)
        motion.json   keyframes : names / times / keys (format Choregraphe)
        ymca.wav      la musique (une copie doit aussi être sur le robot)

Convention de temps : tous les instants (keyframes et évènements) sont en
secondes depuis le DÉBUT DE LA MUSIQUE. Si le premier "Y" tombe à 4,2 s dans le
morceau, la keyframe du "Y" est à 4,2 s.

Pourquoi des données et pas du code ? Ajouter une danse = ajouter un dossier,
sans toucher au programme. Et un fichier JSON ne peut rien exécuter : on peut
le charger sans risque, en Python 2 comme en Python 3.
"""
from __future__ import absolute_import, print_function

import io
import json
import numbers
import os

from compat import to_native


class ChoreographyError(Exception):
    """Dossier de chorégraphie absent ou mal formé."""


def _load_json(path):
    with io.open(path, encoding="utf-8") as f:
        return to_native(json.load(f))


def save_motion(path, names, times, keys):
    """Écrit motion.json lisiblement : une ligne par articulation."""
    def block(rows):
        return ",\n".join("    " + json.dumps(r) for r in rows)
    text = ('{\n  "names": %s,\n  "times": [\n%s\n  ],\n  "keys": [\n%s\n  ]\n}\n'
            % (json.dumps(names), block(times), block(keys)))
    with open(path, "w") as f:
        f.write(text)


def save_meta(path, meta):
    """Écrit meta.json (separators évite les espaces en fin de ligne de Python 2)."""
    with open(path, "w") as f:
        json.dump(meta, f, indent=2, separators=(",", ": "))
        f.write("\n")


def _parse_color(value):
    """'#FF00FF', 'FF00FF', '0xFF00FF' ou un entier -> entier 0xRRGGBB."""
    if isinstance(value, numbers.Integral):
        return int(value)
    text = str(value).strip().lstrip("#")
    if text.lower().startswith("0x"):
        text = text[2:]
    return int(text, 16)


def _parse_event(raw):
    t = float(raw["t"])
    kind = raw.get("type")
    if kind == "say":
        return {"t": t, "type": "say", "text": raw["text"]}
    if kind == "leds":
        return {"t": t, "type": "leds", "color": _parse_color(raw["color"]),
                "duration": float(raw.get("duration", 0.1))}
    raise ChoreographyError("type d'evenement inconnu : %r (attendu 'say' ou 'leds')" % kind)


class Choreography(object):

    def __init__(self, folder):
        self.folder = folder
        self.id = os.path.basename(os.path.normpath(folder))
        meta_path = os.path.join(folder, "meta.json")
        motion_path = os.path.join(folder, "motion.json")
        for path in (meta_path, motion_path):
            if not os.path.isfile(path):
                raise ChoreographyError("%s manquant" % os.path.basename(path))
        try:
            self._parse(_load_json(meta_path), _load_json(motion_path))
        except ChoreographyError:
            raise
        except (KeyError, TypeError, ValueError, IndexError) as err:
            raise ChoreographyError("format invalide : %s: %s" % (type(err).__name__, err))

    def _parse(self, meta, motion):
        self.title = meta.get("title", self.id)
        self.description = meta.get("description", "")
        audio = meta.get("audio")
        self.audio_path = os.path.join(self.folder, audio) if audio else None
        # Copie de la musique SUR LE ROBOT (lue par NAO via la passerelle), et
        # position de départ dans ce fichier (0 si le fichier est déjà l'extrait).
        self.audio_robot = meta.get("audio_robot")
        self.audio_start = float(meta.get("audio_start", 0.0))
        # sync_offset > 0 : le mouvement part APRÈS la musique (en secondes).
        # Valeur mesurée avec la chorégraphie "calibration" (voir README).
        self.sync_offset = float(meta.get("sync_offset", 0.0))
        self.countdown = bool(meta.get("countdown", True))
        # Réglages facultatifs du score : {"start": s, "end": s, "weights": {...},
        # "difficulty": "facile"} (voir docs/EVALUATION.md)
        self.scoring = meta.get("scoring") or {}
        self.difficulty = meta.get("difficulty", self.scoring.get("difficulty"))

        self.names = list(motion["names"])
        self.times = [[float(t) for t in joint_times] for joint_times in motion["times"]]
        raw_keys = motion["keys"]
        # Format Bezier : chaque clé est [angle, poignée_avant, poignée_après].
        # Format simple : chaque clé est un angle.
        self.bezier = bool(raw_keys and raw_keys[0] and isinstance(raw_keys[0][0], list))
        if self.bezier:
            # On convertit l'angle en float ; les poignées restent telles qu'exportées.
            self.keys = [[[float(k[0])] + list(k[1:]) for k in joint] for joint in raw_keys]
        else:
            self.keys = [[float(k) for k in joint] for joint in raw_keys]

        self.events = sorted((_parse_event(e) for e in meta.get("events", [])),
                             key=lambda e: e["t"])
        # Mouvements nommés (facultatif, écrits par tools/compose_choreographies.py) :
        # [{"start": s, "end": s, "name": "Palms up"}]. Servent au bilan du joueur.
        self.moves = [dict(start=float(m["start"]), end=float(m["end"]), name=m.get("name", ""))
                      for m in meta.get("moves", [])]
        self.last_key_time = max(t[-1] for t in self.times if t) if any(self.times) else 0.0
        last_event = self.events[-1]["t"] if self.events else 0.0
        # Fin de la danse : 'end' si précisé (pour couper une musique trop longue),
        # sinon 1 s après la dernière keyframe ou le dernier évènement.
        if meta.get("end") is not None:
            self.end = float(meta["end"])
        else:
            self.end = max(self.last_key_time, last_event) + 1.0

    # --- Essais à vitesse réduite ------------------------------------------------
    def scaled(self, speed):
        """
        Copie jouée `speed` fois plus vite (0.5 = deux fois plus lentement), pour les
        premiers essais sur le robot. La musique est retirée (NAO ne peut pas la
        ralentir) ; keyframes, poignées Bezier, évènements, mouvements nommés et
        fin sont étirés. Les vitesses articulaires sont multipliées par `speed`.
        """
        import copy
        if not 0.1 <= speed <= 1.0:
            raise ValueError("vitesse entre 0.1 et 1.0 attendue")
        k = 1.0 / speed
        out = copy.copy(self)
        out.times = [[t * k for t in joint] for joint in self.times]
        if self.bezier:
            # Poignées : seule la composante "temps" s'étire (la pente est divisée par k)
            from choreography.reference_pose import _detect_handle_time_index
            ti = _detect_handle_time_index(self.keys)

            def stretch(handle):
                h = list(handle)
                h[ti] = h[ti] * k
                return h
            out.keys = [[[key[0], stretch(key[1]), stretch(key[2])] for key in joint]
                        for joint in self.keys]
        out.events = [dict(e, t=e["t"] * k) for e in self.events]
        out.moves = [dict(m, start=m["start"] * k, end=m["end"] * k) for m in self.moves]
        out.end = self.end * k
        out.last_key_time = self.last_key_time * k
        out.scoring = dict(self.scoring)
        for key in ("start", "end"):
            if key in out.scoring:
                out.scoring[key] = out.scoring[key] * k
        out.audio_path = out.audio_robot = None
        out.sync_offset = 0.0
        if speed < 1.0:
            out.title = "%s (%d %% speed, no music)" % (self.title, round(100 * speed))
        return out

    # --- Accès pratiques ---------------------------------------------------------
    def angle(self, key):
        return key[0] if self.bezier else key

    def first_pose(self):
        """(noms, angles) de la première keyframe de chaque articulation."""
        return self.names, [self.angle(k[0]) for k in self.keys]

    # --- Vérifications de sécurité ------------------------------------------------
    def validate(self, limits, speed_warn_ratio=0.6, tolerance=0.01, step=0.01,
                 collision_step=0.04, balance=True):
        """
        Vérifie la chorégraphie AVANT de l'envoyer au robot.
        `limits` = robot.joint_limits(self.names). Renvoie (erreurs, alertes) :
        une erreur interdit la danse, une alerte est seulement affichée.

        On vérifie la TRAJECTOIRE réellement jouée (courbe entre les clés, poignées
        Bezier comprises), échantillonnée tous les `step` s : butées, vitesse de
        pointe, puis distances entre bras, tête et corps (choreography/kinematics.py)
        et enveloppe de la tête. collision_step=None désactive les distances.
        """
        errors, warnings = [], []
        if not self.names:
            return ["aucune articulation dans motion.json"], warnings
        if not (len(self.names) == len(self.times) == len(self.keys)):
            return ["names, times et keys n'ont pas la meme longueur"], warnings
        if len(set(self.names)) != len(self.names):
            return ["une articulation apparait deux fois dans motion.json"], warnings
        from choreography.reference_pose import ReferenceTimeline
        try:
            timeline = ReferenceTimeline(self)
        except (ValueError, TypeError, IndexError) as err:
            return ["trajectoire illisible : %s" % err], warnings

        for name, times, keys in zip(self.names, self.times, self.keys):
            if not times or len(times) != len(keys):
                errors.append("%s : autant de temps que d'angles attendus" % name)
                continue
            if times[0] <= 0:
                errors.append("%s : le premier instant doit etre > 0" % name)
            if any(b <= a for a, b in zip(times, times[1:])):
                errors.append("%s : instants non strictement croissants" % name)
            lim = limits.get(name)
            if lim is None:
                errors.append("%s : articulation inconnue de ce robot" % name)
                continue
            low, high, max_speed = lim
            angles = [self.angle(k) for k in keys]
            # 1. Butées mécaniques (clés)
            for t, a in zip(times, angles):
                if a < low - tolerance or a > high + tolerance:
                    errors.append("%s : %.3f rad a t=%.2f s, hors butees [%.3f ; %.3f]"
                                  % (name, a, t, low, high))
                    break
            worst, worst_t = 0.0, 0.0
            if errors and errors[-1].startswith(name + " :"):
                continue
            # 2. Courbe réellement jouée : butées entre les clés et vitesse de pointe
            try:
                track = timeline.tracks[name]
            except (NameError, KeyError):
                track = None
            if track is not None and len(times) > 1:
                n = max(1, int((times[-1] - times[0]) / step))
                prev = track.value(times[0])
                for k in range(1, n + 1):
                    t = times[0] + k * (times[-1] - times[0]) / n
                    a = track.value(t)
                    if a < low - tolerance or a > high + tolerance:
                        errors.append("%s : la courbe sort des butees a t=%.2f s (%.3f rad)"
                                      % (name, t, a))
                        break
                    v = abs(a - prev) * n / (times[-1] - times[0])
                    if v > worst:
                        worst, worst_t = v, t
                    prev = a
            if max_speed:
                if worst > max_speed:
                    errors.append("%s : %.1f rad/s vers t=%.2f s, au-dela du max (%.1f rad/s)"
                                  % (name, worst, worst_t, max_speed))
                elif worst > speed_warn_ratio * max_speed:
                    warnings.append("%s : %.1f rad/s vers t=%.2f s (%d %% du max)"
                                    % (name, worst, worst_t, 100 * worst / max_speed))

        if self.audio_path and not os.path.isfile(self.audio_path):
            errors.append("musique introuvable sur le PC : %s" % self.audio_path)
        if self.end < self.last_key_time:
            errors.append("'end' (%.1f s) est avant la derniere keyframe (%.1f s)"
                          % (self.end, self.last_key_time))
        if any(e["t"] < 0 for e in self.events):
            errors.append("evenement avec un instant negatif")
        legs = [n for n in self.names if any(p in n for p in ("Hip", "Knee", "Ankle"))]
        if legs:
            warnings.append("bouge les jambes (%s) : tester d'abord sur le robot virtuel, "
                            "puis sur le vrai robot tenu par quelqu'un" % ", ".join(legs))
        for m in self.moves:
            if not m["start"] < m["end"]:
                errors.append("mouvement '%s' : debut apres la fin" % m["name"])
        # 3. Distances bras / tête / corps et enveloppe de la tête, le long de la danse
        if collision_step and not errors:
            from choreography.kinematics import check_trajectory
            arm_joints = any(n[1:] in ("ShoulderPitch", "ShoulderRoll", "ElbowYaw", "ElbowRoll")
                             for n in self.names)
            head = "HeadPitch" in self.names
            if arm_joints or head:
                start, end = timeline.first_key_time, timeline.last_key_time
                coll_err, coll_warn, _worst = check_trajectory(timeline.pose_at, start, end,
                                                               collision_step, arms=arm_joints,
                                                               head=head)
                errors.extend(coll_err)
                warnings.extend(coll_warn)
        # 4. Équilibre : déplacement estimé du point d'appui (ZMP) dû aux bras.
        #    Seuils réglés d'après la chute réelle de NAO avec l'échauffement v4 :
        #    voir kinematics.BALANCE_LIMITS.
        if balance and not errors and any(n[1:] in ("ShoulderPitch", "ShoulderRoll") for n in self.names):
            from choreography.kinematics import BALANCE_LIMITS, balance_summary
            bal = balance_summary(timeline.pose_at, timeline.first_key_time,
                                  timeline.last_key_time, step=0.02)
            for key, label in (("dyn", "par les accelerations des bras (avant/arriere)"),
                               ("back", "vers l'arriere"), ("fwd", "vers l'avant"),
                               ("lat", "sur le cote")):
                warn, maxi = BALANCE_LIMITS[key]
                if bal[key] > maxi:
                    errors.append("equilibre : appui deplace de %.0f mm %s (max %.0f mm) : "
                                  "bras trop rapides ou trop amples ensemble" % (bal[key], label, maxi))
                elif bal[key] > warn:
                    warnings.append("equilibre : appui deplace de %.0f mm %s (alerte a %.0f mm)"
                                    % (bal[key], label, warn))
        return errors, warnings
