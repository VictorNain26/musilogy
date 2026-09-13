// Vite's dev server serves public/*.gz through sirv, which sets
// Content-Encoding: gzip, so fetch decompresses before we see the body.
// GitHub Pages sends the same file verbatim as application/gzip. The sniff is
// what lets one build read both (vitejs/vite#12266, open since 2023).
export async function inflateIfGzipped(bytes: Uint8Array<ArrayBuffer>): Promise<ArrayBuffer> {
  if (bytes[0] !== 0x1f || bytes[1] !== 0x8b) {
    return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  }
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
  return await new Response(stream).arrayBuffer();
}

export async function loadBlob(url: string): Promise<ArrayBuffer> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url}: HTTP ${response.status}`);
  }
  return inflateIfGzipped(new Uint8Array(await response.arrayBuffer()));
}
