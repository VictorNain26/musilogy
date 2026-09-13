const MAGIC = "MFZ1";
const VERSION = 1;
const decoder = new TextDecoder();

export interface Frieze {
  readonly count: number;
  readonly pairs: number;
  readonly y0: Uint16Array;
  readonly y1: Uint16Array;
  readonly ended: Uint8Array;
  readonly yEndIsDeclared: Uint8Array;
  readonly nAlbums: Uint8Array;
  readonly genreOffsets: Uint32Array;
  readonly genreIds: Uint16Array;
  name(i: number): string;
}

export function readFrieze(buffer: ArrayBuffer): Frieze {
  const view = new DataView(buffer);
  const magic = decoder.decode(new Uint8Array(buffer, 0, 4));
  if (magic !== MAGIC) {
    throw new Error(`frieze.bin: expected magic ${MAGIC}, got ${JSON.stringify(magic)}`);
  }
  const version = view.getUint16(4, true);
  if (version !== VERSION) {
    throw new Error(`frieze.bin: unsupported version ${version}`);
  }

  const count = view.getUint32(8, true);
  const pairs = view.getUint32(12, true);

  let at = 16;
  const nameOffsets = new Uint32Array(buffer, at, count + 1);
  at += 4 * (count + 1);
  const genreOffsets = new Uint32Array(buffer, at, count + 1);
  at += 4 * (count + 1);

  if (genreOffsets[count] !== pairs) {
    throw new Error(
      `frieze.bin: genres section has ${pairs} pairs, offsets end at ${genreOffsets[count]}`,
    );
  }

  const spans = new Uint16Array(buffer, at, 2 * count);
  at += 4 * count;
  const genreIds = new Uint16Array(buffer, at, pairs);
  at += 2 * pairs;
  const nAlbums = new Uint8Array(buffer, at, count);
  at += count;
  const names = new Uint8Array(buffer, at);

  if (nameOffsets[count] !== names.length) {
    throw new Error(
      `frieze.bin: names section is ${names.length} bytes, offsets end at ${nameOffsets[count]}`,
    );
  }

  const y0 = new Uint16Array(count);
  const y1 = new Uint16Array(count);
  const ended = new Uint8Array(count);
  const yEndIsDeclared = new Uint8Array(count);
  for (let i = 0; i < count; i++) {
    const begin = spans[2 * i];
    const end = spans[2 * i + 1];
    y0[i] = begin & 0x7fff;
    ended[i] = begin >>> 15;
    y1[i] = end & 0x7fff;
    yEndIsDeclared[i] = end >>> 15;
  }

  return {
    count,
    pairs,
    y0,
    y1,
    ended,
    yEndIsDeclared,
    nAlbums,
    genreOffsets,
    genreIds,
    // The writer appends "\n" after each name and records the offset past it,
    // so the range includes a separator the caller must not see.
    name: (i) => decoder.decode(names.subarray(nameOffsets[i], nameOffsets[i + 1] - 1)),
  };
}
