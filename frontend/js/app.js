// Lógica principal da interface (mobile-first).
import { api } from "./api.js";
import { Brush } from "./brush.js";

const $ = (id) => document.getElementById(id);

const els = {
  file: $("fileInput"),
  tapZone: $("tapZone"),
  uploadView: $("uploadView"),
  editorView: $("editorView"),
  img: $("stageImg"),
  mask: $("maskCanvas"),
  overlayHint: $("overlayHint"),
  brushToolbar: $("brushToolbar"),
  brushSize: $("brushSize"),
  brushClear: $("brushClear"),
  brushCancel: $("brushCancel"),
  brushUndo: $("brushUndo"),
  aiRow: $("aiRow"),
  btnWatermark: $("btnWatermark"),
  btnLighting: $("btnLighting"),
  btnUpscale: $("btnUpscale"),
  btnReset: $("btnReset"),
  btnDownload: $("btnDownload"),
  btnNew: $("btnNew"),
  btnCompare: $("btnCompare"),
  btnInstall: $("btnInstall"),
  formatSelect: $("formatSelect"),
  resLabel: $("resLabel"),
  loading: $("loading"),
  loadingText: $("loadingText"),
  toast: $("toast"),
  engineBadge: $("engineBadge"),
  strength: $("strength"),
  strengthValue: $("strengthValue"),
};

const brush = new Brush(els.mask);

const state = {
  original: null, // Blob original
  originalUrl: null, // URL do original (para comparar)
  current: null, // Blob de trabalho
  history: [], // pilha para desfazer
  maskMode: false,
  busy: false,
  comparing: false,
  aiAvailable: false,
};

// ---------------------------------------------------------------------------
// Utilidades de UI
// ---------------------------------------------------------------------------
function setLoading(on, text = "Processando...") {
  state.busy = on;
  els.loadingText.textContent = text;
  els.loading.classList.toggle("hidden", !on);
  els.loading.classList.toggle("flex", on);
  [els.btnWatermark, els.btnLighting, els.btnUpscale, els.btnReset, els.btnCompare].forEach((b) => {
    if (b) b.disabled = on;
  });
}

let toastTimer;
function toast(msg, kind = "info") {
  els.toast.textContent = msg;
  els.toast.className =
    "fixed left-1/2 -translate-x-1/2 bottom-28 z-[60] max-w-[90vw] px-4 py-3 rounded-2xl text-sm font-medium shadow-xl transition-all duration-300 " +
    (kind === "error" ? "bg-red-600 text-white" : "bg-slate-800 text-slate-100");
  els.toast.classList.remove("opacity-0", "translate-y-4");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => els.toast.classList.add("opacity-0", "translate-y-4"), 3200);
}

function showEngine(engine) {
  if (!engine) return;
  els.engineBadge.textContent = engine;
  els.engineBadge.classList.remove("hidden");
}

function showResolution(w, h) {
  if (els.resLabel && w && h) els.resLabel.textContent = `${w} × ${h} px`;
}

function setImage(blob) {
  const url = URL.createObjectURL(blob);
  els.img.onload = () => URL.revokeObjectURL(url);
  els.img.src = url;
}

// ---------------------------------------------------------------------------
// Carregar imagem
// ---------------------------------------------------------------------------
async function loadFile(file) {
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    toast("Selecione um arquivo de imagem.", "error");
    return;
  }
  const probe = new Image();
  const url = URL.createObjectURL(file);
  probe.onload = () => {
    if (state.originalUrl) URL.revokeObjectURL(state.originalUrl);
    state.originalUrl = url;
    els.img.src = url;

    els.uploadView.classList.add("hidden");
    els.editorView.classList.remove("hidden");
    els.editorView.classList.add("flex");
    els.engineBadge.classList.add("hidden");

    brush.resize(probe.naturalWidth, probe.naturalHeight);
    showResolution(probe.naturalWidth, probe.naturalHeight);
  };
  probe.onerror = () => {
    URL.revokeObjectURL(url);
    toast("Não foi possível abrir a imagem.", "error");
  };
  probe.src = url;

  state.original = file;
  state.current = file;
  state.history = [];
  exitMaskMode();
}

function pushHistory(blob) {
  state.history.push(blob);
  if (state.history.length > 15) state.history.shift();
}

