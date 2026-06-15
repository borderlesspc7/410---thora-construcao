import os
from pathlib import Path

from dotenv import load_dotenv

# Paths
BASE_DIR = Path(__file__).resolve().parent
# .env na raiz do repo e em backend/ (não depender só do diretório de trabalho ao rodar `py main.py`)
load_dotenv(BASE_DIR.parent / ".env")
load_dotenv(BASE_DIR / ".env")
load_dotenv()
IS_VERCEL = os.getenv("VERCEL", "").strip().lower() in {"1", "true", "yes", "on"}
RUNTIME_BASE_DIR = Path("/tmp") if IS_VERCEL else BASE_DIR
UPLOAD_FOLDER = RUNTIME_BASE_DIR / "uploads"
TEMP_FOLDER = RUNTIME_BASE_DIR / "temp"
CACHE_FOLDER = RUNTIME_BASE_DIR / "cache"

# Criar pastas se não existirem
UPLOAD_FOLDER.mkdir(exist_ok=True)
TEMP_FOLDER.mkdir(exist_ok=True)
CACHE_FOLDER.mkdir(exist_ok=True)

# Ambiente
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DEBUG = ENVIRONMENT == "development"

# Upload
_default_max_file_size = 8 * 1024 * 1024 if IS_VERCEL else 50 * 1024 * 1024
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", _default_max_file_size))

# CORS
EXTRA_FRONTEND_URLS = [
    url.strip()
    for url in os.getenv("FRONTEND_URLS", "").split(",")
    if url.strip()
]

FRONTEND_URLS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:8001",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8001",
    "https://410-thora.netlify.app",
    "https://borderles-410.netlify.app",
    os.getenv("FRONTEND_URL", ""),
    *EXTRA_FRONTEND_URLS,
]
FRONTEND_URLS = [url for url in FRONTEND_URLS if url]

# Permite previews e novos sites Netlify sem redeploy do backend (ex.: *.netlify.app)
CORS_ORIGIN_REGEX = os.getenv(
    "CORS_ORIGIN_REGEX",
    r"https://[\w-]+\.netlify\.app",
)

# Server
API_TITLE = "Automação de Orçamentos"
API_VERSION = "1.0.0"
API_DESCRIPTION = "API para processar e gerar orçamentos de obras"

# AI (Google Gemini)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# AI fallback providers (OpenAI-compatible APIs)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "qwen/qwen3-14b:free")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
# Fluxo Orçamento Analítico (GPT-4o) — chave sempre via .env (nunca no código)
OPENAI_ORCAMENTO_MODEL = os.getenv("OPENAI_ORCAMENTO_MODEL", "gpt-4o")
_default_orcamento_timeout = "55" if IS_VERCEL else "120"
OPENAI_ORCAMENTO_TIMEOUT_SECONDS = float(
    os.getenv("OPENAI_ORCAMENTO_TIMEOUT", _default_orcamento_timeout)
)

# AI local provider (Ollama)
_default_ollama_enabled = "false" if IS_VERCEL else "true"
OLLAMA_ENABLED = os.getenv("OLLAMA_ENABLED", _default_ollama_enabled).lower() in (
    "1",
    "true",
    "yes",
    "on",
)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
_default_ollama_timeout = "55" if IS_VERCEL else "45"
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", _default_ollama_timeout))

_default_ai_provider_timeout = "55" if IS_VERCEL else "45"
AI_PROVIDER_TIMEOUT_SECONDS = float(
    os.getenv("AI_PROVIDER_TIMEOUT_SECONDS", _default_ai_provider_timeout)
)

_default_multi_provider_chain = "false" if IS_VERCEL else "true"
ENABLE_MULTI_PROVIDER_CHAIN = os.getenv(
    "ENABLE_MULTI_PROVIDER_CHAIN", _default_multi_provider_chain
).lower() in ("1", "true", "yes", "on")

# Firebase Storage (PDFs originais)
FIREBASE_STORAGE_BUCKET = os.getenv(
    "FIREBASE_STORAGE_BUCKET",
    "borderless-5a4c8.firebasestorage.app",
)

# Detecção de tabelas em PDF (limite de páginas para pdfplumber/Camelot)
DETECT_TABLES_MAX_PAGES = int(os.getenv("DETECT_TABLES_MAX_PAGES", "60"))

# Redis / Celery (fila persistente de Orçamento Analítico)
REDIS_URL = os.getenv("REDIS_URL", "").strip()
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL).strip()
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL).strip()
_default_use_celery = "false" if IS_VERCEL else "true"
USE_CELERY_QUEUE = os.getenv("USE_CELERY_QUEUE", _default_use_celery).lower() in (
    "1",
    "true",
    "yes",
    "on",
) and bool(CELERY_BROKER_URL) and not IS_VERCEL

if GEMINI_API_KEY:
    print("GEMINI_API_KEY carregada")
else:
    print("AVISO: GEMINI_API_KEY não encontrada no .env")
