# Couche 0 — pipeline de données · conception

- **Statut** : révision 4 — intègre deux passes de relecture indépendante et une revue d'architecture. Prête pour un plan d'implémentation ; en attente de relecture humaine.
- **Date** : 2026-09-11
- **Dump de référence** : MusicBrainz JSON dumps `20260909-001002`
- **Portée** : produire, de façon reproductible et testée, le jeu de données qui alimente la frise (couche 1). Aucune interface ici.

Tous les chiffres ont été **mesurés** sur le dump de référence en appliquant les règles telles qu'écrites dans ce document. Rien n'est estimé sauf mention explicite « non vérifié ». Ces mesures proviennent d'une sonde jetable : le premier passage du vrai pipeline doit les retrouver, et c'est lui qui fixera la ligne de base versionnée.

---

## 1. Objet

La couche 0 transforme deux dumps MusicBrainz en cinq tables :

| Table | Contenu | Volume de référence |
|---|---|---|
| `bands` | un groupe : ses preuves de dates, ses genres votés, sa provenance | 63 487 lignes |
| `albums` | un point : une sortie d'album studio d'un groupe | 189 477 lignes |
| `genres` | le vocabulaire utilisé par `bands` | 1 236 lignes |
| `genre_parents` | les relations parent-enfant assertées entre genres | 1 195 arêtes via Wikidata ; source à trancher (§6) |
| `density` | groupes présents par genre et par année | 51 161 cellules |

Principe directeur, appliqué à chaque règle : **la sortie n'affirme jamais plus que ce que la source porte.** Une absence reste une absence : elle n'est ni imputée, ni prolongée, ni arbitrée en silence.

---

## 2. Sources

### 2.1 Retenue : dumps JSON MusicBrainz

| Fichier | Taille | Usage |
|---|---|---|
| `artist.tar.xz` | 2 Go | groupes, dates, genres (MBID et votes), zones, relations |
| `release-group.tar.xz` | 1 Go | albums et date de première sortie |

Emplacement : `https://data.metabrainz.org/pub/musicbrainz/data/json-dumps/<date>/`. Format : JSON Lines dans une archive tar, sous `mbdump/`. Le serveur publie aussi `SHA256SUMS`, `MD5SUMS` et une signature GPG `.asc` par archive.

**Complétude mesurée** (dump du 2026-09-09, statistiques officielles du 2026-09-11) :

| | Lu dans le dump | Officiel | Complétude |
|---|---|---|---|
| Artistes | 2 980 305 | 2 982 124 | 99,94 % |
| Release-groups | 4 507 265 | 4 510 822 | 99,92 % |

L'écart correspond à deux jours d'éditions. Les signalements d'incomplétude du forum MetaBrainz concernent les dumps `recording` et `release`, non utilisés.

**Conservation** : le serveur ne garde que les deux derniers dumps (constaté le 2026-09-11 : `20260905-001001`, `20260909-001002`). Le dump de référence doit donc être archivé localement (§5.3).

### 2.2 Licence

- Données de base (artistes, dates, albums, relations) : **CC0**.
- Genres et tags : données supplémentaires **CC-BY-NC-SA 3.0**.
- Le jeu publié est donc **CC-BY-NC-SA 3.0**, avec attribution à MusicBrainz, et le partage à l'identique s'impose à toute redistribution. Compatible avec le caractère non commercial du projet.

### 2.3 Écartées (vérifié)

- **Discogs** : l'objet artiste de l'API n'a aucun champ de date ; les membres n'ont pas de dates.
- **Spotify** : dix champs, aucun temporel, aucun membre.
- **Wikidata comme source de dates** : 2 312 dates de dissolution pour 114 335 groupes.
- **DBpedia** : 20 241 dates de fin déclarées ; enrichissement possible en v2.

Wikidata reste candidate pour **l'arbre des genres** uniquement (§6).

---

## 3. Modèle de sortie

