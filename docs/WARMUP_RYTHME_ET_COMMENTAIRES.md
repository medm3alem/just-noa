# Warm-up : rythme et remarques vocales

## Rythme (v5, 2 nov.)

- La version prudente (un bras a la fois, levee jusqu'a ShoulderPitch 0.38 rad,
  4 temps pour monter et 4 pour descendre a 92 BPM) etait trop lente.
- Nouvelle version : **96 BPM**, une pose tous les **2 temps (1,25 s)**, puis un
  geste **par temps** pour les biceps. Cinq blocs de 8 temps : bras ouverts sur
  le cote, un bras devant puis l'autre, bras en haut par le cote, biceps l'un
  apres l'autre, ouvrir la poitrine. Duree inchangee (29,7 s).
- Les gestes a deux bras se font sur le cote ou en opposition (voir
  docs/WARMUP_SAFE.md) : part dynamique estimee 4,2 mm, contre 13,7 mm pour la
  version qui a fait tomber NAO.
- Le score redevient utilisable : joueur simule immobile 19/100, bon joueur
  100/100.

## Remarques pendant les danses

- Commentaires anglais pendant la danse : 2 dans Macarena, 2 dans NAO Party,
  2 dans Warm-up, et 2 dans la nouvelle danse Mekassarat ("Yalla! Show me your
  moves!", "Even my circuits are dancing!"). Les phrases sont fixes et ne
  pretendent pas refleter le score en direct. Les consignes du Warm-up et les
  commentaires de fin sont conserves.
- Warm-up : "Easy there, I am not a helicopter!" (temps 21) et "Looking good!
  My grandma approves!" (temps 37) ; les consignes annoncent chaque bloc.
- Les commentaires sont des evenements `say` asynchrones, qui ne mettent pas en
  pause les mouvements ; une voix peut toutefois se superposer a la musique. Le
  comportement effectif sur le NAO doit etre verifie.
- Les tests logiciels ne prouvent pas la stabilite du robot physique. Comme NAO
  a deja chute, inspecter les articulations et les alertes avant reprise, faire
  examiner les trajectoires et tester progressivement sous surveillance. Ne pas
  relancer le mouvement en cas de chute ou de bruit moteur anormal.
