import { describe, expect, it } from "vitest";

describe("the runtime", () => {
  it("has DecompressionStream, which the blob reader needs", () => {
    expect(typeof DecompressionStream).toBe("function");
  });
});
