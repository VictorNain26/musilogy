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
