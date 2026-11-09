// A long-lived Node process that runs the call strings jy produces (an#257 spike).
//
// jy has no JavaScript runtime: it turns a JS signature into a Python function that
// RETURNS the call as a string. This host is the runtime: it imports previz's built
// `dist/`, evaluates `previz_facade.js` in its global scope, then reads one JSON line
// per request ({"id", "expr"}) on stdin, awaits `expr`, and writes one JSON line
// ({"id", "ok", "value"} or {"id", "ok": false, "error"}) on stdout.
//
// Usage: node previz_host.mjs <previz checkout> <facade.js>
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { createInterface } from 'node:readline';
import { pathToFileURL } from 'node:url';
import { crc32, deflateSync } from 'node:zlib';

const [previzDir, facadePath] = process.argv.slice(2);
if (!previzDir || !facadePath) {
  process.stderr.write('usage: node previz_host.mjs <previz checkout> <facade.js>\n');
  process.exit(2);
}
const load = (rel) => import(pathToFileURL(path.join(previzDir, rel)).href);

globalThis.previz = await load('dist/index.js');
globalThis.previzDemo = await load('dist/engines/demo/index.js');
globalThis.spike = {};

const PNG_SIGNATURE = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
const PNG_RGB = 2;

function chunk(type, body) {
  const head = Buffer.alloc(4);
  head.writeUInt32BE(body.length);
  const typed = Buffer.concat([Buffer.from(type, 'ascii'), body]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(typed) >>> 0);
  return Buffer.concat([head, typed, crc]);
}

// A previz Frame (RGBA, ImageData-shaped) as an 8-bit RGB PNG, base64. RGB because
// the demo engine draws opaque frames and an's frame stage wants opaque pixels.
globalThis.encodePng = function encodePng({ width, height, data }) {
  const stride = width * 3 + 1;
  const raw = Buffer.alloc(stride * height);
  for (let y = 0; y < height; y++) {
    const row = y * stride;
    for (let x = 0; x < width; x++) {
      const s = (y * width + x) * 4;
      const d = row + 1 + x * 3;
      raw[d] = data[s];
      raw[d + 1] = data[s + 1];
      raw[d + 2] = data[s + 2];
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;
  ihdr[9] = PNG_RGB;
  return Buffer.concat([
    PNG_SIGNATURE,
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw, { level: 1 })),
    chunk('IEND', Buffer.alloc(0)),
  ]).toString('base64');
};

// Indirect eval: the facade's function declarations become globals.
(0, eval)(readFileSync(facadePath, 'utf8'));

const reply = (msg) => process.stdout.write(JSON.stringify(msg) + '\n');
const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
let queue = Promise.resolve();
lines.on('line', (line) => {
  // Requests are answered strictly in order.
  queue = queue.then(async () => {
    let id = null;
    try {
      const req = JSON.parse(line);
      id = req.id;
      reply({ id, ok: true, value: await (0, eval)(req.expr) });
    } catch (e) {
      reply({ id, ok: false, error: String((e && e.stack) || e) });
    }
  });
});
reply({ id: 'ready', ok: true, value: { node: process.version } });
