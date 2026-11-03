# Évaluation du joueur : comment le score est calculé

Ce document explique, de bout en bout, comment Just Nao passe de « NAO bouge
ses moteurs » et « une webcam filme le joueur » à un score défendable.
Chaque réglage cité se trouve dans `config.py`.

---

## 1. Vue d'ensemble

```
motion.json ──> pose de NAO à l'instant t ──> directions des bras de NAO
                (choreography/reference_pose.py)  (evaluation/pose_mapping.py)
                                                           │  miroir ou même côté
                                                           v
webcam ──> MediaPipe ──> lissage ──> directions des bras du joueur ──> comparaison
           (vision/)      One Euro    (vision/pose_features.py)       (evaluation/comparator.py)
                                                                           │
            tolérance temporelle, activité, agrégation  <──────────────────┘
            (evaluation/scoring.py)  ──>  score en direct, bilan, conseils
```

---

## 2. La pose de référence (ce que fait NAO)

`ReferenceTimeline.pose_at(t)` reconstruit les angles de NAO à n'importe quel
instant à partir des **vraies** keyframes de `motion.json` :

| Format des clés | Interpolation utilisée |
|---|---|
| simple (un angle par keyframe) | cubique monotone (Fritsch-Carlson) : passe par chaque keyframe, vitesse nulle sur les paliers, jamais de dépassement, comme l'interpolation lissée de NAOqi |
| Bezier (export Choregraphe) | vraie courbe de Bézier avec les poignées exportées |

- Avant la première keyframe, la valeur est celle de cette keyframe : le
  lecteur y place NAO avant le départ.
- Les articulations que la danse ne pilote pas gardent la posture StandInit
  (`REFERENCE_DEFAULT_POSE`, **valeurs approximatives**).

**Ordre des poignées Bezier.** La doc ALMotion annonce `[type, dAngle, dTime]`.
Les exports Choregraphe ont pourtant la forme `[3, -0.33, 0]`, temps d'abord.
Le code détecte l'ordre automatiquement, car la composante « temps » est
négative pour la poignée gauche et positive pour la droite.

---

## 3. La représentation commune

Comparer un angle NAOqi à un point MediaPipe n'aurait aucun sens : les axes,
les signes et les amplitudes diffèrent. On décrit donc la pose de NAO comme
celle du joueur avec les mêmes grandeurs.

| Caractéristique | Définition | Côté NAO | Côté joueur |
|---|---|---|---|
| `X_upper` | direction épaule → coude (vecteur unitaire 3D) | cinématique directe | points MediaPipe |
| `X_fore` | direction coude → poignet | cinématique directe | points MediaPipe |
| `X_knee` | flexion du genou au-delà de la position debout (°) | `KneePitch` − 0,70 rad | 180° − angle hanche-genou-cheville − 8° |

Ces grandeurs sont exprimées dans le **repère du corps** : x devant soi, y vers sa gauche, z vers le haut.

**Cinématique directe de NAO** (rotations successives de la chaîne du bras) :

```
bras       = Ry(ShoulderPitch) · Rz(ShoulderRoll) · x
avant-bras = Ry(ShoulderPitch) · Rz(ShoulderRoll) · Rx(ElbowYaw) · Rz(ElbowRoll) · x
```

Les tests le vérifient : ShoulderPitch = +90° donne un bras vers le bas, −90°
un bras vers le haut, LShoulderRoll = +90° un bras gauche horizontal vers la
gauche. En StandInit, les avant-bras pointent vers l'avant.

**Repère du joueur.** Il est reconstruit à partir de ses propres points :
- gauche = épaule gauche − épaule droite ;
- haut = milieu des épaules − milieu des hanches, rendu perpendiculaire (si les hanches sont hors champ, on prend la verticale de la caméra) ;
- devant = gauche ∧ haut.