async function applyResult(blob, engine, w, h) {
  pushHistory(state.current);
  state.current = blob;
  setImage(blob);
  showEngine(engine);
  showResolution(w, h);
}

// ---------------------------------------------------------------------------
// Ações (backend)
// ---------------------------------------------------------------------------
async function runLighting() {
  if (state.busy) return;
  try {
    setLoading(true, "Melhorando iluminação...");
    const r = await api.improveLighting(state.current, parseFloat(els.strength.value));
    await applyResult(r.blob, r.engine, r.width, r.height);
    toast("Iluminação melhorada.");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    setLoading(false);
  }
}

async function runUpscale() {
  if (state.busy) return;
  try {
    setLoading(true, "Aumentando resolução...");
    const r = await api.improveResolution(state.current, 2);
    await applyResult(r.blob, r.engine, r.width, r.height);
    toast("Resolução aumentada.");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    setLoading(false);
  }
}

async function runInpaint() {
  if (state.busy) return;
  const useAI = state.aiAvailable;
  const empty = brush.isEmpty();
  if (empty && !useAI) {
    toast("Pinte a marca d'água com o dedo primeiro.", "error");
    return;
  }
  try {
    setLoading(
      true,
      useAI
        ? empty
          ? "Detectando e removendo com IA..."
          : "Removendo com IA... pode levar ~30s"
        : "Removendo marca d'água..."
    );
    const maskBlob = empty ? null : await brush.toBlob();
    const r = useAI
      ? await api.removeWatermarkAI(state.current, maskBlob)
      : await api.removeWatermark(state.current, maskBlob, 0);
    await applyResult(r.blob, r.engine, r.width, r.height);
    exitMaskMode();
    if (r.decision) toast(`IA: ${r.decision}`);
    else toast(useAI ? "Marca removida com IA." : "Marca d'água removida.");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    setLoading(false);
  }
}

// ---------------------------------------------------------------------------
// Modo máscara (pincel)
// ---------------------------------------------------------------------------
function enterMaskMode() {
  state.maskMode = true;
  els.mask.classList.remove("hidden");
  els.overlayHint.classList.remove("hidden");
  els.brushToolbar.classList.remove("hidden");
  els.brushToolbar.classList.add("flex");
  if (state.aiAvailable) {
    els.aiRow.classList.remove("hidden");
    els.aiRow.classList.add("flex");
  }
  els.btnWatermark.querySelector("[data-label]").textContent = "Aplicar";
  els.btnWatermark.classList.add("ring-2", "ring-amber-300");
}

function exitMaskMode() {
  state.maskMode = false;
  els.mask.classList.add("hidden");
  els.overlayHint.classList.add("hidden");
  els.brushToolbar.classList.add("hidden");
  els.brushToolbar.classList.remove("flex");
  els.aiRow.classList.add("hidden");
  els.aiRow.classList.remove("flex");
  const label = els.btnWatermark.querySelector("[data-label]");
  if (label) label.textContent = "Remover Marca d'Água";
  els.btnWatermark.classList.remove("ring-2", "ring-amber-300");
}

function onWatermarkClick() {
  if (state.busy) return;
  if (state.maskMode) {
    runInpaint();
    return;
  }
  autoDetect();
}

// Detecta a marca d'água sozinho e carrega a máscara no pincel;
// se nada for encontrado, entra no modo manual (pinta com o dedo).
async function autoDetect() {
  try {
    setLoading(true, "Detectando marca d'água...");
    const r = await api.detectWatermark(state.current);
    enterMaskMode();
    if (r.found === "1") {
      await loadMaskIntoBrush(r.blob);
      toast("Marca detectada — toque em Aplicar (ajuste com o pincel se precisar).", "info");
    } else {
      brush.clear();
      toast("Nenhuma marca clara encontrada — pinte você mesmo.", "info");
    }
  } catch (err) {
    enterMaskMode();
    brush.clear();
    toast(`${err.message} — pinte manualmente.`, "error");
  } finally {
    setLoading(false);
  }
}

