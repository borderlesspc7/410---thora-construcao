# 🚀 Guia de Deploy - Borderless 410

## Backend no Render.com

### 1️⃣ Preparar o Firebase

- No Firebase Console, gere uma nova chave privada (Service Account)
- Copie o JSON completo

### 2️⃣ Criar o serviço no Render

1. Acesse [Render.com](https://render.com)
2. Faça login/registre-se
3. Clique em **"New+"** → **"Web Service"**
4. Conecte seu repositório GitHub
5. Preencha as configurações:

| Campo             | Valor                                                                                    |
| ----------------- | ---------------------------------------------------------------------------------------- |
| **Name**          | `borderless-api`                                                                         |
| **Region**        | `Ohio (US East)` ou próximo de seus usuários                                             |
| **Branch**        | `main`                                                                                   |
| **Runtime**       | `Python 3`                                                                               |
| **Build Command** | `pip install -r backend/requirements.txt && pip install gunicorn uvicorn[standard]` |
| **Start Command** | `cd backend && gunicorn -w 4 -b 0.0.0.0:$PORT -k uvicorn.workers.UvicornWorker main:app` |

### 3️⃣ Configurar Variáveis de Ambiente

No painel do Render, vá em **"Environment"** e adicione:

```
ENVIRONMENT=production
FRONTEND_URL=https://seu-frontend-url.vercel.app
FIREBASE_CREDENTIALS={"type":"service_account","project_id":"seu-project",...}
```

⚠️ **Importante**:

- O JSON **DEVE estar em uma única linha** (sem quebras de linha)
- Remova todos os espaçamentos e quebras do JSON
- Use um minificador: https://jsoncrack.com/editor ou similar
- Copie o resultado minificado inteiro para a variável

### 4️⃣ Deploy

- Clique em **"Deploy"**
- Aguarde 5-10 minutos
- Sua API estará disponível em: `https://borderless-api.onrender.com`

---

## Frontend no Vercel

### 1️⃣ Preparar o Frontend

1. Atualize a URL da API no arquivo `frontend/src/services/api.ts`:

```typescript
const API_BASE_URL =
  process.env.VITE_API_URL || "https://borderless-api.onrender.com";
```

2. Crie um arquivo `.env.production`:

```
VITE_API_URL=https://borderless-api.onrender.com
VITE_FIREBASE_CONFIG=seu_config_aqui
```

### 2️⃣ Deploy no Vercel

1. Acesse [Vercel.com](https://vercel.com)
2. Conecte seu repositório GitHub
3. Selecione o projeto
4. Configure:
   - **Framework**: `Vite`
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`

5. Adicione variáveis de ambiente no painel do Vercel
6. Clique em **"Deploy"**

---

## Arquivos Criados/Modificados

- ✅ `Procfile` - Configuração para Render
- ✅ `.render/build.sh` - Script de build customizado
- ✅ `.env.example` - Template de variáveis
- ✅ `backend/requirements.txt` - Adicionado gunicorn e uvicorn
- ✅ `backend/config.py` - URLs de CORS para produção

---

## ✅ Checklist Final

- [ ] Firebase Service Account JSON preparado
- [ ] Variáveis de ambiente configuradas no Render
- [ ] Build do Render passou com sucesso
- [ ] API respondendo em `/health`
- [ ] Frontend apontando para URL correta da API
- [ ] CORS configurado corretamente
- [ ] Teste de upload de PDF funcionando

---

## 🔗 URLs úteis

- **Render Dashboard**: https://dashboard.render.com
- **Seu Backend**: https://borderless-api.onrender.com
- **Health Check**: https://borderless-api.onrender.com/health
