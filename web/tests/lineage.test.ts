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