### 3.1 `bands`

| Champ | Type | Règle |
|---|---|---|
| `mbid` | texte | seule clé d'identité (R8) |
| `name` | texte | tel que dans la source |
| `y0` | entier | année de formation (R2) |
| `y_end_declared` | entier nul | année de fin déclarée, après validation (R2) |
| `y_last_album` | entier nul | année du dernier album retenu (R3) |
| `ended` | booléen | drapeau `ended` de la source, tel quel |
| `country` | texte nul | code pays |
| `begin_area` | texte nul | zone de formation, telle que dans la source — ville **ou pays** : 10 994 des 42 940 valeurs renseignées sont identiques à la zone générale, donc un pays |
| `genres` | liste de `(genre_mbid, votes)` | triée par votes décroissants, puis par nom (R5) |
| `y_presence_end` | entier | **dérivé** — fin de présence calculée par R7 |

Aucune année de fin n'est *inventée* (R4). `y_presence_end` est publiée mais explicitement étiquetée comme dérivation de la couche 0, distincte des trois preuves qui la précèdent : sans elle, la couche 1 réimplémenterait la formule de R7 dans un autre langage, avec un risque de divergence silencieuse.

### 3.2 `albums`

`band_mbid`, `rg_mbid`, `title`, `y` (entier), `soundtrack` (booléen).

### 3.3 `genres`

`genre_mbid`, `name`, `n_bands` (nombre de groupes de `bands` portant ce genre).

### 3.4 `genre_parents`

`genre_mbid`, `parent_mbid`, `source` (`musicbrainz` ou `wikidata`). Relation **multivaluée** : un genre peut avoir plusieurs parents assertés. Le choix d'un parent unique, si la couche 1 en a besoin, n'est pas fait ici.

### 3.5 `density`

`(genre_mbid, year, present)` — nombre de groupes dont la présence est **attestée** cette année-là (R7).

---

## 4. Règles

Chaque règle vit dans son propre fichier SQL numéroté et possède ses témoins (§9.1). Les numéros ne forment pas une liste mais un **ordre topologique** : R6 précède R2, qui précède R1, dont dépendent R3 et R5, dont dépend R7. Ils avancent par pas de dix pour qu'une règle s'insère sans renumérotation, et l'en-tête de chaque fichier nomme les tables dont il dépend.

### R1 — Population

Un artiste entre dans `bands` si et seulement si :

1. `type = 'Group'` ;
2. son année de formation est valide après R2 ;
3. `1850 ≤ y0 ≤ année du dump` ;
4. il porte au moins un genre.

Effet mesuré : 682 447 artistes de type Group, Orchestra ou Choir → **63 487**.

Exclusions assumées :

- **Orchestres et chœurs** : 630 entités avec genre dans la fenêtre. Leur modèle — existence séculaire, répertoire d'autrui — ne correspond pas à une ligne de vie de groupe.
- **Groupes dont seule la fin est lisible** : 467 groupes avec genre ont une fin valide mais aucune formation valide ; faute de `y0`, ils sont exclus.
- **Groupes sans genre** : de loin la plus grosse exclusion, et la plus structurante. Sur 229 241 groupes de type `Group` datés dans la fenêtre, **63 487 portent au moins un genre et 165 754 sont écartés, soit 72,3 %**. Un groupe sans genre n'a pas de place sur une frise filtrable par genre, et l'étiquetage communautaire fait office de filtre de notoriété naturel — mais c'est le choix le plus lourd de la couche 0, et il doit être lu comme tel.

Avec ce filtre, la formation la plus ancienne est en 1855 et 9 groupes précèdent 1900.

### R2 — Dates

Règles de lecture, **déterministes** — le pipeline tranche toujours, sans intervention humaine :

