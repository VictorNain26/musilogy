# Layer 0 — Frieze blobs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the three binary artifacts the frieze consumes — `frieze.bin`, `lineage.bin`, `frieze_ids.bin` — from the existing pipeline, plus the licences the repository never declared.

**Architecture:** Two new SQL files define the data (`70_frieze.sql`, `85_lineage.sql`), following the repository rule that rules live in SQL and Python only chains and writes. `publish.py` gains three serialisers that turn those tables into little-endian blobs of typed arrays. No front-end code: this plan ends with artifacts on disk, verified by tests.

**Tech Stack:** Python 3.12, uv, DuckDB, pytest, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-13-layer1-frieze-design.md`

## Global Constraints

- Python 3.12, run everything through `uv run`.
- Dependencies pinned to the patch; this plan adds none.
- `ruff check`, `ruff format --check` and `mypy src tests` must stay clean — a hook runs ruff after every tool call.
- Comments only for a non-obvious WHY. No "added for task N".
- Commits: `<type>(<scope>): <description>` in English.
- Frozen figures live in `tests/test_baseline.py` and nowhere else; figures quoted elsewhere are descriptive.
- Byte reproducibility is contractual (PR #4, #5): every published artifact has a total order, gzip is written with `mtime=0`, and `output_sha256` covers every delivered file.
- Frieze population is the 84 262 bands of `density`: `y0 IS NOT NULL`, `type = 'Group'`, and at least one genre with `density_eligible`.

---

## File Structure

| File | Responsibility |
|---|---|
| `LICENSE` | MIT, covering the code |
| `LICENSE-DATA` | CC-BY-NC-SA 3.0, covering produced data |
| `pyproject.toml` | declare the code licence |
| `src/musilogy/sql/70_frieze.sql` | `frieze` table: the display population, one row per band, with its rank key and edge flags |
| `src/musilogy/sql/85_lineage.sql` | `lineage` table: oriented edges between frieze bands sharing a musician |
| `src/musilogy/sql/90_invariants.sql` | new views for both tables |
| `src/musilogy/build.py` | register the new invariants |
| `src/musilogy/publish.py` | three serialisers + wiring into `publish()` |
| `tests/test_frieze.py` | the `frieze` table's rules |
| `tests/test_lineage.py` | the `lineage` table's rules |
| `tests/test_publish.py` | blob format and round-trip |
| `tests/test_invariants.py` | the new invariant views |
| `tests/test_baseline.py` | freeze the new counts on the real dump |

---

### Task 1: Declare the licences

The repository declares none, which makes the code all-rights-reserved by default while the README announces CC-BY-NC-SA data. Independent of everything else; done first so later commits land under a stated licence.

**Files:**
- Create: `LICENSE`, `LICENSE-DATA`
- Modify: `pyproject.toml`
- Test: `tests/test_env.py`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_env.py`:

```python
from musilogy.paths import PACKAGE_DIR

REPO_ROOT = PACKAGE_DIR.parent.parent


def test_both_licences_are_declared():
    # The code and the produced data are under different licences: MusicBrainz
    # genres and tags force CC-BY-NC-SA on the data, which must not contaminate
    # the pipeline itself.
    assert (REPO_ROOT / "LICENSE").read_text(encoding="utf-8").startswith("MIT License")
    assert "CC BY-NC-SA 3.0" in (REPO_ROOT / "LICENSE-DATA").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_env.py -k licences -v`
Expected: FAIL with `FileNotFoundError` on `LICENSE`.

- [ ] **Step 3: Write the licence files**

`LICENSE` — the standard MIT text, first line exactly `MIT License`, copyright `2026 Victor Lenain`.

`LICENSE-DATA`:

```
The data produced by this pipeline is licensed under
Creative Commons Attribution-NonCommercial-ShareAlike 3.0 Unported
(CC BY-NC-SA 3.0).

https://creativecommons.org/licenses/by-nc-sa/3.0/

MusicBrainz core data is CC0, but genres and tags are CC-BY-NC-SA 3.0.
`bands` and `genres` depend on them, so the produced dataset inherits that
licence: attribution, non-commercial use, share alike. The versioned test
fixtures and the published blobs follow the same terms.

The code in this repository is under the MIT licence; see LICENSE.
```

