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
  const expectedSize = HEADER + 16 * count;
  if (buffer.byteLength !== expectedSize) {
    throw new Error(`frieze_ids.bin: expected ${expectedSize} bytes, got ${buffer.byteLength}`);
  }

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
