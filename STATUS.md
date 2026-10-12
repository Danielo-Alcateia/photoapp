# STATUS.md — Onde estamos

> Diário vivo do projeto. **Atualize este arquivo ao fim de cada sessão.**
> Última atualização: **2026-10-12** (sessão 3: auditoria + otimização FREE 512 MB).

## 0. ⚠️ SEGURANÇA — AÇÃO MANUAL URGENTE (rotacionar segredos)
Três segredos foram expostos em chat e **devem ser rotacionados** (o valor antigo
fica inválido a partir da rotação):
1. **REPLICATE_API_TOKEN** — gere um novo em https://replicate.com/account/api-tokens
   e atualize no Render (Environment). O antigo (`r8_Z5O…`) deve ser revogado.
2. **Render API key** — revogue em https://dashboard.render.com/u/settings (API Keys)
   e gere outra. A antiga (`rnd_cVQ…`) deve ser apagada.
3. **HF token** (`hf_AswL…`) — revogue em https://huggingface.co/settings/tokens.

Boas práticas já aplicadas no repo: `.env.example` criado; `.env` no `.gitignore`
(e `.dockerignore`); **nenhum arquivo versionado contém segredo**; o token nunca é
impresso em log (só usado no header `Authorization`).

## 1. Objetivo
PWA de edição de fotos que remove marca d'água (inpainting), melhora iluminação
e resolução — sem alterar a identidade das pessoas. Novo foco em andamento:
**"Modo IA" automático** (o sistema analisa a imagem e escolhe/combina modelos
de IA de nuvem para o melhor resultado, sem o usuário escolher).

## 2. O que já está pronto e NO AR
- App: https://photoapp-ywlg.onrender.com (Render free, Docker).
- Commit em produção: `afc0418` (branch `main`) — **Auditoria FREE 512 MB**.
- Endpoints: `/api/health`, `/api/detect-watermark`, `/api/inpaint`,
  `/api/inpaint-ai`, `/api/lighting`, `/api/upscale`.
- Detecção automática de marca d'água (`backend/processors/watermark.py`).
- Inpainting local: LaMa (máquinas grandes) / OpenCV Telea (Render free).
- **Modo IA automático (Replicate) NO AR**: o usuário só vê o chip "Modo IA
  automático"; o backend decide sozinho (Local grátis / Bria / FLUX fill-pro),
  com teto de 2 chamadas pagas e verificação por `score`. Health expõe
  `ai.engine_fill = black-forest-labs/flux-fill-pro`, `engine_eraser = bria/eraser`.
  → Caminho **grátis** verificado live (200, `X-Decision: Local | US$0.000`).
  → Caminho **pago** verificado live (chega no Replicate; retorna
    **402 `no_credit`** — antes era 502 genérico). Falta só o crédito + rotação.
- Deploy IDs úteis: últimos = `dep-db6i7ms9v7es7391ts30` e `dep-db6i7n6b5qgc73duk4tg`.

## 3. Histórico da última sessão (concluído)
**Orquestrador automático ("Auto") — commit `3466ca2`, no ar e testado.**

- `backend/config.py` — vars: `REPLICATE_MODEL_FILL` (default
  `black-forest-labs/flux-fill-pro`), `REPLICATE_MODEL_ERASER` (`bria/eraser`),
  `AUTO_MAX_CALLS`=2, `AUTO_RESIDUAL_THRESHOLD`=0.18, `BRIA_MASK_INVERT`,
  `COST_FILL_USD`=0.045, `COST_ERASER_USD`=0.035.
- `backend/processors/ai_inpaint.py` — `_call_model` genérico, `flux_fill()`,
  `bria_erase()` (Bria com `sync`), `remove_watermark_ai()` (retrocompat).
- `backend/processors/auto_edit.py` — **novo**: `analyze()` · `decide()` ·
  `score()` (residual + halo + emenda) · `run_auto()`.
- `backend/app.py` — `/api/inpaint-ai` aceita `mode=auto` (padrão) / `flux` /
  `bria` / `combo` / `free`; devolve `X-Decision`/`X-Engine`/`X-Score`;
  `expose_headers` atualizado; `/api/health` expõe o bloco `ai`.