In `pyproject.toml`, under `[project]`, add: `license = "MIT"`

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_env.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add LICENSE LICENSE-DATA pyproject.toml tests/test_env.py
git commit -m "docs(licence): declare MIT for the code and CC-BY-NC-SA for the data"
```

---

### Task 2: The `frieze` table

The display population and its columns, defined in SQL so `publish.py` only serialises.

**Files:**
- Create: `src/musilogy/sql/70_frieze.sql`, `tests/test_frieze.py`
- Modify: `src/musilogy/sql/90_invariants.sql`, `src/musilogy/build.py`

**Interfaces:**
- Consumes: `bands` (10_bands, 30_bands_lifespan), `albums` (20_albums), `genres` (50_genres, 55_genre_reliability).
- Produces: table `frieze(i BIGINT, mbid VARCHAR, name VARCHAR, y0 SMALLINT, y1 SMALLINT, ended BOOLEAN, y_end_declared BOOLEAN, n_albums UTINYINT)`, ordered by `i` which runs 0..n-1 over `(y0, mbid)`. Tasks 3, 4 and 5 index rows by this `i`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_frieze.py`:

```python
def test_frieze_holds_only_bands_density_can_place(con):
    rows = con.execute("""
        SELECT count(*) FROM frieze f
        WHERE f.y0 IS NULL OR f.mbid NOT IN (SELECT mbid FROM bands WHERE type = 'Group')
    """).fetchone()
    assert rows[0] == 0


def test_frieze_excludes_bands_whose_only_genres_are_ineligible(con):
    # A band kept in `bands` but carrying no publishable genre has no cell in
    # density; showing it on the frieze would make the two views disagree on
    # the population.
    orphans = con.execute("""
        SELECT count(*) FROM frieze f WHERE NOT EXISTS (
          SELECT 1 FROM bands b, UNNEST(b.genres) AS t(g)
          JOIN genres gx ON gx.genre_mbid = t.g.mbid
          WHERE b.mbid = f.mbid AND gx.density_eligible)
    """).fetchone()
    assert orphans[0] == 0


def test_frieze_index_is_dense_and_ordered_by_formation(con):
    n, lo, hi = con.execute("SELECT count(*), min(i), max(i) FROM frieze").fetchone()
    assert (lo, hi) == (0, n - 1)
    ordered = con.execute("SELECT i FROM frieze ORDER BY y0, mbid").fetchall()
    assert [r[0] for r in ordered] == list(range(n))


def test_frieze_album_count_saturates_at_255(con):
    over = con.execute("SELECT count(*) FROM frieze WHERE n_albums > 255").fetchone()
    assert over[0] == 0
    matches = con.execute("""
        SELECT count(*) FROM frieze f
        LEFT JOIN (SELECT band_mbid, count(*) n FROM albums GROUP BY 1) a
          ON a.band_mbid = f.mbid
        WHERE f.n_albums <> least(coalesce(a.n, 0), 255)
    """).fetchone()
    assert matches[0] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_frieze.py -v`
Expected: FAIL — `Catalog Error: Table with name frieze does not exist`.

- [ ] **Step 3: Write the SQL**

Create `src/musilogy/sql/70_frieze.sql`. 70_ is free between density (60_) and members (80_), and the table depends on both `genres` and `albums`, so it must run after 55_ and 20_.

