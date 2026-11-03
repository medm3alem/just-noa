# -*- coding: utf-8 -*-
"""
app/controller.py - Le chef d'orchestre de l'application.

C'est le SEUL point d'entrée des interfaces : le clavier et la HMI appellent
les mêmes méthodes (select, start, stop, wake, rest, status). Aucune logique
robot n'est dupliquée dans les interfaces.

Machine à états (une seule vérité sur "ce que fait NAO") :

    REPOS --start--> PREPARATION --musique--> DANSE --fin/stop--> ARRET --> PRET
      ^                                                                    |
      +------------------------------ rest <-------------------------------+
    REPOS --wake--> OCCUPE --> PRET          PRET --rest--> OCCUPE --> REPOS
    chute ou erreur (n'importe quand) --> ERREUR --wake ou rest--> PRET / REPOS

Les actions longues (réveil, danse, repos) tournent dans un thread "worker" :
les méthodes publiques rendent la main tout de suite, l'interface reste
réactive et le bouton Stop marche pendant la danse.

Chaque méthode publique renvoie (ok, message) : l'interface affiche le message.

Jeu interactif (facultatif, Python 3) : si `session_factory` est fourni, chaque
danse crée une GameSession (app/game_session.py) qui note le joueur. Le
contrôleur la crée au départ, la signale via `on_session` (la chaîne vision s'y
branche), la clôt à la fin selon une politique explicite :
  - fin naturelle                -> session "terminee", bilan complet ;
  - Stop, chute, erreur, fermeture -> session "interrompue", notée sur la partie
    dansée ; enregistrée si au moins une pose a été évaluée.
Le bilan est enregistré (reports/session_store.py) puis exposé par last_report().

Commentaire de fin (NAO coach sarcastique, evaluation/nao_personality.py) :
le texte est ajouté au bilan AVANT l'enregistrement, puis NAO le dit dans un
thread à part, seulement quand la musique est coupée et NAO revenu en posture.
Jamais après une chute. Le joueur peut le passer (skip_commentary) ; "Repos" et
la fermeture attendent la fin de la phrase en cours.

Messages renvoyés aux interfaces : en anglais (affichés au joueur). Journal : français.
"""
from __future__ import absolute_import, print_function

import threading
import time
import traceback
from collections import deque

import config
from robot.base import RobotError
from sync.player import FINISHED, Player

REPOS = "REPOS"
OCCUPE = "OCCUPE"
PRET = "PRET"
PREPARATION = "PREPARATION"
DANSE = "DANSE"
ARRET = "ARRET"
ERREUR = "ERREUR"

DANCING = (PREPARATION, DANSE)
FALL_MESSAGE = "NAO fell! Put it back on its feet, then press Wake up or Rest"
BUSY = (OCCUPE, PREPARATION, DANSE, ARRET)


