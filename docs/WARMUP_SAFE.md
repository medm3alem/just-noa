# Warm-up (arms) - securite apres les chutes

## Historique

- **v4** (92 BPM, les deux bras ensemble vers l'avant / le haut / le bas toutes
  les ~1,3 s) : **NAO est tombe plusieurs fois**.
- **Version prudente de Med** (conservee dans
  `tools/old_versions/choreographies_v4/echauffement_lent/`) : un seul bras a la
  fois, jamais au-dessus des epaules, chaque geste monte sur 4 temps et descend
  sur 4 temps. Plus de chute, mais trop lent, et trop faible pour distinguer un
  joueur immobile.
- **Version actuelle (v5, 2 nov.)** : rythme vivant (une pose tous les 2 temps a
  96 BPM, puis un geste par temps), en suivant les regles d'equilibre ci-dessous.
  Details : docs/DANCES.md, sections 0 et 4.

## Ce qui a fait tomber NAO (estimation)

Le controle `choreography/kinematics.py` estime ou le poids de NAO appuie sur le
sol pendant que les bras bougent (ZMP). Quand les deux bras **accelerent
ensemble vers l'avant ou vers le haut**, ils poussent le corps dans l'autre sens :
c'est la "part dynamique". Valeurs du modele :

| Version | Part dynamique |
|---|---|
| warm-up v4 (chute) | **13,7 mm** |
| premier test Choregraphe de Med (aucun probleme) | 1,0 mm |
| version prudente de Med | 0,4 mm |
| **warm-up v5** | **4,2 mm** (2,6 mm a `--speed 0.75`, 1,2 mm a `--speed 0.5`) |

Toute choregraphie est maintenant **refusee** au-dessus de 9 mm (avertissement
au-dessus de 6 mm). Le warm-up v4 serait refuse. Ce seuil vient d'une seule
chute et d'un modele simplifie : il permet de comparer les danses, il ne
garantit pas la stabilite reelle.

## Regles suivies par la v5

- Jamais les deux bras ensemble vers l'avant, l'arriere ou le haut en passant
  par devant.
- Gestes a deux bras **sur le cote** (plan frontal), symetriques : les poussees
  gauche et droite s'annulent.
- Un bras vers l'avant **pendant que l'autre redescend** (poussees opposees).
- Gestes lents pour les grands mouvements (au moins 1,2 temps), rapides
  seulement pour les avant-bras (biceps).
- Pas de commandes de jambes ou de torse (interdites par la passerelle).

**Difference avec la version prudente :** dans le bloc "Arms up through the
sides" (temps 17-24), les bras passent **au-dessus de la tete, par le cote**.
Le modele le considere equilibre (geste lateral symetrique), mais il ne respecte
pas la regle "pas de bras au-dessus des epaules". Tester ce bloc seul d'abord.
Pour le retirer : dans `warmup()` de `tools/compose_choreographies.py`,
remplacer le bloc `(17, "Arms up through the sides", ...)` par une copie du
premier bloc, puis regenerer (commande plus bas).

## Essais physiques

Apres plusieurs chutes, verifier l'etat mecanique et les alertes du robot.
Ne pas lancer la danse tant qu'un responsable du robot n'a pas confirme son bon etat.
Tester d'abord la posture et de petits mouvements isoles, puis la choregraphie
a vitesse reduite avec un operateur a proximite et Stop accessible :
`--speed 0.5`, bloc par bloc, puis `--speed 0.75`, puis 100 %
(docs/DANCE_VALIDATION.md, etapes 0, C et D).
Arreter au moindre signe de desequilibre, bruit anormal ou contact.
Si 100 % parait limite, garder `--speed 0.75` (le warm-up n'a pas de musique),
ou revenir a la version prudente (copier les deux fichiers de
`tools/old_versions/choreographies_v4/echauffement_lent/` dans
`choreography/library/echauffement/`).

Pour regenerer uniquement cette danse :

`python tools/compose_choreographies.py echauffement`

Sans argument, le generateur regenere les quatre danses composees (Macarena,
NAO Party, Warm-up, Mekassarat) ; elles ont toutes ete refaites en v5, donc ce
n'est plus un probleme, mais toute modification manuelle d'un `motion.json`
serait ecrasee.