```sql
-- The display projection: one row per band the frieze can draw, in the order
-- it draws them. Deliberately narrower than `bands` and exactly as wide as
-- `density`'s population — a band absent from density has no cell to sit in,
-- and showing it would make the two views disagree on what exists.
--
-- `i` is the identity the published blobs use. Bands travel as a row index
-- rather than an mbid because 36-byte UUIDs are half the payload and are only
-- needed to open MusicBrainz; 85_lineage.sql references this same `i`.
CREATE OR REPLACE TABLE frieze AS
WITH eligible AS (
  SELECT DISTINCT b.mbid
  FROM bands b, UNNEST(b.genres) AS t(g)
  JOIN genres gx ON gx.genre_mbid = t.g.mbid
  WHERE b.y0 IS NOT NULL AND b.type = 'Group' AND gx.density_eligible
),
counted AS (
  SELECT band_mbid, count(*) AS n FROM albums GROUP BY band_mbid
)
SELECT
  (row_number() OVER (ORDER BY b.y0, b.mbid) - 1)::BIGINT AS i,
  b.mbid,
  b.name,
  b.y0::SMALLINT AS y0,
  b.y_presence_end::SMALLINT AS y1,
  coalesce(b.ended, false) AS ended,
  -- Published beside y1 because y_presence_end collapses to y0 when the end is
  -- unknown: without this flag the frieze draws a one-year bar and asserts an
  -- end the source never declared.
  b.y_end_source = 'declared' AS y_end_declared,
  -- The rank key. Album count is carried by the source; a notoriety score
  -- would have to be invented, and the frieze can only show a few hundred
  -- bands at once so the choice has to be defensible.
  least(coalesce(c.n, 0), 255)::UTINYINT AS n_albums
FROM bands b
SEMI JOIN eligible e ON e.mbid = b.mbid
LEFT JOIN counted c ON c.band_mbid = b.mbid;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_frieze.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Add the invariants**

Append to `src/musilogy/sql/90_invariants.sql`:

```sql
-- frieze is density's population seen band by band: a band in one and not the
-- other means the aggregate view and the detailed view disagree on what exists.
CREATE OR REPLACE VIEW frieze_population_mismatch AS
  SELECT f.mbid FROM frieze f
  WHERE NOT EXISTS (
    SELECT 1 FROM bands b, UNNEST(b.genres) AS t(g)
    JOIN genres gx ON gx.genre_mbid = t.g.mbid
    WHERE b.mbid = f.mbid AND gx.density_eligible);
-- The row index is the identity the blobs publish: a gap or a duplicate
-- silently shifts every band the frieze draws.
CREATE OR REPLACE VIEW frieze_index_broken AS
  SELECT i FROM frieze GROUP BY i HAVING count(*) > 1
  UNION ALL
  SELECT 1 WHERE (SELECT count(*) FROM frieze) <> (SELECT count(DISTINCT i) FROM frieze)
  UNION ALL
  SELECT 1 WHERE (SELECT max(i) + 1 FROM frieze) <> (SELECT count(*) FROM frieze);
-- Years are written into 15 bits of a u16, the top bit carrying a flag.
CREATE OR REPLACE VIEW frieze_year_unencodable AS
  SELECT i FROM frieze WHERE y0 < 0 OR y0 > 32767 OR y1 < 0 OR y1 > 32767 OR y1 < y0;
```

Add the three names to `INVARIANTS` in `src/musilogy/build.py`, after `"density_excluded_genre_present"`:

```python
    "frieze_population_mismatch",
    "frieze_index_broken",
    "frieze_year_unencodable",
```

- [ ] **Step 6: Test the invariants**

Append to `tests/test_invariants.py`:

```python
def test_frieze_invariants_are_empty_on_the_fixtures(con):
    from musilogy.build import check_invariants
    from musilogy.paths import SQL_DIR

    violations = dict(check_invariants(con, SQL_DIR))
    for name in ("frieze_population_mismatch", "frieze_index_broken", "frieze_year_unencodable"):
        assert name not in violations
```

Run: `uv run pytest tests/test_invariants.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/musilogy/sql/70_frieze.sql src/musilogy/sql/90_invariants.sql src/musilogy/build.py tests/test_frieze.py tests/test_invariants.py
git commit -m "feat(frieze): project the display population as its own table"
```

---

### Task 3: The `lineage` table

Oriented edges between frieze bands that shared a musician.

**Files:**
- Create: `src/musilogy/sql/85_lineage.sql`, `tests/test_lineage.py`
- Modify: `src/musilogy/sql/90_invariants.sql`, `src/musilogy/build.py`

**Interfaces:**
- Consumes: `frieze` (Task 2), `members` (80_members).
- Produces: table `lineage(src BIGINT, dst BIGINT, shared UTINYINT)` where `src` and `dst` are `frieze.i`. Task 5 serialises it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_lineage.py`:

