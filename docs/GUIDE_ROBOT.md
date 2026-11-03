# Guide robot et chorégraphies (Just Nao)

> **Robot physique avec le jeu : utiliser la passerelle Choregraphe v3**
> (`main.py --choregraphe`, Python 3.12) décrite dans docs/CHOREGRAPHE.md et
> docs/AUDIO_MACARENA.md. Ce guide décrit le mode NAOqi direct (SDK Python 2.7,
> sans jeu) et le format des chorégraphies, toujours valables. Les textes vus
> par le joueur sont désormais en anglais (Wake up, Rest, Dance, Stop...).

> Partie "robot" de la documentation : installation du SDK NAOqi, format des
> chorégraphies, Choregraphe, musique, synchronisation, sécurité. Le jeu
> interactif (vision, score, bilans) est décrit dans le README principal et
> dans docs/EVALUATION.md.

NAO exécute une chorégraphie synchronisée avec une musique ; l'utilisateur la reproduit.
Pilotage au clavier ou par une interface graphique (HMI) qui affiche aussi le flux vidéo
de l'utilisateur (webcam, puis flux annoté du groupe 2).

Équipe : Med (robot et synchronisation), Ram (chorégraphies), Armin (interfaces).

**Matériel de l'équipe** (relevé le 1er novembre 2026)

| Élément | Version |
|---|---|
| Robot | NAO, nom `nao` ; NAO V6 d'après la version de NAOqi (à confirmer : ligne « Version du corps » de `check_nao.py`) |
| NAOqi (sur le robot) | 2.8.7.4 |
| Choregraphe | 2.8.7.4 |
| SDK Python | pynaoqi 2.8.7, Python 2.7 64 bits (Windows) |

Conséquences pour le code : l'API `qi.Session` est disponible (connexion principale), la
détection de chute par évènement fonctionne, le port NAOqi est 9559.

---

## 1. Démarrage rapide

Toutes les commandes se lancent depuis le dossier `just_nao/`.

| Commande | Ce qu'elle fait |
|---|---|
| `python main.py --fake` | Sans robot ni SDK : tout est simulé, interface clavier |
| `python main.py --fake --ui hmi` | Sans robot, interface graphique |
| `python main.py --ip 127.0.0.1 --port <port>` | Robot virtuel de Choregraphe (mouvements visibles en 3D) |
| `python main.py --ip <IP du robot>` | Vrai robot, interface clavier |
| `python main.py --ip <IP du robot> --ui hmi` | Vrai robot, interface graphique |
| `python main.py --fake --valider` | Vérifie toutes les chorégraphies (butées, vitesses), puis quitte |
| `python tools/check_nao.py --ip <IP>` | Diagnostic : version NAOqi, services, batterie |

Options utiles : `--video 0` (webcam n°0), `--video http://localhost:8080/stream.mjpg`
(flux du groupe 2), `--video aucune`.

L'IP du robot : appuyer une fois sur le bouton du torse, NAO l'annonce.

---

## 2. Installation

**Pour le vrai robot (obligatoire)**, sur chaque PC de l'équipe :
1. Python **2.7 64 bits** : le SDK NAOqi 2.8 pour Windows est en 64 bits
   (`pynaoqi-python2.7-2.8.x-win64-vs2015-...zip`), Python doit avoir la même architecture.
2. Extraire le SDK pynaoqi 2.8.7, puis ajouter son dossier `lib` à la variable
   d'environnement `PYTHONPATH`. Si Choregraphe n'est pas installé sur ce PC, installer
   aussi le redistribuable Visual C++ demandé par le guide d'installation du SDK.
3. Vérifier : `python -c "import qi"` puis `python tools/check_nao.py --ip <IP>`.
   Ligne « Python » du script : elle doit indiquer `64bit`.

**Pour la vidéo dans la HMI (facultatif)**

    pip install numpy==1.16.6 opencv-python==4.2.0.32 Pillow==6.2.2

Ce sont les dernières versions compatibles Python 2.7 ; testé avec OpenCV 4.2 et Pillow 6.2.
Si pip ne trouve pas de version pour votre Python, le panneau vidéo affiche un message et
tout le reste fonctionne.

**Pour développer sans SDK** : le mode `--fake` tourne aussi en Python 3 (HMI comprise).

---

## 3. Ton test Choregraphe, devenu le projet

Le test qui a marché sur le robot est la chorégraphie `nao_party`. Chaque morceau du code
d'origine a trouvé sa place :

