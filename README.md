# musilogy

Couche 0 : transforme deux dumps JSON MusicBrainz en cinq tables reproductibles et testées. Ce dépôt ne contient aucune interface — la frise chronologique qui consommera ces tables (couche 1) n'existe pas encore.

## Principe directeur

**La sortie n'affirme jamais plus que ce que la source porte.** Une absence reste une absence : elle n'est ni imputée, ni prolongée, ni arbitrée en silence. C'est la raison derrière la plupart des choix ci-dessous — en particulier le refus de calculer une date de fin de groupe (R4) et le fait que R2 neutralise une date illisible plutôt que de la deviner.

## Les cinq tables

Mesurées sur le dump de référence `20260909-001002` :

| Table | Contenu | Lignes |
|---|---|---|
| `bands` | un groupe : ses preuves de dates, ses genres votés, sa provenance | 63 487 |
| `albums` | un point : une sortie d'album studio d'un groupe | 189 477 |
| `genres` | le vocabulaire effectivement porté par `bands` | 1 236 |
| `genre_parents` | relations parent-enfant assertées entre genres (Wikidata) | 1 195 arêtes, 951 genres couverts sur 1 236 |
| `density` | groupes présents par genre et par année | 51 161 cellules |

Colonnes réelles (voir `pipeline/sql/`) :

- **`bands`** : `mbid`, `name`, `y0`, `y_end_declared`, `ended`, `country`, `begin_area`, `genres` (liste de `{mbid, name, votes}`, triée), `y_last_album`, `y_presence_end`.
- **`albums`** : `band_mbid`, `rg_mbid`, `title`, `y`, `soundtrack`.
- **`genres`** : `genre_mbid`, `name`, `n_bands`.
- **`genre_parents`** : `genre_mbid`, `parent_mbid`, `source` (`wikidata` ou `musicbrainz`).
- **`density`** : `genre_mbid`, `year`, `present`.

Une table intermédiaire, `presence(mbid, y0, y_presence_end)`, est calculée mais non publiée — c'est elle qui porte les invariants de présence.

## Les règles

Chaque règle vit dans son fichier SQL numéroté (`pipeline/sql/`) ; la numérotation est un ordre topologique, pas une liste — R6 précède R2, qui précède R1, dont dépendent R3 et R5, dont dépend R7.

- **R1 — Population.** Un artiste entre dans `bands` s'il est de type `Group`, a une année de formation valide dans `[1850, année du dump]`, et porte au moins un genre. Les orchestres et chœurs sont exclus malgré un genre, faute d'un modèle de ligne de vie comparable. La plus grosse exclusion — et la plus structurante — est l'absence de genre : sur 229 241 groupes datés, 72,3 % sont écartés faute de genre.
- **R2 — Dates.** Lecture déterministe, sans intervention humaine : l'année tient sur les quatre premiers caractères ; sinon, ou si elle est future, ou si la fin précède le début, la date est **absente**, pas devinée. Chaque sous-règle alimente un compteur dans `manifest.json` pour qu'une anomalie neutralisée reste visible plutôt qu'absorbée en silence.
- **R3 — Albums.** Un release-group compte comme album s'il est de type primaire `Album` (filtré dès l'extraction, `pipeline/extract.py`), crédité à un seul artiste distinct présent dans `bands`, daté au plus tard que l'année du dump, sans type secondaire hors `Soundtrack`, et dans la fenêtre `[y0 − 5, borne_haute + 5]`. Les albums à plusieurs artistes distincts sont exclus.
- **R4 — Bord droit.** La couche 0 ne calcule **jamais** de date de fin de groupe. Elle transporte trois preuves indépendantes — `y_end_declared`, `y_last_album`, `ended` — et laisse le rendu de l'incertitude à la couche 1.
- **R5 — Genres.** Tous les genres d'un groupe sont conservés, triés explicitement par votes décroissants puis par nom (l'ordre de la source est alphabétique, jamais hérité). Aucun plafond en couche 0.
- **R6 — Corrections manuelles.** `pipeline/corrections.csv`, versionné, colonnes `mbid, field, value, justification, source` : chaque ligne cite une source vérifiable. Appliqué avant R2, sur `raw_artists`. Le pipeline ne dépend jamais de ce fichier pour fonctionner — R2 neutralise déjà toute anomalie — et un garde-fou échoue au-delà de 50 lignes.
- **R7 — Présence et densité.** Un groupe est présent l'année `y` si `y0 ≤ y ≤ fin_de_présence`, où `fin_de_présence` est la fin déclarée si elle existe, sinon `max(y0, y_last_album)`, plafonnée à l'année du dump. `density` compte, par genre et par année, les groupes présents portant ce genre ; un groupe à plusieurs genres compte dans chacun.

## Chiffres de référence (contrat de non-régression)

Sur le dump `20260909-001002`, corrections vides :

