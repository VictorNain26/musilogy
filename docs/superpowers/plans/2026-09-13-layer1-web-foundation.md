# Layer 1 — Web foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `web/` TypeScript workspace and the pure functions that turn the three published blobs back into the tables layer 0 holds, with the delivered blobs versioned in the repository and guarded against drift.

**Architecture:** A Vite + TypeScript workspace rooted at `web/`, tested with Vitest in a Node environment. Reading a blob is a pure function from `ArrayBuffer` to typed arrays — no DOM, no fetch, no canvas — so the whole of this plan is testable without a browser. Two independent fixtures guard it: the witness blobs, republished from the Python test fixtures and compared byte for byte, and the real delivered blobs, whose SHA-256 must match the committed manifest.

**Tech Stack:** Node 24.16.0, pnpm 11.24.0, vite 8.3.0, vitest 4.1.11, typescript 7.0.2, @biomejs/biome 2.5.13. No runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-09-13-layer1-frieze-design.md`

**Not in this plan.** The canvas renderer, the time window, the density banner and its cutoff year, search, selection, lineage arcs, ListenBrainz, the exposed state object, the Playwright end-to-end suite and the GitHub Pages deployment. They need a page to act on; this plan builds what the page will read. The two layer 0 debts the spec assigns to their own PR — the genre ordering column, and retiring `bands_timeline.json.gz` / `bands_rest.json.gz` — are also out of scope.

## Global Constraints

- **Every measurement in this plan was taken on this repository at commit `684522f` (pre-rebase) / the tip of `feat/layer0-frieze-blobs`.** Numbers are acceptance criteria, not illustrations: a step that produces a different one has found a bug, in the code or in this plan.
- **No runtime dependency.** `web/package.json` carries `devDependencies` only. The spec rejects `d3-scale` and `hyparquet` by measurement; do not reintroduce a library without one.
- **Pin to the patch.** Every version in `package.json` is exact — no `^`, no `~`. The repository pins its Python dependencies to the patch because the pipeline's reproducibility depends on it; the reader of a byte format has the same obligation.
- **English** in code, comments, commit messages and identifiers.
- **Zero comments by default.** A comment earns its place only for a non-obvious WHY — a hidden constraint, a subtle invariant, a workaround for a precise bug. Three such comments are prescribed by name in this plan; they are not optional, and they are close to the whole budget.
- **Strict validation at the boundary, trust inside.** A blob arriving from the network is a boundary: check its magic, its version and its self-consistency. Between two of our own functions, no defensive guard.
- Commits follow `<type>(<scope>): <description>`.

## What the blobs actually contain

Measured, not quoted from the spec. `src/musilogy/publish.py` is the authority; this section is what a reader must implement against.

**`frieze.bin.gz`** — gzip of a little-endian blob. On the reference dump `20260909-001002`: 1 167 037 bytes gzipped, 84 262 bands. On the witnesses: 595 bytes gzipped, 762 raw, 20 bands, 130 band-genre pairs.

| offset | section | type | length |
|---|---|---|---|
| 0 | magic | `u8[4]` | `MFZ1` |
| 4 | version | `u16` | `1` |
| 6 | padding | `u16` | |
| 8 | `n_bands` | `u32` | |
| 12 | `n_pairs` | `u32` | |
| 16 | `name_offsets` | `u32` | `n_bands + 1` |
| `16 + 4(n+1)` | `genre_offsets` | `u32` | `n_bands + 1` |
| `16 + 8(n+1)` | `spans` | `u16` | `2 · n_bands` |
| `16 + 8(n+1) + 4n` | `genre_ids` | `u16` | `n_pairs` |
| `… + 2·n_pairs` | `n_albums` | `u8` | `n_bands` |
| `… + n_bands` | `names` | UTF-8 | to the end |

Three things the table does not show, all verified by decoding the witness blob:

- **`spans` packs a flag into the high bit of each word.** `spans[2i] = y0 | (ended << 15)` and `spans[2i+1] = y1 | (y_end_is_declared << 15)`. Mask with `0x7fff`, shift by 15. Witness band 0, The Beatles: `spans[0] = 34728` → `y0 = 1960`, `ended = 1`; `spans[1] = 34738` → `y1 = 1970`, `y_end_is_declared = 1`.
- **Each name is followed by a `\n` that its own offset range includes.** The writer does `names += name.encode() + b"\n"` and only then records the offset. Band `i` is therefore `names[name_offsets[i] .. name_offsets[i+1] - 1]`, dropping the last byte. Witness band 0 decodes to `"The Beatles\n"` if you forget it.
- **`genre_ids` index `web/genres.json.gz` directly.** The blob's vocabulary is `SELECT genre_mbid FROM genres ORDER BY genre_mbid` and `ORDER_BY["genres"]` in `publish.py:52` is `"genre_mbid"` — the same order, so `genre_ids[k]` is a position in the delivered arrays. Band `i` owns `genre_ids[genre_offsets[i] .. genre_offsets[i+1]]`.

**`lineage.bin.gz`** — 108 131 bytes gzipped on the reference dump, 37 136 edges. On the witnesses: 35 bytes gzipped, 21 raw, 1 edge — `src = 6` (Joy Division), `dst = 7` (New Order), `shared = 3`.

| offset | section | type | length |
|---|---|---|---|
| 0 | magic | `u8[4]` | `MLN1` |
| 4 | version | `u16` | `1` |
| 6 | padding | `u16` | |
| 8 | `n_edges` | `u32` | |
| 12 | `src` | `u32` | `n_edges` |
| `12 + 4n` | `dst` | `u32` | `n_edges` |
| `12 + 8n` | `shared` | `u8` | `n_edges` |

`src` and `dst` are row indices of `frieze.bin`, not MBIDs.

**`frieze_ids.bin`** — uncompressed. 1 348 208 bytes on the reference dump, 336 on the witnesses, which is `16 + 20 × 16`.

| offset | section | type | length |
|---|---|---|---|
| 0 | magic | `u8[4]` | `MID1` |
| 4 | version | `u16` | `1` |
| 6 | padding | `u16` | |
| 8 | `n_bands` | `u32` | |
| 12 | padding | `u8[4]` | |
| 16 | `mbid` | `u8[16]` | `n_bands` |

The 4 bytes of padding make record `k` start at `16(k + 1)`, a multiple of its own size.

## The gzip trap

Vite's dev server and GitHub Pages disagree about a file named `*.gz`, and the disagreement is invisible until the wrong one is deployed.

- Vite 8 serves `public/` through `sirv`, which maps the `.gz` extension to `Content-Encoding: gzip` (`sirv/index.mjs`, `const ENCODING = { '.br': 'br', '.gz': 'gzip' }`). `fetch` therefore decompresses transparently and hands the caller the raw blob.
- GitHub Pages sends `Content-Type: application/gzip` with **no** `Content-Encoding` — measured on four live Pages sites on 2026-09-13, all returning the gzip bytes verbatim. The long-standing request to support pre-compressed files (github/isaacs/github#611, community discussion #21655) has never been implemented.

The upstream Vite issue is vitejs/vite#12266, open since 2023-03-02 and unresolved. So the reader cannot assume either behaviour: it sniffs the two gzip magic bytes `1f 8b` and decompresses only when they are there. That branch is not defensive programming inside our own code — it is a boundary whose two servers behave differently.

## File Structure

```
web/
  package.json          exact-pinned devDependencies, the four scripts
  pnpm-lock.yaml
  vite.config.ts        Vite config + the Vitest `test` key
  tsconfig.json
  biome.json
  index.html            placeholder until the renderer plan
  src/
    blob/
      gzip.ts           inflateIfGzipped, loadBlob — the network boundary
      frieze.ts         readFrieze
      lineage.ts        readLineage
      ids.ts            readFriezeIds
  tests/
    fixtures/           witness blobs, produced by `musilogy make-web-fixtures`
    gzip.test.ts
    frieze.test.ts
    lineage.test.ts
    ids.test.ts
    delivered.test.ts   the real blobs, read end to end
  public/
    data/               the delivered blobs, versioned
