const decoder = new TextDecoder();
const VERSION = 1;

export function readHeader(buffer: ArrayBuffer, label: string, magic: string): DataView {
  if (buffer.byteLength < 6) {
    throw new Error(`${label}: expected at least 6 bytes of header, got ${buffer.byteLength}`);
  }
  const view = new DataView(buffer);
  const got = decoder.decode(new Uint8Array(buffer, 0, 4));
  if (got !== magic) {
    throw new Error(`${label}: expected magic ${magic}, got ${JSON.stringify(got)}`);
  }
  const version = view.getUint16(4, true);
  if (version !== VERSION) {
    throw new Error(`${label}: unsupported version ${version}`);
  }
  return view;
}