- Frontend — chip "Modo IA automático" (informativo, sem toggle);
  `api.removeWatermarkAI()` em `mode=auto` com `headerMap` de `X-Decision`;
  `runInpaint()` usa Auto quando há token e mostra o "decidido por" no toast;
  service worker em `photoapp-v5`.
- `render.yaml` — `REPLICATE_MODEL_FILL`/`REPLICATE_MODEL_ERASER`/`AUTO_MAX_CALLS`.

### Correções durante a sessão
- Bug: ao esgotar o orçamento pago, o loop fazia `break` e **não rodava** o
  fallback grátis. Trocado por `continue` (rede de segurança sempre roda).
- Removido o "retry invertido" do Bria (gastava orçamento sem necessidade — o
  fallback + verificação já descartam resultado ruim).
- `render.yaml` passou a definir os modelos; a 1ª sincronização do blueprint
  chegou **depois** do build, então foi preciso disparar um 2º deploy para o
  `flux-fill-pro` valer.

### Testes
- Unitários mockados (`C:\Users\Bianca\AppData\Local\Temp\opencode\wm_auto_test.py`):
  **7/7 passaram** (Local liso · Bria->FLUX · budget=1 · área grande · máscara
  vazia autodetectada · falha paga cai no Local · rota HTTP 200 + `X-Decision`).
- Live: Auto grátis → `200` + `X-Decision: Local | US$0.000`; `mode=flux` →
  `502 Insufficient credit` (integração OK).

## 3.1 Auditoria (sessão 3) — correções aplicadas
Auditoria completa do sistema para o plano FREE 512 MB. **Commit: `afc0418` (no ar).**

**Fidelidade/RAM (regras invioláveis) — mantidas:**
- `_composite()` segue existindo e só altera pixels **dentro da máscara**.
- Torch/GFPGAN/CodeFormer proibidos; `config.LOW_RAM` agora **força** os flags
  `*_LITTLE_RAM` (Telea/LANCZOS) mesmo com override manual. `/api/health` não
  importa torch (sem OOM). `memory.py` mantém só **1 modelo residente**.

**Fixes desta sessão:**
1. Detector full-image: `/api/detect-watermark` devolve **máscara central**
   sugestiva (`X-Watermark-Suggested: 1`) quando nada é achado; frontend carrega
   no pincel e avisa. Mensagem do Auto mais clara.
2. Dockerfile: prefetch **não-fatal** (`|| echo`) + ordem requirements → torch
   CPU → requirements-ai documentada.
3. Service Worker **v6** com **stale-while-revalidate** + fallback de navegação.
4. `render.yaml`: + `AUTO_EARLY_STOP_SCORE`, `AUTO_RESIDUAL_THRESHOLD`,
   `PHOTOAPP_DETECT_CACHE`.
5. **Early-stop**: 1ª chamada paga boa (score ≤ 0.12) → não gasta a 2ª (economia
   ~50%).
6. **402 no_credit**: `ReplicateNoCredit` → `{error:"no_credit", fallback:"opencv-telea"}`;
   frontend cai no grátis automaticamente.
7. **Cache LRU** (20) na detecção de marca d'água (por hash do conteúdo).
8. **Segurança**: `.env.example`, `.env` no `.gitignore`/`.dockerignore`, aviso
   de rotação (seção 0). Nenhum segredo versionado; token não vai para log.

**Testes (13/13 mockados + live local):**
- 13/13 PASS (`wm_auto_test.py`): Local liso · Bria→FLUX · budget=1 · área grande ·
  máscara vazia autodetectada · falha paga cai no Local · early-stop · fallback
  central · erro claro sem fallback · rota auto 200 + X-Decision · rota 402 ·
  detect sugere central · cache LRU.
- Local (servidor real): `/api/detect-watermark` (teste.jpg) → `found=0,
  suggested=1`; `/api/inpaint-ai?mode=auto` → `200`, `X-Decision: Local |
  US$0.000`, `X-Engine: lama` (dev), `X-Score: 0.123`.
