# Couche 1 — la frise chronologique

Conception validée le 2026-09-13. La couche 0 est en place et produit une
livraison reproductible ; ce document décrit le consommateur.

Les chiffres cités ici sont **descriptifs**, mesurés sur le dump de référence
`20260909-001002`. Le contrat exécutable reste `tests/test_baseline.py`.

## Objet

Une frise qui montre la vie des genres musicaux dans le temps, et permet de
descendre jusqu'aux groupes qui la composent. Deux échelles, un seul objet :
la densité par genre en vue d'entrée, les artistes individuels au zoom.

L'application et le pipeline vivent dans le même dépôt. Ce n'est pas une
séparation de produit mais de responsabilité : le SQL arbitre, le Python
enchaîne et publie, le front rend. La couche 0 a toujours été écrite pour ce
consommateur — `density` est décrite dès le `CLAUDE.md` comme une projection
destinée à la frise.

## Ce que la mesure a établi

Cinq mesures fondent les décisions qui suivent. Aucune n'était acquise avant
d'être prise.

**La vue agrégée ne pèse rien.** `density` + le vocabulaire font 113 Ko gzip
pour 52 201 cellules, 1 299 genres, 172 ans. Le tri introduit par la PR #4 y a
divisé `density.json.gz` par 9,4, de 655 709 à 70 106 octets.

**La population plaçable est plus petite qu'annoncé.** 84 722 groupes sont à la
fois de type `Group`, datés et porteurs d'un genre — pas les 380 866 lignes de
`bands_timeline`, qui incluent tout ce qui n'a pas de genre. 186 071 paires
groupe-genre en découlent.

**Le poids du JSON est celui de l'identité.** Sur les 16,31 Mo gzip de
`bands_timeline`, `mbid` pèse 7,79 Mo (48 %) et `name` 3,09 Mo (19 %). Les UUID
en texte ne se compressent pas.

**Un format binaire réduit le transport d'un facteur 14,6 et la lecture d'un
facteur 106** : 1,12 Mo et 18 ms, contre 16,31 Mo et 953 ms pour le JSON
(mesuré sous Node 24).

**Aucun format standard ne fait mieux ici.** Parquet zstd au même contenu fait
1,17 Mo — équivalent — mais se décode en 279 ms via hyparquet, qui ajoute
824 Ko de dépendances. Arrow pèse 5,82 Mo décompressé pour 1 Mo de données. Le
format maison est retenu sur mesure, pas par réflexe, et il ne remplace rien :
les cinq Parquet restent l'archive interopérable.

## Architecture des données

Deux fichiers produits par `publish.py`, à côté des projections existantes.

`web/frieze.bin.gz` (~1,12 Mo) porte tout ce qu'il faut pour dessiner.
`web/frieze_ids.bin.gz` (~1,35 Mo) porte les `mbid` bruts sur 16 octets, chargé
au premier clic seulement : ils ne servent qu'à ouvrir MusicBrainz et sont
incompressibles par nature.

### Format de `frieze.bin`

Little-endian. **Les sections vont du type le plus large au plus étroit**, car
un `TypedArray` dont l'offset n'est pas un multiple de la taille de son élément
lève une `RangeError` — vérifié, ce n'est pas une précaution de style.

| section | type | longueur | rôle |
|---|---|---|---|
| magic + version | `u8[4]` + `u16` + padding `u16` | 8 o | `MFZ1` |
| `n_bands`, `n_pairs` | `u32` × 2 | 8 o | cardinalités |
| `name_offsets` | `u32` | `n+1` | bornes dans `names` |
| `genre_offsets` | `u32` | `n+1` | bornes dans `genre_ids` |
| `spans` | `u16` | `2n` | `y0`, `y_presence_end` + 2 bits de drapeaux |
| `genre_ids` | `u16` | `n_pairs` | index dans le vocabulaire |
| `names` | UTF-8 | reste | noms concaténés |

Les groupes sont triés par `(y0, mbid)`, ce qui rend `spans` monotone sur sa
première composante et le compresse bien. L'index de ligne est l'identité
côté client ; `frieze_ids.bin` est aligné sur le même ordre, ce qui rend la
jointure implicite.

`genre_ids` indexe le vocabulaire de `web/genres.json.gz`, qui reste en JSON :
1 348 entrées, 43 Ko, et il porte déjà `density_eligible` et les deux mesures
qui motivent la règle d'exclusion.

### Reproductibilité

