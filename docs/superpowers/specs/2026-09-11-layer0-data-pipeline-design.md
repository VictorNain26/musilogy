# Couche 0 — pipeline de données · conception

- **Statut** : brouillon, à relire (relecture indépendante puis relecture humaine)
- **Date** : 2026-09-11
- **Dump de référence** : MusicBrainz JSON dumps `20260909-001002`
- **Portée** : produire, de façon reproductible et testée, le jeu de données qui alimente la frise (couche 1). Aucune interface ici.

Tous les chiffres de ce document ont été **mesurés** sur le dump de référence, par une sonde jetable écrite pendant la phase d'exploration. Ils servent de ligne de base aux tests de non-régression. Rien n'est estimé sauf mention explicite « non vérifié ».

---

## 1. Objet

La couche 0 transforme deux dumps MusicBrainz en quatre tables :

| Table | Contenu | Volume de référence |
|---|---|---|
| `bands` | un groupe = une vie datée, ses genres, sa provenance | 63 487 lignes |
| `albums` | un point = une sortie d'album studio d'un groupe | 189 459 lignes |
| `genres` | le vocabulaire utilisé, avec compte et parent | 1 164 lignes |
| `density` | groupes présents par genre et par année | ~48 000 cellules |

Principe directeur, appliqué à chaque règle : **la sortie n'affirme jamais plus que ce que la source porte.** Une absence de donnée reste une absence ; elle n'est ni imputée ni prolongée.

---

## 2. Sources

### 2.1 Retenue : dumps JSON MusicBrainz

| Fichier | Taille | Usage |
|---|---|---|
| `artist.tar.xz` | 2 Go | groupes, dates, genres (avec votes), zone, relations |
| `release-group.tar.xz` | 1 Go | albums et leur date de première sortie |

Emplacement : `https://data.metabrainz.org/pub/musicbrainz/data/json-dumps/<date>/`.
Format : JSON Lines dans une archive tar, un enregistrement par ligne sous `mbdump/`.

**Complétude mesurée** (dump du 2026-09-09 contre les statistiques officielles du 2026-09-11) :

| | Lu dans le dump | Officiel | Complétude |
|---|---|---|---|
| Artistes | 2 980 305 | 2 982 124 | 99,94 % |
| Release-groups | 4 507 265 | 4 510 822 | 99,92 % |

L'écart correspond à deux jours d'éditions. Les signalements d'incomplétude du forum MetaBrainz concernent les dumps `recording` et `release`, qui ne sont pas utilisés.

### 2.2 Licence

- Données de base (artistes, dates, albums, relations) : **CC0**.
- Genres et tags : données supplémentaires **CC-BY-NC-SA 3.0**.
- Conséquence : le jeu publié par la couche 0 est **CC-BY-NC-SA 3.0**, avec attribution à MusicBrainz. Compatible avec le caractère non commercial du projet. Le partage à l'identique s'impose à toute redistribution.

### 2.3 Écartées (vérifié)

- **Discogs** : l'objet artiste de l'API n'a aucun champ de date ; les membres n'ont pas de dates.
- **Spotify** : dix champs, aucun temporel, aucun membre.
- **Wikidata comme source de dates** : 2 312 dates de dissolution seulement pour 114 335 groupes.
- **DBpedia** : 20 241 dates de fin déclarées ; enrichissement envisageable en v2, pas en v1.

Wikidata reste candidate pour **l'arbre des genres** uniquement (§6).

---

## 3. Modèle de sortie

### 3.1 `bands`

| Champ | Type | Règle |
|---|---|---|
| `mbid` | texte | identifiant MusicBrainz — **seule clé d'identité** (R8) |
| `name` | texte | nom tel que dans la source |
| `y0` | entier | année de formation (R2) |
| `y_end_declared` | entier nul | année de fin déclarée par la source (R2, R4) |
| `y_last_album` | entier nul | année du dernier album retenu (R3, R4) |
| `ended` | booléen | drapeau `ended` de la source, tel quel |
| `country` | texte nul | code pays |
| `city` | texte nul | `begin-area` de la source |
| `genres` | liste | genres triés par votes décroissants (R5) |

