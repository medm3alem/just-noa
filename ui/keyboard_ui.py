# -*- coding: utf-8 -*-
"""
ui/keyboard_ui.py - Interface console : piloter NAO au clavier.

Elle ne contient aucune logique robot : chaque touche appelle une méthode du
contrôleur et affiche le message (ok, message) qu'il renvoie. La danse tourne
dans un thread du contrôleur, donc on peut taper "3" (Arrêter) pendant qu'elle
se déroule. Appuyer sur Entrée sans rien taper rafraîchit l'état.

Les textes affichés sont en anglais (vus par l'opérateur et les joueurs) et
sans caractères spéciaux : la console Windows de Python 2 les afficherait mal.
"""
from __future__ import absolute_import, print_function

import sys

from compat import input_text

MENU = """
=============== JUST NAO ===============
  1) Choose a choreography
  2) Start the dance
  3) Stop the dance
  4) Robot status
  5) Wake up (stand)      6) Rest
  s) Skip NAO's comment
  m) Show this menu       q) Quit
  (Enter alone: refresh the status)
========================================"""


def _mmss(seconds):
    seconds = int(seconds)
    return "%02d:%02d" % (seconds // 60, seconds % 60)


def _header(st):
    robot = st["robot"]
    parts = ["[%s]" % st["state"], st["title"] or "(no choreography)"]
    if st["state"] in ("DANSE", "ARRET") and st["elapsed"]:
        parts.append("%s / %s" % (_mmss(st["elapsed"]), _mmss(st["duration"])))
    if robot.get("battery") is not None:
        parts.append("battery %d%%" % robot["battery"])
    if robot.get("posture"):
        parts.append("posture %s" % robot["posture"])
    if robot.get("connected") is False:
        parts.append("CONNECTION LOST")
    if st.get("speaking"):
        parts.append("NAO is talking (s = skip)")
    return " | ".join(parts)


def _show(result):
    ok, message = result
    print(("  OK : " if ok else "  !! : ") + message)


def _choose(ctrl):
    items = ctrl.choreographies()
    print("\n--- Choreographies ---")
    for i, (cid, title, duration, _description) in enumerate(items, 1):
        print("  %d) %-32s %s   [%s]" % (i, title, _mmss(duration), cid))
    print("  0) Back to the main menu")
    choice = input_text("Number > ").strip()
    if choice in ("", "0"):
        return
    if choice.isdigit() and 1 <= int(choice) <= len(items):
        _show(ctrl.select(items[int(choice) - 1][0]))
    else:
        print("  !! : invalid choice")


def _details(ctrl):
    st = ctrl.status()
    robot = st["robot"]
    print("\n--- Status ---")
    print("  Application  : %s (%s)" % (st["state"], st["message"]))
    print("  Choreography : %s" % (st["title"] or "-"))
    for label, key, fmt in (("Robot", "robot", "%s"), ("API", "backend", "%s"),
                            ("Connected", "connected", "%s"), ("Motors on", "awake", "%s"),
                            ("Posture", "posture", "%s"), ("Battery", "battery", "%s %%"),
                            ("Max temp.", "temperature", "%.0f C")):
        value = robot.get(key)
        print("  %-13s: %s" % (label, fmt % value if value is not None else "unknown"))


def _print_log(line):
    # Une seule écriture par ligne : plusieurs threads journalisent en même temps,
    # print() en Python 2 écrirait le texte et le saut de ligne séparément.
    sys.stdout.write("  | " + line + "\n")
    sys.stdout.flush()


def run(ctrl):
    ctrl.on_log = _print_log
    actions = {
        "2": ctrl.start, "3": ctrl.stop, "5": ctrl.wake, "6": ctrl.rest, "s": ctrl.skip_commentary,
    }
    print(MENU)
    while True:
        print("\n" + _header(ctrl.status()))
        try:
            choice = input_text("Choice > ").strip().lower()
        except EOFError:      # entrée standard fermée (ex. script de test)
            break
        if choice == "q":
            break
        elif choice == "1":
            _choose(ctrl)
        elif choice in actions:
            _show(actions[choice]())
        elif choice == "4":
            _details(ctrl)
        elif choice in ("m", "?"):
            print(MENU)
        elif choice == "f" and hasattr(ctrl.robot, "simulate_fall"):
            ctrl.robot.simulate_fall()            # test de la gestion de chute (mode --fake)
        elif choice:
            print("  !! : unknown key (m for the menu)")
    ctrl.on_log = None