```python
def test_lineage_edges_point_forward_in_time(con):
    backwards = con.execute("""
        SELECT count(*) FROM lineage l
        JOIN frieze s ON s.i = l.src JOIN frieze t ON t.i = l.dst
        WHERE s.y0 >= t.y0
    """).fetchone()
    assert backwards[0] == 0


def test_lineage_drops_pairs_formed_the_same_year(con):
    # Two bands formed the same year give no direction, and inventing one would
    # assert a precedence the source does not carry.
    same_year = con.execute("""
        SELECT count(*) FROM frieze a JOIN frieze b ON a.y0 = b.y0 AND a.i < b.i
        WHERE EXISTS (
          SELECT 1 FROM members ma JOIN members mb ON ma.person_mbid = mb.person_mbid
          WHERE ma.band_mbid = a.mbid AND mb.band_mbid = b.mbid)
          AND EXISTS (SELECT 1 FROM lineage l WHERE (l.src, l.dst) IN ((a.i, b.i), (b.i, a.i)))
    """).fetchone()
    assert same_year[0] == 0


def test_lineage_counts_distinct_shared_musicians(con):
    wrong = con.execute("""
        SELECT count(*) FROM lineage l
        JOIN frieze s ON s.i = l.src JOIN frieze t ON t.i = l.dst
        WHERE l.shared <> (
          SELECT count(DISTINCT ma.person_mbid) FROM members ma
          JOIN members mb ON ma.person_mbid = mb.person_mbid
          WHERE ma.band_mbid = s.mbid AND mb.band_mbid = t.mbid)
    """).fetchone()
    assert wrong[0] == 0


def test_lineage_has_no_self_edge_and_no_duplicate(con):
    assert con.execute("SELECT count(*) FROM lineage WHERE src = dst").fetchone()[0] == 0
    assert con.execute(
        "SELECT count(*) FROM (SELECT src, dst FROM lineage GROUP BY 1,2 HAVING count(*) > 1)"
    ).fetchone()[0] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_lineage.py -v`
Expected: FAIL — `Catalog Error: Table with name lineage does not exist`.

- [ ] **Step 3: Write the SQL**

Create `src/musilogy/sql/85_lineage.sql`. It must run after 80_members and after 70_frieze; 85_ satisfies both and leaves 90_ to the invariants.

```sql
-- Lineage between bands, derived from the musicians they share. This is not
-- influence: MusicBrainz carries no influence relationship, Wikidata's P737
-- covers 624 bands of 682 447 and DBpedia's influencedBy none at all. What the
-- source does carry is who played where, and two bands sharing a musician are
-- linked by a fact the reader can check — which is the only claim this table
-- makes.
--
-- Restricted to `frieze` on both ends: an edge toward a band the frieze cannot
-- draw has nowhere to land.
CREATE OR REPLACE TABLE lineage AS
WITH m AS (
  SELECT f.i, f.y0, r.person_mbid
  FROM members r JOIN frieze f ON f.mbid = r.band_mbid
)
SELECT
  a.i AS src,
  b.i AS dst,
  least(count(DISTINCT a.person_mbid), 255)::UTINYINT AS shared
FROM m a JOIN m b ON a.person_mbid = b.person_mbid
-- Oriented by formation year, and only when the years differ: equal years give
-- no precedence, and the pair is dropped rather than ordered arbitrarily.
WHERE a.y0 < b.y0
GROUP BY a.i, b.i;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_lineage.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Add the invariants**

Append to `src/musilogy/sql/90_invariants.sql`:

```sql
-- Both ends must be drawable rows of `frieze`, or the published edge points at
-- a row index the blob does not contain.
CREATE OR REPLACE VIEW lineage_endpoint_missing AS
  SELECT src AS i FROM lineage WHERE src NOT IN (SELECT i FROM frieze)
  UNION ALL
  SELECT dst FROM lineage WHERE dst NOT IN (SELECT i FROM frieze);
CREATE OR REPLACE VIEW lineage_not_oriented AS
  SELECT l.src FROM lineage l
  JOIN frieze s ON s.i = l.src JOIN frieze t ON t.i = l.dst
  WHERE s.y0 >= t.y0;
