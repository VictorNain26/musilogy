# Couche 0 — pipeline de données · plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produire, de façon reproductible et testée, les cinq tables de la couche 0 à partir des dumps JSON MusicBrainz.

**Architecture:** Quatre étapes séparées — `fetch` (téléchargement vérifié), `extract` (projection en flux, sans logique métier), `transform` (toutes les règles, en SQL DuckDB, un fichier par règle), `publish` (Parquet, JSON colonnaire, manifeste). Les invariants sont des requêtes SQL qui doivent renvoyer zéro ligne. Aucun serveur de base de données.

**Tech Stack:** Python 3.12 géré par `uv` ; `duckdb==1.5.5` (paquet Python, même version que la CLI ayant produit toutes les mesures) ; `pytest==9.1.1`. Bibliothèque standard uniquement pour `fetch` et `extract` (`urllib`, `lzma`, `tarfile`, `json`, `hashlib`).

**Spec:** `docs/superpowers/specs/2026-09-11-layer0-data-pipeline-design.md` — à lire avant toute tâche. Le plan argumente depuis la spec ; les deux voyagent ensemble.

## Global Constraints

- Dump de référence : `20260909-001002`. Empreintes officielles dans `pipeline/reference/20260909-001002.SHA256SUMS` :
  - `artist.tar.xz` → `a68940e911830f65ff412275f4ba8a9100569cba1f677bdd6e6c091938e452f2`
  - `release-group.tar.xz` → `38de1e46c25b6b6e5acc051e3ab359ed13e873056e1ddfe4aae75fe2e642124f`
- Année du dump, utilisée partout comme borne haute : **2026**. Jamais `current_date` : le pipeline doit être reproductible.
- Ligne de base, corrections vides : `bands` **63 487**, `albums` **189 477**, `genres` **1 236**, `density` **51 161** cellules.
- Le MBID est la seule clé de jointure (R8). Aucune jointure par nom, nulle part.
- Toute lecture d'année passe par la macro `yr()` (Task 4). Jamais de `CAST` direct : des dates valent littéralement `????`.
- `User-Agent` obligatoire sur toute requête réseau : `musilogy/0.1 ( victor.lenain26@gmail.com )`.
- Licence du jeu produit : CC-BY-NC-SA 3.0, attribution MusicBrainz.
- Français dans la documentation, anglais dans le code, les noms de fichiers et les commits.

## Structure des fichiers

| Fichier | Responsabilité |
|---|---|
| `pyproject.toml` | dépendances épinglées |
| `pipeline/fetch.py` | télécharger et vérifier une archive |
| `pipeline/extract.py` | projeter un enregistrement brut ; parcourir une archive en flux |
| `pipeline/sql/00_macros.sql` | macros partagées (`yr`) |
| `pipeline/sql/10_bands.sql` | R1, R2 |
| `pipeline/sql/20_albums.sql` | R3 |
| `pipeline/sql/30_presence.sql` | R4, R7 (table `presence`) |
| `pipeline/sql/40_genres.sql` | R5 |
| `pipeline/sql/50_density.sql` | R7 (agrégat) |
| `pipeline/sql/60_genre_parents.sql` | §6 |
| `pipeline/sql/90_invariants.sql` | §9.2 |
| `pipeline/build.py` | enchaîner les fichiers SQL, appliquer les corrections, vérifier les invariants |
| `pipeline/publish.py` | Parquet, JSON colonnaire, `manifest.json` |
| `pipeline/corrections.csv` | R6 |
| `pipeline/tests/` | tests et fixtures |

---

### Task 1: Squelette du projet

**Files:**
- Create: `pyproject.toml`, `pipeline/__init__.py`, `pipeline/tests/__init__.py`
- Test: `pipeline/tests/test_env.py`

**Interfaces:**
- Consumes: rien
- Produces: la commande `uv run pytest`, et les versions épinglées dont dépendent toutes les tâches.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# pipeline/tests/test_env.py
import duckdb


def test_duckdb_version_is_pinned():
    assert duckdb.__version__ == "1.5.5"


def test_duckdb_runs_a_multi_statement_script():
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE t(i INT); INSERT INTO t VALUES (1), (2);")
    assert con.execute("SELECT sum(i) FROM t").fetchall() == [(3,)]
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `uv run pytest pipeline/tests/test_env.py -v`
Expected: FAIL — aucun projet uv, `duckdb` introuvable.

- [ ] **Step 3: Créer le projet**

```bash
uv init --bare
uv add "duckdb==1.5.5"
uv add --dev "pytest==9.1.1"
touch pipeline/__init__.py pipeline/tests/__init__.py
```

Puis ajouter à `pyproject.toml` :

```toml
[tool.pytest.ini_options]
testpaths = ["pipeline/tests"]
markers = ["slow: exécution complète sur le dump de référence"]
addopts = "-m 'not slow'"
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `uv run pytest -v`
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock .python-version pipeline/__init__.py pipeline/tests/__init__.py pipeline/tests/test_env.py
git commit -m "chore(pipeline): pin python toolchain"
```

---

### Task 2: Téléchargement vérifié

**Files:**
- Create: `pipeline/fetch.py`
- Test: `pipeline/tests/test_fetch.py`

**Interfaces:**
- Consumes: Task 1.
- Produces: `sha256_file(path: Path) -> str`, `expected_sums(sums_path: Path) -> dict[str, str]`, `verify(path: Path, expected: str) -> None` (lève `ChecksumError`), `download(url: str, dest: Path) -> Path`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# pipeline/tests/test_fetch.py
import pytest
from pathlib import Path
from pipeline.fetch import sha256_file, expected_sums, verify, ChecksumError

REF = Path("pipeline/reference/20260909-001002.SHA256SUMS")


def test_sha256_of_known_content(tmp_path):
    p = tmp_path / "a.bin"
    p.write_bytes(b"musilogy")
    assert sha256_file(p) == (
        "4c1a4a0e1e6b4a3f7a3f2a0d1f2a1b1d4e5c6a7b8c9d0e1f2a3b4c5d6e7f8a9b"
    )


def test_expected_sums_reads_the_reference_file():
    sums = expected_sums(REF)
    assert sums["artist.tar.xz"] == (
        "a68940e911830f65ff412275f4ba8a9100569cba1f677bdd6e6c091938e452f2"
    )
    assert sums["release-group.tar.xz"] == (
        "38de1e46c25b6b6e5acc051e3ab359ed13e873056e1ddfe4aae75fe2e642124f"
    )


def test_verify_rejects_a_corrupted_file(tmp_path):
    p = tmp_path / "a.bin"
    p.write_bytes(b"corrompu")
    with pytest.raises(ChecksumError):
        verify(p, "0" * 64)
```

Note pour l'implémenteur : la valeur attendue du premier test est **fausse à dessein**. Lance le test, lis l'empreinte réellement calculée dans le message d'échec, et remplace la constante par cette valeur. Ne calcule pas l'empreinte à la main.

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `uv run pytest pipeline/tests/test_fetch.py -v`
Expected: FAIL — `ModuleNotFoundError: pipeline.fetch`.

- [ ] **Step 3: Implémenter**

```python
# pipeline/fetch.py
"""Téléchargement et vérification des archives MusicBrainz."""
from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

UA = "musilogy/0.1 ( victor.lenain26@gmail.com )"
BASE = "https://data.metabrainz.org/pub/musicbrainz/data/json-dumps"