- **Nuvem (Render, pós-deploy `afc0418`)**: health `ai` OK; `detect-watermark`
  → `suggested=1`; `inpaint-ai?mode=auto` → `200`, `X-Decision: Local |
  US$0.000`, `X-Engine: opencv-telea`; `mode=flux` → **402 `no_credit`**;
  service worker em `photoapp-v6`.

## 4. PRÓXIMOS PASSOS
1. Usuário (URGENTE): ver **seção 0** — rotacionar `REPLICATE_API_TOKEN`,
   API key do Render e token HF; e adicionar cartão internacional/crédito no
   Replicate (só aceita cartão internacional — não aceita Pix).
2. Após crédito: teste live do caminho pago (Bria/FLUX/combo) na `teste.jpg`.
3. (Futuro) Detecção de marca d'água **full-image**: hoje o detector devolve uma
   **máscara central sugestiva** (`X-Watermark-Suggested: 1`) que o usuário
   ajusta no pincel; evolução = detecção real de overlay semitransparente.

## 5. Decisões travadas (com o usuário)
- Interface: **só o botão Auto** (sem seletor de modos).
- Auto pode gastar **até 2 chamadas pagas** por pedido (Telea grátis sempre 1º),
  com **early-stop** (não gasta a 2ª se a 1ª já vier boa).
- Mostrar **qual motor foi usado + custo estimado** (toast / `X-Decision`).
- Detecção automática de máscara **incluída** (máscara vazia → detector →
  fallback central sugestivo).
- Melhor modelo escolhido: **FLUX.1 Fill [pro]** (`black-forest-labs/flux-fill-pro`).
- Combo recomendado: **Bria Eraser → FLUX Fill pro** (apagar + refinar).
- Tokens: **devem ser rotacionados** (ver seção 0).

## 6. Fatos técnicos que importam
- `flux-fill-pro`: input `image`, `mask` (**branco = preencher**), `prompt`,
  `steps`, `guidance`, `seed`, `output_format` (default jpg).
- `bria/eraser`: input `image`, `mask`, `sync` (bool). Polaridade não
  documentada → assumimos **branco = apagar** (config `BRIA_MASK_INVERT`); se
  estiver errada, o resultado fica ruim e a verificação descarta (o fallback
  assume).
- Render free = 512 MB → LaMa/torch dão `oomKilled`; usar Telea na nuvem.
  `config.LOW_RAM` **força** `INPAINT_LITTLE_RAM`/`UPSCALE_LITTLE_RAM` mesmo que
  o engine seja setado manualmente — impossível carregar torch no free.
- `/api/health` **nunca** importa torch (usa `importlib.util.find_spec`).
- Prefetch de pesos é **não-fatal** (script com try/except + `|| echo` no Dockerfile).
- Service worker **v6** com **stale-while-revalidate** (abre do cache mesmo com
  o Render "dormindo"); bumpar a versão do cache a cada deploy.
- Sem o token do Replicate, o app volta ao modo grátis automaticamente.
- Erro de crédito do Replicate vira **HTTP 402** `{error:"no_credit", fallback:"opencv-telea"}`
  e o frontend cai automaticamente no grátis (Telea).
- Detecção de marca tem **cache LRU em memória** (por hash do conteúdo; default 20).

## 7. Comandos rápidos
```powershell
& ".\.venv\Scripts\python.exe" backend/app.py                    # rodar local
& "C:\Program Files\Git\cmd\git.exe" status                      # git (fora do PATH)
# health na nuvem:
Invoke-RestMethod https://photoapp-ywlg.onrender.com/api/health
```

## 8. Pendências / riscos
- Conta Replicate **sem crédito** → testes de IA ao vivo bloqueados até recarga
  (ver seção 0).
- O "juiz automático" (`score`) é heurístico: pode escolher um resultado um pouco
  pior. O custo agora é contido por `AUTO_EARLY_STOP` + `AUTO_MAX_CALLS`.
- Marca d'água que cobre a foto inteira: o detector de bordas não pega; hoje o
  sistema sugere a máscara central (ajustável). Detecção real de overlay
  semitransparente = trabalho futuro.
