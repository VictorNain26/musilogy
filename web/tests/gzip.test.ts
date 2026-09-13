import { gzipSync } from "node:zlib";
import { afterEach, describe, expect, it, vi } from "vitest";
import { inflateIfGzipped, loadBlob } from "../src/blob/gzip";

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

describe("loadBlob", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetches and inflates a gzipped response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(gzipSync(PLAIN), { status: 200 })),
    );
    const buffer = await loadBlob("https://example.test/frieze.bin.gz");
    expect(new Uint8Array(buffer)).toEqual(PLAIN);
  });

  it("names the url and the status when the response is not ok", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 404 })),
    );
    await expect(loadBlob("https://example.test/frieze.bin.gz")).rejects.toThrow(
      /https:\/\/example\.test\/frieze\.bin\.gz: HTTP 404/,
    );
  });
});
