# musilogy

Couche 0 : transforme deux dumps JSON MusicBrainz en cinq tables reproductibles et testées. Ce dépôt ne contient aucune interface — la frise chronologique qui consommera ces tables (couche 1) n'existe pas encore.

## Principe directeur

**La sortie n'affirme jamais plus que ce que la source porte.** Une absence reste une absence : elle n'est ni imputée en silence, ni prolongée, ni arbitrée. Quand une valeur est dérivée, elle est publiée avec la colonne qui dit d'où elle vient, pour que le consommateur distingue une donnée déclarée d'une donnée inférée.

**Population et projection sont deux choses distinctes.** `bands` et `albums` portent la population complète ; `density` est une projection délibérément plus étroite, destinée à la frise. Un filtre d'affichage vit dans la projection, jamais dans la population — sinon la donnée écartée devient irrécupérable en aval.

C'est le changement le plus lourd par rapport à la première version de ce dépôt, qui appliquait le filtre de la frise à la population et n'en publiait que 63 487 groupes sur 682 447, soit 30 % de la masse d'albums réelle.

## Les cinq tables

Mesurées sur le dump de référence `20260909-001002` :

| Table | Contenu | Lignes |
|---|---|---|
| `bands` | un artiste : ses preuves de dates, sa ligne de vie dérivée, ses genres votés | 682 447 |
| `albums` | un point : une sortie d'album créditée à un seul artiste | 643 403 |
| `genres` | le vocabulaire porté par `bands` | 1 348 |
| `genre_parents` | relations parent-enfant assertées entre genres (Wikidata) | 1 283 arêtes |
| `density` | groupes présents par genre et par année | 53 029 cellules |

Colonnes réelles (voir `src/musilogy/sql/`) :

- **`bands`** : `mbid`, `name`, `type`, `y0_declared`, `y_end_declared`, `ended`, `country`, `begin_area`, `genres` (liste de `{mbid, name, votes}`, triée), `y_first_album`, `y_last_album`, `y0`, `y0_source`, `y_end`, `y_end_source`, `y_presence_end`.
- **`albums`** : `band_mbid`, `rg_mbid`, `title`, `y`, `soundtrack`.
- **`genres`** : `genre_mbid`, `name`, `n_bands`.
- **`genre_parents`** : `genre_mbid`, `parent_mbid`, `source`.
- **`density`** : `genre_mbid`, `year`, `present`.

Une table intermédiaire, `presence(mbid, y0, y_presence_end)`, est calculée mais non publiée.

## Les règles

Chaque règle vit dans son fichier SQL numéroté (`src/musilogy/sql/`) ; **la numérotation est un ordre topologique de dépendance**, pas un rang dans une liste, et avance par pas de dix pour qu'une règle s'insère sans renumérotation.

- **`10_bands` — Population et lecture des dates.** Tout artiste extrait entre dans `bands` : aucun filtre de type, de date ou de genre. La lecture des dates est déterministe : l'année tient sur les quatre premiers caractères, sinon elle est **absente**, pas devinée. Une date hors de `[1850, année du dump]` — aux deux bords — et une fin antérieure au début sont neutralisées, et **chaque neutralisation alimente un compteur** dans `manifest.json` pour rester visible plutôt qu'absorbée en silence. Tous les genres sont conservés, triés explicitement par votes décroissants puis par nom (l'ordre de la source est alphabétique, jamais hérité).

- **`20_albums` — Albums.** Un release-group compte comme album s'il est de type primaire `Album` (filtré dès l'extraction), crédité à un **seul artiste distinct** présent dans `bands`, daté dans `[1850, année du dump]`, et dont les types secondaires sont vides ou inclus dans `{Soundtrack, Demo}`. La fenêtre de ±5 ans autour de la formation a disparu : `y0` dérive désormais en partie des albums, l'utiliser ici créerait un cycle.

  Les démos sont acceptées parce qu'elles sont une preuve *contemporaine* d'activité précoce : 67,5 % des groupes ayant démo et album studio ont sorti la démo d'abord, 3 ans plus tôt en médiane. Les albums live sont exclus pour la raison inverse : **MusicBrainz les date de leur publication, pas du concert** — 727 groupes ont un live daté plus de 20 ans après leur dernier studio, avec des titres qui portent eux-mêmes la vraie date (« Live in Paris (1966) », publié en 2024). Les compilations, DJ-mix et remix sont exclus au même titre.