| Dans la boîte Choregraphe | Dans le projet | Pourquoi |
|---|---|---|
| `ALProxy("ALMotion")` sans IP (code exécuté sur le robot) | `robot/nao_robot.py` : session `tcp://IP:9559` | Le programme tourne sur le PC et parle au robot par le réseau |
| Listes `joints` et `poses` | `library/nao_party/motion.json` | Une danse = des données, pas du code |
| `lyrics`, `colors`, `fadeRGB` | Évènements `say` / `leds` de `meta.json` | Datés sur une timeline au lieu de suivre la durée de la parole |
| `wakeUp`, `goToPosture("StandInit", 0.5)` | `app/controller.py` (avant et après chaque danse) | Même règle de sécurité pour toutes les danses |
| `tts.post.say` + `angleInterpolation` en parallèle | `sync/player.py` : un thread par activité, départ commun | Indispensable pour caler une musique |
| `self.running = False` dans `onInput_onStop` | `ctrl.stop()` → `killTasksUsingResources`, `audio.stop`, `tts.stopAll` | Arrêt immédiat, pas seulement à la fin de la pose en cours |
| `try / except / finally: onStopped()` | `try / finally` + `shutdown()` qui remet NAO au repos | Même idée, étendue à tout le programme |

Différence de timing à connaître : dans le test, chaque pose attendait la fin de la phrase
(`tts.wait`). Ici tout est daté (pose atteinte en 0,8 s, tenue jusqu'à 2,5 s), car une
musique n'attend pas. Avant le départ, NAO rejoint sa pose de départ, puis il dit l'intro.

---

## 4. Architecture

```
just_nao/
├── main.py                 point d'entrée : choisit FakeRobot ou NaoRobot, clavier ou HMI
├── config.py               IP, langue, vitesses, seuils, source vidéo
├── compat.py               différences Python 2 / 3, horloge précise
├── robot/
│   ├── base.py             LE CONTRAT : méthodes communes à tous les robots
│   ├── nao_robot.py        NAOqi réel ou virtuel (qi, ou ALProxy en secours)       [Med]
│   └── fake_robot.py       simulation sans robot ni SDK                              [Med]
├── choreography/
│   ├── choreography.py     lecture + vérification d'une chorégraphie               [Ram]
│   ├── loader.py           découverte des dossiers de library/                      [Ram]
│   └── library/
│       ├── _modele/        modèle à copier (ignoré car il commence par "_")
│       ├── calibration/    métronome + bras qui frappe : mesure de la synchro
│       └── nao_party/      ton test Choregraphe converti
├── sync/player.py          lecture synchronisée musique + mouvement + évènements    [Med]
├── app/controller.py       machine à états, seul point d'entrée des interfaces      [Armin]
├── ui/
│   ├── keyboard_ui.py      menu console                                              [Armin]
│   ├── hmi.py              fenêtre Tkinter (menu principal + écran de danse)         [Armin]
│   └── video_panel.py      affichage du flux vidéo (webcam ou groupe 2)              [Armin]
└── tools/
    ├── check_nao.py        diagnostic de connexion
    ├── import_choregraphe.py   export Choregraphe → motion.json                     [Ram]
    └── make_calibration.py     régénère la chorégraphie de calibration              [Med]
```

Chaque couche ne parle qu'à celle du dessous : interfaces → contrôleur → lecteur → robot.

**La machine à états du contrôleur**

```
REPOS --Danser--> PREPARATION --musique--> DANSE --fin ou Stop--> ARRET --> PRET
REPOS --Réveiller--> OCCUPE --> PRET          PRET --Repos--> OCCUPE --> REPOS
chute ou erreur --> ERREUR --Réveiller ou Repos--> PRET / REPOS
```

Le contrôleur refuse ce qui n'a pas de sens (« Danser » pendant une danse, « Repos »
pendant un réveil) et renvoie toujours `(ok, message)` : les deux interfaces affichent
le même message.

**Pourquoi des threads ?** Les appels NAOqi sont bloquants : `play()` ne rend la main
qu'à la fin de la musique. Pour lancer le son et le mouvement *en même temps*, chacun a
son thread ; pour que le bouton Stop réponde pendant une danse, la danse tourne dans un
thread « worker » et l'interface reste libre.

---

## 5. Format d'une chorégraphie

Un dossier dans `choreography/library/` :

```
ymca/
├── meta.json      description, musique, synchro, évènements
├── motion.json    keyframes (généré par tools/import_choregraphe.py)
└── ymca.wav       la musique (une copie doit aussi être sur le robot)
```

**Convention de temps** : tous les instants sont en secondes **depuis le début de la
musique**. Si le premier « Y » tombe à 4,2 s dans le morceau, sa keyframe est à 4,2 s.

**meta.json**

| Champ | Rôle | Défaut |
|---|---|---|
| `title` | Nom affiché (sans accents de préférence : console Windows) | nom du dossier |
| `description` | Une phrase affichée dans la HMI | vide |
| `audio` | Fichier musique dans le dossier (wav, mp3, ogg), ou `null` | `null` |
| `sync_offset` | Décalage mesuré en calibration (s). > 0 : le mouvement part après la musique | `0.0` |
| `countdown` | Dire « Three! Two! One! » avant le départ | `true` |
| `end` | Fin de la danse (s) : coupe une musique plus longue que la chorégraphie | dernière keyframe + 1 s |
| `events` | Liste d'évènements datés (ci-dessous) | `[]` |

