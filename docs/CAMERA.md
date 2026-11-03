# Guide caméra et détection de pose

## 1. Installer la détection (une fois)

Dans PowerShell, depuis le dossier du projet :

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tools\download_model.py
```

- **MediaPipe** s'installe avec ses dépendances, dont `numpy` et OpenCV (`cv2`).
- **Modèle de pose** : `tools\download_model.py` télécharge le modèle « full »
  (environ 9 Mo) dans `models\`.
- **Sans Internet** : le script affiche l'URL du modèle. On peut la télécharger
  sur un autre PC et copier le fichier dans `models\pose_landmarker_full.task`.

Variantes du modèle :
- `--variante lite` : plus rapide, pour un PC lent ;
- `--variante heavy` : plus précis, mais lent sans carte graphique.

Pour utiliser une variante, modifier `POSE_MODEL_PATH` dans `config.py`.

**Version de MediaPipe.** L'ancienne API `mediapipe.solutions` a été supprimée
à partir de MediaPipe 0.10.30. Le projet utilise l'API actuelle, **Tasks**
(`PoseLandmarker`). Ne pas réinstaller une vieille version de MediaPipe pour
retrouver `solutions`.

---

## 2. Choisir la webcam

| Source | Commande |
|---|---|
| première webcam | `--video 0` (défaut) |
| webcam externe | `--video 1` (ou 2...) |
| flux réseau | `--video http://localhost:8080/stream.mjpg` |
| fichier vidéo de test | `--video C:\chemin\danse.mp4` |
| sans vidéo | `--video aucune` |
| sans caméra, joueur simulé | `--joueur-simule` |

La source se change aussi dans **Paramètres**. Elle est enregistrée dans
`results\settings.json` et appliquée immédiatement.

Sous Windows, une webcam numérotée est ouverte avec DirectShow (démarrage
rapide). Si elle échoue, le pilote par défaut prend le relais automatiquement.

---

## 3. Bien placer le joueur

- **Distance** : 2 à 3 m, corps entier visible. Au minimum, épaules, coudes,
  poignets et hanches doivent être dans l'image.
- **Éclairage** : lumière de face ou latérale, pas de fenêtre derrière le joueur.
- **Placement** : la caméra à hauteur de poitrine, le joueur face à elle.
- **Une seule personne dans le champ.** Le modèle suit un seul joueur.

L'écran **Préparation** vérifie en direct :
- que le robot est connecté ;
- que la caméra est active ;
- que la détection fonctionne ;
- que le joueur est entièrement visible.

La pastille verte en haut à gauche de la vidéo indique un joueur bien détecté.

---

## 4. Autoriser la caméra (Windows 10/11)

Paramètres Windows → **Confidentialité et sécurité** → **Caméra** :
- activer « Accès à la caméra » ;
- activer « Autoriser les applications de bureau à accéder à votre caméra ».

Fermer les autres applications qui utilisent la webcam (Teams, Zoom, le navigateur...) :
une webcam ne peut être ouverte que par un programme à la fois.

---

## 5. Problèmes courants

| Symptôme | Cause probable | Solution |
|---|---|---|
| « Camera 0 unavailable » | webcam utilisée ailleurs, débranchée ou interdite | fermer Teams/Zoom ; vérifier l'autorisation Windows ; essayer `--video 1` ou Settings > Camera ; bouton « Retry camera » |
| « Pose model missing » | modèle non téléchargé | `tools\download_model.py` |
| « MediaPipe absent » | dépendances non installées dans le `.venv` | `pip install -r requirements.txt` avec **le Python du .venv** |
| `import cv2` échoue, ou erreur de DLL OpenCV | deux paquets OpenCV installés (`opencv-python` et `opencv-contrib-python`) | `pip uninstall -y opencv-python opencv-contrib-python` puis `pip install -r requirements.txt` |
| « Step back so I can see your whole upper body! » permanent | trop près de la caméra | reculer : épaules, coudes et poignets visibles |
| squelette qui tremble | éclairage faible | plus de lumière ; baisser `FILTER_MIN_CUTOFF` pour lisser davantage |
| squelette en retard sur les gestes | PC lent | modèle `lite`, ou `VISION_MAX_FPS = 15` |
| gauche et droite inversées dans la note | convention d'imitation | Paramètres → Imitation (auto par défaut) |
| vidéo noire mais caméra « on » | webcam virtuelle sélectionnée | essayer une autre source (`--video 1`) |

---

## 6. Brancher la vision d'une autre équipe

Un flux MJPEG annoté suffit pour **afficher** la vidéo (`--video URL`), mais pas
pour **noter** : il faut les coordonnées des articulations.

Tout détecteur qui fournit la méthode
`detect(image_bgr, t) -> PoseSample ou None` peut remplacer MediaPipe
(voir `vision/pose_detector.py`). Le `PoseSample` contient :
- les 13 points principaux, en coordonnées normalisées et avec une visibilité ;
- et, si possible, leurs coordonnées 3D en mètres.

Les noms des points et leur format sont décrits dans `vision/pose_features.py`.
