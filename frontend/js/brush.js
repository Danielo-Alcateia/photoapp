// Pincel interativo para pintar a máscara da marca d'água.
// Suporta toque (pointer events) e mouse, com suavização de borda e undo.

export class Brush {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.size = 40;
    this.drawing = false;
    this.last = null;
    this.onFirstStroke = null;
    this._undo = [];
    this._maxUndo = 6;

    this._pointers = new Map();

    canvas.addEventListener("pointerdown", (e) => this._down(e));
    canvas.addEventListener("pointermove", (e) => this._move(e));
    canvas.addEventListener("pointerup", (e) => this._up(e));
    canvas.addEventListener("pointerleave", (e) => this._up(e));
    canvas.addEventListener("pointercancel", (e) => this._up(e));
    canvas.style.touchAction = "none";
  }

  resize(width, height) {
    this.canvas.width = width;
    this.canvas.height = height;
    this.clear();
  }

  setSize(radius) {
    this.size = Math.max(6, Math.min(220, radius));
  }

  clear() {
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    this._undo = [];
  }

  undo() {
    const data = this._undo.pop();
    if (!data) return false;
    const img = new Image();
    img.onload = () => {
      this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
      this.ctx.drawImage(img, 0, 0);
    };
    img.src = data;
    return true;
  }

  isEmpty() {
    const { data } = this.ctx.getImageData(0, 0, this.canvas.width, this.canvas.height);
    for (let i = 3; i < data.length; i += 4) if (data[i] > 0) return false;
    return true;
  }

  _snapshot() {
    try {
      this._undo.push(this.canvas.toDataURL("image/png"));
      if (this._undo.length > this._maxUndo) this._undo.shift();
    } catch (_) {
      /* canvas grande: ignora undo */
    }
  }

  _pos(e) {
    const rect = this.canvas.getBoundingClientRect();
    return {
      x: ((e.clientX - rect.left) / rect.width) * this.canvas.width,
      y: ((e.clientY - rect.top) / rect.height) * this.canvas.height,
    };
  }

  _down(e) {
    e.preventDefault();
    this.canvas.setPointerCapture?.(e.pointerId);
    this._pointers.set(e.pointerId, true);
    if (!this.drawing) this._snapshot();
    this.drawing = true;
    this.last = this._pos(e);
    this._stamp(this.last.x, this.last.y);
    if (this.onFirstStroke) {
      this.onFirstStroke();
      this.onFirstStroke = null;
    }
  }

  _move(e) {
    if (!this.drawing) return;
    e.preventDefault();
    const p = this._pos(e);
    this._stroke(this.last, p);
    this.last = p;
  }

  _up(e) {
    this._pointers.delete(e.pointerId);
    if (this._pointers.size === 0) {
      this.drawing = false;
      this.last = null;
    }
  }

  _brushFill() {
    const r = this.size;
    const g = this.ctx.createRadialGradient(0, 0, r * 0.6, 0, 0, r);
    g.addColorStop(0, "rgba(255,255,255,1)");
    g.addColorStop(0.8, "rgba(255,255,255,0.9)");
    g.addColorStop(1, "rgba(255,255,255,0)");
    return g;
  }

  _stroke(a, b) {
    const ctx = this.ctx;
    ctx.save();
    ctx.strokeStyle = "rgba(255,255,255,0.98)";
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.lineWidth = this.size * 2;
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();
    ctx.restore();
    this._stamp(b.x, b.y);
  }

  _stamp(x, y) {
    const ctx = this.ctx;
    ctx.save();
    ctx.translate(x, y);
    ctx.fillStyle = this._brushFill();
    ctx.beginPath();
    ctx.arc(0, 0, this.size, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  // Exporta a máscara como PNG (branco sobre preto) para o backend.
  toBlob() {
    return new Promise((resolve, reject) => {
      const out = document.createElement("canvas");
      out.width = this.canvas.width;
      out.height = this.canvas.height;
      const octx = out.getContext("2d");
      octx.fillStyle = "#000";
      octx.fillRect(0, 0, out.width, out.height);
      octx.drawImage(this.canvas, 0, 0);
      out.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("Falha ao gerar máscara"))), "image/png");
    });
  }
}
