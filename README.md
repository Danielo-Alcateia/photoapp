---
title: PhotoApp - Edicao Cirurgica de Fotos
colorFrom: gray
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# PhotoApp — PWA de Edição Cirúrgica de Fotos

Aplicação web responsiva (PWA) com **três ferramentas cirúrgicas** de edição de fotos.
A prioridade absoluta é a **fidelidade fisionômica**: nenhuma ferramenta usa modelos
generativos que reinventem traços, olhos, dentes ou expressões das pessoas.

| Ferramenta | Motor principal | Fallback (também não-generativo) |
|---|---|---|
| Remover Marca d'Água | **LaMa** (`simple-lama-inpainting`) | OpenCV `cv2.inpaint` (Telea) |
| Melhorar Iluminação | **OpenCV CLAHE** + Gray-World + curva de sombras | — (núcleo) |
| Melhorar Resolução | **Real-ESRGAN** (RRDBNet, PyTorch puro) | OpenCV `INTER_LANCZOS4` + unsharp |

> **Política de fidelidade:** reconstrução facial generativa (CodeFormer/GFPGAN) é
> **proibida** e ignorada defensivamente por `config.py`. O RRDBNet (textura) foi
> reimplementado em PyTorch puro (`processors/rrdbnet.py`) justamente para **não**
> depender do pacote `realesrgan`, que arrasta o `gfpgan` como dependência.

---

## 1. Plano de Implementação

### Estrutura de arquivos
```
Projeto app de fotos/
├── backend/                     # Servidor Python (Flask)
│   ├── app.py                   # Rotas da API + serve o PWA + pré-aquecimento
│   ├── config.py                # Caminhos, limites e política de fidelidade
│   ├── image_io.py              # Decode com correção EXIF + limites de tamanho
│   ├── processors/
│   │   ├── __init__.py
│   │   ├── inpainting.py        # LaMa (fallback Telea) — remove marca d'água
│   │   ├── lighting.py          # CLAHE + white balance — iluminação
│   │   ├── upscale.py           # Real-ESRGAN (fallback LANCZOS) — resolução
│   │   └── rrdbnet.py           # RRDBNet oficial em PyTorch puro (sem basicsr/gfpgan)
│   ├── models/                  # Pesos baixados sob demanda (.gitkeep)
│   ├── requirements.txt         # Núcleo leve (Flask/OpenCV/Pillow)
│   └── requirements-ai.txt      # Apenas LaMa (torch instalado à parte)
│
├── frontend/                    # PWA (mobile-first, Tailwind)
│   ├── index.html               # Upload, viewer, pincel touch, 3 botões
│   ├── manifest.json            # Instalação na tela inicial
│   ├── service-worker.js        # App shell offline
│   ├── css/styles.css
│   ├── js/  (app.js, api.js, brush.js)
│   └── icons/                   # icon-192, icon-512, maskable-512 (PNG)
│
├── scripts/
│   ├── install.ps1              # .venv + dependências ([-AI] inclui LaMa/torch)
│   ├── run.ps1                  # Sobe o servidor e abre o navegador
│   ├── serve-frontend.js        # Preview do PWA sem Python
│   └── generate-icons.js        # Ícones PNG (sem dependências)
├── package.json  ·  .gitignore  ·  README.md
```

### Bibliotecas open-source (gratuitas)
**Núcleo (`requirements.txt`)**
- `Flask` + `flask-cors` — servidor HTTP e API.
- `opencv-python` — CLAHE, inpaint Telea, LANCZOS, LUT/gamma, EXIF.
- `Pillow` — ponte para o LaMa (orientação EXIF e RGB).
- `numpy` — álgebra de pixels.

**IA (`requirements-ai.txt` + torch)**
- `simple-lama-inpainting` (LaMa) — inpainting por **texturas vizinhas** da própria foto.
- `torch`/`torchvision` (CPU ou CUDA) — runtime da rede RRDBNet (Real-ESRGAN).
- Pesos oficiais baixados automaticamente para `backend/models/`.

