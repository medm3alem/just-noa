# -*- coding: utf-8 -*-
"""
check_nao.py - Just Nao, etape 1 : diagnostic de connexion au robot NAO.

Compatible Python 2.7 + SDK Python NAOqi (pynaoqi).

Exemples :
    python check_nao.py --ip 192.168.1.12            # lecture seule, aucun mouvement
    python check_nao.py --ip 192.168.1.12 --move     # + test reveil / posture / repos
    python check_nao.py --ip 127.0.0.1 --port 50123  # robot virtuel de Choregraphe

Note : les messages affichés sont volontairement sans accents. En Python 2, les
chaînes littérales sont des octets ; la console Windows les afficherait mal.
Les commentaires, eux, peuvent garder leurs accents grâce à la ligne "coding" ci-dessus.
"""
from __future__ import print_function

import argparse
import platform
import sys

# Le module 'qi' est fourni par le SDK Python NAOqi. S'il manque, inutile d'aller plus loin.
try:
    import qi
except ImportError:
    print("[ERREUR] Module 'qi' introuvable.")
    print("  -> Le SDK Python NAOqi (pynaoqi) n'est pas installe, ou son dossier")
    print("     n'est pas dans PYTHONPATH. Verifie aussi que tu lances bien Python 2.7.")
    sys.exit(1)


# Services NAOqi dont le projet aura besoin. On vérifie leur présence un par un.
SERVICES = [
    "ALSystem", "ALMemory", "ALMotion", "ALRobotPosture", "ALAudioPlayer",
    "ALBehaviorManager", "ALAutonomousLife", "ALTextToSpeech", "ALBattery",
]


def connecter(ip, port):
    """Ouvre une session qi vers NAOqi. Quitte proprement si le robot est injoignable."""
    session = qi.Session()
    url = "tcp://{}:{}".format(ip, port)
    try:
        session.connect(url)
    except RuntimeError as err:
        print("[ERREUR] Connexion impossible a {} : {}".format(url, err))
        print("  -> Appuie une fois sur le bouton du torse : NAO annonce son IP.")
        print("  -> Verifie que le PC et le robot sont sur le meme reseau.")
        sys.exit(1)
    print("[OK] Connecte a {}".format(url))
    return session


def recuperer_services(session):
    """Retourne un dict {nom: proxy ou None}. Un service absent n'est pas fatal ici."""
    services = {}
    for nom in SERVICES:
        try:
            services[nom] = session.service(nom)   # proxy réseau vers le service du robot
            etat = "present"
        except RuntimeError:
            services[nom] = None
            etat = "ABSENT"
        print("  {:<20} {}".format(nom, etat))
    return services


def lire(services, nom_service, methode, description, *args):
    """
    Appelle services[nom_service].methode(*args) et affiche le résultat.
    getattr() fonctionne parce qu'un proxy qi découvre ses méthodes à l'exécution :
    elles ne sont pas écrites dans le SDK, elles sont annoncées par le robot.
    """
    proxy = services.get(nom_service)
    if proxy is None:
        valeur = "service absent"
    else:
        try:
            valeur = getattr(proxy, methode)(*args)
        except Exception as err:   # robot virtuel ou version ancienne : appel indisponible
            valeur = "indisponible ({})".format(err)
    print("  {:<28} {}".format(description, valeur))


def afficher_infos(services):
    print("\n== Robot ==")
    lire(services, "ALSystem", "robotName", "Nom du robot")
    lire(services, "ALSystem", "systemVersion", "Version NAOqi")
    lire(services, "ALMemory", "getData", "Version du corps", "RobotConfig/Body/BaseVersion")
    lire(services, "ALBattery", "getBatteryCharge", "Batterie (%)")
    lire(services, "ALMotion", "robotIsWakeUp", "Moteurs actifs (wakeUp)")
    lire(services, "ALRobotPosture", "getPosture", "Posture actuelle")
    lire(services, "ALAutonomousLife", "getState", "Etat Autonomous Life")

    # Les behaviors déjà installés : utile pour savoir si une danse existe déjà sur le robot.
    print("\n== Behaviors installes ==")
    bm = services.get("ALBehaviorManager")
    if bm is None:
        print("  service absent")
        return
    try:
        behaviors = sorted(bm.getInstalledBehaviors())
    except Exception as err:
        print("  indisponible ({})".format(err))
        return
    print("  {} behavior(s) installe(s)".format(len(behaviors)))
    for nom in behaviors[:15]:
        print("   - {}".format(nom))
    if len(behaviors) > 15:
        print("   ...")


def test_mouvement(services):
    """Cycle de vie sûr d'une séance : réveil -> posture de référence -> repos."""
    motion = services.get("ALMotion")
    posture = services.get("ALRobotPosture")
    if motion is None or posture is None:
        print("[SKIP] ALMotion ou ALRobotPosture absent : test de mouvement impossible.")
        return

    print("\n== Test de mouvement ==")
    print("NAO va se lever. Il doit etre au sol, sur une surface plane, 1 m degage autour.")
    raw_input("Entree pour continuer, Ctrl+C pour annuler... ")   # rien n'a encore bougé

    motion.wakeUp()   # active les moteurs (stiffness) ; bloquant jusqu'à la fin du réveil
    try:
        ok = posture.goToPosture("StandInit", 0.5)   # posture debout de référence, 50 % vitesse max
        print("  StandInit atteinte : {}".format(ok))
        tts = services.get("ALTextToSpeech")
        if tts is not None:
            tts.say("Hello, I am ready to dance.")
        raw_input("Entree pour remettre NAO au repos... ")
    finally:
        # Quoi qu'il arrive après le réveil (Ctrl+C, exception), on remet le robot au repos :
        # accroupi, moteurs relâchés. Même règle dans tout le projet.
        motion.rest()
    print("[OK] Test de mouvement termine.")


def main():
    parser = argparse.ArgumentParser(description="Diagnostic de connexion NAO (Just Nao)")
    parser.add_argument("--ip", required=True,
                        help="IP du robot, ou 127.0.0.1 pour le robot virtuel de Choregraphe")
    parser.add_argument("--port", type=int, default=9559,
                        help="port NAOqi (9559 sur un vrai robot)")
    parser.add_argument("--move", action="store_true",
                        help="tester wakeUp / StandInit / rest (le robot bouge)")
    args = parser.parse_args()

    print("Python {} ({})".format(platform.python_version(), platform.architecture()[0]))
    if sys.version_info[0] != 2:
        print("[ATTENTION] Ce script est prevu pour Python 2.7 (SDK NAOqi).")

    session = connecter(args.ip, args.port)
    print("\n== Services ==")
    services = recuperer_services(session)
    afficher_infos(services)

    if args.move:
        test_mouvement(services)
    else:
        print("\n(Aucun mouvement. Relance avec --move pour tester wakeUp / StandInit / rest.)")


if __name__ == "__main__":
    main()
