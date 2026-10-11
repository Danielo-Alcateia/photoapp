// Gerador de ícones PNG do PWA sem dependências externas.
// Desenha um ícone de câmera (fundo gradiente + corpo + lente) e grava
// PNG válido usando apenas o módulo zlib do Node.
//
//   node scripts/generate-icons.js
const fs = require("fs");
const path = require("path");
const zlib = require("zlib");

// --- CRC32 (exigido pelo formato PNG) ---
const CRC_TABLE = (() => {
  const table = new Int32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c;
  }
  return table;
})();

function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const typeBuf = Buffer.from(type, "ascii");
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([typeBuf, data])), 0);
  return Buffer.concat([len, typeBuf, data, crc]);
}

function encodePNG(width, height, rgba) {
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // RGBA
  ihdr[10] = 0;
  ihdr[11] = 0;
  ihdr[12] = 0;

  const stride = width * 4;
  const raw = Buffer.alloc((stride + 1) * height);
  for (let y = 0; y < height; y++) {
    raw[y * (stride + 1)] = 0; // filtro None
    rgba.copy(raw, y * (stride + 1) + 1, y * stride, y * stride + stride);
  }
  const idat = zlib.deflateSync(raw, { level: 9 });
  return Buffer.concat([sig, chunk("IHDR", ihdr), chunk("IDAT", idat), chunk("IEND", Buffer.alloc(0))]);
}

// --- Desenho ---
function clamp(v, a, b) {
  return Math.max(a, Math.min(b, v));
}
function lerp(a, b, t) {
  return a + (b - a) * t;
}
function mixC(c1, c2, t) {
  return [lerp(c1[0], c2[0], t), lerp(c1[1], c2[1], t), lerp(c1[2], c2[2], t)];
}

function makeIcon(size, { maskable = false } = {}) {
  const buf = Buffer.alloc(size * size * 4);
  const c1 = [56, 189, 248]; // sky-400
  const c2 = [167, 139, 250]; // violet-400
  const cx = size / 2;
  const cy = size / 2;

  // Escala do conteúdo: maskable exige "safe zone" (≈80% central).
  const content = maskable ? size * 0.62 : size * 0.74;

  const roundedBg = !maskable; // fundo arredondado no ícone "any"
  const cornerR = size * 0.22;

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const i = (y * size + x) * 4;
      const t = clamp((x + y) / (2 * size), 0, 1);
      const bg = mixC(c1, c2, t);

      let r = bg[0],
        g = bg[1],
        b = bg[2],
        a = 255;

      // Cantos arredondados (fora do corpo arredondado -> transparente).
      if (roundedBg) {
        const dx = Math.abs(x - cx);
        const dy = Math.abs(y - cy);
        const half = size / 2;
        if (dx > half - cornerR && dy > half - cornerR) {
          const ox = dx - (half - cornerR);
          const oy = dy - (half - cornerR);
          if (Math.hypot(ox, oy) > cornerR) a = 0;
        }
      }

      // Câmera: corpo (retângulo arredondado) + topo + lente.
      const bw = content;
      const bh = content * 0.68;
      const bodyLeft = cx - bw / 2;
      const bodyTop = cy - bh / 2 + content * 0.06;
      const inBody =
        x >= bodyLeft && x <= bodyLeft + bw && y >= bodyTop && y <= bodyTop + bh;

      // "Trilho" superior (hump) da câmera.
      const humpW = content * 0.36;
      const humpH = content * 0.14;
      const inHump =
        x >= cx - humpW / 2 &&
        x <= cx + humpW / 2 &&
        y >= bodyTop - humpH &&
        y <= bodyTop + 1;

      const lr = content * 0.24; // raio da lente
      const distLens = Math.hypot(x - cx, y - (bodyTop + bh * 0.52));
      const inLensOuter = distLens <= lr;
      const inLensInner = distLens <= lr * 0.55;

      if (inHump) {
        [r, g, b] = [255, 255, 255];
      } else if (inBody) {
        [r, g, b] = [255, 255, 255];
        if (inLensOuter) {
          [r, g, b] = [15, 23, 42]; // slate-900
          if (inLensInner) [r, g, b] = mixC([56, 189, 248], [167, 139, 250], t);
        }
      }

      buf[i] = r | 0;
      buf[i + 1] = g | 0;
      buf[i + 2] = b | 0;
      buf[i + 3] = a;
    }
  }
  return encodePNG(size, size, buf);
}

const outDir = path.join(__dirname, "..", "frontend", "icons");
fs.mkdirSync(outDir, { recursive: true });

const files = [
  ["icon-192.png", makeIcon(192)],
  ["icon-512.png", makeIcon(512)],
  ["maskable-512.png", makeIcon(512, { maskable: true })],
];

for (const [name, data] of files) {
  fs.writeFileSync(path.join(outDir, name), data);
  console.log(`  gerado  frontend/icons/${name} (${data.length} bytes)`);
}
console.log("Ícones do PWA criados com sucesso.");
