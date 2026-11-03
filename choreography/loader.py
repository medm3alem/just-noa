# -*- coding: utf-8 -*-
"""
choreography/loader.py - Découvre les chorégraphies du dossier library/.

Chaque sous-dossier contenant meta.json + motion.json devient une
chorégraphie. Les dossiers qui commencent par "_" (comme _modele) sont
ignorés. Un dossier mal formé est signalé puis ignoré : une erreur dans
une danse ne bloque pas les autres.
"""
from __future__ import absolute_import, print_function

import os
from collections import OrderedDict

from choreography.choreography import Choreography, ChoreographyError


def load_library(library_dir, log=print):
    library = OrderedDict()
    if not os.path.isdir(library_dir):
        log("[ERREUR] Dossier de choregraphies introuvable : %s" % library_dir)
        return library
    for name in sorted(os.listdir(library_dir)):
        folder = os.path.join(library_dir, name)
        if not os.path.isdir(folder) or name.startswith((".", "_")):
            continue
        try:
            library[name] = Choreography(folder)
        except ChoreographyError as err:
            log("[IGNOREE] %s : %s" % (name, err))
    log("[OK] %d choregraphie(s) chargee(s) : %s" % (len(library), ", ".join(library) or "-"))
    return library
