import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { readFrieze } from "../src/blob/frieze";
import { inflateIfGzipped } from "../src/blob/gzip";
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