Ces directions sont unitaires : le résultat ne dépend **ni de la taille du
joueur, ni de sa distance, ni de sa position dans l'image, ni d'une rotation
du corps** (testé jusqu'à 25° et ±25 % de taille).

**Le miroir.** La détection travaille toujours sur l'image **non inversée** :
« gauche » désigne la gauche anatomique du joueur. Seul l'affichage est en
miroir, avec un squelette dessiné aux coordonnées inversées.

---

## 4. NAO ↔ joueur : miroir ou même côté

| Mode (`MAPPING_MODE`) | Correspondance |
|---|---|
| `miroir` | Le joueur imite NAO face à lui, comme dans un miroir : bras gauche de NAO = bras droit du joueur, axe gauche/droite inversé. |
| `meme_cote` | Bras gauche = bras gauche. |
| `auto` (défaut) | Les deux sont évalués en parallèle et le plus favorable est retenu. En direct, c'est le meilleur des dernières secondes ; dans le bilan, le meilleur sur la partie. |

Le mode `auto` évite de pénaliser un joueur qui n'a pas compris la convention.
Le choix porte sur toute la partie, jamais image par image.

**Ce qui est noté.** Seules les caractéristiques dont NAO bouge réellement les
articulations sont évaluées. Un bras que la chorégraphie ne pilote pas a une
pose « robot » par défaut sans équivalent humain, il n'est donc pas noté. La
tête n'est pas évaluée.

---

## 5. Comparer une pose (instant par instant)

Pour chaque caractéristique valide, l'erreur est :
- l'angle entre la direction attendue et celle du joueur, pour un bras ou un avant-bras ;
- l'écart de flexion, pour un genou.

L'erreur devient une note :

```
note = 1                                si erreur <= pleine
note = 0                                si erreur >= nulle
note = 1 - (erreur - pleine) / (nulle - pleine)   entre les deux
```

| Type | pleine | nulle | poids dans la partie |
|---|---|---|---|
| bras (épaule → coude) | 20° | 60° | 0,6 |
| avant-bras | 25° | 70° | 0,4 |
| genou | 15° | 45° | 0,5 |

Une erreur sous le seuil « pleine » ne coûte rien, car MediaPipe et la
morphologie introduisent déjà 10 à 15° de bruit. Ensuite :
- note d'une partie (bras gauche, bras droit, jambes) = moyenne pondérée de ses caractéristiques ;
- note de la pose = moyenne pondérée des parties (`PART_WEIGHTS`, ou `"scoring": {"weights": ...}` dans le `meta.json` d'une danse).

**Données manquantes.** Un point masqué ou hors champ rend sa caractéristique
**invalide** : elle n'est pas notée, elle n'est jamais comptée comme une erreur
maximale. Si moins de la moitié du poids attendu est mesurable, la pose est
« insuffisante » : ni réussie, ni ratée.

**Mode 2D** (`EVAL_DEPTH = False`, ou fournisseur de pose sans profondeur). On
compare les directions projetées dans le plan de face. Une direction presque
dans l'axe de la caméra, comme un bras tendu vers l'avant, devient illisible :
son poids diminue, voire elle n'est pas notée.

---

## 6. Synchronisation et tolérance temporelle

**Horloge commune.** Toutes les heures viennent de la même horloge monotone
(`compat.now()`, soit `time.perf_counter`) :
- le lecteur (`sync/player.py`) note l'instant `t_origin` où musique et mouvement partent : c'est t = 0 de la chorégraphie ;
- chaque image est horodatée **à la capture**, pas à la fin de l'analyse.

L'instant de la danse vu par le joueur est :

```
tau = (t_image − CAMERA_LATENCY) − t_origin − ROBOT_LATENCY
```

- `CAMERA_LATENCY` (0,08 s) : délai entre le geste et l'arrivée de l'image.
- `ROBOT_LATENCY` (0,10 s) : délai entre l'envoi de la commande et le mouvement de NAO, passerelle Choregraphe comprise.

Les deux se règlent dans Paramètres.

**Le joueur réagit après NAO.** Sa pose à `tau` est comparée aux poses de NAO
entre `tau − 0,3 s` et `tau + 1,0 s`. Le décalage retenu est pénalisé :

```
pénalité(d) = 1                         si 0 <= d <= 0,5 s   (réagir 0,5 s après est normal ;
                                                              0,55 à 0,65 s mesurés sur les
                                                              parties Macarena réelles)
                                        ou -0,15 s <= d < 0  (petite avance tolérée)
            = 1 − 0,3 × (|d| − libre) / (bord − libre)   au-delà, jusqu'à 0,7 au bord
```

**Retard habituel.** Image par image, le meilleur décalage est ambigu : quand
NAO tient une pose, tous les décalages se valent. On cumule donc, sur
4 secondes et uniquement pendant les mouvements de NAO, la note obtenue pour
chaque décalage. Le pic de cette corrélation donne le **retard habituel** du
joueur. Chaque image est ensuite notée autour de ce retard (± `TIME_FLEX`
= 0,15 s), et non au meilleur décalage trouvé par hasard. Ainsi, un joueur
constamment en retard ne retrouve pas la note pleine pendant les poses tenues.

---

## 7. Joueur immobile : le facteur d'activité

Sur une fenêtre de 2 s, on compare l'amplitude des mouvements de NAO et celle
du joueur, chacune diminuée du tremblement normal de la détection (6° par
caractéristique) :

```
si NAO bouge (amplitude > 25°) :
    facteur = clamp( (amplitude joueur − bruit) / (0,5 × (amplitude NAO − bruit)), 0,25, 1 )
sinon : facteur = 1        (NAO tient une pose : rester immobile est juste)
note de l'image = note de la pose × pénalité temporelle × facteur
```

Un joueur figé ne peut donc pas obtenir un bon score parce que sa pose
ressemble par hasard à celle du robot.

---

## 8. Du direct au bilan

- **Score en direct** : moyenne exponentielle des notes d'image, sur environ 1 s.
- **Bilan** : la fenêtre évaluée (1 s avant la première keyframe → 0,5 s après la dernière) est découpée en intervalles de 0,5 s.

| Grandeur | Calcul |
|---|---|
| intervalle « suivi » | contient au moins une pose notée |
| performance | moyenne des intervalles suivis : qualité quand on te voit |
| taux de suivi | intervalles suivis / intervalles totaux |
| **score final** | performance × min(1, taux de suivi / 0,9) |
| poses correctes | part des intervalles suivis notés ≥ 60 |
| parties du corps | moyenne par partie sur les intervalles suivis |
| mouvements réussis | mouvements nommés de `meta.json` ("moves", écrits par tools/compose_choreographies.py : 56 pour la Macarena) ; sinon danse découpée aux keyframes (segments ≥ 1 s). Réussi si suivi à plus de 50 % et note moyenne ≥ 60. Les conseils citent les mouvements nommés les plus souvent ratés |
| retard moyen | pic de la corrélation sur toute la partie |

Un instant **non détecté** n'est jamais compté comme une erreur à 0. Il baisse
la couverture, qui pèse sur le score final (10 % de pertes tolérées). Si le
joueur est suivi moins de 40 % du temps, ou si la partie évaluée dure moins
de 5 s, elle est déclarée **« non évaluable »** : un joueur absent n'a pas de
score.

**Catégories** (`SCORE_CATEGORIES`, seuils initiaux, pas des normes scientifiques) :

| Score | Catégorie |
|---|---|
| 90–100 | Excellent |
| 75–89 | Great |
| 55–74 | Good |
| 35–54 | Needs work |
| 0–34 | Try again |

Les textes vus par le joueur sont en anglais (catégories, messages, conseils,
voix de NAO) ; une partie non notée affiche « Not scored ».

**Partie interrompue** (Stop, chute, erreur, fermeture). Elle est notée sur la
partie réellement dansée et enregistrée avec le statut `interrompue`. Elle ne
compte jamais pour le record de la chorégraphie.

---

## 9. Messages et conseils

Tous les messages sont **déduits des mesures** ; aucun encouragement n'est
tiré au hasard (les synonymes d'un même niveau tournent dans l'ordre). Ils
sont en anglais. Ordre de priorité :
1. détection : « Come back into the camera frame! » (absent), « Step back so I
   can see your whole upper body! » (moins de la moitié des points utiles
   visibles), « Move to the center of the frame! » (au bord) ;
2. « Get ready... copy NAO! » avant le début de la partie notée ;
3. « Don't stop now! » si le facteur d'activité est bas ;
4. progrès mesurés : « Great recovery! », « You're getting better! » ;
5. « Almost perfect! » / « Excellent! » / « Nice moves! » selon le score ;
6. « You're a little late! » / « Keep up with the beat! » si le retard
   dépasse `FEEDBACK_LATE` (0,55 s) ;
7. une correction ciblée sur la caractéristique la plus fausse : « Raise /
   Lower your left arm! », « Spread your right arm out! », « Bring your left
   arm in! », « Bend your right elbow! », « Straighten your left arm! »... ;
8. sinon « Keep going! ».

Un message reste affiché au moins 1,2 s, sauf les alertes de détection.

Les **conseils de fin** reposent sur les moyennes de la partie : partie du
corps la plus faible et sens de l'erreur, retard moyen, temps hors champ,
manque d'amplitude, mouvements ratés.

**Voix de NAO pendant la danse** (`VOICE_FEEDBACK`, désactivée par défaut :
la musique est forte) : au plus un « Great job! » toutes les 12 s, après 4 s
d'affilée au niveau « Excellent ». La phrase est dite dans un thread séparé,
et jamais deux à la fois.

**Commentaire de fin** (score annoncé + une pique sarcastique sur la
performance mesurée) : voir docs/PERSONALITY.md.

---

## 10. Résultats testés

`tests/test_features_scoring.py` utilise un joueur simulé, construit à partir de
la chorégraphie, avec des défauts réglables. Résultats sur « Échauffement » :

| Scénario | Score obtenu |
|---|---|
| joueur correct, 0,35 s de retard (réaction normale) | ≈ 100 (≥ 90 exigé) |
| même joueur, convention « même côté » | ≈ 100, mode détecté `meme_cote` |
| 1,2 s de retard | ≈ 74, retard mesuré ≥ 0,8 s, conseil « retard » |
| joueur immobile | ≈ 19 (< 35 exigé) |
| mouvements inversés | ≈ 44 (< 60 exigé) |
| joueur absent | non évaluable |
| bras gauche caché | bras gauche non noté, bras droit ≈ 100 |
| taille ±25 %, corps tourné de 25° | ≥ 88 |

Ces résultats valident la **logique** du score sur des données simulées. Ils
ne remplacent pas des essais avec de vrais joueurs devant la webcam (§ 11).

---

## 11. Limites connues et réglages à valider en vrai

1. **MediaPipe en conditions réelles.** La profondeur (axe caméra) est la
   composante la moins fiable. Si les bras tendus vers l'avant sont mal notés,
   passer en évaluation 2D (Paramètres) ou élargir les tolérances.
2. **Posture par défaut de NAO** (`REFERENCE_DEFAULT_POSE`) : approximative.
   C'est surtout `ElbowYaw`, rarement présent dans les chorégraphies, qui
   oriente l'avant-bras. À mesurer sur le robot si les avant-bras semblent mal
   notés.
3. **Latences** (`CAMERA_LATENCY`, `ROBOT_LATENCY`) : estimées. À mesurer avec
   la chorégraphie de calibration et une vidéo au ralenti.
4. **`nao_party`** a des poses proches les unes des autres (environ 30°) : le
   score y est peu discriminant. « Échauffement » ou YMCA conviennent mieux au
   jeu.
5. **Mouvements périodiques** (calibration à 90 BPM) : un retard d'un nombre
   entier de temps ressemble à « être en rythme ». C'est inhérent à la
   répétition, comme dans Just Dance.
6. **Tête et tronc** non évalués ; **jambes** évaluées par la flexion des
   genoux seulement, et seulement si la danse les fait bouger.
7. Un seul joueur à la fois (`num_poses = 1`).