CREATE OR REPLACE VIEW lineage_duplicate AS
  SELECT src, dst FROM lineage GROUP BY src, dst HAVING count(*) > 1;
```

Add to `INVARIANTS` in `build.py`, after the three frieze names:

```python
    "lineage_endpoint_missing",
    "lineage_not_oriented",
    "lineage_duplicate",
```

- [ ] **Step 6: Run the whole fast suite**

Run: `uv run pytest -q`
Expected: PASS, no regression.

- [ ] **Step 7: Commit**

```bash
git add src/musilogy/sql/85_lineage.sql src/musilogy/sql/90_invariants.sql src/musilogy/build.py tests/test_lineage.py
git commit -m "feat(lineage): derive oriented band lineage from shared musicians"
```

---

### Task 4: Serialise `frieze.bin`

**Files:**
- Modify: `src/musilogy/publish.py`
- Test: `tests/test_publish.py`

**Interfaces:**
- Consumes: table `frieze` (Task 2), `bands.genres`, `genres.genre_mbid`.
- Produces: `write_frieze_blob(con, path) -> int` returning the number of bands written, and the file `web/frieze.bin.gz`. Task 5 follows the same shape.

**Layout** — little-endian; every section starts at a multiple of its element size, or `TypedArray` construction throws `RangeError` in the browser:

| offset | section | type | length |
|---|---|---|---|
| 0 | magic `MFZ1` | `u8` | 4 |
| 4 | version, padding | `u16` | 2 |
| 8 | `n_bands`, `n_pairs` | `u32` | 2 |
| 16 | `name_offsets` | `u32` | n+1 |
| … | `genre_offsets` | `u32` | n+1 |
| … | `spans` | `u16` | 2n |
| … | `genre_ids` | `u16` | n_pairs |
| … | `n_albums` | `u8` | n |
| … | `names` | UTF-8 | rest |

`spans[2i] = y0 | (ended << 15)` and `spans[2i+1] = y1 | (y_end_declared << 15)`. Years are ≤ 2026, so bit 15 is free — the `frieze_year_unencodable` invariant of Task 2 guarantees it.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_publish.py`:

```python
import struct

from musilogy.publish import write_frieze_blob


def read_frieze_blob(raw):
    """Mirrors what the browser does: a header, then typed-array views."""
    assert raw[:4] == b"MFZ1"
    n, pairs = struct.unpack_from("<II", raw, 8)
    o = 16
    name_offsets = struct.unpack_from(f"<{n + 1}I", raw, o); o += 4 * (n + 1)
    genre_offsets = struct.unpack_from(f"<{n + 1}I", raw, o); o += 4 * (n + 1)
    spans = struct.unpack_from(f"<{2 * n}H", raw, o); o += 4 * n
    genre_ids = struct.unpack_from(f"<{pairs}H", raw, o); o += 2 * pairs
    albums = struct.unpack_from(f"<{n}B", raw, o); o += n
    names = raw[o:]
    return {
        "n": n, "pairs": pairs, "spans": spans, "albums": albums,
        "genre_ids": genre_ids, "genre_offsets": genre_offsets,
        "names": [names[name_offsets[i]:name_offsets[i + 1] - 1].decode() for i in range(n)],
    }


def test_frieze_blob_round_trips_every_band(con, tmp_path):
    path = tmp_path / "frieze.bin.gz"
    written = write_frieze_blob(con, path)
    blob = read_frieze_blob(gzip.decompress(path.read_bytes()))
    expected = con.execute(
        "SELECT name, y0, y1, ended, y_end_declared, n_albums FROM frieze ORDER BY i"
    ).fetchall()
    assert written == blob["n"] == len(expected)
    assert blob["names"] == [r[0] for r in expected]
    for i, (_, y0, y1, ended, declared, n_albums) in enumerate(expected):
        assert blob["spans"][2 * i] & 0x7FFF == y0
        assert blob["spans"][2 * i + 1] & 0x7FFF == y1
        assert bool(blob["spans"][2 * i] >> 15) == ended
        assert bool(blob["spans"][2 * i + 1] >> 15) == declared
        assert blob["albums"][i] == n_albums


def test_frieze_blob_sections_are_aligned_for_typed_arrays(con, tmp_path):
    # A TypedArray whose byteOffset is not a multiple of its element size throws
    # RangeError in the browser, so the offsets are asserted rather than hoped
    # for. Computed the way a reader computes them, from the header alone.
    path = tmp_path / "frieze.bin.gz"
    write_frieze_blob(con, path)
    raw = gzip.decompress(path.read_bytes())
    n, pairs = struct.unpack_from("<II", raw, 8)
    name_offsets_at = 16
    genre_offsets_at = name_offsets_at + 4 * (n + 1)
    spans_at = genre_offsets_at + 4 * (n + 1)
    genre_ids_at = spans_at + 4 * n
    albums_at = genre_ids_at + 2 * pairs
    assert name_offsets_at % 4 == 0
    assert genre_offsets_at % 4 == 0
    assert spans_at % 2 == 0
    assert genre_ids_at % 2 == 0
    assert albums_at + n <= len(raw)


def test_frieze_blob_carries_no_timestamp(con, tmp_path):
    path = tmp_path / "frieze.bin.gz"
    write_frieze_blob(con, path)
    assert int.from_bytes(path.read_bytes()[4:8], "little") == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_publish.py -k frieze_blob -v`
