# -*- coding: utf-8 -*-
"""
sync/player.py - Lecture synchronisée : musique + mouvement + évènements.

Le problème : la musique et le mouvement sont deux commandes envoyées au robot
par le réseau. Si on les lançait l'une après l'autre dans le même thread, la
seconde ne partirait qu'à la FIN de la première (les appels sont bloquants).

La solution, en 4 temps :
  1. PRÉPARER   : la musique est préchargée sur le robot (loadFile) et NAO
                  rejoint en douceur la pose de départ de la danse ;
  2. DÉCOMPTER  : "Three! Two! One!" (optionnel) ;
  3. LANCER     : trois threads démarrent au même instant `t_go` :
                    - audio      : robot.play_audio()  (bloquant)
                    - mouvement  : robot.play_motion() (bloquant)
                    - évènements : parole et LEDs, chacun à son instant ;
                  `sync_offset` retarde le mouvement (ou la musique s'il est
                  négatif) pour compenser la latence mesurée ;
  4. SURVEILLER : on attend la fin de la timeline ('end') ou un arrêt. Sur
                  arrêt, on coupe tout (mouvement, musique, parole).

La musique ET le mouvement s'exécutent sur le robot, avec la même horloge :
une fois partis ensemble, ils ne dérivent pas. Seul le DÉPART traverse le
réseau ; son petit décalage est mesuré une fois (chorégraphie "calibration").
"""
from __future__ import absolute_import, print_function

import threading

import config
from compat import now, sleep_until

FINISHED = "fini"
STOPPED = "arrete"


