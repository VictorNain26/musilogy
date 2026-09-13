import { readHeader } from "./header";

const MAGIC = "MLN1";

export interface Lineage {
  readonly count: number;
  readonly src: Uint32Array;
  readonly dst: Uint32Array;
  readonly shared: Uint8Array;
}

export function readLineage(buffer: ArrayBuffer): Lineage {
  const view = readHeader(buffer, "lineage.bin", MAGIC);

  const count = view.getUint32(8, true);
  const expectedSize = 12 + 9 * count;
  if (buffer.byteLength !== expectedSize) {
    throw new Error(`lineage.bin: expected ${expectedSize} bytes, got ${buffer.byteLength}`);
  }

  return {
    count,
    src: new Uint32Array(buffer, 12, count),
    dst: new Uint32Array(buffer, 12 + 4 * count, count),
    shared: new Uint8Array(buffer, 12 + 8 * count, count),
  };
}
