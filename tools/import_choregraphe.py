# -*- coding: utf-8 -*-
"""
tools/import_choregraphe.py - Convertit un export Python de Choregraphe en motion.json.

Dans Choregraphe :
  1. ouvrir la Timeline de la danse, sélectionner toutes les keyframes ;
  2. clic droit > "Export motion to clipboard" > Python > Bezier (ou simplified) ;
  3. coller le presse-papiers dans un fichier texte, par ex. ymca_export.py.

Puis :
  python tools/import_choregraphe.py ymca_export.py choreography/library/ymca/motion.json
  python tools/import_choregraphe.py ymca_export.py .../motion.json --decalage 2.3

--decalage décale toutes les keyframes (en s) : utile si la danse a été créée
à partir de 0 alors que le premier temps fort de la musique tombe à 2,3 s.

Le fichier exporté n'est JAMAIS exécuté : on lit seulement les lignes
names.append(...), times.append(...), keys.append(...) avec ast.literal_eval,
qui n'accepte que des valeurs littérales (nombres, listes, chaînes). Le bloc
"try: ... ALProxy(...)" ajouté par Choregraphe en fin d'export est ignoré.
"""
from __future__ import print_function

import argparse
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, os.pardir)))
from choreography.choreography import save_motion  # noqa: E402

APPEND = re.compile(r"\b(names|times|keys)\.append\(")


def extract_appends(source):
    """Liste ordonnée des (variable, valeur) trouvés dans le texte exporté."""
    found = []
    for match in APPEND.finditer(source):
        start = i = match.end()
        depth = 1                       # on cherche la parenthèse fermante associée
        while i < len(source) and depth:
            if source[i] == "(":
                depth += 1
            elif source[i] == ")":
                depth -= 1
            i += 1
        if depth:
            raise ValueError("parenthese non fermee apres %s.append" % match.group(1))
        found.append((match.group(1), ast.literal_eval(source[start:i - 1].strip())))
    return found


def shift_times(times, shift):
    return [[round(t + shift, 4) for t in joint] for joint in times]


def main():
    parser = argparse.ArgumentParser(description="Export Choregraphe -> motion.json")
    parser.add_argument("export", help="fichier texte colle depuis Choregraphe")
    parser.add_argument("sortie", help="chemin du motion.json a ecrire")
    parser.add_argument("--decalage", type=float, default=0.0,
                        help="secondes ajoutees a toutes les keyframes")
    args = parser.parse_args()

    with open(args.export) as f:
        found = extract_appends(f.read())
    data = {"names": [], "times": [], "keys": []}
    for var, value in found:
        data[var].append(value)
    names, times, keys = data["names"], data["times"], data["keys"]

    if not names:
        sys.exit("[ERREUR] Aucun names.append(...) trouve : est-ce bien un export Choregraphe ?")
    if not (len(names) == len(times) == len(keys)):
        sys.exit("[ERREUR] %d names / %d times / %d keys : export incomplet ?"
                 % (len(names), len(times), len(keys)))
    if args.decalage:
        times = shift_times(times, args.decalage)
    if min(t[0] for t in times) <= 0:
        sys.exit("[ERREUR] Un instant est <= 0 : augmenter --decalage.")

    folder = os.path.dirname(os.path.abspath(args.sortie))
    if not os.path.isdir(folder):
        os.makedirs(folder)
    save_motion(args.sortie, names, times, keys)

    bezier = isinstance(keys[0][0], list)
    print("[OK] %s : %d articulations, %d keyframes, %.2f s -> %.2f s, format %s"
          % (args.sortie, len(names), sum(len(t) for t in times),
             min(t[0] for t in times), max(t[-1] for t in times),
             "Bezier" if bezier else "simple"))
    print("     Articulations : %s" % ", ".join(names))
    print("     Verifier ensuite : python main.py --fake --valider")


if __name__ == "__main__":
    main()