class Player(object):

    def __init__(self, robot, log=print):
        self.robot = robot
        self.log = log
        self._lock = threading.Lock()
        self._t_ref = None     # instant now() qui correspond à t = 0 de la chorégraphie
        self._end = 0.0

    def timeline_origin(self):
        """
        Instant now() qui correspond à t = 0 de la chorégraphie (départ de la
        musique et du mouvement), ou None hors danse. C'est l'horloge commune
        utilisée par l'évaluation du joueur (app/game_session.py).
        """
        with self._lock:
            return self._t_ref

    def progress(self):
        """(secondes écoulées, durée totale) de la danse en cours ; (0, 0) sinon."""
        with self._lock:
            if self._t_ref is None:
                return 0.0, 0.0
            return max(0.0, min(now() - self._t_ref, self._end)), self._end

    # =========================================================================
    def play(self, choreo, stop_event, on_start=None):
        """
        Bloquant : joue `choreo` jusqu'à la fin ou jusqu'à ce que `stop_event`
        soit levé (par le contrôleur). Renvoie FINISHED ou STOPPED.
        `on_start` est appelé au moment où la musique et le mouvement partent.
        """
        robot = self.robot
        handle = None
        halt = threading.Event()        # levé quand la timeline est finie ou arrêtée
        try:
            # --- 1. Préparer -------------------------------------------------------
            if choreo.audio_path or getattr(choreo, "audio_robot", None):
                handle = robot.prepare_audio(choreo.audio_path,
                                             robot_path=getattr(choreo, "audio_robot", None),
                                             start=getattr(choreo, "audio_start", 0.0))
            names, first_angles = choreo.first_pose()
            # Sans cela, NAO sauterait de StandInit à la 1re keyframe en quelques
            # centièmes de seconde si celle-ci est très tôt dans la musique.
            # Interruptible : un Stop pendant ce mouvement l'arrête aussitôt.
            if not self._interruptible(lambda: robot.move_to(names, first_angles, config.PREPOSITION_TIME),
                                       stop_event, lambda: robot.stop_motion(names)):
                return STOPPED

            # --- 2. Décompter ------------------------------------------------------
            if choreo.countdown:
                if not self._interruptible(lambda: robot.say(config.COUNTDOWN_TEXT),
                                           stop_event, robot.stop_speech):
                    return STOPPED

            # --- 3. Lancer ---------------------------------------------------------
            delay_motion = max(0.0, choreo.sync_offset)
            delay_audio = max(0.0, -choreo.sync_offset)
            t_go = now() + 0.1                 # 100 ms pour démarrer les threads
            t_ref = t_go + delay_motion        # t = 0 du mouvement et des évènements
            with self._lock:
                self._t_ref, self._end = t_ref, choreo.end

            threads = [
                self._spawn(self._run_audio, handle, t_go + delay_audio, halt),
                self._spawn(self._run_motion, choreo, t_ref, halt),
                self._spawn(self._run_events, choreo.events, t_ref, halt),
            ]
            if on_start is not None:
                on_start()
            self.log("[SYNC] Depart : %s (decalage %+.3f s, duree %.1f s)"
                     % (choreo.title, choreo.sync_offset, choreo.end))

            # --- 4. Surveiller -----------------------------------------------------
            finished = sleep_until(t_ref + choreo.end, stop_event)
            halt.set()
            if finished:
                if handle is not None:
                    robot.stop_audio(handle)   # coupe la musique si elle dépasse 'end'
                result = FINISHED
            else:
                self._stop_everything(choreo, handle)
                result = STOPPED
            for t in threads:
                t.join(3.0)
            return result

        except Exception:
            halt.set()
            self._stop_everything(choreo, handle)
            raise
        finally:
            if handle is not None:
                robot.release_audio(handle)
            try:
                robot.set_leds(0xFFFFFF, 0.3)   # yeux blancs : retour à la normale
            except Exception:
                pass
            with self._lock:
                self._t_ref = None

    # =========================================================================
    # Threads
    # =========================================================================
    def _interruptible(self, action, stop_event, cancel):
        """
        Lance une action bloquante dans un thread et surveille stop_event :
        sur Stop, `cancel` interrompt l'action (au lieu d'attendre sa fin).
        Renvoie True si l'action s'est terminée normalement.
        """
        done = threading.Event()
        errors = []

        def run():
            try:
                action()
            except Exception as err:
                errors.append(err)
            finally:
                done.set()
        self._spawn(run)
        while not done.wait(0.05):
            if stop_event.is_set():
                try:
                    cancel()
                except Exception as err:
                    self.log("[ATTENTION] Interruption : %s" % err)
                done.wait(3.0)
                return False
        if errors and not stop_event.is_set():
            raise errors[0]
        return not stop_event.is_set()

    @staticmethod
    def _spawn(target, *args):
        t = threading.Thread(target=target, args=args)
        t.daemon = True        # ne bloque jamais la fermeture du programme
        t.start()
        return t

    def _run_audio(self, handle, t_start, halt):
        if handle is None or not sleep_until(t_start, halt):
            return
        try:
            self.robot.play_audio(handle)
        except Exception as err:
            if not halt.is_set():
                self.log("[ERREUR] Musique : %s" % err)

    def _run_motion(self, choreo, t_start, halt):
        if not sleep_until(t_start, halt):
            return
        try:
            self.robot.play_motion(choreo.names, choreo.times, choreo.keys)
        except Exception as err:
            # Un arrêt (killTasksUsingResources) peut faire lever l'appel : normal.
            if not halt.is_set():
                self.log("[ERREUR] Mouvement : %s" % err)

    def _run_events(self, events, t_ref, halt):
        for event in events:
            if not sleep_until(t_ref + event["t"], halt):
                return
            # Chaque évènement dans son propre thread : une phrase de 2 s ne doit
            # pas retarder le flash de LEDs prévu 0,5 s plus tard.
            self._spawn(self._fire, event)

    def _fire(self, event):
        try:
            if event["type"] == "say":
                self.robot.say(event["text"])
            elif event["type"] == "leds":
                self.robot.set_leds(event["color"], event["duration"])
        except Exception as err:
            self.log("[ERREUR] Evenement a t=%.2f s : %s" % (event["t"], err))

    def _stop_everything(self, choreo, handle):
        actions = (
            ("mouvement", lambda: self.robot.stop_motion(choreo.names)),
            ("musique", lambda: self.robot.stop_audio(handle)),
            ("parole", self.robot.stop_speech),
        )
        for label, action in actions:
            try:
                action()
            except Exception as err:
                self.log("[ATTENTION] Arret %s : %s" % (label, err))