### Fluxo dos endpoints
| Método | Rota | Entrada | Saída |
|---|---|---|---|
| GET | `/api/health` | — | status + motor ativo de cada ferramenta |
| POST | `/api/inpaint` | `image`, `mask`, `dilate` | PNG/JPG (marca d'água preenchida) |
| POST | `/api/lighting` | `image`, `strength` | PNG/JPG (sombras clareadas) |
| POST | `/api/upscale` | `image`, `scale` | PNG/JPG (x2/x4) |

Todos `POST` aceitam `format=png|jpg` e respondem em `X-Engine` o motor usado
(`lama`, `opencv-telea`, `realesrgan-xN`, `lanczos-xN`).

---

## 2. Como executar

```powershell
# 1) Instalar núcleo
powershell -ExecutionPolicy Bypass -File scripts\install.ps1

# 1b) Com a IA (LaMa + Real-ESRGAN) — baixa torch (~200MB) + LaMa (~200MB)
powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -AI

# 2) Rodar (abre http://localhost:8000)
powershell -ExecutionPolicy Bypass -File scripts\run.ps1
```

> No primeiro `/api/inpaint` o LaMa baixa `big-lama.pt`; no primeiro `/api/upscale`
> baixa `RealESRGAN_x2plus.pth`. Depois ficam em cache local (`backend/models/`).

### Instalar como atalho na tela inicial (celular)
1. Acesse pelo celular na mesma rede: `http://SEU-IP:8000`.
2. **Android/Chrome:** menu ⋮ → *Adicionar à tela inicial* / *Instalar app*.
3. **iOS/Safari:** Compartilhar ⤴ → *Adicionar à Tela de Início*.

---

## 3. Uso
1. Toque na área central e escolha uma foto da galeria (EXIF/rotação já corrigida).
2. **Remover Marca d'Água:** toque no botão, **pinte com o dedo** a marca e toque em
   **Aplicar**. Só pixels vizinhos (pele/cabelo/roupa) são usados.
3. **Melhorar Iluminação:** ajuste a intensidade ("Luz") e toque no botão.
4. **Melhorar Resolução:** gera a versão x2 (uso em GPU opcional para x4).
5. **Salvar** em JPG ou PNG; **Desfazer** volta um passo; **Ver original** compara.

---

## 4. Publicar na nuvem gratuita (Render / Railway)

O projeto inclui `Dockerfile`, `render.yaml` e `railway.json` prontos. A imagem
instala `torch` (CPU), o LaMa e já **assou os pesos** dos modelos no build —
o primeiro acesso é rápido. Em nuvem o limite de tamanho cai para
`PHOTOAPP_MAX_DIM=2400` (memória do plano gratuito).

```sh
# Talvez precise do Docker só para publicar:
# (no Railway o serviço já detecta o Dockerfile automaticamente)

# Railway (dispensa git e Docker local):
#   1. Crie conta em https://railway.app (gratuito)
#   2. Baixe o CLI:  npm i -g @railway/cli
#   3. Gere um token em: Dashboard -> Settings -> Tokens
#   4. No projeto:  railway link  e  railway up --detach
#   5. Abra o domínio gerado (https://<nome>-up.railway.app)

# Render (via GitHub):
#   1. Suba este repositório para o GitHub
#   2. Em https://render.com -> New -> Blueprint (usa o render.yaml)
#   3. Pronto: https://<nome>.onrender.com
```

Privacidade: nuvem gratuita é ótima para testes. Para fotos sensíveis da sua
galeria, o mais seguro é rodar **na sua máquina** (processamento 100% local).

---

## 5. Notas de engenharia
- **Sem GPU?** Funciona em CPU (mais lento em fotos grandes). Com GPU NVIDIA:
  `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121`
- O Real-ESRGAN roda com **tiling** (memória controlada mesmo em fotos/telas grandes,
  `processors/rrdbnet.py`).
- O inpainting **recorta** só a região da marca (+margem) para velocidade e qualidade,
  e a cola de volta com borda suave.
- Escala padrão: `PHOTOAPP_UPSCALE` (2). Limite de upload: 25 MB.
- Service worker exige servir via HTTP (nunca `file://`).