- `bands` : 63 487 · `albums` : 189 477 · `genres` : 1 236 · `density` : 51 161 cellules.
- Anomalies R2 (sur les 682 447 groupes/orchestres/chœurs) : 34 formations illisibles, 7 fins illisibles, 15 formations futures, 3 fins futures, 2 fins antérieures au début.
- `genre_parents` : 1 195 arêtes couvrant 951 genres sur 1 236.

Ces chiffres sont vérifiés par `uv run pytest -m slow` (voir plus bas) ; un écart signale une règle mal implémentée, jamais un prétexte pour ajuster la ligne de base.

## Limites assumées

- **72,3 % des groupes datés sont écartés faute de genre** — le choix le plus lourd de la couche 0. Un groupe sans genre n'a pas de place sur une frise filtrable par genre, mais c'est un filtre de notoriété communautaire, pas une mesure objective.
- **Les albums crédités à plusieurs artistes distincts sont exclus**, avec un biais non uniforme selon les genres : 19,7 % des albums écartés en grindcore contre 8,4 % en ambient. `density` n'est donc **pas** rigoureusement comparable d'un genre à l'autre.
- **Près du présent, la densité est une borne basse** : un groupe non terminé sans fin déclarée n'est compté présent que jusqu'à son dernier album connu, jamais prolongé jusqu'à aujourd'hui.
- **L'arbre des genres vient de Wikidata seule** et couvre 951 genres sur 1 236 ; la piste MusicBrainz (`subgenre`) reste non tranchée faute de mesure aboutie.

## Installation, tests, exécution

Python 3.12 géré par `uv`.

```bash
uv sync
```

Deux niveaux de test :

- `uv run pytest` — suite rapide, quelques secondes, sans dépendance au dump. Tourne sur 28 témoins réels versionnés dans `pipeline/tests/fixtures/` (extraits authentiques du dump de référence, pas de données inventées).
- `uv run pytest -m slow` — test de ligne de base : confronte le pipeline entier aux ~3 millions d'enregistrements du dump de référence et compare **exactement** les comptes ci-dessus. Exige les extractions dans `data/work/` (non versionnées, ~10 min à produire) ; sinon le test est ignoré.

Exécution complète (télécharge et vérifie les archives si besoin, extrait, transforme, valide, publie) :

```bash
uv run python scripts/run_pipeline.py
```

Produit `data/out/20260909-001002/` : les cinq tables en Parquet, un export JSON colonnaire gzippé pour `bands` et `genres`, et `manifest.json` (empreintes, comptes, anomalies R2, commit).

## Structure du dépôt

```
pipeline/
  fetch.py               télécharge et vérifie une archive MusicBrainz (SHA-256)
  extract.py             projette les enregistrements bruts en flux, sans logique métier
  build.py               enchaîne les fichiers SQL, applique les corrections, vérifie les invariants
  publish.py             écrit Parquet, JSON colonnaire et manifest.json
  corrections.csv        R6, versionné
  reference/             empreintes officielles, archive Wikidata datée et sa requête SPARQL
  sql/
    00_macros.sql        macro yr() : lecture stricte d'une année, jamais un CAST direct
    10_bands.sql         R1, R2 : population et dates
    20_albums.sql        R3 : sélection des albums
    30_presence.sql      R4, R7 : table presence, y_presence_end
    40_genres.sql        R5 : vocabulaire des genres
    50_density.sql       R7 : agrégat de densité
    60_genre_parents.sql arbre des genres depuis Wikidata
    90_invariants.sql    vues de contrôle qui doivent renvoyer zéro ligne
  tests/
    fixtures/            témoins réels versionnés (artists.jsonl, release_groups.jsonl, ATTRIBUTION.md)
    test_*.py            suite rapide (une par règle) et test_baseline.py (suite lente)
scripts/
  make_fixtures.py       extrait les témoins des extractions complètes
  check_genre_parents.py vérifie l'empreinte de l'archive Wikidata, aucun appel réseau
  run_pipeline.py        exécution complète : fetch → extract → transform → validate → publish
```

Les numéros des fichiers SQL forment un ordre topologique de dépendance, pas une liste : ils avancent par pas de dix pour qu'une règle s'insère sans renumérotation.

## Licence et attribution

Les données de base MusicBrainz (artistes, dates, albums, relations) sont **CC0**. Les genres et tags sont des données supplémentaires sous **CC-BY-NC-SA 3.0**. Comme `bands` et `genres` en dépendent, **le jeu de données produit par ce pipeline est distribué sous CC-BY-NC-SA 3.0** : attribution à MusicBrainz obligatoire, usage non commercial uniquement, et partage à l'identique imposé à toute redistribution.

Les fixtures versionnées dans `pipeline/tests/fixtures/` sont des extraits réels du dump MusicBrainz de référence, soumis à la même licence (voir `pipeline/tests/fixtures/ATTRIBUTION.md`).