Évènements :

```json
{"t": 4.2, "type": "say",  "text": "Y!"}
{"t": 4.2, "type": "leds", "color": "#FF0000", "duration": 0.1}
```

**motion.json** : le format exporté par Choregraphe, en JSON.
`names[i]` = articulation, `times[i]` = instants de ses keyframes, `keys[i]` = angles
(radians). Chaque clé est soit un angle (export « simplified »), soit
`[angle, poignée, poignée]` (export « Bezier ») ; les deux sont acceptés.

**Avant chaque danse, le programme vérifie** que chaque angle est dans les butées du
robot connecté (`ALMotion.getLimits`), que les vitesses entre keyframes restent sous la
vitesse max, et que les instants sont croissants. Une erreur bloque la danse et
s'affiche dans le journal.

---

## 6. Créer une chorégraphie avec Choregraphe (Ram)

1. Choregraphe, connecté au **robot virtuel** d'abord. Clic droit dans le diagramme →
   *Create a new box* → *Timeline*. Double-clic pour l'ouvrir.
2. Repérer dans la musique (Audacity, par exemple) l'instant du premier temps fort et le
   tempo. Un temps dure `60 / BPM` secondes ; à 25 images/s (réglage *Framerate* de la
   Timeline), la keyframe d'un instant `t` est à l'image `t × 25`.
3. Placer NAO dans la pose voulue (curseurs du panneau de mouvement, ou sur le vrai robot
   en mode animation), puis clic droit sur l'image → *Store joints in keyframe* → *Arms*
   ou *Head* (pour YMCA : **bras et tête uniquement**, jambes en StandInit).
4. Rejouer sur le robot virtuel, ajuster.
5. Sélectionner toutes les keyframes → clic droit → *Export motion to clipboard* →
   *Python* → *Bezier*. Coller dans un fichier texte, par ex. `ymca_export.py`.
6. Convertir :

       python tools/import_choregraphe.py ymca_export.py choreography/library/ymca/motion.json

   Si la Timeline commence à 0 alors que le premier temps fort de la musique est à 2,3 s,
   ajouter `--decalage 2.3`. Le fichier exporté n'est jamais exécuté : l'outil lit
   seulement les lignes `names/times/keys.append(...)`.
7. Copier `_modele/meta.json` dans `ymca/`, le compléter, ajouter `ymca.wav`.
8. `python main.py --fake --valider`, puis robot virtuel, puis vrai robot.

Pistes pour YMCA : **Y** bras levés en V ; **M** mains au-dessus de la tête (garder de
la marge pour ne pas toucher la tête) ; **C** bras en arc d'un côté ; **A** mains jointes
au-dessus de la tête. Garder des vitesses modérées : le validateur prévient au-delà de
60 % de la vitesse max d'un moteur.

---

## 7. Musique sur le robot