Pas de champ « année de fin » calculé. Voir R4.

### 3.2 `albums`

| Champ | Type |
|---|---|
| `band_mbid` | texte |
| `rg_mbid` | texte |
| `title` | texte |
| `y` | entier |
| `soundtrack` | booléen |

### 3.3 `genres`

| Champ | Type |
|---|---|
| `genre_mbid` | texte |
| `name` | texte |
| `n_bands` | entier |
| `parent_mbid` | texte nul (§6) |

### 3.4 `density`

`(genre_mbid, year, present)` — nombre de groupes dont la présence est **attestée** cette année-là (R7).

---

## 4. Règles

Chaque règle vit dans son propre fichier SQL numéroté et possède ses tests (§9).

### R1 — Population

Un artiste entre dans `bands` si et seulement si :

1. `type = 'Group'` ;
2. son année de formation est lisible (R2) ;
3. `1850 ≤ y0 ≤ année du dump` ;
4. il porte au moins un genre.

Effet mesuré : 682 447 artistes de type Group, Orchestra ou Choir → **63 487**.

Orchestres et chœurs sont exclus (630 entités dans la fenêtre) : leur modèle — existence séculaire, répertoire d'autrui — ne correspond pas à une ligne de vie de groupe. Avec ce filtre, la formation la plus ancienne est en 1855 et 9 groupes seulement précèdent 1900.

### R2 — Dates

- L'année est lue sur les quatre premiers caractères ; si ce ne sont pas quatre chiffres, la date est **absente** (cas mesuré : `????-??-18`, `????-09`).
- La précision au mois ou au jour n'est pas conservée en v1.
- Anomalies détectées sur les 682 447 groupes : 41 dates illisibles, 15 formations dans le futur, 2 fins antérieures au début — 0,046 % au total.
- Une année antérieure à 1850 **n'est pas une anomalie** : 27 cas mesurés, tous exacts (Wiener Philharmoniker 1842, Regensburger Domspatzen 975…). Ils sont hors périmètre par R1, pas « corrigés ».

### R3 — Albums

Un release-group est retenu comme album d'un groupe si et seulement si :

1. `primary-type = 'Album'` ;
2. il est crédité à **un seul** artiste, et cet artiste est dans `bands` ;
3. sa date de première sortie a une année lisible ;
4. ses types secondaires sont **vides ou exactement `{Soundtrack}`** ;
5. son année est dans `[y0 − 5, borne_haute + 5]`, où `borne_haute = y_end_declared` si elle existe, sinon l'année du dump.

Effets mesurés :

