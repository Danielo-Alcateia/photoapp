// Camada de comunicação com o backend Python.
// Usa a mesma origem quando servido pelo Flask; caso contrário, cai no
// host indicado em window.PHOTOAPP_API (definido no index.html).

const API_BASE =
  window.PHOTOAPP_API ||
  (location.protocol.startsWith("http") ? location.origin : "http://localhost:8000");

async function postImage(path, blob, extra = {}, headerMap = {}) {
  const form = new FormData();
  form.append("image", blob, "image.png");
  for (const [key, value] of Object.entries(extra)) {
    if (value instanceof Blob) form.append(key, value, `${key}.png`);
    else form.append(key, value);
  }

  const res = await fetch(`${API_BASE}${path}`, { method: "POST", body: form });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      if (data && data.error) detail = data.error;
    } catch (_) {
      /* resposta não-JSON */
    }
    throw new Error(detail);
  }
  const meta = {
    engine: res.headers.get("X-Engine") || "",
    width: parseInt(res.headers.get("X-Width") || "0", 10),
    height: parseInt(res.headers.get("X-Height") || "0", 10),
  };
  for (const [key, header] of Object.entries(headerMap)) {
    meta[key] = res.headers.get(header) || "";
  }
  const outBlob = await res.blob();
  return { blob: outBlob, ...meta };
}

export const api = {
  base: API_BASE,

  health() {
    return fetch(`${API_BASE}/api/health`).then((r) => r.json());
  },

  detectWatermark(imageBlob) {
    return postImage(
      "/api/detect-watermark",
      imageBlob,
      {},
      { found: "X-Watermark-Found", boxes: "X-Watermark-Boxes" }
    );
  },

  removeWatermark(imageBlob, maskBlob, dilate = 0) {
    return postImage("/api/inpaint", imageBlob, { mask: maskBlob, dilate });
  },

  removeWatermarkAI(imageBlob, maskBlob, prompt = "") {
    return postImage("/api/inpaint-ai", imageBlob, { mask: maskBlob, prompt });
  },

  improveLighting(imageBlob, strength = 1.0) {
    return postImage("/api/lighting", imageBlob, { strength });
  },

  improveResolution(imageBlob, scale = 2) {
    return postImage("/api/upscale", imageBlob, { scale });
  },
};