```

Python side: `src/musilogy/paths.py` gains three constants, `src/musilogy/cli.py` gains two commands, `tests/` gains one file. Nothing in `build.py`, `extract.py` or the SQL changes — layer 0 is complete.

One file per blob rather than one `reader.ts`: each is a different format with its own header, they change independently, and a subagent can hold one in context whole.

---

### Task 1: The `web/` workspace

**Files:**
- Create: `web/package.json`, `web/.nvmrc`, `web/vite.config.ts`, `web/tsconfig.json`, `web/biome.json`, `web/index.html`, `web/src/version.ts`, `web/tests/version.test.ts`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: nothing.
- Produces: the four pnpm scripts every later task runs — `pnpm run check` (Biome, non-writing), `pnpm run types` (`tsc --noEmit`), `pnpm run test` (`vitest run`), `pnpm run build` (`vite build`). All are run from `web/`.

- [ ] **Step 1: Write the failing test**

`web/tests/version.test.ts` — a single test proving the harness resolves TypeScript sources, runs in Node, and has `DecompressionStream` available, which every later task depends on:

```ts
import { describe, expect, it } from "vitest";
import { FORMAT_VERSION } from "../src/version";

describe("the test harness", () => {
  it("resolves a TypeScript source", () => {
    expect(FORMAT_VERSION).toBe(1);
  });

  it("has DecompressionStream, which the blob reader needs", () => {
    expect(typeof DecompressionStream).toBe("function");
  });
});
```

- [ ] **Step 2: Create the workspace and run the test to verify it fails**

`web/package.json` — versions exact, no range:

```json
{
  "name": "musilogy-web",
  "private": true,
  "type": "module",
  "packageManager": "pnpm@11.24.0",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "check": "biome ci .",
    "fix": "biome check --write .",
    "types": "tsc --noEmit",
    "test": "vitest run"
  },
  "devDependencies": {
    "@biomejs/biome": "2.5.13",
    "typescript": "7.0.2",
    "vite": "8.3.0",
    "vitest": "4.1.11"
  }
}
```

`web/.nvmrc` — one line, `24.16.0`. Both `nvm use` and the CI job read it, so the Node version lives in one place, pinned to the patch like everything else in this repository.

`web/tsconfig.json` — `baseUrl` is gone in TypeScript 7 and is not used here; `bundler` resolution is still accepted and is what Vite expects:

```json
{
  "compilerOptions": {
    "target": "es2022",
    "lib": ["es2023", "dom", "dom.iterable"],
    "module": "esnext",
    "moduleResolution": "bundler",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "verbatimModuleSyntax": true,
    "isolatedModules": true,
    "skipLibCheck": true,
    "noEmit": true
  },
  "include": ["src", "tests", "vite.config.ts"]
}
```

`web/vite.config.ts` — Vitest 4 reads a `test` key straight out of the Vite config when the triple-slash reference is present, which avoids a second config file that would silently override this one:

```ts
/// <reference types="vitest/config" />
import { defineConfig } from "vite";