1. L'année est lue sur les quatre premiers caractères ; si ce ne sont pas quatre chiffres, la date est **absente** (cas réels : `????-??-18`, `????-09`).
2. Une année de formation postérieure à l'année du dump est **absente**.
3. Une année de fin postérieure à l'année du dump est **absente**.
4. Une année de fin antérieure à l'année de formation est **absente** ; la formation est conservée.
5. La précision au mois ou au jour n'est pas conservée en v1.

Anomalies mesurées sur les 682 447 groupes, orchestres et chœurs : 34 formations illisibles, 7 fins illisibles, 15 formations dans le futur, 3 fins dans le futur, 2 fins antérieures au début. Soit **61 cas, 0,0089 %**. Dans la population R1, quatre sont concernés : 3 fins illisibles et 1 fin antérieure au début (Blackdeath).

Chaque sous-règle de R2 alimente un compteur écrit dans `manifest.json` : sur un nouveau dump, une anomalie neutralisée reste visible au lieu d'être absorbée en silence.

Les années antérieures à 1850 ne sont pas traitées par R2 : elles sortent du périmètre par R1. Il y en a 258 tous types confondus, dont 27 avec genre ; certaines sont exactes (Wiener Philharmoniker 1842), d'autres manifestement fausses (`0001-03-22`, `0011`, `0201`). Aucune n'est affirmée juste ou fausse par ce document.

Conséquence connue de la règle 4 : une fin neutralisée ouvre la fenêtre R3 jusqu'à l'année du dump. Blackdeath (début 1998, fin 1997) retient ainsi 13 albums de 1995 à 2024. C'est précisément le cas où une correction R6 sourcée est préférable à la neutralisation.

### R3 — Albums

Un release-group est retenu comme album d'un groupe si et seulement si :

1. `primary-type = 'Album'` ;
2. il est crédité à **un seul artiste distinct**, et cet artiste est dans `bands` — un même artiste crédité deux fois compte pour un (361 release-groups sont dans ce cas) ;
3. son année de première sortie est valide et **au plus égale à l'année du dump** ;
4. ses types secondaires sont **vides ou exactement `{Soundtrack}`** ;
5. son année est dans `[y0 − 5, borne_haute + 5]`, où `borne_haute = y_end_declared` si elle existe, sinon l'année du dump.

La condition 1 est appliquée à l'extraction (`pipeline/extract.py::reduce_release_group`), pas dans le SQL de cette règle : le champ `primary-type` n'est même pas transporté jusqu'à `raw_release_groups`, par choix de volume assumé pour ne pas conserver en mémoire ou sur disque des dizaines de millions de release-groups non-Album. Conséquence à connaître : si ce filtre d'extraction s'assouplissait un jour, aucune couche en aval ne rattraperait les non-albums qui s'y glisseraient.

Effets mesurés :

- 2 317 879 albums dans la base, dont 94,7 % datés.
- Retenus : **189 477**, dont **1 910** bandes originales.
- The Beatles : 72 release-groups « Album » sans type secondaire, 18 dans la fenêtre, **22 retenus** avec les bandes originales (1963 à 1970).

Limites connues et acceptées :