Expected: FAIL with `ImportError: cannot import name 'write_frieze_blob'`.

- [ ] **Step 3: Write the serialiser**

Add to `src/musilogy/publish.py`, after `_columnar`:

```python
FRIEZE_MAGIC = b"MFZ1"
FRIEZE_VERSION = 1


def write_frieze_blob(con: duckdb.DuckDBPyConnection, path: Path) -> int:
    """Serialises `frieze` as typed arrays. Sections are laid out so each one
    starts at a multiple of its element size: a TypedArray built on a
    misaligned byteOffset throws RangeError in the browser."""
    rows = con.execute(
        "SELECT f.i, f.name, f.y0, f.y1, f.ended, f.y_end_declared, f.n_albums, "
        "  coalesce(list_transform(b.genres, g -> g.mbid), []) AS genre_mbids "
        "FROM frieze f JOIN bands b ON b.mbid = f.mbid ORDER BY f.i"
    ).fetchall()
    vocabulary = {
        mbid: index
        for index, (mbid,) in enumerate(
            con.execute("SELECT genre_mbid FROM genres ORDER BY genre_mbid").fetchall()
        )
    }

    names = bytearray()
    name_offsets = [0]
    genre_offsets = [0]
    spans: list[int] = []
    genre_ids: list[int] = []
    albums: list[int] = []
    for _, name, y0, y1, ended, declared, n_albums, genre_mbids in rows:
        names += name.encode() + b"\n"
        name_offsets.append(len(names))
        spans += [y0 | (int(ended) << 15), y1 | (int(declared) << 15)]
        albums.append(n_albums)
        genre_ids += [vocabulary[m] for m in genre_mbids if m in vocabulary]
        genre_offsets.append(len(genre_ids))

    n = len(rows)
    blob = b"".join(
        (
            FRIEZE_MAGIC,
            struct.pack("<HH", FRIEZE_VERSION, 0),
            struct.pack("<II", n, len(genre_ids)),
            struct.pack(f"<{n + 1}I", *name_offsets),
            struct.pack(f"<{n + 1}I", *genre_offsets),
            struct.pack(f"<{2 * n}H", *spans),
            struct.pack(f"<{len(genre_ids)}H", *genre_ids),
            struct.pack(f"<{n}B", *albums),
            bytes(names),
        )
    )
    path.write_bytes(gzip.compress(blob, 9, mtime=0))
    return n
```

Add `import struct` to the imports at the top of the file, in alphabetical order among the standard-library imports.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_publish.py -k frieze_blob -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/musilogy/publish.py tests/test_publish.py
git commit -m "feat(publish): serialise the frieze as a binary blob"
```

---

### Task 5: Serialise `lineage.bin` and `frieze_ids.bin`, and wire all three into `publish()`

**Files:**
- Modify: `src/musilogy/publish.py`
- Test: `tests/test_publish.py`

**Interfaces:**
- Consumes: `write_frieze_blob` (Task 4), tables `frieze` and `lineage`.
- Produces: `write_lineage_blob(con, path) -> int`, `write_frieze_ids(con, path) -> int`, and three files under `web/`. `publish()` writes them and `output_sha256` covers them.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_publish.py`:

