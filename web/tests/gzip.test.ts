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