Les deux blobs entrent dans la livraison et donc dans `output_sha256`
(PR #5). L'écriture suit les règles posées par la PR #4 : ordre total, et
`mtime=0` sur le gzip.

## Versionnement et déploiement

Les blobs sont **versionnés dans le dépôt**, contrairement au reste de `data/`.
La règle « les sorties ne sont pas versionnées » visait des Parquet de 25 Mo ;
1,12 Mo est le poids d'une photo, et le bénéfice est net : développement et
production lisent le même fichier, GitHub Pages sert le dépôt tel quel, et la
CI n'a besoin ni du dump de 2,8 Go ni des dix minutes du pipeline.

Le chemin versionné est `web/public/data/`, alimenté depuis
`data/out/<dump>/web/` par une commande explicite — jamais par le pipeline
lui-même, qui doit rester capable de tourner sans toucher au dépôt.

## Rendu

Canvas 2D, sans bibliothèque. Les échelles d'une frise sont deux fonctions
affines et les axes quelques traits : `d3-scale` tirerait quatre dépendances,
figées depuis 2021, pour ce que dix lignes font.

Deux échelles et une transition :

- **agrégée** — une bande par genre, épaisseur proportionnelle au nombre de
  groupes actifs l'année considérée. 52 201 cellules, tout en mémoire.
- **détaillée** — une barre par groupe, de `y0` à `y_presence_end`. Jusqu'à
  10 527 barres pour `rock`, 84 722 si aucun genre n'est sélectionné.

Stratégie : dessin dans un bitmap hors écran, re-blitté au déplacement,
redessiné au zoom et au changement de sélection. **Ce choix est à vérifier en
conditions réelles** — si le redessin dépasse le budget d'image, le recours est
WebGL, et la décision se prendra sur une mesure, pas sur une intuition.

### Le piège de rendu que la couche 0 signale

`y_presence_end` vaut `y0` quand la fin est inconnue : 22 496 groupes sur 84 722
(26,6 %) se réduisent alors à une barre d'un an, dont 9 788 qui ne sont pas
terminés et n'ont aucune preuve de fin. Le rendu doit lire `ended` et
`y_end_source` pour distinguer une fin déclarée d'une absence de preuve, faute
de quoi il affirme qu'un groupe formé en 2026 a duré un an. Le README nomme ce
cas comme le rendu faux le plus probable d'une première intégration ; il est
traité dès la première version, pas après.

Conséquence sur le format : `y_end_source` et `ended` doivent voyager dans le
blob. Deux bits par groupe suffisent, logés dans les deux bits hauts de
`spans`, qui est donc non signé : une année de la fenêtre 1850-2026 tient dans
les 14 bits restants, qui vont jusqu'à 16 383.

## Ordre des genres

Les 1 348 genres sont plats. Le README a mesuré que l'arbre Wikidata casse là
où ça compte : `black metal`, `death metal`, `thrash metal` et `doom metal` ne
figurent pas parmi les descendants de `metal`.

L'ordre d'affichage est donc **dérivé de nos propres données** : deux genres
sont proches s'ils partagent des groupes. 49 321 groupes portent plusieurs
genres, 2,08 en moyenne, et 7 347 paires de genres co-occurrent sur au moins
5 groupes — le signal existe. L'ordre est calculé en couche 0, publié comme une
colonne du vocabulaire, et testé comme le reste.

Ce n'est pas une hiérarchie et ne s'en donne pas l'air : c'est un ordre qui met
les voisins côte à côte. La donnée ne porte pas de taxonomie et la frise n'en
inventera pas.

## Licence

Le dépôt n'en déclarait aucune, ce qui le rendait tous droits réservés par
défaut. Deux licences, chacune sur ce qu'elle couvre :

- **code** (pipeline et application) — MIT, déclaré dans `LICENSE` et dans
  `pyproject.toml` ;
- **données produites** — CC-BY-NC-SA 3.0, imposé par les genres et tags
  MusicBrainz dont `bands` et `genres` dépendent, déclaré dans
  `LICENSE-DATA` et déjà décrit dans le README.

Les blobs versionnés relèvent de la seconde.

## Tests

Le front ajoute deux niveaux, sans rien retirer à l'existant.

**Côté Python**, l'écriture du blob se teste comme le reste de `publish.py` :
sur les témoins, et par la ligne de base sur le dump réel. Un test relit le
blob écrit et vérifie qu'il rend exactement les mêmes groupes que la table
`bands`, spans et genres compris. C'est ce test qui empêche le format de
dériver silencieusement.

**Côté front**, la lecture du blob est une fonction pure de `ArrayBuffer` vers
des tableaux typés : elle se teste sans navigateur, sur un blob de témoins
produit par la suite Python. Le rendu lui-même n'est pas testé pixel à pixel ;
ce qui est testé est ce qui se trompe — la projection année vers pixel, la
sélection d'un genre, et la règle de fin inconnue.

La CI ajoute une étape Node à côté des étapes Python existantes.

## Hors périmètre

`members` (601 759 relations) n'entre pas dans la frise. `bands_rest` — les
groupes sans `y0`, non plaçables — non plus : ils ne sont pas sur une frise par
définition. La recherche par nom parmi 84 722 entrées est un filtre linéaire de
quelques millisecondes et n'appelle aucun index.

`web/bands_timeline.json.gz` et `web/bands_rest.json.gz` deviennent sans
consommateur une fois le blob en place. Leur retrait est un changement de
contrat de livraison : il se fait dans sa propre PR, après que la frise
fonctionne, pas avant.
