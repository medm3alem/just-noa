# Guide de démonstration (environ 5 minutes)

## Avant le public (10 minutes avant)

1. Brancher la webcam et poser la caméra à hauteur de poitrine, face à
   l'espace de danse (2 à 3 m dégagés).
2. Démarrer Choregraphe, le robot virtuel et la passerelle (voir le guide
   Choregraphe) ; ou allumer NAO.
3. Lancer Just Nao :
   ```powershell
   cd C:\Users\USER\Desktop\just_nao
   .\.venv\Scripts\python.exe main.py --choregraphe --ui hmi --video 0
   ```
4. Faire une partie d'essai sur « Échauffement » pour vérifier la détection et
   le son.
5. Plan B sans caméra : `--joueur-simule`, qui affiche un joueur simulé,
   clairement indiqué comme tel.

## Déroulé

| Temps | Étape | À dire / à montrer |
|---|---|---|
| 0:00 | **Menu** | Les chorégraphies, leur durée, leur niveau et le record. Le journal montre la connexion au robot. |
| 0:30 | **Réveiller** NAO | L'état passe de « Au repos » à « Prêt ». Dans Choregraphe, NAO se lève. |
| 0:50 | Sélectionner **Échauffement** → **Danser** | L'écran Préparation vérifie en direct robot, caméra, détection et joueur. Le volontaire se place : son squelette apparaît, la pastille passe au vert. |
| 1:30 | **Commencer** | Compte à rebours 3-2-1, puis NAO danse. |
| 1:40 | **Jeu** | Le score en direct, la couleur des bras (vert, orange ou rouge), les messages. Ils viennent des mesures : « Raise your left arm! », « Don't stop now! » quand on s'arrête. La silhouette « Target pose » vient directement de la chorégraphie. |
| 2:20 | Montrer la robustesse | Le volontaire sort du champ : « Come back into the camera frame! », et la note ne s'effondre pas. Il revient : l'évaluation reprend. |
| 2:40 | **Fin** | NAO annonce le score puis lance une pique sur la danse (« NAO says » à l'écran, bouton « Skip comment »). Le bilan s'affiche automatiquement : score final, catégorie, courbe (les zones rosées montrent quand il est sorti du champ), parties du corps, mouvements réussis, retard moyen, conseils. |
| 3:30 | **Exporter** | CSV et JSON dans `results\exports\`. |
| 3:45 | **Historique** | La partie est enregistrée ; double-clic pour revoir un ancien bilan. |
| 4:15 | **Stop** en pleine danse (deuxième partie courte) | NAO s'arrête aussitôt et revient en posture. La partie est enregistrée « interrompue » et ne compte pas pour le record. |
| 4:45 | **Mettre au repos** | NAO s'accroupit, moteurs relâchés. |

## Points à expliquer si on pose des questions

- **Comparer un robot et un humain** : on ne compare pas les angles moteurs.
  On compare les **directions des bras** dans le repère du corps : c'est
  indépendant de la taille et de la distance (docs/EVALUATION.md, § 3).
- **Le retard humain** : on accepte 0,4 s sans pénalité, et le retard habituel
  du joueur est mesuré (§ 6).
- **Rester immobile ne paie pas** : facteur d'activité (§ 7).
- **Être hors champ** n'est jamais compté comme une erreur, mais réduit la
  couverture (§ 8).

## Si quelque chose ne va pas

- **Pas de squelette** : vérifier la ligne « Détection » de la barre d'état,
  puis voir docs/CAMERA.md.
- **NAO ne bouge pas** : vérifier le journal, puis la passerelle Choregraphe.
- **En dernier recours** : `--joueur-simule` montre toute la boucle de jeu sans
  caméra.
