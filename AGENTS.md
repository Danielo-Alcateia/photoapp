# AGENTS.md — PhotoApp (leia isto primeiro)

> **Onde estamos?** Leia [`STATUS.md`](./STATUS.md) **antes de começar** e
> **atualize-o** ao terminar qualquer sessão de trabalho. É o diário vivo do
> projeto: objetivo, estado atual, próximos passos e pendências.

## O que é
PWA de edição de fotos (Flask + JS) que faz, **sem alterar a identidade das
pessoas**: remover marca d'água (inpainting), melhorar iluminação e resolução.

- Backend: `backend/` (Flask). Frontend: `frontend/` (PWA, service worker).
- Deploy: **Render** (Docker, plano free 512 MB), `render.yaml` + `Dockerfile`.
- Repositório: `Danielo-Alcateia/photoapp` (branch `main`).
- App online: https://photoapp-ywlg.onrender.com

## Regras invioláveis
1. **Fidelidade fisionômica**: nenhum modelo generativo de reconstrução facial
   (CodeFormer/GFPGAN). Ver `config.FORBIDDEN_FACE_GENERATORS` e
   `backend/processors/__init__.py`.
2. Toda saída de IA **generativa só pode alterar pixels dentro da máscara**;
   o resto da foto fica idêntico.
3. **Nunca** gravar segredos (tokens) no repositório. Tokens vão por variável
   de ambiente (Render → Environment / `.env` local, que é ignorado).
4. RAM baixa: no Render free, LaMa/Real-ESRGAN não cabem; ver `config.LOW_RAM`
   e os flags `*_LITTLE_RAM`. Não ligue warmup de modelos pesados na nuvem.

## Comandos
```powershell
# Rodar local (usa .venv)
& ".\.venv\Scripts\python.exe" backend/app.py

# Checar sintaxe rápida
& ".\.venv\Scripts\python.exe" -c "import ast; ast.parse(open('backend/app.py',encoding='utf-8').read())"

# Git (o git fica fora do PATH)
& "C:\Program Files\Git\cmd\git.exe" status
```

## Fluxo de trabalho
- Faça `commit` + `push` **somente** quando pedido; o push dispara deploy no
  Render automaticamente.
- Ao final de cada tarefa, **atualize o `STATUS.md`** (seção "Estado atual" e
  "Próximos passos").