- Les albums crédités à plusieurs artistes distincts (9,10 % des albums) sont écartés, soit 12 067 release-groups pour 189 477 retenus. **Ce biais n'est pas uniforme selon les genres** : rapporté aux albums des groupes portant le genre, il écarte 19,7 % en grindcore, 16,1 % en free improvisation, 14,9 % en dub, 14,3 % en noise, 12,8 % en black metal et 10,4 % en jazz, contre 8,4 % en ambient ou sludge metal. Conséquence à assumer : `density` n'est pas rigoureusement comparable d'un genre à l'autre, et la couche 1 ne doit pas la présenter comme telle.
- Les éditions contemporaines parallèles sont conservées : les Beatles gardent leurs remontages nord-américains (*Meet The Beatles!*, *Beatles '65*…), réellement publiés à ces dates.
- **Groupes marqués terminés sans fin valide** (1 741 groupes) : la borne haute retombe sur l'année du dump, faute d'autre information. La fenêtre ne les protège donc pas du bruit posthume : Flesh Field, formé en 1996 et marqué terminé, retient des albums jusqu'en 2026 ; 9 groupes de ce statut retiennent un album de 2026. Une correction R6 sourcée est le seul remède.
- Même limite pour un groupe séparé dont la source ignore la séparation.

### R4 — Bord droit : des preuves, jamais une fin inventée

La couche 0 ne calcule **pas** d'année de fin. Elle transporte trois preuves indépendantes : `y_end_declared`, `y_last_album`, `ended`.

Statut mesuré des 63 487 groupes :

| Statut | Groupes |
|---|---|
| fin datée | 14 738 |
| terminé sans date, avec albums | 892 |
| terminé sans date, sans album | 849 |
| non terminé, dernier album ≥ 2020 | 18 431 |
| non terminé, dernier album < 2020 | 18 596 |
| non terminé, aucun album | 9 981 |

Pourquoi aucune fin n'est calculée :

- « fin déclarée, sinon dernier album » ferait s'arrêter 18 431 groupes vraisemblablement actifs à la date de leur dernier disque — U2, non terminé, s'arrêterait en 2025 ;
- prolonger jusqu'à aujourd'hui les groupes sans fin fabriquerait de la présence : en 2024, **48 532** groupes seraient comptés présents, contre **10 569** dont la présence est attestée (R7).

Le rendu de l'incertitude relève de la couche 1.

### R5 — Genres

- Tous les genres d'un groupe sont conservés, avec leur MBID et leur nombre de votes.
- Tri **par votes décroissants, puis par nom** en cas d'égalité. L'ordre de la source est alphabétique (vérifié sur 63 487 groupes sur 63 487) : le tri est donc toujours explicite, jamais hérité.
- Vocabulaire résultant : **1 236 genres**. Moyenne **2,253** genres par groupe, maximum 116. Aucun plafond en couche 0 ; afficher les trois premiers relève de la couche 1.
- Le MBID de chaque genre figure dans le dump (vérifié sur un enregistrement brut : `{"id": "fe4ba6a1-…", "count": 1, "name": "funk"}`) et doit être conservé dès l'extraction.

### R6 — Corrections manuelles

- Fichier `pipeline/corrections.csv`, versionné : `mbid, champ, valeur, justification, source`. Chaque ligne cite une source vérifiable.
- Appliqué après l'extraction ; les valeurs corrigées passent ensuite par R2 comme n'importe quelle autre.
- **Le pipeline ne dépend jamais de ce fichier pour fonctionner** : R2 neutralise déjà toute anomalie. Une correction améliore la donnée, elle ne débloque rien.
- La ligne de base (§9.3) **et les fixtures** (§9.1) se calculent avec un fichier de corrections **vide**. Un test dédié vérifie qu'une correction ne modifie que ce qui dépend du groupe visé : ses lignes de `bands` et d'`albums`, les cellules de `density` de ses genres, et `genres.n_bands` si la correction peut faire entrer ou sortir le groupe du périmètre.
- Garde-fou : un test échoue au-delà de 50 lignes. Au-delà, c'est une règle qui est fausse, pas la donnée.
- Erreurs réelles identifiées parmi les groupes avec genre : **11** (6 formations illisibles, 3 fins illisibles, 1 formation en 2088, 1 fin antérieure au début), dont 4 dans la population R1. Elles doivent être corrigées **en amont** sur MusicBrainz par le porteur du projet.

### R7 — Présence et densité

Un groupe est **présent** l'année `y` si `y0 ≤ y ≤ fin_de_présence`, avec :

- `fin_de_présence = y_end_declared` si elle existe ;
- sinon `max(y0, y_last_album)` ;
- plafonnée à l'année du dump.

Justification :

- **Une fin déclarée fait foi**, même si le dernier album est antérieur (un groupe actif sans disque pendant ses dernières années reste présent jusqu'à sa fin) et même si des albums lui sont postérieurs : Cardiacs, fin 2020, garde *LSD* (2025) comme point, mais n'est plus présent après 2020.
- **Sans fin déclarée, le dernier album est la dernière preuve**, et `y0` la première : un groupe sans album est présent en `y0` seulement, et un groupe dont tous les albums retenus précèdent sa formation aussi (25 cas, dont Polska Radio One : formé en 2015, albums en 2013 et 2014).
- Mesuré : 6 574 groupes ont une fin déclarée postérieure à leur dernier album et restent présents jusqu'à cette fin ; 594 ont des albums postérieurs à leur fin déclarée et cessent d'être présents à cette fin.

`density(genre, y)` compte les groupes présents portant ce genre. Un groupe à plusieurs genres compte dans chacun : **les totaux par genre ne s'additionnent pas.** Près du présent, la densité est une **borne basse** (voir R4).

Volume mesuré : **51 161 cellules**, 1 236 genres, 1855 à 2026.

La présence de chaque groupe est matérialisée dans une table intermédiaire `presence(mbid, y0, y_presence_end)`, calculée dans `transform` et non publiée : c'est sur elle que portent les invariants de présence (§9.2).

### R8 — Identité

Le MBID est la seule clé, à toutes les étapes. Les noms ne servent jamais de jointure : trois groupes distincts s'appellent « The Beatles » et deux « Orange Juice » dans le dump de référence.

---

## 5. Architecture du pipeline

### 5.1 Étapes

```
fetch        →  extract        →  transform      →  validate     →  publish
dump daté       JSON réduit       SQL, une règle     invariants      Parquet + JSON
empreinte       (projection)      par fichier        (0 ligne)       + manifeste
vérifiée
```

| Étape | Outil | Logique ? |
|---|---|---|
| fetch | Python, bibliothèque standard | non — téléchargement et vérification SHA256 |
| extract | Python, bibliothèque standard, en flux | non — projection des champs utiles, MBID et votes des genres compris |
| transform | DuckDB, `pipeline/sql/NN_*.sql` | **oui — toutes les règles** |
| validate | DuckDB, requêtes d'invariants | contrôle seulement |
| publish | DuckDB + Python | sérialisation seulement |

### 5.2 Choix

- **Aucun PostgreSQL** : les dumps JSON portent tout ce qui est nécessaire.
- **Logique en SQL, pas en Python** : les règles sont des filtres et des jointures ; les tester, c'est tester le SQL qui tournera.
- **Extraction en flux** : 3 Go compressés, ~20 Go décompressés, jamais écrits sur disque ; environ dix minutes mesurées sur 4 cœurs et 5,8 Go de RAM.
- **Environnement** : Python 3.12 géré par `uv` ; DuckDB via son paquet Python, version épinglée ; tests `pytest`.

### 5.3 Reproductibilité

- `pipeline/reference/20260909-001002.SHA256SUMS` (versionné) contient les empreintes officielles des deux archives de référence, copiées depuis le serveur.
- Les archives elles-mêmes sont conservées localement dans `data/raw/20260909-001002/` (non versionné, ~3 Go) ; `fetch` refuse toute archive dont l'empreinte diffère.
- La réponse SPARQL de Wikidata est archivée et datée : `pipeline/reference/20260912-wikidata-genre-parents.csv`, empreinte dans le `.sha256` voisin. Versionner la requête ne fige pas la réponse ; le pipeline lit l'archive, jamais le service en direct.
- Chaque étape est idempotente et rejouable depuis son entrée : `fetch` ne retélécharge pas une archive déjà vérifiée, `extract` réécrit sa sortie, `transform` recrée ses tables avec `CREATE OR REPLACE`.
- Chaque exécution écrit un `manifest.json` : date du dump, empreintes des archives, comptes de chaque table, compteurs d'anomalies R2, identifiant du commit, empreinte de `corrections.csv`.

---

## 6. Arbre des genres — source à trancher

Le schéma est fixé (`genre_parents`, §3.4) ; la source ne l'est pas.

| Candidate | État mesuré |
|---|---|
| **Wikidata** `P279` (sous-classe de), jointe **par MBID** via `P8052` | L'export compte 2 179 MBID distincts portant `P8052`. Sur nos 1 236 genres : 1 236 ont un MBID MusicBrainz, 1 235 sont connus de Wikidata, 967 ont au moins un parent, **951 ont au moins un parent présent dans le vocabulaire (77 %)**. 224 genres ont plusieurs parents. 17 parents distincts sont hors vocabulaire — tous des genres MusicBrainz qu'aucun de nos groupes ne porte. Restreint au vocabulaire : 1 195 arêtes, aucun cycle, 285 racines ; seul `rapcore` n'a pas d'entrée Wikidata. Biais de mesure : l'export ne retient que les parents qui portent eux-mêmes `P8052` ; un parent Wikidata sans équivalent MusicBrainz est invisible. Requête versionnée : `pipeline/reference/wikidata_genre_parents.rq` ; réponse archivée et horodatée : `pipeline/reference/20260912-wikidata-genre-parents.csv`. |
| **MusicBrainz**, relation `subgenre` | Affichée sur les pages HTML des genres (« subgenre of: »). L'API ne la sert pas : `ws/2/genre/<id>?inc=genre-rels` répond HTTP 200 **sans** relations. Absente des dumps JSON (aucun dump `genre`). Présence dans le dump PostgreSQL : **non vérifiée**. |

Joint par MBID, il n'existe pas de doublons de racines : `rock`, `pop`, `electronic` et `hip hop` correspondent chacun à une seule entrée Wikidata.

Chantier parallèle, découplé du reste : mesurer la couverture de la relation MusicBrainz par un moyen autorisé, puis retenir MusicBrainz, Wikidata, ou les deux avec la colonne `source`. **Critère de repli** : si la mesure n'aboutit pas, Wikidata seule fait foi, à 951 genres sur 1 236. D'ici là, `genre_parents` peut rester vide sans bloquer les autres tables.

---

## 7. Livrables

### 7.1 Archive : Parquet

`data/out/<date_dump>/{bands,albums,genres,genre_parents,density}.parquet` + `manifest.json`. Non versionné.

### 7.2 Web : JSON colonnaire gzippé

Format retenu après mesure : JSON colonnaire (`{"name": [...], "y0": [...]}`) gzippé. Décodage mesuré à ~45 ms pour 63 487 lignes, contre ~300 ms pour Parquet via `hyparquet` et un moteur de 9,4 Mo pour DuckDB-Wasm.

Tailles **indicatives**, mesurées sur la sonde avec un schéma antérieur (sans votes, sans MBID de genre, vocabulaire tronqué) ; à remesurer :

| Fichier | gzip |
|---|---|
| groupes, sans MBID | 0,88 Mo |
| albums (offsets + années) | 0,24 Mo |
| genres | 0,01 Mo |
| densité | 0,03 Mo |
| MBID des groupes, fichier séparé chargé à la demande | 1,36 Mo |

---

## 8. Hors périmètre

- Les arêtes de personnel : 646 620 relations « member of band » ; 23,8 % ont une date de début, 24,8 % au moins une date, 12,3 % les deux. Conservées dans l'extraction, **non publiées** en v1.
- Le regroupement des genres en familles de couleur : couche 1.
- DBpedia et tout autre enrichissement.
- La soumission des corrections sur MusicBrainz : action humaine, sur le compte du porteur du projet.
- Tout ce qui touche au rendu.

---

## 9. Stratégie de test

### 9.1 Fixtures réelles et témoins

Des enregistrements **réels**, extraits du dump de référence pour les témoins ci-dessous et leurs release-groups, versionnés dans `pipeline/tests/fixtures/` avec un fichier d'attribution. Aucune donnée inventée. Pour chaque témoin, le résultat attendu est **écrit à la main après inspection de la source** ; les valeurs de la colonne « mesuré » servent de recoupement.

| Groupe | MBID | Règle éprouvée | Mesuré |
|---|---|---|---|
| The Beatles | `b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d` | R3 : bruit posthume, bandes originales | 22 albums, 1963-1970 |
| The Beatles (homonyme) | `9d953ee6-4ea6-4b0e-aea6-7268d380bef1` | R1, R8 : exclu | ni date ni genre |
| The Beatles (homonyme) | `8d3431db-bc83-4dc2-93b8-0e46e31d09f7` | R1, R8 : exclu | ni date ni genre |
| Joy Division | `9a58fda3-f4ed-4080-a3a5-f457aac9fcdd` | R2 : dates au mois | `1978-01` → `1980-05` |
| New Order | `f1106b17-dcbb-45f6-b938-199ccfab50cc` | R4 : non terminé, sans fin | |
| U2 | `a3cb23fc-acd3-4ce0-8f36-1e5aa6a18432` | R4 : actif, aucune fin produite | 30 albums, dernier 2025 |
| Portishead | `8f6bd1e4-fbe1-4f50-aa9b-94c450ec0f11` | R4 : non terminé, sans fin ; R5 : genres votés | |
| XTC | `97c86b2c-2765-46a2-aef8-76a7e24c430f` | R4, R7 : fin datée | fin 2006 |
| Orange Juice | `e598d30e-4ce1-402e-94a7-6f44779da6b7` | R4 : fin datée | fin 1984 |
| Orange Juice (homonyme) | `6959c3d5-3e7f-41bb-aba3-50e38225d23d` | R1, R8 : exclu | ni date ni genre |
| Disincarnate | `a9424175-8b06-44ad-a1f4-319e92a50879` | R5 : un seul genre | |
| 3OH!3 | `125948ec-7f91-4d1a-8b83-accbf50fae3d` | R5 : départage par nom | synth-pop (3), puis crunkcore, electronic, electropop, pop (2 chacun) |
| Lethal Shöck | `d25be955-6fed-4303-bffb-8c440c191edb` | R2.2 : formation 2088 → absente → exclu | |
| Blackdeath | `53fc0417-7585-490c-b2ea-5f9737e14c0f` | R2.4 : fin neutralisée, fenêtre R3 ouverte | 13 albums, 1995-2024 |
| Cleef | `1434b0d0-d647-421e-b345-1b9847045a52` | R2.1 : formation illisible → exclu | `????-??-18` |
| Unheilig | `6dfa03fb-8b02-4055-b7cc-e48f426b13f8` | R2.1 et R3 : fin illisible, `ended = true`, borne haute = année du dump | `????-09` |
| Wiener Philharmoniker | `d770374d-05e9-4ed3-a068-3fbd4e6e4dd6` | R1 : Orchestra exclu | |
| Maroon 5 | `0ab49580-c84f-44d4-875f-d83760ea2cfe` | R3 borne basse | album de 1997 retenu, formé 2001 |
| Polska Radio One | `703c4c92-43f7-4268-9f85-0ca6f0cd1a22` | R7 : plancher `max(y0, y_last_album)` | formé 2015, albums 2013 et 2014 : présent en 2015 seulement |
| Cardiacs | `f7338f2a-136b-4d5e-b099-5504cf997f58` | R3 marge posthume, R7 : fin déclarée fait foi | fin 2020, *LSD* 2025 |
| Fleetwood Mac | `bd13909f-1c29-4c27-a874-d4aaf27c5b1a` | R3 marge posthume ; R3.2 : album à deux artistes distincts, qu'aucun autre filtre n'exclut | fin 2022, album 2023 ; *The Biggest Thing Since Colossus* (1969) écarté |
| ROD | `3cb86073-22d7-43d5-8f22-422b1e54988e` | R4, R7 : aucun album, présent en `y0` seulement | formé 1996 |
| Flesh Field | `212faddb-cd09-4fbc-9336-3ed7cadfba68` | R3 : terminé sans date, bruit tardif retenu | formé 1996, albums jusqu'en 2026 |
| Demented Are Go! | `8a1f012c-acc1-4dda-878f-43ac02f2366f` | R3.2 : même artiste crédité deux fois, retenu | *The Day the Earth Spat Blood*, 1989 |
| The Belle Stars | `62f7a211-0056-45fe-934a-37a388a7356f` | R1.4 : sans genre → exclu | Group, formé 1980, aucun genre |
| Handel and Haydn Society | `35ddcb29-4c16-4af6-b6f8-32143ee24a6c` | R1.3 : formation avant 1850 → exclu | Group, formé 1815, un genre |
| Thunder Jolt | `d36b0fad-abd7-44e4-88fa-f638bbf8c9a6` | R2.3 : fin postérieure à l'année du dump → absente | fin `2027-01-05` |

### 9.2 Invariants

Chacun est une requête qui doit renvoyer zéro ligne, exécutée sur les fixtures **et** sur chaque exécution complète :

- MBID unique et non nul dans `bands` ;
- `1850 ≤ y0 ≤ année du dump` ;
- `y0 ≤ y_end_declared ≤ année du dump` quand présente ;
- `y_last_album = max(albums.y)` du groupe, ou nul s'il n'a pas d'album ;
- tout album appartient à un groupe de `bands`, respecte la fenêtre R3 et a une année au plus égale à l'année du dump ;
- aucun album n'a de type secondaire autre que `Soundtrack` ;
- tout groupe a au moins un genre ; ses genres sont triés par votes décroissants puis par nom ;
- tout genre de `bands` existe dans `genres`, et `genres.n_bands` égale le nombre de groupes qui le portent ;
- tout `genre_parents` référence des genres existants, et le graphe est sans cycle ;
- aucune cellule de `density` au-delà de l'année du dump ; `density.present ≤ genres.n_bands` ;
- dans `presence` : `y0 ≤ y_presence_end ≤ année du dump`, et `y_presence_end = y_end_declared` quand celle-ci existe ;
- `corrections.csv` compte au plus 50 lignes.

### 9.3 Deux niveaux de test

**Rapide — à chaque commit.** Fixtures + invariants sur les fixtures. Quelques secondes, aucune dépendance au dump.

**Complet — manuel.** Pipeline entier sur le dump de référence archivé (~10 min), invariants, puis comparaison **exacte** à la ligne de base, calculée avec un fichier de corrections vide :

| | Ligne de base |
|---|---|
| `bands` | 63 487 |
| `albums` | 189 477 |
| `genres` | 1 236 |
| `density` | 51 161 cellules |

Sur un dump plus récent, les comptes sont rapportés et comparés avec une tolérance de ±2 %. Cette tolérance est un filet grossier : elle ne garantit pas que les règles sont justes — une dérive de règle peut être masquée par la croissance de la base. **La justesse des règles est garantie par les fixtures, pas par les comptes.**

---

## 10. Non vérifié

- La couverture de la relation `subgenre` de MusicBrainz et sa présence dans le dump PostgreSQL (§6).
- L'année de fin réelle d'Unheilig, et plus généralement les valeurs à porter dans `corrections.csv` : chacune exige une source.
- L'interprétation des 18 596 groupes « non terminés, dernier album avant 2020 » : séparation silencieuse ou activité sans disque, la source ne permet pas de trancher.
- La nature exacte des remontages nord-américains des Beatles (certains pourraient être canadiens).
- La présence, dans la population, d'ensembles classiques typés `Group` par la source (exemple observé : Ensemble intercontemporain) ; leur nombre n'est pas mesuré.
- Les tailles du livrable web (§7.2) sous le schéma final.