export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
  },
});
```

`web/biome.json`:

```json
{
  "$schema": "https://biomejs.dev/schemas/2.5.13/schema.json",
  "vcs": { "enabled": true, "clientKind": "git", "useIgnoreFile": true },
  "files": { "ignoreUnknown": false },
  "formatter": { "enabled": true, "indentStyle": "space", "indentWidth": 2, "lineWidth": 100 },
  "linter": { "enabled": true, "rules": { "recommended": true } },
  "javascript": { "formatter": { "quoteStyle": "double" } },
  "assist": { "enabled": true, "actions": { "source": { "organizeImports": "on" } } }
}
```

`web/index.html` — a placeholder the renderer plan replaces:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>musilogy</title>
  </head>
  <body></body>
</html>
```

Then:

```bash
cd web && pnpm install && pnpm run test
```

Expected: FAIL, `Cannot find module '../src/version'`.

- [ ] **Step 3: Write the minimal source**

`web/src/version.ts`:

```ts
export const FORMAT_VERSION = 1;
```

- [ ] **Step 4: Run the full local gate**

```bash
cd web && pnpm run check && pnpm run types && pnpm run test
```

Expected: Biome reports no diagnostics, `tsc` prints nothing, Vitest reports `2 passed`.

If Biome reports formatting differences on the files you just wrote, run `pnpm run fix` and re-run — do not hand-tune the files to match.

- [ ] **Step 5: Add the Node job to CI**

`.github/workflows/ci.yml` gains a second job beside the existing `test` job. Do not touch the Python job.

The workflow pins every action by full commit SHA with the tag in a trailing comment — `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1`. Match that convention; the SHAs below were resolved from the GitHub API on 2026-09-13, `actions/checkout` being reused verbatim from the existing job.

```yaml
  web:
    name: web lint, type-check, test
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1

      # Before setup-node, which needs pnpm on PATH to resolve its store for
      # the cache. package_json_file points at web/, whose packageManager
      # field is the single place the pnpm version is written.
      - uses: pnpm/action-setup@ea17c68df8912ef543352723c149a84f56e3d413 # v6.1.0
        with:
          package_json_file: web/package.json

      - uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0
        with:
          node-version-file: web/.nvmrc
          cache: pnpm
          cache-dependency-path: web/pnpm-lock.yaml

      - name: Install
        run: pnpm install --frozen-lockfile

      - name: Biome
        run: pnpm run check

      - name: Types
        run: pnpm run types

      - name: Test
        run: pnpm run test

      - name: Build
        run: pnpm run build
```

- [ ] **Step 6: Commit**

```bash
git add web/package.json web/pnpm-lock.yaml web/vite.config.ts web/tsconfig.json \
        web/biome.json web/index.html web/src/version.ts web/tests/version.test.ts \
        .github/workflows/ci.yml
git commit -m "build(web): stand up the Vite and TypeScript workspace"
```

---

### Task 2: Witness blobs for the TypeScript tests

The reader tests need blobs whose contents are known band by band. The repository already has the idiom: `musilogy make-fixtures` writes versioned witness files and `tests/test_fixtures.py` guards them against drift and against `.gitignore` swallowing them. This task applies it to the blobs.

**Files:**
- Modify: `src/musilogy/paths.py`, `src/musilogy/cli.py`
- Create: `tests/test_web_fixtures.py`
- Create (generated): `web/tests/fixtures/frieze.bin.gz`, `web/tests/fixtures/lineage.bin.gz`, `web/tests/fixtures/frieze_ids.bin`, `web/tests/fixtures/genres.json.gz`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `musilogy.paths.WEB_DIR`, `WEB_FIXTURES_DIR`, `WEB_DATA_DIR`; the CLI command `musilogy make-web-fixtures`; the four fixture files Tasks 4, 5 and 6 read.

- [ ] **Step 1: Write the failing test**

`tests/test_web_fixtures.py`. It re-publishes the witnesses into a temporary directory and demands the committed fixtures be byte-identical — the pipeline is deterministic, so anything else means the fixtures are stale.

```python
import subprocess

from musilogy import REFERENCE_DUMP as DUMP
from musilogy.paths import REPO_ROOT, WEB_FIXTURES_DIR
from musilogy.publish import publish

WEB_FIXTURES = ("frieze.bin.gz", "lineage.bin.gz", "frieze_ids.bin", "genres.json.gz")


def test_the_committed_web_fixtures_match_a_fresh_witness_publish(con, tmp_path):
    publish(con, tmp_path, DUMP, None)
    for name in WEB_FIXTURES:
        assert (WEB_FIXTURES_DIR / name).read_bytes() == (tmp_path / "web" / name).read_bytes(), (
            f"{name} is stale: run `uv run musilogy make-web-fixtures`"
        )


def test_the_web_fixtures_are_not_ignored_by_git():
    # Same trap as tests/fixtures/*.jsonl: a repo-wide pattern can swallow a
    # generated file that only survives because it is already in the index, and
    # a fresh clone then loses it silently.
    for name in WEB_FIXTURES:
        path = f"web/tests/fixtures/{name}"
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", path],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 128, (
            f"git check-ignore could not answer for {path}: {result.stderr.strip()}"
        )
        assert result.returncode == 1, f"{path} is ignored: {result.stdout.strip()}"


def test_the_witness_frieze_holds_the_bands_the_reader_tests_expect(con):
    assert con.execute("SELECT count(*) FROM frieze").fetchone()[0] == 20
    assert con.execute("SELECT count(*) FROM lineage").fetchone()[0] == 1
    assert con.execute("SELECT src, dst, shared FROM lineage").fetchone() == (6, 7, 3)
```