```python
from musilogy.publish import write_frieze_ids, write_lineage_blob


def test_lineage_blob_round_trips_every_edge(con, tmp_path):
    path = tmp_path / "lineage.bin.gz"
    written = write_lineage_blob(con, path)
    raw = gzip.decompress(path.read_bytes())
    assert len(raw) == written * 9
    got = [struct.unpack_from("<IIB", raw, 9 * k) for k in range(written)]
    assert got == con.execute("SELECT src, dst, shared FROM lineage ORDER BY src, dst").fetchall()


def test_frieze_ids_are_raw_sixteen_byte_uuids_in_row_order(con, tmp_path):
    # Published without gzip: UUIDs do not compress, and the row order is what
    # makes the join to frieze.bin implicit.
    path = tmp_path / "frieze_ids.bin"
    written = write_frieze_ids(con, path)
    raw = path.read_bytes()
    assert len(raw) == written * 16
    expected = con.execute("SELECT mbid FROM frieze ORDER BY i").fetchall()
    assert raw[:16].hex() == expected[0][0].replace("-", "")


def test_publish_delivers_the_three_blobs_and_digests_them(con, tmp_path):
    manifest = publish(con, tmp_path, DUMP, None)
    for name in ("web/frieze.bin.gz", "web/lineage.bin.gz", "web/frieze_ids.bin"):
        assert (tmp_path / name).exists()
        assert name in manifest["output_sha256"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_publish.py -k "lineage_blob or frieze_ids or three_blobs" -v`
Expected: FAIL with `ImportError: cannot import name 'write_lineage_blob'`.

- [ ] **Step 3: Write the serialisers**

Add to `src/musilogy/publish.py`, after `write_frieze_blob`:

```python
def write_lineage_blob(con: duckdb.DuckDBPyConnection, path: Path) -> int:
    """One 9-byte record per edge: src, dst as u32 row indices of `frieze`,
    then the shared-musician count as u8. Sorted by (src, dst), which groups
    a band's edges without a separate index."""
    edges = con.execute("SELECT src, dst, shared FROM lineage ORDER BY src, dst").fetchall()
    blob = b"".join(struct.pack("<IIB", src, dst, shared) for src, dst, shared in edges)
    path.write_bytes(gzip.compress(blob, 9, mtime=0))
    return len(edges)


def write_frieze_ids(con: duckdb.DuckDBPyConnection, path: Path) -> int:
    """Raw 16-byte mbids in frieze row order, so the join back to frieze.bin
    needs no key. Written uncompressed: UUIDs are incompressible, and gzip here
    would only add a header."""
    rows = con.execute("SELECT mbid FROM frieze ORDER BY i").fetchall()
    path.write_bytes(b"".join(bytes.fromhex(mbid.replace("-", "")) for (mbid,) in rows))
    return len(rows)
```

- [ ] **Step 4: Wire them into `publish()`**

In `publish()`, immediately after the `for name, condition in (...)` loop that writes `bands_timeline` and `bands_rest`, and before the pruning loop:

```python
    written.add("frieze.bin.gz")
    written.add("lineage.bin.gz")
    write_frieze_blob(con, web_dir / "frieze.bin.gz")
    write_lineage_blob(con, web_dir / "lineage.bin.gz")
    write_frieze_ids(con, web_dir / "frieze_ids.bin")
```

The pruning loop below globs `web/*.json.gz` only, so `frieze_ids.bin` is untouched by it; the two `.gz` names must be in `written` or the next run deletes them.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_publish.py -v`
Expected: PASS, including the existing `output_sha256` test which now covers three more files.

- [ ] **Step 6: Run the whole fast suite, lint and types**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src tests`
Expected: all clean.

- [ ] **Step 7: Commit**

```bash
git add src/musilogy/publish.py tests/test_publish.py
git commit -m "feat(publish): deliver the lineage and identity blobs"
```