function loadMaskIntoBrush(blob) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(blob);
    const im = new Image();
    im.onload = () => {
      const ctx = els.mask.getContext("2d");
      ctx.clearRect(0, 0, els.mask.width, els.mask.height);
      ctx.drawImage(im, 0, 0, els.mask.width, els.mask.height);
      URL.revokeObjectURL(url);
      resolve();
    };
    im.onerror = resolve;
    im.src = url;
  });
}

// ---------------------------------------------------------------------------
// Comparar antes/depois (segurar)
// ---------------------------------------------------------------------------
function showOriginal(on) {
  if (!state.originalUrl || state.busy) return;
  state.comparing = on;
  els.img.src = on ? state.originalUrl : URL.createObjectURL(state.current);
  els.btnCompare.classList.toggle("ring-2", on);
  els.btnCompare.classList.toggle("ring-sky-300", on);
}

// ---------------------------------------------------------------------------
// Salvar (re-codifica no formato escolhido)
// ---------------------------------------------------------------------------
async function download() {
  if (!state.current) return;
  const type = els.formatSelect.value; // image/jpeg | image/png
  let blob = state.current;
  if (type === "image/jpeg") {
    const bmp = await createImageBitmap(blob);
    const c = document.createElement("canvas");
    c.width = bmp.width;
    c.height = bmp.height;
    const ctx = c.getContext("2d");
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, c.width, c.height);
    ctx.drawImage(bmp, 0, 0);
    blob = await new Promise((res) => c.toBlob((b) => res(b), type, 0.95));
  }
  const ext = type === "image/jpeg" ? "jpg" : "png";
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `photoapp-${Date.now()}.${ext}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

// ---------------------------------------------------------------------------
// Eventos
// ---------------------------------------------------------------------------
els.tapZone.addEventListener("click", () => els.file.click());
els.file.addEventListener("change", (e) => loadFile(e.target.files[0]));
els.btnNew.addEventListener("click", () => els.file.click());

els.btnWatermark.addEventListener("click", onWatermarkClick);
els.btnLighting.addEventListener("click", runLighting);
els.btnUpscale.addEventListener("click", runUpscale);

els.btnReset.addEventListener("click", () => {
  if (!state.history.length) {
    toast("Nada para desfazer.");
    return;
  }
  state.current = state.history.pop();
  setImage(state.current);
  els.engineBadge.classList.add("hidden");
  toast("Desfeito.");
});

els.btnDownload.addEventListener("click", download);

els.btnCompare.addEventListener("pointerdown", (e) => {
  e.preventDefault();
  showOriginal(true);
});
["pointerup", "pointerleave", "pointercancel"].forEach((evt) =>
  els.btnCompare.addEventListener(evt, () => showOriginal(false))
);

els.brushSize.addEventListener("input", (e) => brush.setSize(parseInt(e.target.value, 10)));
els.brushClear.addEventListener("click", () => brush.clear());
els.brushCancel.addEventListener("click", () => exitMaskMode());
els.brushUndo.addEventListener("click", () => brush.undo());
els.strength.addEventListener("input", () => {
  els.strengthValue.textContent = `${parseFloat(els.strength.value).toFixed(1)}x`;
});

["dragover", "drop"].forEach((evt) =>
  document.addEventListener(evt, (e) => {
    e.preventDefault();
    if (evt === "drop" && e.dataTransfer?.files?.[0]) loadFile(e.dataTransfer.files[0]);
  })
);

// ---------------------------------------------------------------------------
// PWA: instalação + service worker + health
// ---------------------------------------------------------------------------
let deferredPrompt = null;
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  deferredPrompt = e;
  els.btnInstall?.classList.remove("hidden");
});
els.btnInstall?.addEventListener("click", async () => {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  await deferredPrompt.userChoice;
  deferredPrompt = null;
  els.btnInstall.classList.add("hidden");
});

window.addEventListener("load", async () => {
  brush.setSize(parseInt(els.brushSize.value, 10));

  if ("serviceWorker" in navigator) {
    try {
      await navigator.serviceWorker.register("service-worker.js");
    } catch (err) {
      console.warn("Service worker não registrado:", err);
    }
  }

  try {
    const health = await api.health();
    state.aiAvailable = !!(health && health.ai && health.ai.available);
    showEngine("online");
    console.log("Backend:", health);
  } catch (err) {
    toast("Backend offline. Rode o servidor Python.", "error");
  }
});