`from musilogy import REFERENCE_DUMP as DUMP` is the form `tests/test_publish.py:10` already uses; do not invent a second spelling.

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run pytest tests/test_web_fixtures.py -v
```

Expected: FAIL — `ImportError` on `WEB_FIXTURES_DIR`.

- [ ] **Step 3: Add the paths**

`src/musilogy/paths.py`, after `FIXTURES_DIR`:

```python
WEB_DIR = REPO_ROOT / "web"
WEB_FIXTURES_DIR = WEB_DIR / "tests" / "fixtures"
WEB_DATA_DIR = WEB_DIR / "public" / "data"
```

- [ ] **Step 4: Add the command**

`src/musilogy/cli.py`. Publishing to a temporary directory and copying out, rather than calling the three writers directly, is what makes the fixtures byte-identical to a real delivery: they travel the same code path.

```python
def make_web_fixtures() -> None:
    """Publishes the witness blobs the TypeScript reader tests read."""
    con = duckdb.connect(":memory:")
    build(con, SQL_DIR, FIXTURES_DIR / "artists.jsonl", FIXTURES_DIR / "release_groups.jsonl", None)
    WEB_FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        publish(con, out, DUMP, None)
        for name in ("frieze.bin.gz", "lineage.bin.gz", "frieze_ids.bin", "genres.json.gz"):
            shutil.copyfile(out / "web" / name, WEB_FIXTURES_DIR / name)
    print("web fixtures written to", WEB_FIXTURES_DIR)
```

Add the imports the file does not already have (`shutil`, `tempfile`, `Path`, `publish`, `FIXTURES_DIR`, `WEB_FIXTURES_DIR`) and register the subcommand in `main()`, beside `make-fixtures`:

```python
    subparsers.add_parser(
        "make-web-fixtures", help="publish the witness blobs the web reader tests read"
    )
```

```python
    elif args.command == "make-web-fixtures":
        make_web_fixtures()
```

- [ ] **Step 5: Generate the fixtures and run the test**

```bash
uv run musilogy make-web-fixtures
uv run pytest tests/test_web_fixtures.py -v
```

Expected: 3 passed. `web/tests/fixtures/frieze.bin.gz` must be **595 bytes** and `web/tests/fixtures/frieze_ids.bin` exactly **336** — that is `16 + 20 × 16`, and any other value means the witness population changed and the numbers in this plan no longer hold. Stop and report if so rather than adjusting the plan's expectations to the output.

- [ ] **Step 6: Run the whole fast suite**

```bash
uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest
```

Expected: 217 passed (214 before this task, plus the three added here).

- [ ] **Step 7: Commit**

```bash
git add src/musilogy/paths.py src/musilogy/cli.py tests/test_web_fixtures.py web/tests/fixtures
git commit -m "test(web): publish the witness blobs the reader tests read"
```

---

### Task 3: The network boundary

**Files:**
- Create: `web/src/blob/gzip.ts`, `web/tests/gzip.test.ts`

**Interfaces:**
- Consumes: the workspace from Task 1.
- Produces:
  - `inflateIfGzipped(bytes: Uint8Array): Promise<ArrayBuffer>`
  - `loadBlob(url: string): Promise<ArrayBuffer>`

  Tasks 4, 5 and 6 take an `ArrayBuffer`; only this file knows about gzip or the network.

- [ ] **Step 1: Write the failing test**

`web/tests/gzip.test.ts`. Both branches of the sniff are exercised, because production hits one and the dev server hits the other.

```ts
import { gzipSync } from "node:zlib";
import { describe, expect, it } from "vitest";
import { inflateIfGzipped } from "../src/blob/gzip";

const PLAIN = new Uint8Array([0x4d, 0x46, 0x5a, 0x31, 0x01, 0x00, 0x00, 0x00]);