---

### Task 6: Freeze the new counts on the real dump

**Files:**
- Modify: `tests/test_baseline.py`

**Interfaces:**
- Consumes: everything above.
- Produces: the contractual figures for `frieze` and `lineage`.

- [ ] **Step 1: Measure on the reference dump**

Run:

```bash
uv run python -c "
import duckdb
from musilogy.build import build
from musilogy.paths import SQL_DIR, work_dir
from musilogy import REFERENCE_DUMP as D
w = work_dir(D)
con = duckdb.connect(':memory:')
build(con, SQL_DIR, w / 'artists.jsonl', w / 'release_groups.jsonl', None)
print('frieze', con.execute('SELECT count(*) FROM frieze').fetchone()[0])
print('lineage', con.execute('SELECT count(*) FROM lineage').fetchone()[0])
print('lineage >=2', con.execute('SELECT count(*) FROM lineage WHERE shared >= 2').fetchone()[0])
print('albums 0', con.execute('SELECT count(*) FROM frieze WHERE n_albums = 0').fetchone()[0])
"
```

Expected order of magnitude, from the spec: `frieze` ≈ 84 262, `lineage` ≈ 37 322, `shared >= 2` ≈ 5 340. **If a figure differs, do not adjust the expectation to match the output.** Find the rule that produced the difference, say why the new figure is the right one, and only then freeze it — that is the repository's standing rule for baseline drift.

- [ ] **Step 2: Write the baseline assertions**

There is no shared fixture: `test_reference_dump_matches_the_baseline` builds
its own connection inline and skips when the extractions are absent. Extend
that test rather than adding a second one — a new slow test would replay the
whole pipeline a second time and double the suite's runtime for nothing.

Add the constants near the other frozen figures at the top of
`tests/test_baseline.py`, using the values measured in Step 1:

```python
# The frieze projection and its lineage graph. FRIEZE is density's population
# seen band by band: if it diverges from the density population, one of the two
# is wrong, and the frieze_population_mismatch invariant says which.
FRIEZE = 84_262
LINEAGE = 37_322
LINEAGE_STRONG = 5_340
```

Then append these assertions at the end of the body of
`test_reference_dump_matches_the_baseline`, following the `row is not None`
style the file already uses:

```python
    row = con.execute("SELECT count(*) FROM frieze").fetchone()
    assert row is not None
    assert row[0] == FRIEZE

    row = con.execute("SELECT count(*) FROM lineage").fetchone()
    assert row is not None
    assert row[0] == LINEAGE

    row = con.execute("SELECT count(*) FROM lineage WHERE shared >= 2").fetchone()
    assert row is not None
    assert row[0] == LINEAGE_STRONG
```

- [ ] **Step 3: Run the slow suite**

Run: `uv run pytest -m slow -q`
Expected: PASS. This replays the pipeline on the real dump and takes several minutes.

- [ ] **Step 4: Verify byte reproducibility end to end**

Run:

```bash
uv run musilogy run >/dev/null
sha256sum data/out/*/web/*.bin data/out/*/web/*.gz > /tmp/run_a.sha
uv run musilogy run >/dev/null
sha256sum data/out/*/web/*.bin data/out/*/web/*.gz > /tmp/run_b.sha
diff /tmp/run_a.sha /tmp/run_b.sha && echo BYTE-IDENTICAL
```

Expected: `BYTE-IDENTICAL`. If not, a serialiser is iterating something unordered — find it rather than re-running.

- [ ] **Step 5: Commit**

```bash
git add tests/test_baseline.py
git commit -m "test(baseline): freeze the frieze and lineage counts"
```

---

## Out of scope for this plan

The front end (reading the blobs, canvas rendering, search, lineage arcs), the ListenBrainz call, the genre seriation order, versioning the blobs into `web/public/data/`, and the fast-suite guard comparing committed blobs to the manifest. Each depends on this plan's artifacts existing and gets its own plan.

Removing `bands_timeline.json.gz` and `bands_rest.json.gz`, which lose their consumer once the frieze reads the blobs, is a delivery-contract change and belongs in its own PR after the front end works.