- **`30_bands_lifespan` — Ligne de vie et provenance.** Aux deux bords, **la preuve déclarée l'emporte, l'album prend le relais** :
  - `y0` = année déclarée, sinon année du premier album ; `y0_source` vaut `declared`, `first_album` ou NULL.
  - `y_end` = fin déclarée, sinon année du dernier album ; `y_end_source` suit la même logique.
  - Les preuves brutes (`y0_declared`, `y_end_declared`, `y_first_album`, `y_last_album`, `ended`) restent publiées à côté : la valeur dérivée est vérifiable sans relancer le pipeline.

  **Une preuve issue d'un album n'est retenue à un bord que si elle ne contredit pas la preuve déclarée à l'autre bord.** Trois garde-fous symétriques, chacun avec son compteur :

  | garde-fou | cas | compte |
  |---|---|---|
  | `first_album_after_declared_end` | premier album postérieur à une fin déclarée — une réédition posthume, dont la `first-release-date` est la date de réédition, n'est pas une preuve de formation | 81 |
  | `last_album_before_declared_begin` | dernier album antérieur à un début déclaré — symétrique du précédent, il produisait une fin étiquetée `last_album` qui valait en réalité l'année de début | 271 |
  | `first_album_with_begin_below_min_year` | début déclaré sous 1850, donc neutralisé : la source affirme que le groupe précède l'album, en inférer une formation plus tardive affirmerait davantage qu'elle | 73 |

  Après ces garde-fous, `y_end >= y0` est garanti par construction, sans clause défensive.

- **`40_presence` — Présence.** Seuls les artistes dont `y0` est connu. `y_presence_end` borne `y_end` à l'année du dump.

- **`50_genres` — Vocabulaire.** Les genres effectivement portés par `bands`, avec leur nombre d'artistes.

- **`60_density` — Densité.** Délibérément plus étroite que la population : type `Group`, `y0` connu, au moins un genre. Un artiste sans genre n'y produit aucune ligne par construction. Les totaux par genre ne s'additionnent pas : un groupe compte dans chacun des siens.

- **`70_genre_parents` — Arbre des genres.** Depuis une archive Wikidata datée et vérifiée par empreinte, restreinte aux genres présents aux deux extrémités.

- **`90_invariants` — Contrôles.** 24 vues qui doivent toutes renvoyer zéro ligne ; le nom de la vue *est* le nom de l'invariant. Chacune **recalcule indépendamment** ce qu'elle vérifie : réutiliser la formule de production reviendrait à comparer une valeur à elle-même, et une revue a montré qu'un invariant écrit ainsi restait muet sur 265 violations réelles. Les bornes contractuelles y sont codées en dur, aux deux extrémités, sans relire les variables de session dont dépendent les règles de production ; changer de dump impose donc une modification délibérée de ce fichier — c'est précisément l'intention.

Les corrections manuelles (`src/musilogy/corrections.csv`, versionné, colonnes `mbid, field, value, justification, source`) sont appliquées avant la lecture des dates ; chaque ligne cite une source vérifiable. Le pipeline ne dépend jamais de ce fichier pour fonctionner, et un garde-fou échoue au-delà de 50 lignes.

## Ce que reçoit la couche 1

`data/out/<dump>/` contient les cinq tables en Parquet (archive complète), le manifeste, et un export JSON colonnaire gzippé **scindé** :

- `web/bands_timeline.json.gz` — les 380 866 artistes dont `y0` est connu, donc plaçables sur une frise ;
- `web/bands_rest.json.gz` — les 301 581 autres, chargeables à la demande ;
- `web/genres.json.gz` — le vocabulaire.

Chaque ligne porte son `mbid` (clé de jointure vers `density`, `genre_parents` et MusicBrainz), ses `genres`, et les deux bords avec leurs preuves brutes des deux côtés, pour que la provenance soit auditable à gauche comme à droite.

**Le poids reste un sujet ouvert pour la couche 1** : 15,6 Mo gzip pour la frise, 9,4 Mo pour le reste. La cause n'est pas les genres (1,7 Mo) mais les identifiants eux-mêmes — 380 866 UUID de 36 octets ne se compressent pas. Un chargement initial complet n'est pas réaliste sur mobile ; il faudra un découpage par genre ou par période côté couche 1, ce que la couche 0 ne préempte pas.

`manifest.json` porte les empreintes des archives, les comptes, les anomalies de lecture de dates, les trois compteurs de neutralisation, le commit et l'empreinte des corrections.

## Chiffres de référence

Le **contrat exécutable** est `tests/test_baseline.py` : il confronte le pipeline entier au dump de référence et compare exactement les comptes, la somme des cellules de densité, la répartition des provenances, et l'absence de fin antérieure au début. Les chiffres cités dans ce README sont descriptifs ; en cas de divergence, c'est le test qui fait foi.

Un écart à la ligne de base signale une règle mal implémentée — jamais un prétexte pour ajuster la ligne de base.

Provenance des bords, sur le dump de référence :