describe("inflateIfGzipped", () => {
  it("decompresses bytes that start with the gzip magic", async () => {
    const buffer = await inflateIfGzipped(new Uint8Array(gzipSync(PLAIN)));
    expect(new Uint8Array(buffer)).toEqual(PLAIN);
  });

  it("passes bytes through when the server already decompressed them", async () => {
    const buffer = await inflateIfGzipped(PLAIN);
    expect(new Uint8Array(buffer)).toEqual(PLAIN);
  });

  it("does not carry the bytes of a larger backing buffer", async () => {
    const backing = new Uint8Array([0xff, 0xff, ...PLAIN, 0xff]);
    const view = backing.subarray(2, 2 + PLAIN.length);
    const buffer = await inflateIfGzipped(view);
    expect(buffer.byteLength).toBe(PLAIN.length);
    expect(new Uint8Array(buffer)).toEqual(PLAIN);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd web && pnpm run test
```

Expected: FAIL, `Cannot find module '../src/blob/gzip'`.

- [ ] **Step 3: Write the implementation**

`web/src/blob/gzip.ts`:

```ts
// Vite's dev server serves public/*.gz through sirv, which sets
// Content-Encoding: gzip, so fetch decompresses before we see the body.
// GitHub Pages sends the same file verbatim as application/gzip. The sniff is
// what lets one build read both (vitejs/vite#12266, open since 2023).
export async function inflateIfGzipped(bytes: Uint8Array): Promise<ArrayBuffer> {
  if (bytes[0] !== 0x1f || bytes[1] !== 0x8b) {
    return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  }
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
  return await new Response(stream).arrayBuffer();
}

export async function loadBlob(url: string): Promise<ArrayBuffer> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url}: HTTP ${response.status}`);
  }
  return inflateIfGzipped(new Uint8Array(await response.arrayBuffer()));
}
```

- [ ] **Step 4: Run the local gate**

```bash
cd web && pnpm run check && pnpm run types && pnpm run test
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add web/src/blob/gzip.ts web/tests/gzip.test.ts
git commit -m "feat(web): read a blob whether or not the server already ungzipped it"
```

---

### Task 4: `readFrieze`

**Files:**
- Create: `web/src/blob/frieze.ts`, `web/tests/frieze.test.ts`

**Interfaces:**
- Consumes: `web/tests/fixtures/frieze.bin.gz` from Task 2, `inflateIfGzipped` from Task 3.
- Produces:

```ts
export interface Frieze {
  readonly count: number;
  readonly pairs: number;
  readonly y0: Uint16Array;
  readonly y1: Uint16Array;
  readonly ended: Uint8Array;
  readonly yEndIsDeclared: Uint8Array;
  readonly nAlbums: Uint8Array;
  readonly genreOffsets: Uint32Array;
  readonly genreIds: Uint16Array;
  name(i: number): string;
}
export function readFrieze(buffer: ArrayBuffer): Frieze;
```

Tasks 5 and 6 use `count`; the renderer plan uses all of it.

- [ ] **Step 1: Write the failing test**

`web/tests/frieze.test.ts`. Every expected value here was measured by decoding the witness blob; do not soften one to make a test pass.

```ts
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { inflateIfGzipped } from "../src/blob/gzip";
import { readFrieze } from "../src/blob/frieze";

async function witness() {
  const bytes = new Uint8Array(readFileSync(new URL("fixtures/frieze.bin.gz", import.meta.url)));
  return readFrieze(await inflateIfGzipped(bytes));
}

describe("readFrieze", () => {
  it("reads the cardinalities", async () => {
    const frieze = await witness();
    expect(frieze.count).toBe(20);
    expect(frieze.pairs).toBe(130);
  });

  it("reads names without the separator the writer appends", async () => {
    const frieze = await witness();
    expect(frieze.name(0)).toBe("The Beatles");
    expect(frieze.name(6)).toBe("Joy Division");
    expect(frieze.name(19)).toBe("Lethal Shöck");
  });

  it("unpacks the flags out of the high bit of each span", async () => {
    const frieze = await witness();
    expect(frieze.y0[0]).toBe(1960);
    expect(frieze.y1[0]).toBe(1970);
    expect(frieze.ended[0]).toBe(1);
    expect(frieze.yEndIsDeclared[0]).toBe(1);
  });

  it("keeps an end that is over from an end that was never declared", async () => {
    const frieze = await witness();
    // Flesh Field: the band is over, but y1 was inferred from its last album.
    expect(frieze.name(12)).toBe("Flesh Field");
    expect(frieze.ended[12]).toBe(1);
    expect(frieze.yEndIsDeclared[12]).toBe(0);
    // ROD: one-year bar, and no evidence of an end at all.
    expect(frieze.name(13)).toBe("ROD");
    expect(frieze.y0[13]).toBe(1996);
    expect(frieze.y1[13]).toBe(1996);
    expect(frieze.ended[13]).toBe(0);
    expect(frieze.yEndIsDeclared[13]).toBe(0);
  });

  it("reads the album counts", async () => {
    const frieze = await witness();
    expect(frieze.nAlbums[0]).toBe(84);
    expect(frieze.nAlbums[13]).toBe(0);
  });

  it("slices a band's genres out of the shared array", async () => {
    const frieze = await witness();
    expect(frieze.genreOffsets[0]).toBe(0);
    expect(frieze.genreOffsets[1]).toBe(12);
    expect(frieze.genreOffsets[frieze.count]).toBe(frieze.pairs);
    expect(Array.from(frieze.genreIds.subarray(0, 5))).toEqual([4, 37, 31, 54, 11]);
  });

  it("refuses a blob that is not a frieze", async () => {
    const buffer = new ArrayBuffer(16);
    new Uint8Array(buffer).set([0x4d, 0x4c, 0x4e, 0x31]);
    expect(() => readFrieze(buffer)).toThrow(/MFZ1/);
  });

  it("refuses a version it does not know", async () => {
    const bytes = new Uint8Array(readFileSync(new URL("fixtures/frieze.bin.gz", import.meta.url)));
    const buffer = await inflateIfGzipped(bytes);
    new DataView(buffer).setUint16(4, 2, true);
    expect(() => readFrieze(buffer)).toThrow(/version 2/);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd web && pnpm run test
```

Expected: FAIL, `Cannot find module '../src/blob/frieze'`.

- [ ] **Step 3: Write the implementation**

`web/src/blob/frieze.ts`:

```ts
const MAGIC = "MFZ1";
const VERSION = 1;
const decoder = new TextDecoder();

export interface Frieze {
  readonly count: number;
  readonly pairs: number;
  readonly y0: Uint16Array;
  readonly y1: Uint16Array;
  readonly ended: Uint8Array;
  readonly yEndIsDeclared: Uint8Array;
  readonly nAlbums: Uint8Array;
  readonly genreOffsets: Uint32Array;
  readonly genreIds: Uint16Array;
  name(i: number): string;
}

export function readFrieze(buffer: ArrayBuffer): Frieze {
  const view = new DataView(buffer);
  const magic = decoder.decode(new Uint8Array(buffer, 0, 4));
  if (magic !== MAGIC) {
    throw new Error(`frieze.bin: expected magic ${MAGIC}, got ${JSON.stringify(magic)}`);
  }
  const version = view.getUint16(4, true);
  if (version !== VERSION) {
    throw new Error(`frieze.bin: unsupported version ${version}`);
  }

  const count = view.getUint32(8, true);
  const pairs = view.getUint32(12, true);

  let at = 16;
  const nameOffsets = new Uint32Array(buffer, at, count + 1);
  at += 4 * (count + 1);
  const genreOffsets = new Uint32Array(buffer, at, count + 1);
  at += 4 * (count + 1);
  const spans = new Uint16Array(buffer, at, 2 * count);
  at += 4 * count;
  const genreIds = new Uint16Array(buffer, at, pairs);
  at += 2 * pairs;
  const nAlbums = new Uint8Array(buffer, at, count);
  at += count;
  const names = new Uint8Array(buffer, at);

  if (nameOffsets[count] !== names.length) {
    throw new Error(
      `frieze.bin: names section is ${names.length} bytes, offsets end at ${nameOffsets[count]}`,
    );
  }

  const y0 = new Uint16Array(count);
  const y1 = new Uint16Array(count);
  const ended = new Uint8Array(count);
  const yEndIsDeclared = new Uint8Array(count);
  for (let i = 0; i < count; i++) {
    const begin = spans[2 * i];
    const end = spans[2 * i + 1];
    y0[i] = begin & 0x7fff;
    ended[i] = begin >>> 15;
    y1[i] = end & 0x7fff;
    yEndIsDeclared[i] = end >>> 15;
  }

  return {
    count,
    pairs,
    y0,
    y1,
    ended,
    yEndIsDeclared,
    nAlbums,
    genreOffsets,
    genreIds,
    // The writer appends "\n" after each name and records the offset past it,
    // so the range includes a separator the caller must not see.
    name: (i) => decoder.decode(names.subarray(nameOffsets[i], nameOffsets[i + 1] - 1)),
  };
}
```

- [ ] **Step 4: Run the local gate**

```bash
cd web && pnpm run check && pnpm run types && pnpm run test
```

Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add web/src/blob/frieze.ts web/tests/frieze.test.ts
git commit -m "feat(web): decode frieze.bin into typed arrays"
```

---

### Task 5: `readLineage` and `readFriezeIds`

Two formats in one task: they share a header shape, they are each a dozen lines, and neither is worth a reviewer's gate on its own.

**Files:**
- Create: `web/src/blob/lineage.ts`, `web/src/blob/ids.ts`, `web/tests/lineage.test.ts`, `web/tests/ids.test.ts`

**Interfaces:**
- Consumes: `web/tests/fixtures/lineage.bin.gz` and `web/tests/fixtures/frieze_ids.bin` from Task 2, `inflateIfGzipped` from Task 3.
- Produces:

```ts
export interface Lineage {
  readonly count: number;
  readonly src: Uint32Array;
  readonly dst: Uint32Array;
  readonly shared: Uint8Array;
}
export function readLineage(buffer: ArrayBuffer): Lineage;

export interface FriezeIds {
  readonly count: number;
  mbid(i: number): string;
}
export function readFriezeIds(buffer: ArrayBuffer): FriezeIds;
```

- [ ] **Step 1: Write the failing tests**

`web/tests/lineage.test.ts`:

```ts
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { inflateIfGzipped } from "../src/blob/gzip";
import { readLineage } from "../src/blob/lineage";

async function witness() {
  const bytes = new Uint8Array(readFileSync(new URL("fixtures/lineage.bin.gz", import.meta.url)));
  return readLineage(await inflateIfGzipped(bytes));
}

describe("readLineage", () => {
  it("reads the one edge the witnesses carry", async () => {
    const lineage = await witness();
    expect(lineage.count).toBe(1);
    // Joy Division (row 6) to New Order (row 7), three shared musicians.
    expect(lineage.src[0]).toBe(6);
    expect(lineage.dst[0]).toBe(7);
    expect(lineage.shared[0]).toBe(3);
  });

  it("refuses a blob that is not a lineage", () => {
    const buffer = new ArrayBuffer(16);
    new Uint8Array(buffer).set([0x4d, 0x46, 0x5a, 0x31]);
    expect(() => readLineage(buffer)).toThrow(/MLN1/);
  });
});
```

`web/tests/ids.test.ts`:

```ts
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { readFriezeIds } from "../src/blob/ids";

function witness() {
  const bytes = new Uint8Array(readFileSync(new URL("fixtures/frieze_ids.bin", import.meta.url)));
  return readFriezeIds(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength));
}

describe("readFriezeIds", () => {
  it("reads one mbid per frieze row", () => {
    const ids = witness();
    expect(ids.count).toBe(20);
    // The Beatles, frieze row 0.
    expect(ids.mbid(0)).toBe("b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d");
  });

  it("renders every mbid as a hyphenated 36-character uuid", () => {
    const ids = witness();
    for (let i = 0; i < ids.count; i++) {
      expect(ids.mbid(i)).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
    }
  });

  it("refuses a stale cached file", () => {
    const buffer = new ArrayBuffer(16);
    new Uint8Array(buffer).set([0x4d, 0x46, 0x5a, 0x31]);
    expect(() => readFriezeIds(buffer)).toThrow(/MID1/);
  });
});
```

`frieze_ids.bin` is delivered uncompressed, so its test reads the file directly rather than through `inflateIfGzipped`.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd web && pnpm run test
```

Expected: FAIL on both new files, module not found.

- [ ] **Step 3: Write `lineage.ts`**

```ts
const MAGIC = "MLN1";
const VERSION = 1;
const decoder = new TextDecoder();

export interface Lineage {
  readonly count: number;
  readonly src: Uint32Array;
  readonly dst: Uint32Array;
  readonly shared: Uint8Array;
}

export function readLineage(buffer: ArrayBuffer): Lineage {
  const view = new DataView(buffer);
  const magic = decoder.decode(new Uint8Array(buffer, 0, 4));
  if (magic !== MAGIC) {
    throw new Error(`lineage.bin: expected magic ${MAGIC}, got ${JSON.stringify(magic)}`);
  }
  const version = view.getUint16(4, true);
  if (version !== VERSION) {
    throw new Error(`lineage.bin: unsupported version ${version}`);
  }

  const count = view.getUint32(8, true);
  return {
    count,
    src: new Uint32Array(buffer, 12, count),
    dst: new Uint32Array(buffer, 12 + 4 * count, count),
    shared: new Uint8Array(buffer, 12 + 8 * count, count),
  };
}
```

- [ ] **Step 4: Write `ids.ts`**

```ts
const MAGIC = "MID1";
const VERSION = 1;
const HEADER = 16;
const decoder = new TextDecoder();
const HEX = Array.from({ length: 256 }, (_, byte) => byte.toString(16).padStart(2, "0"));

export interface FriezeIds {
  readonly count: number;
  mbid(i: number): string;
}

export function readFriezeIds(buffer: ArrayBuffer): FriezeIds {
  const view = new DataView(buffer);
  const magic = decoder.decode(new Uint8Array(buffer, 0, 4));
  if (magic !== MAGIC) {
    throw new Error(`frieze_ids.bin: expected magic ${MAGIC}, got ${JSON.stringify(magic)}`);
  }
  const version = view.getUint16(4, true);
  if (version !== VERSION) {
    throw new Error(`frieze_ids.bin: unsupported version ${version}`);
  }

  const count = view.getUint32(8, true);
  const bytes = new Uint8Array(buffer, HEADER, count * 16);
  return {
    count,
    mbid: (i) => {
      const at = i * 16;
      let out = "";
      for (let k = 0; k < 16; k++) {
        out += HEX[bytes[at + k]];
        if (k === 3 || k === 5 || k === 7 || k === 9) {
          out += "-";
        }
      }
      return out;
    },
  };
}
```

- [ ] **Step 5: Run the local gate**

```bash
cd web && pnpm run check && pnpm run types && pnpm run test
```

Expected: 18 passed.

- [ ] **Step 6: Commit**

```bash
git add web/src/blob/lineage.ts web/src/blob/ids.ts web/tests/lineage.test.ts web/tests/ids.test.ts
git commit -m "feat(web): decode lineage.bin and frieze_ids.bin"
```

---

### Task 6: Version the delivered blobs and close the loop

The spec versions the blobs in the repository so development, CI and production read the same bytes and neither needs the 2.8 GB dump. That only holds if a committed blob cannot drift from the pipeline, so the copy command and the drift check land together.

**Files:**
- Modify: `.gitignore`, `src/musilogy/cli.py`
- Create: `tests/test_delivery.py`, `web/tests/delivered.test.ts`
- Create (generated): `web/public/data/frieze.bin.gz`, `lineage.bin.gz`, `frieze_ids.bin`, `genres.json.gz`, `density.json.gz`, `manifest.json`

**Interfaces:**
- Consumes: `readFrieze`, `readLineage`, `readFriezeIds`, `inflateIfGzipped`.
- Produces: `musilogy sync-web`; the versioned delivery under `web/public/data/`.

- [ ] **Step 1: Anchor the gitignore**

`.gitignore` line 1 is `data/`, which has no leading slash and therefore matches a directory named `data` at any depth. Verified on this repository:

```
$ git check-ignore --no-index -v web/public/data/frieze.bin.gz
.gitignore:1:data/	web/public/data/frieze.bin.gz
```

The versioned delivery would be silently dropped. Change line 1 to `/data/` — nothing else in the tree is named `data`, so the anchor loses no coverage.

- [ ] **Step 2: Write the failing tests**

`tests/test_delivery.py`:

```python
import hashlib
import json
import subprocess

from musilogy.paths import REPO_ROOT, WEB_DATA_DIR

DELIVERED = (
    "frieze.bin.gz",
    "lineage.bin.gz",
    "frieze_ids.bin",
    "genres.json.gz",
    "density.json.gz",
)


def test_the_versioned_blobs_match_the_manifest_they_shipped_with():
    # The blobs are versioned but data/out/ is not, so nothing else can catch a
    # hand-edited or half-copied file: the manifest travels with them and the
    # fast suite is the only place the two are ever compared.
    manifest = json.loads((WEB_DATA_DIR / "manifest.json").read_text(encoding="utf-8"))
    digests = manifest["output_sha256"]
    for name in DELIVERED:
        expected = digests[f"web/{name}"]
        actual = hashlib.sha256((WEB_DATA_DIR / name).read_bytes()).hexdigest()
        assert actual == expected, f"{name} does not match the manifest: run `musilogy sync-web`"


def test_the_versioned_blobs_are_not_ignored_by_git():
    for name in (*DELIVERED, "manifest.json"):
        path = f"web/public/data/{name}"
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", path],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 128, (
            f"git check-ignore could not answer for {path}: {result.stderr.strip()}"
        )
        assert result.returncode == 1, f"{path} is ignored: {result.stdout.strip()}"
```

`web/tests/delivered.test.ts` — the same delivery read by the code that will render it:

```ts
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { inflateIfGzipped } from "../src/blob/gzip";
import { readFrieze } from "../src/blob/frieze";
import { readFriezeIds } from "../src/blob/ids";
import { readLineage } from "../src/blob/lineage";

function delivered(name: string) {
  const bytes = new Uint8Array(readFileSync(new URL(`../public/data/${name}`, import.meta.url)));
  return bytes;
}

describe("the delivered blobs", () => {
  it("hold the frieze population the baseline freezes", async () => {
    const frieze = readFrieze(await inflateIfGzipped(delivered("frieze.bin.gz")));
    expect(frieze.count).toBe(84262);
  });

  it("hold the lineage edges the baseline freezes", async () => {
    const lineage = readLineage(await inflateIfGzipped(delivered("lineage.bin.gz")));
    expect(lineage.count).toBe(37136);
  });

  it("carry one mbid per frieze row", async () => {
    const frieze = readFrieze(await inflateIfGzipped(delivered("frieze.bin.gz")));
    const bytes = delivered("frieze_ids.bin");
    const ids = readFriezeIds(
      bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
    );
    // A row-for-row misalignment here would show every band under its
    // neighbour's name, and nothing else in the suite would see it.
    expect(ids.count).toBe(frieze.count);
  });

  it("index a genre vocabulary that covers every pair", async () => {
    const frieze = readFrieze(await inflateIfGzipped(delivered("frieze.bin.gz")));
    const vocabulary = JSON.parse(
      new TextDecoder().decode(await inflateIfGzipped(delivered("genres.json.gz"))),
    ) as { genre_mbid: string[] };
    let highest = 0;
    for (const id of frieze.genreIds) {
      if (id > highest) {
        highest = id;
      }
    }
    expect(highest).toBeLessThan(vocabulary.genre_mbid.length);
  });

  it("keep every lineage endpoint inside the frieze population", async () => {
    const frieze = readFrieze(await inflateIfGzipped(delivered("frieze.bin.gz")));
    const lineage = readLineage(await inflateIfGzipped(delivered("lineage.bin.gz")));
    for (let i = 0; i < lineage.count; i++) {
      expect(lineage.src[i]).toBeLessThan(frieze.count);
      expect(lineage.dst[i]).toBeLessThan(frieze.count);
    }
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
uv run pytest tests/test_delivery.py -v
cd web && pnpm run test
```

Expected: both fail — the files do not exist yet.

- [ ] **Step 4: Write the command**

`src/musilogy/cli.py`. It copies, it never builds: the pipeline must stay able to run without touching the repository, so promoting a delivery is a separate, explicit gesture.

```python
DELIVERED_TO_WEB = (
    "frieze.bin.gz",
    "lineage.bin.gz",
    "frieze_ids.bin",
    "genres.json.gz",
    "density.json.gz",
)


def sync_web() -> None:
    """Copies the current delivery into the versioned web/public/data/."""
    source = out_dir(DUMP) / "web"
    manifest = out_dir(DUMP) / "manifest.json"
    if not manifest.exists():
        raise SystemExit(f"no delivery at {manifest}: run `musilogy run` first")
    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in DELIVERED_TO_WEB:
        shutil.copyfile(source / name, WEB_DATA_DIR / name)
    shutil.copyfile(manifest, WEB_DATA_DIR / "manifest.json")
    print("delivery copied to", WEB_DATA_DIR)
```

Register it in `main()` beside the others:

```python
    subparsers.add_parser("sync-web", help="copy the current delivery into web/public/data/")
```

```python
    elif args.command == "sync-web":
        sync_web()
```

- [ ] **Step 5: Copy the delivery and run both suites**

```bash
uv run musilogy sync-web
uv run pytest tests/test_delivery.py -v
cd web && pnpm run test
```

Expected: 2 passed on the Python side, 23 passed on the web side.

`web/public/data/` will weigh about 2.7 MB. That is the spec's decision, taken against a 25 MB Parquet: development and production read the same file, GitHub Pages serves the repository as it is, and CI needs neither the dump nor the pipeline.

- [ ] **Step 6: Run the whole gate**

```bash
uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest
cd web && pnpm run check && pnpm run types && pnpm run test
```

Expected: 219 passed on the Python side, 23 on the web side.

- [ ] **Step 7: Commit**

```bash
git add .gitignore src/musilogy/cli.py tests/test_delivery.py \
        web/tests/delivered.test.ts web/public/data
git commit -m "feat(web): version the delivered blobs and check them against the manifest"
```

---

## Acceptance

The plan is done when, from a clean clone with `uv sync` and `pnpm install`:

| check | expected |
|---|---|
| `uv run pytest` | 219 passed |
| `cd web && pnpm run check` | no diagnostic |
| `cd web && pnpm run types` | no output |
| `cd web && pnpm run test` | 23 passed |
| `cd web && pnpm run build` | succeeds |
| CI | both jobs green |

And the delivered blobs read back, in TypeScript, as 84 262 bands and 37 136 edges — the same numbers `tests/test_baseline.py` freezes on the real dump, reached by a completely different path.
