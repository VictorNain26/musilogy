# musilogy

Couche 0 : deux dumps JSON MusicBrainz transformés en cinq tables Parquet
reproductibles. Les règles métier et les chiffres sont dans le `README.md` ; ce
fichier décrit comment on travaille sur ce dépôt.

## Travailler avec des agents

Le dépôt se prête bien au travail délégué : les règles sont en SQL, les sorties
sont chiffrées, donc vérifiables.

- **Donner des critères d'acceptation mesurables.** Un agent d'implémentation
  travaille bien quand la réussite est un nombre ou un code de sortie, mal quand
  c'est une intention. « `density` doit valoir 52 201 cellules » vaut mieux que
  « corriger la densité ».
- **Vérifier un rapport avant de bâtir dessus.** Un compte rendu de sous-agent
  est une affirmation, pas un fait : `git status`, la suite de tests et le
  filesystem tranchent.
- **Séparer qui écrit et qui juge.** Une revue à contexte neuf, qui lit le code
  et non le rapport de l'implémenteur, trouve ce que l'auteur ne peut pas voir.
- **Déléguer l'exploration large, garder la conclusion.** Une recherche qui
  balaie trente fichiers appartient à un sous-agent ; le contexte principal n'a
  besoin que du résultat.
- **Figer avant de paralléliser.** Deux agents sur les mêmes fichiers produisent
  un diff impossible à séparer ensuite en commits lisibles.

## Mesurer plutôt que raisonner

Les extractions complètes vivent dans `data/work/` et DuckDB lit un JSONL de
400 Mo en quelques secondes. Une question chiffrée — « combien de groupes perd
cette règle ? », « ce changement bouge-t-il la densité ? » — se tranche par une
requête, pas par un raisonnement plausible. C'est souvent plus rapide que d'en
débattre, et le résultat est opposable.

Le pipeline étant déterministe, un contrefactuel est toujours possible : rejouer
la chaîne avec une règle modifiée et comparer les tables donne le coût exact
d'une décision avant de l'écrire.

## Python

- Python 3.12, `uv` pour l'environnement et l'exécution, dépendances épinglées
  au patch près — la reproductibilité du pipeline en dépend autant que le code.
- Typage sur les frontières publiques ; validation stricte de ce qui vient du
  dehors (archive téléchargée, CSV externe, entrée utilisateur), confiance entre
  fonctions internes.
- `pathlib` partout, et des chemins ancrés sur le paquet plutôt que sur le
  répertoire courant : `musilogy.paths` existe pour ça, et la suite de tests doit
  passer depuis n'importe où.
- Séparer le calcul de l'entrée-sortie, comme le fait déjà le paquet :
  `extract.py` projette sans règle métier, `build.py` orchestre, `publish.py`
  écrit. Une fonction qui fait les deux est difficile à tester.
- Commentaire seulement pour un « pourquoi » non évident. Les bons exemples du
  dépôt sont dans `90_invariants.sql` : ils expliquent une contrainte cachée,
  pas ce que le code fait déjà lire.
- `ruff` pour le lint et le format, `mypy` pour les types. `ty` est plus rapide
  et cohérent avec l'outillage Astral, mais il est encore en 0.0.x : adosser la
  vérification de types à un outil dont la sémantique peut bouger contredit
  l'épinglage au patch près que le reste du dépôt s'impose.

## Architecture

- **La couche 0 produit des tables, pas des vues d'affichage.** Un filtre qui
  sert au rendu appartient à la projection (`density`, export web) ; la
  population reste complète. Confondre les deux fait disparaître des données
  qu'on ne sait plus récupérer en aval.
- **Une valeur dérivée voyage avec sa provenance.** Publier `y0` à côté de
  `y0_source` permet au consommateur de distinguer une donnée déclarée d'une
  donnée inférée, au lieu de lui faire confiance à l'aveugle.
- **Les règles vivent dans le SQL**, numérotées par ordre topologique de
  dépendance (pas de dix, pour insérer sans renuméroter). Le Python enchaîne et
  vérifie, il n'arbitre pas.
- **Un invariant recalcule indépendamment ce qu'il vérifie.** Réutiliser la
  formule de production revient à comparer une valeur à elle-même.
- **Une donnée de référence n'a qu'un seul point d'autorité.** Le contrat
  exécutable des chiffres est `tests/test_baseline.py`. Un chiffre repris
  ailleurs — README, commentaire — est descriptif et doit se donner comme tel :
  c'est la duplication silencieuse qui finit par diverger, et c'est la source la
  plus courante de documentation qui se contredit.

## Tests

- Les témoins viennent du vrai dump (`musilogy make-fixtures`), pas de données
  inventées : un cas fabriqué valide ma compréhension de la source, pas la source.
- Nommer la casse avant d'écrire le test : quel changement du code de production
  le ferait échouer ? Un test qui ne casse que sur une constante volontairement
  modifiée signale les refontes et dort sur les bugs.
- Deux niveaux : la suite rapide sur les témoins, la ligne de base sur le dump
  complet. Un écart à la ligne de base se comprend avant d'être entériné.

## Dépôt

- Une branche par chantier, courte, mergée au fil de l'eau.
- Stager fichier par fichier ; un commit doit raconter un seul changement.
- La CI passe le lint, les types et la suite rapide ; la suite lente exige le
  dump et tourne à la demande.
- Les sorties (`data/`) ne sont pas versionnées — seules les empreintes et les
  fixtures le sont.

## Commandes

```bash
uv sync
uv run pytest                 # suite rapide, sur les témoins
uv run pytest -m slow         # ligne de base sur le dump réel, exige data/work/
uv run musilogy run           # fetch → extract → transform → validate → publish
uv run musilogy make-fixtures
```

## Licence

Les données de base MusicBrainz sont CC0, mais les genres et tags sont
CC-BY-NC-SA 3.0. Comme `bands` et `genres` en dépendent, le jeu produit est
CC-BY-NC-SA 3.0 : attribution, usage non commercial, partage à l'identique. Les
fixtures versionnées suivent la même licence. Toute question de diffusion des
sorties part de là.