class Controller(object):

    def __init__(self, robot, library, session_factory=None, store=None, personality=None,
                 cfg=None):
        self.robot = robot
        self.library = library
        self.session_factory = session_factory   # (choreo, origin_fn, on_voice) -> GameSession
        self.store = store                       # SessionStore ou None
        self.personality = personality           # NaoPersonality ou None (commentaire de fin)
        self.cfg = cfg or config
        self._speech_thread = None
        self._speech_cancel = threading.Event()
        self._speech_active = False
        self.on_log = None                  # fonction(ligne) : affichage console
        self.on_session = None              # fonction(session ou None) : branche la vision
        self._session = None
        self._last_report = None
        self._report_seq = 0
        self._speaking = False
        self._logs = deque(maxlen=300)      # (numéro, ligne) pour la HMI
        self._log_seq = 0
        self._lock = threading.RLock()      # protège l'état partagé entre threads
        self._stop = threading.Event()
        self._worker = None
        self._fallen = False
        self._selected = None
        self._robot_status = {}
        self._warned = set()
        self._checked = {}                  # id -> (erreurs, alertes) de validate()

        robot.log = self.log                # les messages du robot arrivent ici aussi
        robot.on_fall(self._on_fall)
        self._player = Player(robot, log=self.log)

        try:
            awake = robot.is_awake()
        except Exception as err:            # robot injoignable : l'appli démarre quand même
            self.log("[ATTENTION] Etat du robot inconnu : %s" % err)
            awake = False
        self._state = PRET if awake else REPOS
        self._message = "Ready" if self._state == PRET else "Robot resting"
        self.log("[OK] Just Nao pret : %d choregraphie(s), robot %s, etat %s"
                 % (len(library), robot.name, self._state))
        if library:
            self.select(list(library)[0])

        self._monitor_running = True
        self._monitor = threading.Thread(target=self._monitor_loop)
        self._monitor.daemon = True
        self._monitor.start()
        checker = threading.Thread(target=self._prevalidate)
        checker.daemon = True
        checker.start()

    # =========================================================================
    # API publique (appelée par les interfaces)
    # =========================================================================
    def choreographies(self):
        """[(id, titre, durée en s, description)] dans l'ordre de la bibliothèque."""
        return [(c.id, c.title, c.end, c.description) for c in self.library.values()]

    def select(self, choreo_id):
        with self._lock:
            if self._state in BUSY:
                return False, "Not possible while the robot is busy"
        choreo = self.library.get(choreo_id)
        if choreo is None:
            return False, "Unknown choreography: %s" % choreo_id
        # Vérification de sécurité AVANT toute danse : butées, vitesses, distances
        # bras / tête / corps le long de la trajectoire (résultat gardé en cache)
        errors, warnings = self._validation(choreo)
        for w in warnings:
            self.log("[ATTENTION] %s : %s" % (choreo.id, w))
        if errors:
            for e in errors:
                self.log("[REFUSEE] %s : %s" % (choreo.id, e))
            return False, "%s refused for safety: %d error(s), see the log" % (choreo.title, len(errors))
        with self._lock:
            self._selected = choreo
        return True, "Selected: %s" % choreo.title

    def _validation(self, choreo):
        cached = self._checked.get(choreo.id)
        if cached is not None:
            return cached
        limits = self.robot.joint_limits(choreo.names)
        result = choreo.validate(limits, config.SPEED_WARN_RATIO, config.LIMIT_TOLERANCE)
        self._checked[choreo.id] = result
        return result

    def _prevalidate(self):
        """Au démarrage, en tâche de fond : "Dance" n'attend pas la vérification (~1 s)."""
        for choreo in list(self.library.values()):
            try:
                self._validation(choreo)
            except Exception as err:          # la vérification sera refaite à la sélection
                self.log("[ATTENTION] Verification de %s : %s" % (choreo.id, err))

    def start(self):
        with self._lock:
            if self._selected is None:
                return False, "No choreography selected"
            if self._state not in (REPOS, PRET):
                return False, "Cannot start now (robot state: %s)" % self._state
            choreo = self._selected
            self._stop.clear()
            self.skip_commentary()      # une nouvelle danse coupe l'ancien commentaire
            self._set_state(PREPARATION, "Getting ready: %s" % choreo.title)
            self._launch(self._dance, choreo)
        return True, "Dance started: %s" % choreo.title

    def stop(self):
        with self._lock:
            if self._state not in DANCING:
                return False, "No dance in progress"
            self._set_state(ARRET, "Stopping")
            self._stop.set()
        return True, "Stopping the dance"

    def wake(self):
        with self._lock:
            if self._state not in (REPOS, ERREUR):
                return False, "The robot is not resting (state: %s)" % self._state
            self._fallen = False
            self._set_state(OCCUPE, "Waking up and standing")
            self._launch(self._do_wake)
        return True, "Waking up"

    def rest(self):
        with self._lock:
            if self._state not in (PRET, ERREUR):
                return False, "Cannot rest now (state: %s)" % self._state
            self._set_state(OCCUPE, "Going to rest")
            self._launch(self._do_rest)
        return True, "Going to rest"

    def status(self):
        """Photo instantanée de l'application, sans appel réseau (lecture du cache)."""
        elapsed, duration = self._player.progress()
        with self._lock:
            sel = self._selected
            return {
                "state": self._state,
                "message": self._message,
                "selected": sel.id if sel else None,
                "title": sel.title if sel else None,
                "elapsed": elapsed,
                "duration": duration or (sel.end if sel else 0.0),
                "robot": dict(self._robot_status),
                "game": self._session.snapshot() if self._session is not None else None,
                "report_seq": self._report_seq,
                "speaking": self._speech_active,
            }

    def skip_commentary(self):
        """Le joueur passe le commentaire de NAO : on coupe la phrase en cours."""
        if not self._speech_active:
            return False, "Nothing to skip"
        self._speech_cancel.set()
        try:
            self.robot.stop_speech()
        except Exception as err:
            self.log("[ATTENTION] Arret de la parole : %s" % err)
        return True, "Commentary skipped"

    def current_session(self):
        with self._lock:
            return self._session

    def last_report(self):
        with self._lock:
            return self._last_report

    def logs_since(self, seq):
        """Lignes de journal plus récentes que `seq` -> (nouveau seq, [lignes])."""
        with self._lock:
            lines = [line for n, line in self._logs if n > seq]
            return self._log_seq, lines

    def shutdown(self):
        """Fin du programme : arrêter la danse, mettre NAO au repos, fermer."""
        self._monitor_running = False
        self.on_session = None
        self.skip_commentary()
        self._wait_speech(5.0)
        with self._lock:
            if self._state in DANCING:
                self._set_state(ARRET, "Stopping (closing)")
                self._stop.set()
            worker = self._worker
        if worker is not None:
            worker.join(20.0)
        self._close_session("interrompue")      # au cas où la danse n'a pas fini proprement
        try:
            if self.robot.is_awake():
                self.log("Mise au repos avant de quitter...")
                self.robot.rest()
        except Exception as err:
            self.log("[ATTENTION] Repos impossible : %s" % err)
        self.robot.close()

    # =========================================================================
    # Journal
    # =========================================================================
    def log(self, message):
        line = time.strftime("%H:%M:%S ") + message
        with self._lock:
            self._log_seq += 1
            self._logs.append((self._log_seq, line))
        if self.on_log is not None:
            self.on_log(line)

    # =========================================================================
    # Travail en arrière-plan
    # =========================================================================
    def _set_state(self, state, message=""):
        with self._lock:
            old, self._state, self._message = self._state, state, message
        if old != state:
            self.log("[ETAT] %s -> %s  %s" % (old, state, message))

    def _launch(self, target, *args):
        self._worker = threading.Thread(target=target, args=args)
        self._worker.daemon = True
        self._worker.start()

    def _dance(self, choreo):
        try:
            self._wait_speech(5.0)          # la phrase coupée doit être finie avant de bouger
            self._open_session(choreo)
            if not self.robot.is_awake():
                self.robot.wake_up()
            self.robot.go_to_posture(config.POSTURE, config.POSTURE_SPEED)
            result = "arrete"
            if not self._stop.is_set():
                result = self._player.play(choreo, self._stop, on_start=self._on_music_start)
            report = self._close_session("terminee" if result == FINISHED and not self._fallen
                                         else "interrompue")
            if self._fallen:
                self._set_state(ERREUR, FALL_MESSAGE)
                return
            self._set_state(ARRET, "Back to %s posture" % config.POSTURE)
            self.robot.go_to_posture(config.POSTURE, config.POSTURE_SPEED)
            self._set_state(PRET, "Dance finished" if result == FINISHED else "Dance stopped")
            # Musique coupée, NAO stable : il peut commenter la performance.
            self._start_commentary(report)
        except Exception as err:
            self._fail(err)

    def _on_music_start(self):
        with self._lock:
            # Si l'utilisateur a appuyé sur Stop entre-temps, on reste en ARRET.
            if self._state == PREPARATION:
                self._set_state(DANSE, "Dancing")

    def _do_wake(self):
        try:
            self.robot.wake_up()
            self.robot.go_to_posture(config.POSTURE, config.POSTURE_SPEED)
            self._set_state(PRET, "Robot standing, ready to dance")
        except Exception as err:
            self._fail(err)

    def _do_rest(self):
        try:
            self._wait_speech(20.0)        # jamais de repos au milieu d'une phrase
            self.robot.rest()
            self._set_state(REPOS, "Robot resting")
        except Exception as err:
            self._fail(err)

    def _fail(self, err):
        self._close_session("interrompue")
        self.log("[ERREUR] %s" % err)
        if not isinstance(err, RobotError):
            self.log(traceback.format_exc())   # bug inattendu : détail pour l'équipe
        self._set_state(ERREUR, "Robot error: " + str(err).split("\n")[0])

    def _on_fall(self):
        # Appelé depuis un thread de NAOqi (ou par FakeRobot.simulate_fall).
        self.log("[CHUTE] NAO est tombe ! Arret immediat.")
        with self._lock:
            self._fallen = True
            self._stop.set()
            if self._state not in BUSY:
                self._set_state(ERREUR, FALL_MESSAGE)

    # =========================================================================
    # Session de jeu (évaluation du joueur)
    # =========================================================================
    def _open_session(self, choreo):
        if self.session_factory is None:
            return
        try:
            session = self.session_factory(choreo, self._player.timeline_origin, self._voice)
        except Exception as err:          # le jeu ne doit jamais empêcher NAO de danser
            self.log("[ATTENTION] Evaluation indisponible : %s" % err)
            return
        with self._lock:
            self._session = session
        if self.on_session is not None:
            self.on_session(session)

    def _close_session(self, status):
        with self._lock:
            session, self._session = self._session, None
        if session is None:
            return None
        if self.on_session is not None:
            self.on_session(None)
        try:
            report = session.finish(status)
        except Exception as err:
            self.log("[ERREUR] Bilan impossible : %s" % err)
            return None
        self._add_comment(report)
        if report.get("evaluated_duration_s", 0) > 0 and self.store is not None:
            try:
                report["file"] = self.store.save(report)
                self.log("[JEU] Partie enregistree : %s" % report["file"])
            except Exception as err:
                self.log("[ATTENTION] Enregistrement impossible : %s" % err)
        with self._lock:
            self._last_report = report
            self._report_seq += 1
        self.log("[JEU] %s : score %.0f (%s), suivi %d %%"
                 % (status, report.get("score", 0), report.get("category", "-"),
                    round(100 * report.get("tracking_ratio", 0))))
        return report

    # =========================================================================
    # Commentaire de fin de NAO
    # =========================================================================
    def _add_comment(self, report):
        """Texte du commentaire, ajouté au bilan (affiché et enregistré)."""
        if self.personality is None or self._fallen:
            return
        if report.get("frames_analysed", 0) == 0:
            return                          # pas de vision : pas de score à commenter
        if report.get("status") == "interrompue" and not getattr(self.cfg, "ANNOUNCE_INTERRUPTED", True):
            return
        try:
            report["nao_comment"] = self.personality.comment(report)
        except Exception as err:
            self.log("[ATTENTION] Commentaire impossible : %s" % err)

    def _start_commentary(self, report):
        if report is None or "nao_comment" not in report or report.get("announced"):
            return
        report["announced"] = True          # une seule annonce par partie
        if not getattr(self.cfg, "NAO_SPEAKS", True):
            return
        self._wait_speech(5.0)
        self._speech_cancel.clear()
        self._speech_active = True
        self._speech_thread = threading.Thread(target=self._speak_comment,
                                               args=(list(report["nao_comment"]["lines"]),))
        self._speech_thread.daemon = True
        self._speech_thread.start()

    def _speak_comment(self, lines):
        try:
            for i, line in enumerate(lines):
                if self._speech_cancel.is_set() or self._fallen:
                    break
                self.robot.say(line)
                if i == 0:                  # petit silence théâtral après le score
                    self._speech_cancel.wait(getattr(self.cfg, "ROAST_PAUSE", 0.7))
        except Exception as err:
            self.log("[ATTENTION] Commentaire non prononce : %s" % err)
        finally:
            self._speech_active = False

    def _wait_speech(self, timeout):
        t = self._speech_thread
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout)

    def _voice(self, text):
        # Encouragement vocal : dans son propre thread, jamais deux à la fois.
        if self._speaking:
            return
        def speak():
            self._speaking = True
            try:
                self.robot.say(text)
            except Exception:
                pass
            finally:
                self._speaking = False
        t = threading.Thread(target=speak)
        t.daemon = True
        t.start()

    def _monitor_loop(self):
        # Lit l'état du robot toutes les STATUS_PERIOD secondes et le met en cache :
        # l'interface lit le cache sans jamais attendre le réseau.
        while self._monitor_running:
            try:
                st = self.robot.status()
            except Exception:
                st = {"connected": False}
            with self._lock:
                self._robot_status = st
            self._check_alerts(st)
            time.sleep(config.STATUS_PERIOD)

    def _check_alerts(self, st):
        def once(key, message):
            if key not in self._warned:
                self._warned.add(key)
                self.log(message)
        if st.get("connected") is False:
            once("conn", "[ATTENTION] Liaison avec le robot perdue (nouvel essai automatique)")
        elif "conn" in self._warned:
            self._warned.discard("conn")
            self.log("[OK] Liaison avec le robot retablie")
        battery = st.get("battery")
        if battery is not None and battery < config.BATTERY_WARN:
            once("bat", "[ATTENTION] Batterie faible : %d %%" % battery)
        temp = st.get("temperature")
        if temp is not None and temp >= config.TEMPERATURE_WARN:
            once("temp", "[ATTENTION] Moteurs chauds (%.0f C) : laisser NAO au repos" % temp)
