# Deploy: Backend no Render + Frontend no Netlify

Guia passo a passo para o Thora Construção funcionar em produção com IA, PDF e fila de processamento.

---

## Visão geral

| Serviço | Plataforma | Função |
|---------|------------|--------|
| API (FastAPI) | **Render** | PDF, IA, filas, Firestore |
| SPA (React) | **Netlify** | Interface do usuário |
| Redis (opcional) | **Upstash** ou Render Redis | Jobs persistentes + Celery |
| Worker Celery (opcional) | **Render** (2º serviço) | Processamento em background |

> **Recomendação:** use Render **Starter** (não Free) para evitar sleep e disco efêmero. PDF + IA demoram minutos — o plano Free dorme após inatividade e limita recursos.

---

## Parte 1 — Backend no Render

### 1. Criar o Web Service

1. Acesse [render.com](https://render.com) → **New +** → **Web Service**
2. Conecte o repositório GitHub
3. Configure:

| Campo | Valor |
|-------|-------|
| **Name** | `four10-thora-api` (ou o nome que preferir) |
| **Region** | São Paulo ou US East (próximo dos usuários) |
| **Branch** | `main` |
| **Root Directory** | `backend` |
| **Runtime** | Python 3 |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn -w 1 --timeout 600 --graceful-timeout 30 -b 0.0.0.0:$PORT -k uvicorn.workers.UvicornWorker main:app` |
| **Instance Type** | Starter (mínimo recomendado) |

> Se **Root Directory** = `backend`, **não** use `cd backend` no Start Command.

### 2. Variáveis de ambiente (obrigatórias)

No painel Render → **Environment**:

```env
ENVIRONMENT=production
PORT=10000

# OpenAI — obrigatório para orçamento com IA
OPENAI_API_KEY=sk-proj-...
OPENAI_ORCAMENTO_MODEL=gpt-4o
OPENAI_ORCAMENTO_TIMEOUT=120

# Firebase — JSON minificado em UMA linha (sem quebras)
FIREBASE_CREDENTIALS={"type":"service_account","project_id":"...","private_key":"..."}
FIREBASE_STORAGE_BUCKET=seu-projeto.firebasestorage.app

# CORS — URL do site Netlify
FRONTEND_URL=https://seu-site.netlify.app
FRONTEND_URLS=https://seu-site.netlify.app

# Upload
MAX_FILE_SIZE=52428800
DETECT_TABLES_MAX_PAGES=20
```

**Como minificar o JSON do Firebase:**
1. Firebase Console → Project Settings → Service Accounts → Generate new private key
2. Abra o `.json` baixado
3. Use [jsoncrack.com/editor](https://jsoncrack.com/editor) ou remova todas as quebras de linha manualmente
4. Cole o resultado inteiro em `FIREBASE_CREDENTIALS`

### 3. Variáveis opcionais (recomendadas)

```env
# Gemini — fallback / padronização
GEMINI_API_KEY=sua-chave

# Redis — jobs persistentes (Upstash free tier funciona)
REDIS_URL=rediss://default:senha@host.upstash.io:6379
CELERY_BROKER_URL=rediss://default:senha@host.upstash.io:6379
CELERY_RESULT_BACKEND=rediss://default:senha@host.upstash.io:6379
USE_CELERY_QUEUE=true
```

### 4. Health check

Render usa automaticamente `/health` se configurado no `railway.json` — no Render, defina:

- **Health Check Path:** `/health`

Após deploy, teste:

```bash
curl https://SEU-SERVICO.onrender.com/health
```

Resposta esperada: `{"status":"ok",...}`

### 5. (Opcional) Worker Celery — só se usar Redis

Se `USE_CELERY_QUEUE=true` e `REDIS_URL` estiver configurado, crie um **segundo** serviço no Render:

| Campo | Valor |
|-------|-------|
| **Type** | Background Worker |
| **Root Directory** | `backend` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `celery -A celery_app worker --loglevel=info -Q analitico,abc --concurrency=1` |

Copie **as mesmas variáveis de ambiente** do Web Service (OPENAI, Firebase, Redis, etc.).

> **Sem Redis:** o backend usa fila asyncio na mesma instância — funciona para um único servidor, mas jobs em memória se perdem ao reiniciar.

---

## Parte 2 — Frontend no Netlify

### 1. Site já existente

Se o site já está no Netlify, vá em **Site configuration → Environment variables**:

```env
VITE_API_URL=https://SEU-SERVICO.onrender.com
```

### 2. Novo deploy via GitHub

1. [netlify.com](https://netlify.com) → **Add new site** → Import from Git
2. Configure:

| Campo | Valor |
|-------|-------|
| **Base directory** | `frontend` |
| **Build command** | `npm run build` |
| **Publish directory** | `frontend/dist` |

3. Adicione a variável `VITE_API_URL` apontando para o Render (sem barra no final)

### 3. netlify.toml

O arquivo `frontend/netlify.toml` já define `VITE_API_URL` em produção. Atualize a URL se mudou:

```toml
[context.production]
  environment = { VITE_API_URL = "https://SEU-SERVICO.onrender.com" }
```

> **Importante:** o frontend deve chamar a API **diretamente** no Render. Não use proxy do Netlify para `/api/*` — o proxy tem timeout ~26s e quebra detecção de tabelas.

### 4. Redeploy

Após alterar `VITE_API_URL`, faça **Trigger deploy** no Netlify para rebuildar com a URL correta.

---

## Parte 3 — Checklist pós-deploy

### Backend (Render)

- [ ] `GET /health` retorna 200
- [ ] `GET /docs` abre a documentação Swagger
- [ ] Logs mostram `GEMINI_API_KEY carregada` ou aviso (Gemini é opcional)
- [ ] Teste upload: `POST /api/upload` com PDF + token Firebase

### Frontend (Netlify)

- [ ] Login Firebase funciona
- [ ] Upload de PDF inicia detecção de tabelas
- [ ] Barra de progresso avança durante processamento
- [ ] Console do browser **não** mostra erro CORS

### CORS

O backend aceita `*.netlify.app` automaticamente. Se usar domínio customizado, adicione:

```env
FRONTEND_URL=https://www.seudominio.com.br
FRONTEND_URLS=https://www.seudominio.com.br,https://seudominio.com.br
```

---

## Parte 4 — Solução de problemas

| Sintoma | Causa provável | Solução |
|---------|----------------|---------|
| Erro 401/403 na API | Token Firebase inválido | Verifique auth no frontend |
| CORS blocked | URL do Netlify não listada | Adicione em `FRONTEND_URL` |
| Timeout ao detectar tabelas | Render Free dormindo ou PDF grande | Upgrade Starter; PDF menor |
| IA retorna erro 500 | `OPENAI_API_KEY` ausente/inválida | Configure no Render |
| Job `not_found` no polling | Instância reiniciou sem Redis | Adicione Redis + Celery |
| Progresso trava em 0% | Frontend desatualizado | Redeploy Netlify com versão nova |
| Upload 413 | PDF > 50 MB | Reduza arquivo ou aumente `MAX_FILE_SIZE` |

---

## Parte 5 — Configuração mínima (sem Redis)

Para começar rápido, **sem Redis/Celery**:

```env
USE_CELERY_QUEUE=false
```

O processamento roda na mesma instância Gunicorn via fila asyncio. Adequado para testes e baixo volume. Para produção com múltiplos usuários simultâneos, adicione Redis.

---

## URLs de referência do projeto

- Backend atual: `https://four10-thora-construcao.onrender.com`
- Frontend: configurado em `frontend/.env.production` e `netlify.toml`

Após seguir este guia, faça um teste completo: upload PDF → seleção de tabela → processamento IA → exportação XLSX.
