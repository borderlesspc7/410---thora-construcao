cd backend
py -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
py main.py

## Fallback de IA (opcional, recomendado)

Configure uma ou mais chaves no `.env` para evitar indisponibilidade quando a cota do Gemini acabar:

```dotenv
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.0-flash

OPENROUTER_API_KEY=...
OPENROUTER_MODEL=qwen/qwen3-14b:free

GROQ_API_KEY=...
GROQ_MODEL=llama-3.3-70b-versatile

OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o-mini

OLLAMA_ENABLED=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b-instruct
OLLAMA_TIMEOUT_SECONDS=45
```

Ordem de tentativa no endpoint de padronização: Ollama local → Gemini → OpenRouter → Groq → OpenAI → fallback local (sem IA remota).