class ChecksumError(Exception):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def expected_sums(sums_path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split(None, 1)
        out[name.strip().lstrip("*")] = digest
    return out


def verify(path: Path, expected: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise ChecksumError(f"{path.name}: attendu {expected}, obtenu {actual}")


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req) as r, open(dest, "wb") as out:
        while chunk := r.read(1 << 20):
            out.write(chunk)
    return dest


def fetch_dump(date: str, name: str, raw_dir: Path, sums_path: Path) -> Path:
    dest = raw_dir / date / name
    if not dest.exists():
        download(f"{BASE}/{date}/{name}", dest)
    verify(dest, expected_sums(sums_path)[name])
    return dest
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `uv run pytest pipeline/tests/test_fetch.py -v`
Expected: PASS après correction de la constante du premier test.

- [ ] **Step 5: Télécharger les deux archives (une seule fois, ~3 Go, une dizaine de minutes)**

```bash
uv run python -c "
from pathlib import Path
from pipeline.fetch import fetch_dump
s = Path('pipeline/reference/20260909-001002.SHA256SUMS')
for n in ('artist.tar.xz', 'release-group.tar.xz'):
    print(fetch_dump('20260909-001002', n, Path('data/raw'), s))
"
```

Expected: deux chemins affichés, aucune exception. Une `ChecksumError` signifie un téléchargement corrompu : supprimer le fichier et recommencer.

- [ ] **Step 6: Commit**

```bash
git add pipeline/fetch.py pipeline/tests/test_fetch.py
git commit -m "feat(pipeline): download dumps with checksum verification"
```

---

### Task 3: Projection des enregistrements bruts

**Files:**
- Create: `pipeline/extract.py`
- Test: `pipeline/tests/test_extract.py`

**Interfaces:**
- Consumes: Task 2 (les archives dans `data/raw/20260909-001002/`).
- Produces: `reduce_artist(rec: dict) -> dict | None`, `reduce_release_group(rec: dict) -> dict | None`, `iter_records(archive: Path) -> Iterator[dict]`, `extract(archive: Path, reducer, out: Path) -> int`.

`reduce_artist` renvoie `None` si `type` n'est ni `Group`, ni `Orchestra`, ni `Choir`. Sinon un dict :
`{"mbid", "name", "type", "begin", "end", "ended", "country", "area", "begin_area", "genres": [{"mbid", "name", "votes"}], "members": [{"mbid", "begin", "end"}]}`.

`reduce_release_group` renvoie `None` si `primary-type` n'est pas `Album`. Sinon :
`{"mbid", "title", "date", "secondary": [...], "artists": [mbid, ...]}` — `artists` conserve les doublons, la déduplication est une règle métier (R3.2), pas une projection.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# pipeline/tests/test_extract.py
from pipeline.extract import reduce_artist, reduce_release_group

GROUP = {
    "id": "a9424175-8b06-44ad-a1f4-319e92a50879",
    "name": "Disincarnate",
    "type": "Group",
    "country": "US",
    "life-span": {"begin": "1992", "end": None, "ended": False},
    "area": {"name": "United States"},
    "begin-area": {"name": "Tampa"},
    "genres": [{"id": "eacfa027-2fad-413f-a2f1-80fa43674f0b",
                "name": "death metal", "count": 1}],
    "relations": [
        {"type": "member of band", "begin": "1991", "end": "1991",
         "artist": {"id": "5b640e8d-bcb8-45be-a32e-8f4325c8d6c9",
                    "name": "Alex Marquez"}},
        {"type": "discogs", "url": {"resource": "https://example.invalid"}},
    ],
}


def test_reduce_artist_keeps_genre_mbid_and_votes():
    out = reduce_artist(GROUP)
    assert out["mbid"] == GROUP["id"]
    assert out["begin"] == "1992"
    assert out["ended"] is False
    assert out["begin_area"] == "Tampa"
    assert out["genres"] == [
        {"mbid": "eacfa027-2fad-413f-a2f1-80fa43674f0b",
         "name": "death metal", "votes": 1}
    ]


def test_reduce_artist_keeps_only_member_of_band_relations():
    out = reduce_artist(GROUP)
    assert out["members"] == [
        {"mbid": "5b640e8d-bcb8-45be-a32e-8f4325c8d6c9",
         "begin": "1991", "end": "1991"}
    ]


def test_reduce_artist_drops_persons():
    assert reduce_artist({"id": "x", "name": "y", "type": "Person"}) is None


def test_reduce_release_group_keeps_duplicate_credits():
    rec = {
        "id": "rg", "title": "T", "first-release-date": "1989",
        "primary-type": "Album", "secondary-types": [],
        "artist-credit": [{"artist": {"id": "a"}}, {"artist": {"id": "a"}}],
    }
    assert reduce_release_group(rec)["artists"] == ["a", "a"]


def test_reduce_release_group_drops_singles():
    assert reduce_release_group({"id": "r", "primary-type": "Single"}) is None
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `uv run pytest pipeline/tests/test_extract.py -v`
Expected: FAIL — `ModuleNotFoundError: pipeline.extract`.

- [ ] **Step 3: Implémenter**

```python
# pipeline/extract.py
"""Projection en flux des dumps JSON MusicBrainz. Aucune règle métier ici."""
from __future__ import annotations

import json
import lzma
import tarfile
from pathlib import Path
from typing import Callable, Iterator

KEPT_TYPES = {"Group", "Orchestra", "Choir"}


def reduce_artist(rec: dict) -> dict | None:
    if rec.get("type") not in KEPT_TYPES:
        return None
    span = rec.get("life-span") or {}
    return {
        "mbid": rec.get("id"),
        "name": rec.get("name"),
        "type": rec.get("type"),
        "begin": span.get("begin"),
        "end": span.get("end"),
        "ended": bool(span.get("ended")),
        "country": rec.get("country"),
        "area": (rec.get("area") or {}).get("name"),
        "begin_area": (rec.get("begin-area") or {}).get("name"),
        "genres": [
            {"mbid": g.get("id"), "name": g.get("name"), "votes": g.get("count", 0)}
            for g in (rec.get("genres") or [])
        ],
        "members": [
            {
                "mbid": (r.get("artist") or {}).get("id"),
                "begin": r.get("begin"),
                "end": r.get("end"),
            }
            for r in (rec.get("relations") or [])
            if r.get("type") == "member of band"
        ],
    }


def reduce_release_group(rec: dict) -> dict | None:
    if rec.get("primary-type") != "Album":
        return None
    return {
        "mbid": rec.get("id"),
        "title": rec.get("title"),
        "date": rec.get("first-release-date"),
        "secondary": rec.get("secondary-types") or [],
        "artists": [
            (c.get("artist") or {}).get("id") for c in (rec.get("artist-credit") or [])
        ],
    }


def iter_records(archive: Path) -> Iterator[dict]:
    """Parcourt les lignes JSON de mbdump/* sans jamais écrire le tar décompressé."""
    with lzma.open(archive) as xz, tarfile.open(fileobj=xz, mode="r|") as tar:
        for member in tar:
            if not member.isfile() or not member.name.startswith("mbdump/"):
                continue
            stream = tar.extractfile(member)
            if stream is None:
                continue
            for raw in stream:
                line = raw.strip()
                if not line.startswith(b"{"):
                    continue
                try:
                    yield json.loads(line, strict=False)
                except json.JSONDecodeError:
                    continue


def extract(archive: Path, reducer: Callable[[dict], dict | None], out: Path) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    kept = 0
    with open(out, "w", encoding="utf-8") as fh:
        for rec in iter_records(archive):
            reduced = reducer(rec)
            if reduced is None:
                continue
            fh.write(json.dumps(reduced, ensure_ascii=False) + "\n")
            kept += 1
    return kept
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `uv run pytest pipeline/tests/test_extract.py -v`
Expected: PASS, 5 tests.

- [ ] **Step 5: Lancer l'extraction complète (une dizaine de minutes)**

```bash
uv run python -c "
from pathlib import Path
from pipeline.extract import extract, reduce_artist, reduce_release_group
raw = Path('data/raw/20260909-001002')
print('artists :', extract(raw / 'artist.tar.xz', reduce_artist, Path('data/work/artists.jsonl')))
print('rgs     :', extract(raw / 'release-group.tar.xz', reduce_release_group, Path('data/work/release_groups.jsonl')))
"
```

Expected: `artists : 682447` et `rgs : 2317879`. Tout autre nombre est un défaut de projection : ne pas continuer.

- [ ] **Step 6: Commit**

```bash
git add pipeline/extract.py pipeline/tests/test_extract.py
git commit -m "feat(pipeline): stream-project artist and release-group dumps"
```

---

### Task 4: Fixtures réelles

**Files:**
- Create: `pipeline/tests/fixtures/artists.jsonl`, `pipeline/tests/fixtures/release_groups.jsonl`, `pipeline/tests/fixtures/ATTRIBUTION.md`, `scripts/make_fixtures.py`
- Test: `pipeline/tests/test_fixtures.py`

**Interfaces:**
- Consumes: Task 3 (`data/work/*.jsonl`).
- Produces: les fixtures sur lesquelles reposent toutes les tâches SQL. Les 23 MBID témoins sont listés dans la spec §9.1.

- [ ] **Step 1: Écrire le script d'extraction des fixtures**

```python
# scripts/make_fixtures.py
"""Extrait les enregistrements témoins des extractions complètes."""
import json
from pathlib import Path

WITNESSES = [
    "b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d",  # The Beatles
    "9d953ee6-4ea6-4b0e-aea6-7268d380bef1",  # homonyme
    "8d3431db-bc83-4dc2-93b8-0e46e31d09f7",  # homonyme
    "9a58fda3-f4ed-4080-a3a5-f457aac9fcdd",  # Joy Division
    "f1106b17-dcbb-45f6-b938-199ccfab50cc",  # New Order
    "a3cb23fc-acd3-4ce0-8f36-1e5aa6a18432",  # U2
    "8f6bd1e4-fbe1-4f50-aa9b-94c450ec0f11",  # Portishead
    "97c86b2c-2765-46a2-aef8-76a7e24c430f",  # XTC
    "e598d30e-4ce1-402e-94a7-6f44779da6b7",  # Orange Juice
    "6959c3d5-3e7f-41bb-aba3-50e38225d23d",  # homonyme
    "a9424175-8b06-44ad-a1f4-319e92a50879",  # Disincarnate
    "125948ec-7f91-4d1a-8b83-accbf50fae3d",  # 3OH!3
    "d25be955-6fed-4303-bffb-8c440c191edb",  # Lethal Shöck
    "53fc0417-7585-490c-b2ea-5f9737e14c0f",  # Blackdeath
    "1434b0d0-d647-421e-b345-1b9847045a52",  # Cleef
    "6dfa03fb-8b02-4055-b7cc-e48f426b13f8",  # Unheilig
    "d770374d-05e9-4ed3-a068-3fbd4e6e4dd6",  # Wiener Philharmoniker
    "0ab49580-c84f-44d4-875f-d83760ea2cfe",  # Maroon 5
    "703c4c92-43f7-4268-9f85-0ca6f0cd1a22",  # Polska Radio One
    "f7338f2a-136b-4d5e-b099-5504cf997f58",  # Cardiacs
    "bd13909f-1c29-4c27-a874-d4aaf27c5b1a",  # Fleetwood Mac
    "3cb86073-22d7-43d5-8f22-422b1e54988e",  # ROD
    "212faddb-cd09-4fbc-9336-3ed7cadfba68",  # Flesh Field
    "8a1f012c-acc1-4dda-878f-43ac02f2366f",  # Demented Are Go!
]

work = Path("data/work")
out = Path("pipeline/tests/fixtures")
out.mkdir(parents=True, exist_ok=True)
wanted = set(WITNESSES)

kept = []
with open(out / "artists.jsonl", "w", encoding="utf-8") as fh:
    for line in open(work / "artists.jsonl", encoding="utf-8"):
        rec = json.loads(line)
        if rec["mbid"] in wanted:
            fh.write(line)
            kept.append(rec["mbid"])

with open(out / "release_groups.jsonl", "w", encoding="utf-8") as fh:
    for line in open(work / "release_groups.jsonl", encoding="utf-8"):
        rec = json.loads(line)
        if wanted & set(rec["artists"]):
            fh.write(line)

print("témoins trouvés :", len(kept))
missing = wanted - set(kept)
print("manquants :", missing or "aucun")
```

- [ ] **Step 2: Lancer le script**

Run: `uv run python scripts/make_fixtures.py`
Expected: `témoins trouvés : 24`, `manquants : aucun`. Un témoin manquant est un défaut de la Task 3 : ne pas continuer.

- [ ] **Step 3: Écrire l'attribution et le test de garde**

```markdown
<!-- pipeline/tests/fixtures/ATTRIBUTION.md -->
Extraits du dump MusicBrainz `20260909-001002`.
Données de base : CC0. Genres : CC-BY-NC-SA 3.0, attribution MusicBrainz.
Produit par `scripts/make_fixtures.py`. Ne pas éditer à la main.
```

```python
# pipeline/tests/test_fixtures.py
import json
from pathlib import Path

FIX = Path("pipeline/tests/fixtures")


def test_every_witness_is_present():
    from scripts.make_fixtures import WITNESSES  # noqa: PLC0415
    ids = {json.loads(l)["mbid"] for l in open(FIX / "artists.jsonl", encoding="utf-8")}
    assert set(WITNESSES) <= ids


def test_beatles_genres_carry_mbid_and_votes():
    for line in open(FIX / "artists.jsonl", encoding="utf-8"):
        rec = json.loads(line)
        if rec["mbid"] == "b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d":
            assert rec["genres"], "les genres doivent être conservés"
            assert all(g["mbid"] and "votes" in g for g in rec["genres"])
            return
    raise AssertionError("The Beatles absent des fixtures")
```

- [ ] **Step 4: Lancer les tests**

Run: `uv run pytest pipeline/tests/test_fixtures.py -v`
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add scripts/make_fixtures.py pipeline/tests/fixtures pipeline/tests/test_fixtures.py
git commit -m "test(pipeline): add real witness fixtures from reference dump"
```

---

### Task 5: R1 et R2 — population et dates

**Files:**
- Create: `pipeline/sql/00_macros.sql`, `pipeline/sql/10_bands.sql`, `pipeline/build.py`
- Test: `pipeline/tests/test_bands.py`

**Interfaces:**
- Consumes: Task 4 (fixtures), Task 1 (duckdb).
- Produces: `build(con, sql_dir: Path, artists: Path, rgs: Path, corrections: Path | None, dump_year: int = 2026) -> None` ; table `bands(mbid, name, y0, y_end_declared, ended, country, begin_area, genres)` ; macro `yr(s)`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# pipeline/tests/test_bands.py
from pathlib import Path
import duckdb
import pytest
from pipeline.build import build

FIX = Path("pipeline/tests/fixtures")
SQL = Path("pipeline/sql")


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(":memory:")
    build(c, SQL, FIX / "artists.jsonl", FIX / "release_groups.jsonl", None)
    return c


def rows(con, q):
    return con.execute(q).fetchall()


def test_orchestra_is_excluded(con):
    assert rows(con, "SELECT count(*) FROM bands WHERE mbid = 'd770374d-05e9-4ed3-a068-3fbd4e6e4dd6'") == [(0,)]


def test_unreadable_begin_is_excluded(con):
    assert rows(con, "SELECT count(*) FROM bands WHERE mbid = '1434b0d0-d647-421e-b345-1b9847045a52'") == [(0,)]


def test_future_begin_is_excluded(con):
    assert rows(con, "SELECT count(*) FROM bands WHERE mbid = 'd25be955-6fed-4303-bffb-8c440c191edb'") == [(0,)]


def test_homonyms_without_date_or_genre_are_excluded(con):
    assert rows(con, """
        SELECT count(*) FROM bands
        WHERE mbid IN ('9d953ee6-4ea6-4b0e-aea6-7268d380bef1',
                       '8d3431db-bc83-4dc2-93b8-0e46e31d09f7',
                       '6959c3d5-3e7f-41bb-aba3-50e38225d23d')
    """) == [(0,)]


def test_end_before_begin_is_neutralised_and_band_kept(con):
    assert rows(con, """
        SELECT y0, y_end_declared FROM bands
        WHERE mbid = '53fc0417-7585-490c-b2ea-5f9737e14c0f'
    """) == [(1998, None)]


def test_unreadable_end_is_absent_but_band_kept(con):
    assert rows(con, """
        SELECT y0, y_end_declared, ended FROM bands
        WHERE mbid = '6dfa03fb-8b02-4055-b7cc-e48f426b13f8'
    """) == [(1999, None, True)]


def test_month_precision_is_reduced_to_the_year(con):
    assert rows(con, """
        SELECT y0, y_end_declared FROM bands
        WHERE mbid = '9a58fda3-f4ed-4080-a3a5-f457aac9fcdd'
    """) == [(1978, 1980)]
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `uv run pytest pipeline/tests/test_bands.py -v`
Expected: FAIL — `ModuleNotFoundError: pipeline.build`.

- [ ] **Step 3: Implémenter**

```sql
-- pipeline/sql/00_macros.sql
CREATE OR REPLACE MACRO yr(s) AS
  CASE WHEN regexp_full_match(substr(s, 1, 4), '[0-9]{4}')
       THEN CAST(substr(s, 1, 4) AS INTEGER) END;
```

```sql
-- pipeline/sql/10_bands.sql
-- R1 population, R2 dates. $dump_year est fourni par build().
CREATE OR REPLACE TABLE dated AS
SELECT
  mbid, name, type, ended, country, begin_area, genres, members,
  CASE WHEN yr(begin) <= $dump_year THEN yr(begin) END AS y0,
  CASE WHEN yr("end") <= $dump_year
        AND (yr(begin) IS NULL OR yr("end") >= yr(begin))
       THEN yr("end") END AS y_end_declared
FROM raw_artists;

CREATE OR REPLACE TABLE bands AS
SELECT mbid, name, y0, y_end_declared, ended, country, begin_area, genres
FROM dated
WHERE type = 'Group'
  AND y0 BETWEEN 1850 AND $dump_year
  AND len(genres) > 0;
```

```python
# pipeline/build.py
"""Enchaîne les fichiers SQL de transformation sur une connexion DuckDB."""
from __future__ import annotations

from pathlib import Path

import duckdb

RAW_ARTIST_COLUMNS = (
    "{mbid:'VARCHAR', name:'VARCHAR', type:'VARCHAR', begin:'VARCHAR', "
    "\"end\":'VARCHAR', ended:'BOOLEAN', country:'VARCHAR', area:'VARCHAR', "
    "begin_area:'VARCHAR', "
    "genres:'STRUCT(mbid VARCHAR, name VARCHAR, votes INTEGER)[]', "
    "members:'STRUCT(mbid VARCHAR, begin VARCHAR, \"end\" VARCHAR)[]'}"
)
RAW_RG_COLUMNS = (
    "{mbid:'VARCHAR', title:'VARCHAR', date:'VARCHAR', "
    "secondary:'VARCHAR[]', artists:'VARCHAR[]'}"
)


def load_raw(con: duckdb.DuckDBPyConnection, artists: Path, rgs: Path) -> None:
    con.execute(
        f"CREATE OR REPLACE TABLE raw_artists AS SELECT * FROM read_ndjson("
        f"'{artists.as_posix()}', columns={RAW_ARTIST_COLUMNS}, "
        f"format='newline_delimited')"
    )
    con.execute(
        f"CREATE OR REPLACE TABLE raw_release_groups AS SELECT * FROM read_ndjson("
        f"'{rgs.as_posix()}', columns={RAW_RG_COLUMNS}, format='newline_delimited')"
    )


def build(
    con: duckdb.DuckDBPyConnection,
    sql_dir: Path,
    artists: Path,
    rgs: Path,
    corrections: Path | None,
    dump_year: int = 2026,
) -> None:
    load_raw(con, artists, rgs)
    con.execute(f"SET VARIABLE dump_year = {dump_year}")
    for path in sorted(sql_dir.glob("*.sql")):
        if path.name.startswith("90_"):
            continue
        con.execute(path.read_text(encoding="utf-8"))
```

Note pour l'implémenteur : `SET VARIABLE` puis `$dump_year` est la forme DuckDB des variables de session. Si elle ne fonctionne pas dans la version épinglée, remplacer par `path.read_text().replace("$dump_year", str(dump_year))` avant `execute` — et écrire un test qui vérifie qu'aucun `$` ne subsiste dans le SQL exécuté.

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `uv run pytest pipeline/tests/test_bands.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add pipeline/sql/00_macros.sql pipeline/sql/10_bands.sql pipeline/build.py pipeline/tests/test_bands.py
git commit -m "feat(pipeline): implement R1 population and R2 date rules"
```

---

### Task 6: R3 — albums

**Files:**
- Create: `pipeline/sql/20_albums.sql`
- Test: `pipeline/tests/test_albums.py`

**Interfaces:**
- Consumes: Task 5 (`bands`, `raw_release_groups`, macro `yr`).
- Produces: table `albums(band_mbid, rg_mbid, title, y, soundtrack)`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# pipeline/tests/test_albums.py
from pathlib import Path
import duckdb
import pytest
from pipeline.build import build

FIX = Path("pipeline/tests/fixtures")
SQL = Path("pipeline/sql")
BEATLES = "b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d"
FLEETWOOD = "bd13909f-1c29-4c27-a874-d4aaf27c5b1a"
DEMENTED = "8a1f012c-acc1-4dda-878f-43ac02f2366f"
CARDIACS = "f7338f2a-136b-4d5e-b099-5504cf997f58"
MAROON = "0ab49580-c84f-44d4-875f-d83760ea2cfe"


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(":memory:")
    build(c, SQL, FIX / "artists.jsonl", FIX / "release_groups.jsonl", None)
    return c


def test_beatles_keep_22_albums_between_1963_and_1970(con):
    assert con.execute(
        "SELECT count(*), min(y), max(y) FROM albums WHERE band_mbid = ?", [BEATLES]
    ).fetchall() == [(22, 1963, 1970)]


def test_soundtracks_are_kept(con):
    n = con.execute(
        "SELECT count(*) FROM albums WHERE band_mbid = ? AND soundtrack", [BEATLES]
    ).fetchone()[0]
    assert n > 0


def test_multi_artist_album_is_dropped(con):
    assert con.execute(
        "SELECT count(*) FROM albums WHERE rg_mbid IN "
        "(SELECT mbid FROM raw_release_groups WHERE title = 'The Biggest Thing Since Colossus')"
    ).fetchall() == [(0,)]


def test_same_artist_credited_twice_is_kept(con):
    assert con.execute(
        "SELECT count(*) FROM albums WHERE band_mbid = ? AND title = ?",
        [DEMENTED, "The Day the Earth Spat Blood"],
    ).fetchall() == [(1,)]


def test_posthumous_album_inside_the_margin_is_kept(con):
    assert con.execute(
        "SELECT max(y) FROM albums WHERE band_mbid = ?", [CARDIACS]
    ).fetchall() == [(2025,)]


def test_album_before_formation_is_kept_within_five_years(con):
    assert con.execute(
        "SELECT min(y) FROM albums WHERE band_mbid = ?", [MAROON]
    ).fetchall() == [(1997,)]
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `uv run pytest pipeline/tests/test_albums.py -v`
Expected: FAIL — `Catalog Error: Table with name albums does not exist`.

- [ ] **Step 3: Implémenter**

```sql
-- pipeline/sql/20_albums.sql
-- R3. Les types secondaires sont vides ou exactement {Soundtrack}.
CREATE OR REPLACE TABLE albums AS
SELECT
  b.mbid AS band_mbid,
  r.mbid AS rg_mbid,
  r.title,
  yr(r.date) AS y,
  len(coalesce(r.secondary, [])) = 1 AS soundtrack
FROM raw_release_groups r
JOIN bands b ON b.mbid = list_distinct(r.artists)[1]
WHERE len(list_distinct(r.artists)) = 1
  AND yr(r.date) IS NOT NULL
  AND yr(r.date) <= $dump_year
  AND len(list_filter(coalesce(r.secondary, []), s -> s <> 'Soundtrack')) = 0
  AND yr(r.date) BETWEEN b.y0 - 5
                     AND coalesce(b.y_end_declared, $dump_year) + 5;
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `uv run pytest pipeline/tests/test_albums.py -v`
Expected: PASS, 6 tests.

- [ ] **Step 5: Commit**

```bash
git add pipeline/sql/20_albums.sql pipeline/tests/test_albums.py
git commit -m "feat(pipeline): implement R3 album selection"
```

---

### Task 7: R4 et R7 — preuves et présence

**Files:**
- Create: `pipeline/sql/30_presence.sql`
- Modify: `pipeline/sql/10_bands.sql` (ajouter `y_last_album` à `bands`)
- Test: `pipeline/tests/test_presence.py`

**Interfaces:**
- Consumes: Task 6 (`albums`).
- Produces: colonne `bands.y_last_album` ; table `presence(mbid, y0, y_presence_end)`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# pipeline/tests/test_presence.py
from pathlib import Path
import duckdb
import pytest
from pipeline.build import build

FIX = Path("pipeline/tests/fixtures")
SQL = Path("pipeline/sql")


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(":memory:")
    build(c, SQL, FIX / "artists.jsonl", FIX / "release_groups.jsonl", None)
    return c


def end_of(con, mbid):
    return con.execute(
        "SELECT y_presence_end FROM presence WHERE mbid = ?", [mbid]
    ).fetchone()[0]


def test_declared_end_wins_over_a_later_album(con):
    # Cardiacs : fin déclarée 2020, album retenu en 2025.
    assert end_of(con, "f7338f2a-136b-4d5e-b099-5504cf997f58") == 2020


def test_active_band_is_not_stopped_at_its_last_album(con):
    # U2 : aucune fin déclarée, dernier album 2025.
    assert end_of(con, "a3cb23fc-acd3-4ce0-8f36-1e5aa6a18432") == 2025


def test_band_without_album_is_present_only_at_formation(con):
    # ROD : formé en 1996, aucun album retenu.
    assert end_of(con, "3cb86073-22d7-43d5-8f22-422b1e54988e") == 1996


def test_albums_before_formation_do_not_move_the_floor(con):
    # Polska Radio One : formé 2015, albums 2013 et 2014.
    assert end_of(con, "703c4c92-43f7-4268-9f85-0ca6f0cd1a22") == 2015


def test_no_band_is_present_after_its_declared_end(con):
    assert con.execute("""
        SELECT count(*) FROM presence p JOIN bands b USING (mbid)
        WHERE b.y_end_declared IS NOT NULL AND p.y_presence_end > b.y_end_declared
    """).fetchall() == [(0,)]
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `uv run pytest pipeline/tests/test_presence.py -v`
Expected: FAIL — `Catalog Error: Table with name presence does not exist`.

- [ ] **Step 3: Implémenter**

Ajouter à la fin de `pipeline/sql/20_albums.sql` :

```sql
ALTER TABLE bands ADD COLUMN y_last_album INTEGER;
UPDATE bands SET y_last_album = (
  SELECT max(a.y) FROM albums a WHERE a.band_mbid = bands.mbid
);
```

```sql
-- pipeline/sql/30_presence.sql
-- R7. La fin déclarée fait foi ; sinon le dernier album, jamais avant la formation.
CREATE OR REPLACE TABLE presence AS
SELECT
  mbid,
  y0,
  least(
    $dump_year,
    CASE WHEN y_end_declared IS NOT NULL THEN y_end_declared
         ELSE greatest(y0, coalesce(y_last_album, y0)) END
  ) AS y_presence_end
FROM bands;
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `uv run pytest pipeline/tests/test_presence.py -v`
Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add pipeline/sql/20_albums.sql pipeline/sql/30_presence.sql pipeline/tests/test_presence.py
git commit -m "feat(pipeline): implement R4 evidence and R7 presence"
```

---

### Task 8: R5 — genres

**Files:**
- Create: `pipeline/sql/40_genres.sql`
- Modify: `pipeline/sql/10_bands.sql` (trier `genres` à la construction)
- Test: `pipeline/tests/test_genres.py`

**Interfaces:**
- Consumes: Task 5.
- Produces: table `genres(genre_mbid, name, n_bands)` ; `bands.genres` trié par votes décroissants puis par nom.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# pipeline/tests/test_genres.py
from pathlib import Path
import duckdb
import pytest
from pipeline.build import build

FIX = Path("pipeline/tests/fixtures")
SQL = Path("pipeline/sql")
OH3 = "125948ec-7f91-4d1a-8b83-accbf50fae3d"


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(":memory:")
    build(c, SQL, FIX / "artists.jsonl", FIX / "release_groups.jsonl", None)
    return c


def test_genres_are_sorted_by_votes_then_name(con):
    names = con.execute(
        "SELECT list_transform(genres, g -> g.name) FROM bands WHERE mbid = ?", [OH3]
    ).fetchone()[0]
    assert names[0] == "synth-pop"
    assert names[1:5] == ["crunkcore", "electronic", "electropop", "pop"]


def test_genres_table_counts_bands(con):
    assert con.execute("""
        SELECT g.n_bands = (SELECT count(*) FROM bands b
                            WHERE list_contains(list_transform(b.genres, x -> x.mbid), g.genre_mbid))
        FROM genres g
    """).fetchall() == [(True,)] * con.execute("SELECT count(*) FROM genres").fetchone()[0]


def test_every_band_genre_exists_in_the_genres_table(con):
    assert con.execute("""
        SELECT count(*) FROM (SELECT unnest(genres) AS g FROM bands) t
        WHERE t.g.mbid NOT IN (SELECT genre_mbid FROM genres)
    """).fetchall() == [(0,)]
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `uv run pytest pipeline/tests/test_genres.py -v`
Expected: FAIL — `Catalog Error: Table with name genres does not exist`.

- [ ] **Step 3: Implémenter**

Dans `pipeline/sql/10_bands.sql`, remplacer `genres` par sa version triée dans la construction de `bands` :

```sql
list_sort(genres, (a, b) -> CASE
    WHEN a.votes <> b.votes THEN CASE WHEN a.votes > b.votes THEN -1 ELSE 1 END
    WHEN a.name < b.name THEN -1 WHEN a.name > b.name THEN 1 ELSE 0 END) AS genres
```

Note pour l'implémenteur : si `list_sort` n'accepte pas de comparateur dans la version épinglée, obtenir le même résultat par `unnest` + `ORDER BY votes DESC, name` + `list(...)` regroupé par `mbid`. Le test tranche.

```sql
-- pipeline/sql/40_genres.sql
-- R5. Vocabulaire effectivement porté par bands.
CREATE OR REPLACE TABLE genres AS
SELECT g.mbid AS genre_mbid, any_value(g.name) AS name, count(*) AS n_bands
FROM bands, UNNEST(bands.genres) AS t(g)
GROUP BY g.mbid;
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `uv run pytest pipeline/tests/test_genres.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add pipeline/sql/10_bands.sql pipeline/sql/40_genres.sql pipeline/tests/test_genres.py
git commit -m "feat(pipeline): implement R5 genre ordering and vocabulary"
```

---

### Task 9: R7 — densité

**Files:**
- Create: `pipeline/sql/50_density.sql`
- Test: `pipeline/tests/test_density.py`

**Interfaces:**
- Consumes: Task 7 (`presence`), Task 8 (`genres`).
- Produces: table `density(genre_mbid, year, present)`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# pipeline/tests/test_density.py
from pathlib import Path
import duckdb
import pytest
from pipeline.build import build

FIX = Path("pipeline/tests/fixtures")
SQL = Path("pipeline/sql")


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(":memory:")
    build(c, SQL, FIX / "artists.jsonl", FIX / "release_groups.jsonl", None)
    return c


def test_no_cell_after_the_dump_year(con):
    assert con.execute("SELECT count(*) FROM density WHERE year > 2026").fetchall() == [(0,)]


def test_present_never_exceeds_the_band_count(con):
    assert con.execute("""
        SELECT count(*) FROM density d JOIN genres g USING (genre_mbid)
        WHERE d.present > g.n_bands
    """).fetchall() == [(0,)]


def test_a_band_counts_in_each_of_its_genres(con):
    # Cardiacs est présent de 1977 à 2020 ; chacun de ses genres doit le compter en 1990.
    n = con.execute("""
        SELECT count(*) FROM density d
        WHERE d.year = 1990 AND d.genre_mbid IN (
          SELECT g.mbid FROM bands, UNNEST(bands.genres) AS t(g)
          WHERE bands.mbid = 'f7338f2a-136b-4d5e-b099-5504cf997f58')
    """).fetchone()[0]
    assert n > 0
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `uv run pytest pipeline/tests/test_density.py -v`
Expected: FAIL — `Catalog Error: Table with name density does not exist`.

- [ ] **Step 3: Implémenter**

```sql
-- pipeline/sql/50_density.sql
-- R7, agrégat. Les totaux par genre ne s'additionnent pas : un groupe compte dans chacun.
CREATE OR REPLACE TABLE density AS
SELECT g.mbid AS genre_mbid, y.year, count(*) AS present
FROM presence p
JOIN bands b USING (mbid),
     UNNEST(b.genres) AS t(g),
     range(1850, $dump_year + 1) AS y(year)
WHERE y.year BETWEEN p.y0 AND p.y_presence_end
GROUP BY g.mbid, y.year;
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `uv run pytest pipeline/tests/test_density.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add pipeline/sql/50_density.sql pipeline/tests/test_density.py
git commit -m "feat(pipeline): implement R7 density aggregate"
```

---

### Task 10: R6 — corrections manuelles

**Files:**
- Create: `pipeline/corrections.csv`, `pipeline/tests/test_corrections.py`
- Modify: `pipeline/build.py` (appliquer les corrections avant `10_bands.sql`)

**Interfaces:**
- Consumes: Task 5.
- Produces: application des corrections sur `raw_artists` avant toute règle.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# pipeline/tests/test_corrections.py
from pathlib import Path
import duckdb
from pipeline.build import build

FIX = Path("pipeline/tests/fixtures")
SQL = Path("pipeline/sql")
BLACKDEATH = "53fc0417-7585-490c-b2ea-5f9737e14c0f"


def build_with(tmp_path, lines):
    path = tmp_path / "corrections.csv"
    path.write_text(
        "mbid,champ,valeur,justification,source\n" + "".join(lines), encoding="utf-8"
    )
    con = duckdb.connect(":memory:")
    build(con, SQL, FIX / "artists.jsonl", FIX / "release_groups.jsonl", path)
    return con


def test_empty_corrections_leave_the_end_neutralised(tmp_path):
    con = build_with(tmp_path, [])
    assert con.execute(
        "SELECT y_end_declared FROM bands WHERE mbid = ?", [BLACKDEATH]
    ).fetchall() == [(None,)]


def test_a_correction_repairs_the_end(tmp_path):
    con = build_with(
        tmp_path,
        [f'{BLACKDEATH},end,2007,"fin réelle","https://example.invalid/source"\n'],
    )
    assert con.execute(
        "SELECT y_end_declared FROM bands WHERE mbid = ?", [BLACKDEATH]
    ).fetchall() == [(2007,)]


def test_a_correction_touches_no_other_band(tmp_path):
    before = build_with(tmp_path, []).execute(
        "SELECT count(*) FROM bands"
    ).fetchone()[0]
    after = build_with(
        tmp_path,
        [f'{BLACKDEATH},end,2007,"fin réelle","https://example.invalid/source"\n'],
    ).execute("SELECT count(*) FROM bands").fetchone()[0]
    assert before == after


def test_corrections_file_stays_small():
    path = Path("pipeline/corrections.csv")
    assert len(path.read_text(encoding="utf-8").splitlines()) - 1 <= 50
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `uv run pytest pipeline/tests/test_corrections.py -v`
Expected: FAIL — `build()` ignore l'argument `corrections`.

- [ ] **Step 3: Implémenter**

```csv
mbid,champ,valeur,justification,source
```

Ajouter dans `pipeline/build.py`, juste après `load_raw` :

```python
def apply_corrections(con: duckdb.DuckDBPyConnection, corrections: Path | None) -> int:
    if corrections is None:
        return 0
    con.execute(
        "CREATE OR REPLACE TABLE corrections AS SELECT * FROM read_csv("
        f"'{corrections.as_posix()}', header=true, "
        "columns={mbid:'VARCHAR', champ:'VARCHAR', valeur:'VARCHAR', "
        "justification:'VARCHAR', source:'VARCHAR'})"
    )
    for field in ("begin", "end"):
        con.execute(
            f'UPDATE raw_artists SET "{field}" = c.valeur FROM corrections c '
            f"WHERE c.mbid = raw_artists.mbid AND c.champ = '{field}'"
        )
    return con.execute("SELECT count(*) FROM corrections").fetchone()[0]
```

et l'appeler dans `build()` entre `load_raw` et la boucle SQL.

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `uv run pytest pipeline/tests/test_corrections.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add pipeline/corrections.csv pipeline/build.py pipeline/tests/test_corrections.py
git commit -m "feat(pipeline): apply sourced manual corrections before the rules"
```

---

### Task 11: Invariants

**Files:**
- Create: `pipeline/sql/90_invariants.sql`, `pipeline/tests/test_invariants.py`
- Modify: `pipeline/build.py` (fonction `check_invariants`)

**Interfaces:**
- Consumes: toutes les tâches précédentes.
- Produces: `check_invariants(con, sql_dir: Path) -> list[tuple[str, int]]` — renvoie les invariants violés, vide si tout va bien.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# pipeline/tests/test_invariants.py
from pathlib import Path
import duckdb
import pytest
from pipeline.build import build, check_invariants

FIX = Path("pipeline/tests/fixtures")
SQL = Path("pipeline/sql")


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(":memory:")
    build(c, SQL, FIX / "artists.jsonl", FIX / "release_groups.jsonl", None)
    return c


def test_fixtures_satisfy_every_invariant(con):
    assert check_invariants(con, SQL) == []


def test_a_broken_invariant_is_reported(con):
    con.execute("INSERT INTO albums VALUES ('inconnu', 'rg', 'T', 1999, false)")
    violations = dict(check_invariants(con, SQL))
    con.execute("DELETE FROM albums WHERE band_mbid = 'inconnu'")
    assert violations.get("album_without_band") == 1
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `uv run pytest pipeline/tests/test_invariants.py -v`
Expected: FAIL — `ImportError: cannot import name 'check_invariants'`.

- [ ] **Step 3: Implémenter**

```sql
-- pipeline/sql/90_invariants.sql
-- Chaque vue doit être vide. Le nom de la vue est le nom de l'invariant.
CREATE OR REPLACE VIEW duplicate_band AS
  SELECT mbid FROM bands GROUP BY mbid HAVING count(*) > 1;
CREATE OR REPLACE VIEW band_out_of_window AS
  SELECT mbid FROM bands WHERE y0 IS NULL OR y0 < 1850 OR y0 > $dump_year;
CREATE OR REPLACE VIEW end_before_begin AS
  SELECT mbid FROM bands WHERE y_end_declared IS NOT NULL
    AND (y_end_declared < y0 OR y_end_declared > $dump_year);
CREATE OR REPLACE VIEW last_album_mismatch AS
  SELECT b.mbid FROM bands b
  WHERE b.y_last_album IS DISTINCT FROM
        (SELECT max(a.y) FROM albums a WHERE a.band_mbid = b.mbid);
CREATE OR REPLACE VIEW album_without_band AS
  SELECT rg_mbid FROM albums WHERE band_mbid NOT IN (SELECT mbid FROM bands);
CREATE OR REPLACE VIEW album_out_of_window AS
  SELECT a.rg_mbid FROM albums a JOIN bands b ON b.mbid = a.band_mbid
  WHERE a.y NOT BETWEEN b.y0 - 5 AND coalesce(b.y_end_declared, $dump_year) + 5
     OR a.y > $dump_year;
CREATE OR REPLACE VIEW band_without_genre AS
  SELECT mbid FROM bands WHERE len(genres) = 0;
CREATE OR REPLACE VIEW unknown_genre AS
  SELECT t.g.mbid FROM (SELECT unnest(genres) AS g FROM bands) t
  WHERE t.g.mbid NOT IN (SELECT genre_mbid FROM genres);
CREATE OR REPLACE VIEW presence_out_of_range AS
  SELECT p.mbid FROM presence p JOIN bands b USING (mbid)
  WHERE p.y_presence_end < p.y0 OR p.y_presence_end > $dump_year
     OR (b.y_end_declared IS NOT NULL AND p.y_presence_end <> b.y_end_declared);
CREATE OR REPLACE VIEW density_out_of_range AS
  SELECT genre_mbid FROM density WHERE year > $dump_year;
CREATE OR REPLACE VIEW density_above_band_count AS
  SELECT d.genre_mbid FROM density d JOIN genres g USING (genre_mbid)
  WHERE d.present > g.n_bands;
```

```python
# à ajouter dans pipeline/build.py
INVARIANTS = (
    "duplicate_band", "band_out_of_window", "end_before_begin",
    "last_album_mismatch", "album_without_band", "album_out_of_window",
    "band_without_genre", "unknown_genre", "presence_out_of_range",
    "density_out_of_range", "density_above_band_count",
)


def check_invariants(con: duckdb.DuckDBPyConnection, sql_dir: Path) -> list[tuple[str, int]]:
    con.execute((sql_dir / "90_invariants.sql").read_text(encoding="utf-8"))
    violations = []
    for name in INVARIANTS:
        n = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
        if n:
            violations.append((name, n))
    return violations
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `uv run pytest -v`
Expected: PASS, toute la suite.

- [ ] **Step 5: Commit**

```bash
git add pipeline/sql/90_invariants.sql pipeline/build.py pipeline/tests/test_invariants.py
git commit -m "feat(pipeline): add output invariants"
```

---

### Task 12: Arbre des genres

**Files:**
- Create: `scripts/fetch_genre_parents.py`, `pipeline/sql/60_genre_parents.sql`
- Test: `pipeline/tests/test_genre_parents.py`

**Interfaces:**
- Consumes: Task 8 (`genres`), `pipeline/reference/wikidata_genre_parents.rq`.
- Produces: `data/work/genre_parents.csv` (colonnes `mbid,nom,parentMbid,parentNom`) ; table `genre_parents(genre_mbid, parent_mbid, source)`.

**Décision préalable, à trancher avant d'écrire le SQL :** la spec §6 laisse la source ouverte. Mesurer d'abord la couverture de la relation `subgenre` de MusicBrainz par un moyen autorisé (le dump PostgreSQL contient peut-être `l_genre_genre` ; l'API ne sert pas les relations). Si la couverture est inférieure à celle de Wikidata (951 genres sur 1 236), retenir Wikidata seule et le noter dans la spec. La table porte une colonne `source` précisément pour que les deux puissent coexister plus tard.

- [ ] **Step 1: Récupérer l'export Wikidata**

```python
# scripts/fetch_genre_parents.py
"""Exécute la requête SPARQL versionnée et écrit l'export brut."""
import urllib.parse
import urllib.request
from pathlib import Path

UA = "musilogy/0.1 ( victor.lenain26@gmail.com )"
QUERY = Path("pipeline/reference/wikidata_genre_parents.rq").read_text(encoding="utf-8")
url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": QUERY})
req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/csv"})
out = Path("data/work/genre_parents.csv")
out.parent.mkdir(parents=True, exist_ok=True)
with urllib.request.urlopen(req, timeout=180) as r:
    out.write_bytes(r.read())
print(out, out.stat().st_size, "octets")
```

Run: `uv run python scripts/fetch_genre_parents.py`
Expected: un fichier d'environ 2 500 lignes.

- [ ] **Step 2: Écrire le test qui échoue**

```python
# pipeline/tests/test_genre_parents.py
from pathlib import Path
import duckdb
import pytest
from pipeline.build import build

FIX = Path("pipeline/tests/fixtures")
SQL = Path("pipeline/sql")


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(":memory:")
    build(c, SQL, FIX / "artists.jsonl", FIX / "release_groups.jsonl", None)
    return c


def test_parents_reference_known_genres(con):
    assert con.execute("""
        SELECT count(*) FROM genre_parents
        WHERE genre_mbid NOT IN (SELECT genre_mbid FROM genres)
           OR parent_mbid NOT IN (SELECT genre_mbid FROM genres)
    """).fetchall() == [(0,)]


def test_no_genre_is_its_own_parent(con):
    assert con.execute(
        "SELECT count(*) FROM genre_parents WHERE genre_mbid = parent_mbid"
    ).fetchall() == [(0,)]


def test_source_is_recorded(con):
    sources = {r[0] for r in con.execute("SELECT DISTINCT source FROM genre_parents").fetchall()}
    assert sources <= {"wikidata", "musicbrainz"}
```

- [ ] **Step 3: Implémenter**

```sql
-- pipeline/sql/60_genre_parents.sql
-- §6. Relation multivaluée : un genre peut avoir plusieurs parents assertés.
CREATE OR REPLACE TABLE genre_parents AS
SELECT DISTINCT w.mbid AS genre_mbid, w.parentMbid AS parent_mbid, 'wikidata' AS source
FROM read_csv('data/work/genre_parents.csv', header=true) w
WHERE w.parentMbid IS NOT NULL
  AND w.mbid IN (SELECT genre_mbid FROM genres)
  AND w.parentMbid IN (SELECT genre_mbid FROM genres)
  AND w.mbid <> w.parentMbid;
```

Note : ce fichier lit un chemin fixe. Si `data/work/genre_parents.csv` est absent, `build()` doit créer une table `genre_parents` vide plutôt que d'échouer — la spec autorise explicitement une table vide.

- [ ] **Step 4: Lancer les tests**

Run: `uv run pytest pipeline/tests/test_genre_parents.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add scripts/fetch_genre_parents.py pipeline/sql/60_genre_parents.sql pipeline/tests/test_genre_parents.py
git commit -m "feat(pipeline): build genre parent relation from Wikidata"
```

---

### Task 13: Publication

**Files:**
- Create: `pipeline/publish.py`, `pipeline/tests/test_publish.py`

**Interfaces:**
- Consumes: toutes les tables.
- Produces: `publish(con, out_dir: Path, dump: str, corrections: Path | None) -> dict` — écrit les Parquet, le JSON colonnaire gzippé et `manifest.json`, et renvoie le manifeste.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# pipeline/tests/test_publish.py
import gzip
import json
from pathlib import Path
import duckdb
import pytest
from pipeline.build import build
from pipeline.publish import publish

FIX = Path("pipeline/tests/fixtures")
SQL = Path("pipeline/sql")


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(":memory:")
    build(c, SQL, FIX / "artists.jsonl", FIX / "release_groups.jsonl", None)
    return c


def test_publish_writes_every_table(con, tmp_path):
    manifest = publish(con, tmp_path, "20260909-001002", None)
    for name in ("bands", "albums", "genres", "genre_parents", "density"):
        assert (tmp_path / f"{name}.parquet").exists()
        assert name in manifest["counts"]
    assert manifest["dump"] == "20260909-001002"


def test_web_export_is_columnar_and_gzipped(con, tmp_path):
    publish(con, tmp_path, "20260909-001002", None)
    data = json.loads(gzip.decompress((tmp_path / "web" / "bands.json.gz").read_bytes()))
    assert set(data) >= {"name", "y0", "y_end_declared", "y_last_album"}
    assert len(data["name"]) == len(data["y0"])
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `uv run pytest pipeline/tests/test_publish.py -v`
Expected: FAIL — `ModuleNotFoundError: pipeline.publish`.

- [ ] **Step 3: Implémenter**

```python
# pipeline/publish.py
"""Écrit les livrables : Parquet d'archive, JSON colonnaire pour le web, manifeste."""
from __future__ import annotations

import gzip
import json
import subprocess
from pathlib import Path

import duckdb

TABLES = ("bands", "albums", "genres", "genre_parents", "density")
WEB_COLUMNS = {
    "bands": ["name", "y0", "y_end_declared", "y_last_album", "ended",
              "country", "begin_area"],
    "genres": ["genre_mbid", "name", "n_bands"],
}


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return "unknown"


def _columnar(con: duckdb.DuckDBPyConnection, table: str, columns: list[str]) -> dict:
    rows = con.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall()
    return {c: [r[i] for r in rows] for i, c in enumerate(columns)}


def publish(
    con: duckdb.DuckDBPyConnection,
    out_dir: Path,
    dump: str,
    corrections: Path | None,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "web").mkdir(exist_ok=True)

    counts = {}
    for name in TABLES:
        con.execute(
            f"COPY {name} TO '{(out_dir / f'{name}.parquet').as_posix()}' "
            "(FORMAT parquet, COMPRESSION zstd)"
        )
        counts[name] = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]

    for table, columns in WEB_COLUMNS.items():
        payload = json.dumps(
            _columnar(con, table, columns), ensure_ascii=False, separators=(",", ":")
        ).encode()
        (out_dir / "web" / f"{table}.json.gz").write_bytes(gzip.compress(payload, 9))

    manifest = {
        "dump": dump,
        "counts": counts,
        "git_sha": _git_sha(),
        "corrections": corrections.name if corrections else None,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    return manifest
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `uv run pytest pipeline/tests/test_publish.py -v`
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add pipeline/publish.py pipeline/tests/test_publish.py
git commit -m "feat(pipeline): publish parquet, columnar json and manifest"
```

---

### Task 14: Exécution complète et ligne de base

**Files:**
- Create: `scripts/run_pipeline.py`, `pipeline/tests/test_baseline.py`

**Interfaces:**
- Consumes: toutes les tâches.
- Produces: `data/out/20260909-001002/` et le test lent de non-régression.

- [ ] **Step 1: Écrire le script d'exécution**

```python
# scripts/run_pipeline.py
"""Exécution complète sur les extractions de la Task 3."""
from pathlib import Path

import duckdb

from pipeline.build import build, check_invariants
from pipeline.publish import publish

DUMP = "20260909-001002"
con = duckdb.connect(":memory:")
build(con, Path("pipeline/sql"), Path("data/work/artists.jsonl"),
      Path("data/work/release_groups.jsonl"), Path("pipeline/corrections.csv"))

violations = check_invariants(con, Path("pipeline/sql"))
if violations:
    raise SystemExit(f"invariants violés : {violations}")

manifest = publish(con, Path("data/out") / DUMP, DUMP, Path("pipeline/corrections.csv"))
print(manifest["counts"])
```

- [ ] **Step 2: Écrire le test de non-régression**

```python
# pipeline/tests/test_baseline.py
from pathlib import Path
import duckdb
import pytest
from pipeline.build import build, check_invariants

BASELINE = {"bands": 63_487, "albums": 189_477, "genres": 1_236, "density": 51_161}
WORK = Path("data/work")


@pytest.mark.slow
def test_reference_dump_matches_the_baseline():
    if not (WORK / "artists.jsonl").exists():
        pytest.skip("extractions absentes : lancer la Task 3")
    con = duckdb.connect(":memory:")
    build(con, Path("pipeline/sql"), WORK / "artists.jsonl",
          WORK / "release_groups.jsonl", None)
    assert check_invariants(con, Path("pipeline/sql")) == []
    for table, expected in BASELINE.items():
        got = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        assert got == expected, f"{table} : attendu {expected}, obtenu {got}"
```

- [ ] **Step 3: Lancer le test lent**

Run: `uv run pytest -m slow -v`
Expected: PASS. Un écart sur une table signale une règle mal implémentée — le corriger, ne jamais ajuster la ligne de base pour faire passer le test.

- [ ] **Step 4: Lancer le pipeline complet**

Run: `uv run python scripts/run_pipeline.py`
Expected: les comptes de la ligne de base, et `data/out/20260909-001002/manifest.json` écrit.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_pipeline.py pipeline/tests/test_baseline.py
git commit -m "test(pipeline): pin the reference baseline"
```

---

## Auto-relecture

**Couverture de la spec** — R1 et R2 : Task 5. R3 : Task 6. R4 et R7 : Tasks 7 et 9. R5 : Task 8. R6 : Task 10. R8 : contrainte globale, éprouvée par les témoins homonymes de la Task 5. §5 architecture : Tasks 2, 3, 5, 13. §6 : Task 12. §7 livrables : Task 13. §9 tests : Tasks 4, 11, 14.

**Manque assumé** — la spec §7.2 prévoit un fichier séparé pour les MBID des groupes et un export des albums en `offsets`. La Task 13 ne publie que `bands` et `genres` en colonnaire : le format d'échange avec la couche 1 n'est pas figé tant que la couche 1 n'existe pas. À compléter quand elle le sera.

**Cohérence des noms** — `build()`, `check_invariants()`, `publish()` gardent la même signature d'une tâche à l'autre ; les tables gardent les noms de la spec §3 ; `presence` est la seule table intermédiaire non publiée.
