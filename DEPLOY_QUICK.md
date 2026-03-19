# 🚀 Deploy Rápido - Vercel + Railway

## Resumo da Arquitetura
- **Frontend (React):** Vercel ✅
- **Backend (FastAPI):** Railway ✅

---

## 📦 Passo 1: Deploy do Backend (Railway)

1. Acesse https://railway.app e crie uma conta
2. Clique em **"New Project"** → **"Deploy from GitHub repo"**
3. Selecione o repositório na raiz `410---thora-construcao`
4. O Railway usará automaticamente o `nixpacks.toml` e o `Procfile`
4. Configure as variáveis de ambiente:
   ```
   ENVIRONMENT=production
   PORT=8000
   FRONTEND_URL=https://seu-app.vercel.app
   FRONTEND_URLS=https://seu-app.vercel.app,https://seu-preview.vercel.app
   FIREBASE_DISABLED=1
   GEMINI_API_KEY=sua-chave-aqui
   ```
5. Se for usar Firebase em produção, substitua `FIREBASE_DISABLED=1` por:
   ```
   FIREBASE_CREDENTIALS={"type":"service_account","project_id":"..."}
   ```
6. Aguarde o deploy e copie a URL (ex: `https://seu-app.railway.app`)

### Comandos usados pelo Railway

- **Install:** `pip install -r backend/requirements.txt`
- **Start:** `cd backend && gunicorn -w 2 -b 0.0.0.0:$PORT -k uvicorn.workers.UvicornWorker main:app`

### Teste do backend

- Health check: `https://seu-app.railway.app/health`
- Docs: `https://seu-app.railway.app/docs`

---

## 🌐 Passo 2: Deploy do Frontend (Vercel)

### Via GitHub (Automático):

1. Acesse https://vercel.com e faça login
2. Clique em **"Add New"** → **"Project"**
3. Importe o repositório do GitHub
4. Configure:
   - **Root Directory:** `frontend`
   - **Build Command:** `npm run build`
   - **Output Directory:** `dist`
5. Adicione a variável de ambiente:
   - `VITE_API_URL` = URL do Railway (ex: `https://seu-app.railway.app`)
6. Clique em **"Deploy"**

### Via CLI:

```bash
# Instalar Vercel CLI
npm install -g vercel

# Preparar projeto
powershell -ExecutionPolicy Bypass -File prepare_deploy.ps1

# Deploy
vercel --prod
```

---

## ⚙️ Passo 3: Configurar Backend

O backend já aceita `FRONTEND_URL` e `FRONTEND_URLS` por variável de ambiente.

Faça commit e push. O Railway fará redeploy automaticamente.

---

## ✅ Testar

1. Acesse `https://seu-app.vercel.app`
2. Faça upload de um PDF
3. Verifique se a análise funciona

---

## 🔧 Comandos Úteis

```bash
# Ver logs do Vercel
vercel logs

# Atualizar variáveis de ambiente
vercel env add VITE_API_URL production

# Forçar novo deploy
vercel --prod --force
```

---

## 📖 Documentação Completa

Consulte [VERCEL_DEPLOY.md](./VERCEL_DEPLOY.md) para instruções detalhadas e troubleshooting.
