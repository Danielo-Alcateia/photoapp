# STATUS.md — Onde estamos

> Diário vivo do projeto. **Atualize este arquivo ao fim de cada sessão.**
> Última atualização: **2026-10-12** (sessão 2: orquestrador Auto NO AR).

## 1. Objetivo
PWA de edição de fotos que remove marca d'água (inpainting), melhora iluminação
e resolução — sem alterar a identidade das pessoas. Novo foco em andamento:
**"Modo IA" automático** (o sistema analisa a imagem e escolhe/combina modelos
de IA de nuvem para o melhor resultado, sem o usuário escolher).

## 2. O que já está pronto e NO AR
- App: https://photoapp-ywlg.onrender.com (Render free, Docker).
- Commit em produção: `3466ca2` (branch `main`) — **Modo IA automático**.
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
    "Insufficient credit"). Falta só o crédito + rotação do token.
- Deploy IDs úteis: último = `dep-db6h3n49v7es73fdak20`.

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

## 4. PRÓXIMOS PASSOS
1. Usuário: adicionar cartão/crédito no Replicate e **rotacionar o token**
   (o atual ficou exposto no chat) → atualizar `REPLICATE_API_TOKEN` no Render.
   Rotacionar também a API key do Render (exposta no chat).
2. Após crédito: teste live do caminho pago (Bria/FLUX/combo) na `teste.jpg`.
3. (Futuro) Detecção de marca d'água **full-image** — hoje o Auto, com máscara
   vazia, pede para pintar se o detector não achar.

## 5. Decisões travadas (com o usuário)
- Interface: **só o botão Auto** (sem seletor de modos).
- Auto pode gastar **até 2 chamadas pagas** por pedido (Telea grátis sempre 1º).
- Mostrar **qual motor foi usado + custo estimado** (toast).
- Detecção automática de máscara **incluída** (quando a máscara vier vazia).
- Melhor modelo escolhido: **FLUX.1 Fill [pro]** (`black-forest-labs/flux-fill-pro`).
- Combo recomendado: **Bria Eraser → FLUX Fill pro** (apagar + refinar).
- Token: será **rotacionado** pelo usuário (ficou exposto no chat).

## 6. Fatos técnicos que importam
- `flux-fill-pro`: input `image`, `mask` (**branco = preencher**), `prompt`,
  `steps`, `guidance`, `seed`, `output_format` (default jpg).
- `bria/eraser`: input `image`, `mask`, `sync` (bool). Polaridade não
  documentada → assumimos **branco = apagar** (config `BRIA_MASK_INVERT`); se
  estiver errada, o resultado fica ruim e a verificação descarta (o fallback
  assume).
- Render free = 512 MB → LaMa/torch dão `oomKilled`; usar Telea na nuvem.
- Prefetch de pesos agora é **não-fatal** (contorna HTTP 500 do GitHub).
- Service worker é cache-first → **bumpar a versão** do cache a cada deploy.
- Sem o token do Replicate, o app volta ao modo grátis automaticamente.

## 7. Comandos rápidos
```powershell
& ".\.venv\Scripts\python.exe" backend/app.py                    # rodar local
& "C:\Program Files\Git\cmd\git.exe" status                      # git (fora do PATH)
# health na nuvem:
Invoke-RestMethod https://photoapp-ywlg.onrender.com/api/health
```

## 8. Pendências / riscos
- Conta Replicate **sem crédito** → testes de IA ao vivo bloqueados até recarga.
- O "juiz automático" (`score`) é heurístico: às vezes roda 2 chamadas sem
  precisar ou escolhe um resultado um pouco pior. Ajustável por
  `AUTO_RESIDUAL_THRESHOLD`.
- Marca d'água que cobre a foto inteira: o detector de bordas não pega; precisa
  de detecção full-image (trabalho futuro).