`ALAudioPlayer` lit les fichiers **sur le robot**. On copie donc chaque musique une fois
(identifiant `nao`, mot de passe `nao` par défaut, souvent changé par l'école) :

    ssh nao@<IP> "mkdir -p /home/nao/just_nao/audio"
    scp choreography/library/ymca/ymca.wav nao@<IP>:/home/nao/just_nao/audio/
    scp choreography/library/calibration/click.wav nao@<IP>:/home/nao/just_nao/audio/

`ssh` et `scp` sont inclus dans Windows 10 et 11 (sinon WinSCP). Le même fichier reste
aussi dans le dossier de la chorégraphie sur le PC (vérification, mode `--fake`).
Si le fichier manque sur le robot, le message d'erreur donne la commande `scp` exacte.

---

## 8. Synchronisation et calibration (Med)

**Principe.** La musique est préchargée sur le robot (`loadFile`), NAO rejoint sa pose de
départ, puis trois threads partent au même instant : musique, mouvement, évènements. Le son
et le mouvement s'exécutent tous deux sur le robot avec la même horloge : une fois partis
ensemble, ils ne dérivent pas. Seul le départ traverse le réseau ; son petit décalage se
mesure une fois et se corrige avec `sync_offset`.

**Mesurer `sync_offset`**
1. Copier `click.wav` sur le robot (section 7).
2. Lancer la chorégraphie *Calibration synchro* : le bras droit doit être au plus bas à
   chaque clic, et les yeux flashent sur chaque clic.
3. Filmer NAO de profil avec un téléphone posé près de lui (ralenti si possible).
4. Image par image (VLC : touche `E`), mesurer `d = instant du bras au plus bas − instant
   du clic`. Positif si le bras est en retard.
5. Nouveau `sync_offset` = ancien − `d`. Exemple : bras en retard de 80 ms →
   `"sync_offset": -0.08` (la musique est alors retardée de 80 ms).
6. Reporter la valeur dans le `meta.json` de chaque chorégraphie (elle dépend du robot et
   du réseau, pas de la danse). Viser moins de 40 ms d'écart.

Pour régénérer la calibration à un autre tempo : `python tools/make_calibration.py --bpm 120`.

---

## 9. Sécurité

Ce que fait le programme :
- vérifie butées et vitesses avant toute danse ;
- passe en StandInit (50 % de la vitesse) avant et après chaque danse ;
- rejoint la pose de départ en 1,5 s au lieu de « sauter » dessus ;
- désactive Autonomous Life (sinon NAO bouge la tête tout seul) ;
- s'abonne à l'évènement de chute `robotHasFallen` : tout s'arrête, état ERREUR ;
- surveille batterie et température des moteurs (alertes dans le journal) ;
- quoi qu'il arrive en quittant (fermeture, Ctrl+C, erreur) : arrêt et repos.

Ce que fait l'équipe :
- jamais seul avec le robot réel quand il bouge : l'un lance, l'autre est prêt à le rattraper ;
- NAO au sol, sur une surface plane, 1 m dégagé autour ;
- toute nouvelle danse passe par `--valider`, puis le robot virtuel, puis le vrai robot ;
- ne jamais désactiver le réflexe de chute de NAO (*fall manager*) ;
- après une danse longue, laisser NAO au repos (moteurs des jambes).

---

## 10. Tester sans robot

| Niveau | Commande | Ce qu'on vérifie |
|---|---|---|
| Simulation | `--fake` | Logique, interfaces, arrêt, timing (touche `f` : chute simulée) |
| Validation | `--fake --valider` | Butées et vitesses de toutes les chorégraphies |
| Robot virtuel | `--ip 127.0.0.1 --port <port>` | Mouvements en 3D (pas de son, pas de batterie : normal) |
| Vrai robot | `--ip <IP>` | Tout, avec une personne prête à rattraper NAO |

Le port du robot virtuel s'affiche dans Choregraphe (fenêtre de connexion ou préférences).

---

## 11. Vidéo : contrat avec le groupe 2 (Armin)

Proposition à valider avec eux :
- leur programme capture la webcam, applique la détection et **republie** l'image
  annotée en MJPEG sur HTTP, par ex. `http://localhost:8080/stream.mjpg`, 640×480, ~25 i/s ;
- notre HMI l'affiche avec `--video http://localhost:8080/stream.mjpg`
  (ou `VIDEO_SOURCE` dans `config.py`).

Point important : une webcam ne peut être ouverte que par un seul programme. Si leur IA
utilise la webcam, notre HMI doit afficher leur flux, pas la webcam directement.
En attendant, `--video 0` affiche la webcam du PC pour tester.

---

## 12. Prochaines tâches

**Med**
- Lancer `tools/check_nao.py` sur le robot : noter la version de NAOqi.
- Copier `click.wav` sur le robot, mesurer `sync_offset` (section 8).
- Vérifier sur le vrai robot que la musique et le bras partent bien ensemble, et que
  Stop coupe tout immédiatement.

**Ram**
- Créer YMCA dans Choregraphe, l'importer, la valider (section 6).
- Ajouter une 2e chorégraphie sans modifier le code (preuve de modularité).

**Armin**
- Fixer le format vidéo avec le groupe 2 (section 11), tester avec `--video 0`.
- Améliorer la HMI (écran d'état détaillé, ergonomie) sans toucher au contrôleur.

**Ensemble** : procédure de démo et checklist sécurité.

---

## 13. Dépannage

| Message | Cause probable |
|---|---|
| `Ni 'qi' ni 'naoqi' importables` | SDK absent du `PYTHONPATH`, ou Python 3 au lieu de 2.7 |
| `DLL load failed` à l'import de `qi` | Python 32 bits avec le SDK 64 bits, ou runtime Visual C++ manquant |
| `Connexion impossible a tcp://...` | Mauvaise IP, ou PC et robot sur des réseaux différents |
| `Musique introuvable sur le robot` | Fichier pas copié : lancer la commande `scp` affichée |
| `... refusee : n erreur(s)` | Angle hors butées ou vitesse trop élevée : détail dans le journal |
| `Service ... absent` | Normal sur le robot virtuel (audio, batterie) |
| `Detection de chute indisponible` | Connexion en ALProxy (ancien SDK) : le réflexe de NAO reste actif |
| Vidéo « indisponible » | `opencv-python` et `Pillow` non installés (section 2) |
| Accents bizarres dans la console | Normal en Python 2 sous Windows : les messages console sont sans accents |