| | `declared` | dérivé des albums | inconnu |
|---|---|---|---|
| début (`y0_source`) | 235 246 | 145 620 | 301 581 |
| fin (`y_end_source`) | 48 842 | 251 514 | 382 091 |

## Limites assumées

- **Le classique est inexploitable en densité.** L'exclusion des albums crédités à plusieurs artistes distincts retire 9,6 % des albums en moyenne, mais le biais est extrême et non uniforme : **94,3 % en `classical`**, 86,3 % en `orchestral`, contre 0,6 % en `alternative metal` et 0,8 % en `power metal`. Un album classique crédite presque toujours compositeur *et* interprète. `density` n'est donc pas comparable d'un genre à l'autre, et ne veut pratiquement rien dire pour les répertoires savants.

- **Une fin dérivée d'un album n'est pas une fin déclarée.** Elle est marquée `y_end_source = 'last_album'`. Parmi les groupes dont la fin est inférée ainsi et qui ont au moins deux albums, **3,38 % ont un dernier album isolé de plus de 15 ans** du précédent (1,04 % au-delà de 25 ans) : des rééditions de fonds historiques qui étirent la ligne de vie. La couche 0 ne les écarte pas — il faudrait un seuil arbitraire, ce que le principe directeur interdit. L'étiquette de provenance permet à la couche 1 de trancher.

- **Le genre est un filtre de notoriété communautaire, et il est daté.** Part d'artistes sans aucun genre, par époque de formation : 69,3 % pour 1967-1979, 72,6 % pour 1980-1999, 78,9 % pour 2000-2014, **82,7 % depuis 2023**. La densité près du présent est donc doublement une borne basse : par la présence, et parce que les groupes récents sont moins tagués. Ce n'est pas un signal historique, c'est un artefact de catalogage.

- **L'arbre des genres vient de Wikidata seule** et ne couvre pas tout le vocabulaire ; la piste MusicBrainz (`subgenre`) reste non tranchée.

- **`density` ignore les orchestres et chœurs**, faute d'un modèle de ligne de vie comparable. Ils sont présents dans `bands` et `albums` : la couche 1 peut les afficher autrement.

## Installation, tests, exécution

Python 3.12 géré par `uv`.

```bash
uv sync
```

Deux niveaux de test :

- `uv run pytest` — suite rapide, quelques secondes, sans dépendance au dump. Tourne sur 28 témoins réels versionnés dans `tests/fixtures/` (extraits authentiques du dump de référence, jamais de données inventées).
- `uv run pytest -m slow` — ligne de base : confronte le pipeline entier aux ~3 millions d'enregistrements du dump de référence. Exige les extractions dans `data/work/` (non versionnées, ~10 min à produire) ; sinon le test est ignoré.

La suite passe depuis n'importe quel répertoire : tous les chemins sont ancrés sur le paquet (`musilogy.paths`), jamais sur le répertoire courant.

```bash
uv run musilogy run                   # fetch → extract → transform → validate → publish
uv run musilogy make-fixtures         # régénère les témoins depuis les extractions
uv run musilogy check-genre-parents   # vérifie l'empreinte de l'archive Wikidata, sans réseau
```

Qualité : `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`. La CI (`.github/workflows/ci.yml`) passe ces trois contrôles plus la suite rapide ; la suite lente exige le dump et reste manuelle.

## Structure du dépôt

```
src/musilogy/
  fetch.py               télécharge et vérifie une archive MusicBrainz (SHA-256)
  extract.py             projette les enregistrements bruts en flux, sans logique métier
  build.py               enchaîne les fichiers SQL, applique les corrections, vérifie les invariants
  publish.py             écrit Parquet, JSON colonnaire scindé et manifest.json
  cli.py                 les trois commandes
  paths.py               chemins ancrés sur le paquet
  corrections.csv        corrections manuelles, versionné
  reference/             empreintes officielles, archive Wikidata datée et sa requête SPARQL
  sql/                   les règles, en ordre topologique
tests/
  conftest.py            fixtures partagées
  fixtures/              témoins réels versionnés
  test_*.py              une suite par règle, plus test_baseline.py (suite lente)
```

## Licence et attribution

Les données de base MusicBrainz (artistes, dates, albums, relations) sont **CC0**. Les genres et tags sont des données supplémentaires sous **CC-BY-NC-SA 3.0**. Comme `bands` et `genres` en dépendent, **le jeu de données produit par ce pipeline est distribué sous CC-BY-NC-SA 3.0** : attribution à MusicBrainz obligatoire, usage non commercial uniquement, et partage à l'identique imposé à toute redistribution.

Les fixtures versionnées dans `tests/fixtures/` sont des extraits réels du dump MusicBrainz de référence, soumis à la même licence (voir `tests/fixtures/ATTRIBUTION.md`).
