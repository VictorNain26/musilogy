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