- 2 317 879 albums dans la base, dont 94,7 % datés.
- Retenus : **189 459**.
- Conserver `Soundtrack` ajoute 538 albums (sinon *A Hard Day's Night*, *Help!*, *Yellow Submarine* disparaîtraient des Beatles).
- La fenêtre de ±5 ans écarte 1,4 % des albums joints, et élimine le bruit posthume : Beatles, 72 release-groups « Album » sans type secondaire → 18 après fenêtre.

Limites connues et acceptées :

- Les albums crédités à plusieurs artistes (9,1 % des albums) sont écartés.
- Les remontages contemporains restent : 9 remontages américains des Beatles (*Meet The Beatles!*, *Beatles '65*…) sont conservés. Ils ont réellement été publiés à ces dates.
- Pour un groupe sans fin déclarée qui s'est en réalité séparé, la fenêtre ne protège pas du bruit posthume.

### R4 — Bord droit : des preuves, jamais une fin inventée

La couche 0 **ne calcule pas d'année de fin**. Elle transporte trois preuves indépendantes : `y_end_declared`, `y_last_album`, `ended`.

Statut mesuré des 63 487 groupes :

| Statut | Groupes |
|---|---|
| fin datée | 14 739 |
| terminé sans date, avec albums | 891 |
| terminé sans date, sans album | 849 |
| non terminé, dernier album ≥ 2020 | 18 431 |
| non terminé, dernier album < 2020 | 18 596 |
| non terminé, aucun album | 9 981 |

Pourquoi aucune fin n'est calculée : la règle « fin déclarée, sinon dernier album » ferait s'arrêter 18 431 groupes vraisemblablement actifs à la date de leur dernier disque (U2 en 2023). À l'inverse, prolonger jusqu'à aujourd'hui les groupes sans fin fabrique de la présence : en 2024, 50,5 % des groupes qui seraient comptés « vivants » n'ont aucune preuve de l'être.

Le rendu de l'incertitude — trait plein jusqu'à la dernière preuve, prolongement estompé ou non — relève de la couche 1.

### R5 — Genres

- Tous les genres d'un groupe sont conservés, **triés par nombre de votes décroissant, puis par nom** en cas d'égalité.
- La source ne garantit pas cet ordre ; le tri est explicite.
- Un groupe porte en moyenne 2,08 genres, au maximum 116 : aucun plafond n'est appliqué en couche 0 ; l'affichage des trois premiers relève de la couche 1.
- L'identifiant MBID de chaque genre est conservé : c'est la clé de jointure de l'arbre (§6).

### R6 — Corrections manuelles

- Fichier `pipeline/corrections.csv`, versionné : `mbid, champ, valeur, justification, source`.
- Appliqué **après l'extraction et avant R1**, parce qu'une correction peut faire entrer ou sortir un groupe du périmètre.
- Jamais de modification des données importées : le dump est remplacé deux fois par semaine.
- **Garde-fou** : un test échoue si le fichier dépasse 50 lignes. Au-delà, c'est une règle qui est fausse, pas la donnée.
- 12 erreurs réelles identifiées dans le périmètre (1 formation en 2088, 2 fins antérieures au début, 6 débuts illisibles, 3 fins illisibles). Elles doivent être corrigées **en amont** sur MusicBrainz par le porteur du projet ; le fichier local couvre l'intervalle jusqu'au dump suivant.

### R7 — Densité

Un groupe est **présent** l'année `y` si `y0 ≤ y ≤ max(y_end_declared, y_last_album)`, les valeurs nulles étant ignorées. Un groupe sans aucune des deux preuves n'est présent qu'en `y0`.

`density(genre, y)` compte les groupes présents portant ce genre. Un groupe à trois genres compte dans trois cellules : les totaux par genre **ne s'additionnent pas**.

Volume mesuré : 1 163 genres × 172 ans, 48 457 cellules non nulles, 144 Ko en Parquet.

### R8 — Identité

Le MBID est la seule clé, à toutes les étapes. Les noms ne sont jamais utilisés pour joindre : trois artistes distincts s'appellent « The Beatles » et deux « Orange Juice » dans le dump de référence.

---

## 5. Architecture du pipeline

```
fetch      →  extract       →  transform      →  validate     →  publish
dump daté     JSON réduit      SQL, une règle     invariants      Parquet + JSON
vérifié       (projection)     par fichier        (0 ligne)       + manifeste
```

| Étape | Outil | Contient de la logique ? |
|---|---|---|
| fetch | Python, bibliothèque standard | non |
| extract | Python, bibliothèque standard, en flux | non — projection des champs utiles uniquement |
| transform | DuckDB, fichiers `pipeline/sql/NN_*.sql` | **oui — toutes les règles** |
| validate | DuckDB, requêtes d'invariants | contrôle seulement |
| publish | DuckDB + Python | sérialisation seulement |

Choix justifiés :

- **Aucun PostgreSQL.** Les dumps JSON portent tout ce qui est nécessaire. La voie relationnelle officielle (7 Go + import) n'apporte rien ici.
- **Logique en SQL, pas en Python** : les règles sont des filtres et des jointures ; les tester, c'est tester le SQL qui tournera réellement.
- **Extraction en flux** : 3 Go compressés, ~20 Go décompressés, jamais écrits sur disque. Mesuré : environ dix minutes sur 4 cœurs et 5,8 Go de RAM.
- **Environnement** : Python 3.12 géré par `uv` ; DuckDB via son paquet Python, version épinglée ; tests `pytest`.

Reproductibilité : chaque exécution écrit un `manifest.json` — date du dump, tailles des archives, comptes de chaque table, identifiant du commit.

---

## 6. Arbre des genres — question ouverte

La couche 1 a besoin d'un parent pour chaque genre. **La source n'est pas encore tranchée.**

| Candidate | État mesuré |
|---|---|
| Wikidata `P279` (sous-classe de), jointe par `P8052` (MusicBrainz genre ID) | 2 177 genres Wikidata portent `P8052`. Sur nos 1 164 : 930 connus, 761 avec parent déclaré, dont **411 seulement** ont un parent qui est lui-même dans nos 1 164 ; les 350 autres pointent vers 74 parents absents du vocabulaire (« classical music », « club/dance music »…). Doublons de racines : `rock` / `rock music`, `pop` / `pop music`. |
| MusicBrainz, relation `subgenre` | Affichée sur les pages HTML des genres (« subgenre of: »). **Non servie par l'API** : `ws/2/genre/<id>?inc=genre-rels` renvoie HTTP 503 de façon constante (mesuré le 2026-09-11) alors que la même requête sans `inc` renvoie 200. Absente des dumps JSON. Présence dans le dump PostgreSQL : **non vérifiée**. |

Première tâche du plan : mesurer la couverture de la relation MusicBrainz sur nos 1 164 genres, puis choisir. Tant que ce n'est pas fait, `parent_mbid` peut rester nul sans bloquer les autres tables.

---

## 7. Livrables

### 7.1 Archive : Parquet

`data/out/<date_dump>/{bands,albums,genres,density}.parquet` + `manifest.json`. Non versionné (`data/` est ignoré par git).

### 7.2 Web : JSON colonnaire gzippé

Format retenu après mesure : JSON colonnaire (`{"name": [...], "y0": [...]}`), gzippé. Décodage mesuré à ~45 ms pour 63 487 lignes, contre ~300 ms pour Parquet via `hyparquet` et un moteur de 9,4 Mo pour DuckDB-Wasm.

Tailles mesurées sur la sonde (indicatives — R4 et R5 modifient le schéma) :

| Fichier | gzip |
|---|---|
| groupes, sans MBID | 0,88 Mo |
| albums (offsets + années) | 0,24 Mo |
| genres | 0,01 Mo |
| densité | 0,03 Mo |
| **total chargé** | **1,16 Mo** |
| MBID, fichier séparé chargé à la demande | 1,36 Mo |

---

## 8. Hors périmètre

- Les arêtes de personnel (646 620 relations « member of band », 23,8 % datées) : conservées dans l'extraction réduite, **non publiées** en v1.
- Le regroupement des genres en familles de couleur : décision de présentation, couche 1.
- DBpedia et tout autre enrichissement.
- La soumission des corrections sur MusicBrainz : action humaine, sur le compte du porteur du projet.
- Tout ce qui touche au rendu.

---

## 9. Stratégie de test

### 9.1 Fixtures réelles

Des enregistrements **réels**, extraits du dump de référence pour une liste de groupes-témoins, avec leurs release-groups, versionnés dans `pipeline/tests/fixtures/` avec un fichier d'attribution. Aucune donnée inventée.

Pour chaque témoin, le résultat attendu est **écrit à la main** après inspection de la source.

| Groupe | MBID | Ce qu'il éprouve |
|---|---|---|
| The Beatles | `b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d` | bruit posthume, bandes originales, remontages US |
| The Beatles (homonyme) | `9d953ee6-4ea6-4b0e-aea6-7268d380bef1` | exclu : ni date ni genre |
| The Beatles (homonyme) | `8d3431db-bc83-4dc2-93b8-0e46e31d09f7` | exclu : ni date ni genre |
| Joy Division | `9a58fda3-f4ed-4080-a3a5-f457aac9fcdd` | dates au mois (`1978-01` → `1980-05`) |
| New Order | `f1106b17-dcbb-45f6-b938-199ccfab50cc` | non terminé, sans fin déclarée |
| U2 | `a3cb23fc-acd3-4ce0-8f36-1e5aa6a18432` | actif, album récent : ne doit recevoir aucune fin |
| Portishead | `8f6bd1e4-fbe1-4f50-aa9b-94c450ec0f11` | non terminé, genres votés |
| XTC | `97c86b2c-2765-46a2-aef8-76a7e24c430f` | fin datée (2006) |
| Orange Juice | `e598d30e-4ce1-402e-94a7-6f44779da6b7` | fin datée (1984) |
| Orange Juice (homonyme) | `6959c3d5-3e7f-41bb-aba3-50e38225d23d` | exclu : ni date ni genre |
| Disincarnate | `a9424175-8b06-44ad-a1f4-319e92a50879` | un seul genre |
| 3OH!3 | `125948ec-7f91-4d1a-8b83-accbf50fae3d` | 14 genres : tri par votes |
| Lethal Shöck | `d25be955-6fed-4303-bffb-8c440c191edb` | formation en 2088 : hors périmètre sans correction |
| Blackdeath | `53fc0417-7585-490c-b2ea-5f9737e14c0f` | fin antérieure au début : correction R6 |
| Cleef | `1434b0d0-d647-421e-b345-1b9847045a52` | début `????-??-18` : date absente |
| Unheilig | `6dfa03fb-8b02-4055-b7cc-e48f426b13f8` | fin `????-09` : date absente |
| Wiener Philharmoniker | `d770374d-05e9-4ed3-a068-3fbd4e6e4dd6` | Orchestra : exclu par R1 |

À compléter pendant l'écriture des fixtures : un groupe non terminé sans aucun album, et un groupe dont un album est crédité à plusieurs artistes. Leurs MBID ne sont pas encore identifiés.

### 9.2 Invariants

Exécutés sur les fixtures **et** sur chaque exécution complète ; chacun est une requête qui doit renvoyer zéro ligne :

- MBID unique et non nul dans `bands` ;
- `1850 ≤ y0 ≤ année du dump` ;
- `y_end_declared ≥ y0` quand présente ;
- tout album appartient à un groupe de `bands` et respecte la fenêtre R3 ;
- aucun album n'a de type secondaire autre que `Soundtrack` ;
- tout groupe porte au moins un genre, et ses genres sont triés par votes ;
- tout `parent_mbid` renvoie à un genre existant, et le graphe des parents est sans cycle ;
- `corrections.csv` compte au plus 50 lignes.

### 9.3 Non-régression

Sur le dump de référence, les comptes sont **exacts** : 63 487 groupes, 189 459 albums, 1 164 genres. Toute divergence fait échouer le test.

Sur un dump plus récent, tolérance de ±2 % ; au-delà, le test échoue et la ligne de base doit être mise à jour délibérément, dans un commit dédié qui en donne la raison.

Note : R4 et R5 modifient le schéma par rapport à la sonde ; les comptes de lignes ne doivent pas bouger. Si R5 déplace des groupes dans ou hors du périmètre, c'est un bug.

---

## 10. Non vérifié

- La source de l'arbre des genres (§6).
- La présence de sommes de contrôle publiées pour les dumps JSON MusicBrainz.
- La liste exacte d'albums attendue pour les Beatles avec `Soundtrack` conservé : à établir à la main pendant l'écriture des fixtures.
- L'interprétation des 18 596 groupes « non terminés, dernier album avant 2020 » : séparation silencieuse ou activité sans disque, la source ne permet pas de trancher.
