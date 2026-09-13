import { readHeader } from "./header";

const MAGIC = "MID1";
const HEADER = 16;
const HEX = Array.from({ length: 256 }, (_, byte) => byte.toString(16).padStart(2, "0"));

export interface FriezeIds {
  readonly count: number;
  mbid(i: number): string;
}

export function readFriezeIds(buffer: ArrayBuffer): FriezeIds {
  const view = readHeader(buffer, "frieze_ids.bin", MAGIC);

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
