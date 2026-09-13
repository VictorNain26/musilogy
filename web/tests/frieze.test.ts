import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { readFrieze } from "../src/blob/frieze";
import { inflateIfGzipped } from "../src/blob/gzip";

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
