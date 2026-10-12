# STATUS.md — Onde estamos

> Diário vivo do projeto. **Atualize este arquivo ao fim de cada sessão.**
> Última atualização: **2026-10-12**.

## 1. Objetivo
PWA de edição de fotos que remove marca d'água (inpainting), melhora iluminação
e resolução — sem alterar a identidade das pessoas. Novo foco em andamento:
**"Modo IA" automático** (o sistema analisa a imagem e escolhe/combina modelos
de IA de nuvem para o melhor resultado, sem o usuário escolher).

## 2. O que já está pronto e NO AR
- App: https://photoapp-ywlg.onrender.com (Render free, Docker).
- Commit em produção: `1583263` (branch `main`).
- Endpoints: `/api/health`, `/api/detect-watermark`, `/api/inpaint`,
  `/api/inpaint-ai`, `/api/lighting`, `/api/upscale`.
- Detecção automática de marca d'água (`backend/processors/watermark.py`).
- Inpainting local: LaMa (máquinas grandes) / OpenCV Telea (Render free).
- **Modo IA (Replicate) já funcional**: `REPLICATE_API_TOKEN` configurado no
  Render; `health.ai.available = true`. Rota `/api/inpaint-ai` chama o FLUX Fill.
  → Bloqueado por **falta de crédito no Replicate** ("Insufficient credit").
    O usuário vai: (a) adicionar cartão/crédito e (b) **rotacionar o token**.
- Deploy IDs úteis: último = `dep-db6ea0142hec73bucin0`.

## 3. EM ANDAMENTO (ainda NÃO commitado)
Reescrita para o **orquestrador automático** ("Auto"): decidir sozinho entre
Telea grátis / Bria Eraser / FLUX Fill e encadear os dois quando preciso.

Já feitos (no diretório de trabalho, sem commit):
- `backend/config.py` — novas vars: `REPLICATE_MODEL_FILL`,
  `REPLICATE_MODEL_ERASER`, `AUTO_MAX_CALLS`, `AUTO_RESIDUAL_THRESHOLD`,
  `BRIA_MASK_INVERT`, `COST_FILL_USD`, `COST_ERASER_USD`. Default do fill agora
  é `black-forest-labs/flux-fill-pro`.
- `backend/processors/ai_inpaint.py` — refeito: cliente genérico `_call_model`,
  `flux_fill()`, `bria_erase()` (Bria com `sync`), `remove_watermark_ai()` mantido.
- `backend/processors/auto_edit.py` — **novo**: `analyze()` · `decide()` ·
  `score()` (marca residual + halo + emenda) · `run_auto()` (teto 2 chamadas
  pagas, detecção automática de máscara se vier vazia).

## 4. PRÓXIMOS PASSOS (ordem)
1. `backend/app.py`: usar `run_auto` na `/api/inpaint-ai` (campo `mode=auto`),
   cabeçalhos `X-Engine` e `X-Decision` (ASCII, ex. `Bria -> FLUX | US$0.08`),
   expor os modelos no `/api/health`; adicionar `X-Decision` em `expose_headers`.
2. Frontend: trocar o "chip/toggle IA" por **botão único Auto** (sem seletor);
   "Aplicar" usa Auto quando houver token; **toast** "Decidido por: … · ~US$…";
   bump do service worker para `photoapp-v5`.
3. `render.yaml`: adicionar `REPLICATE_MODEL_FILL`, `REPLICATE_MODEL_ERASER`
   (opcionais; já existem `REPLICATE_MODEL`, `REPLICATE_API_TOKEN`,
   `PHOTOAPP_AI_MAX_DIM`).
4. Testes unitários mockados (sem gastar crédito): `analyze`/`decide`/`run_auto`
   com `_call_model` mockado; depois 1 teste live na `teste.jpg`.
5. `commit` + `push` + deploy.

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
  documentada → assumimos branco=apagar + auto-invert de segurança.
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
