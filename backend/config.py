import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Paths
BASE_DIR = Path(__file__).resolve().parent
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
    "http://localhost:8001",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8001",
    "https://410-thora.netlify.app",
    os.getenv("FRONTEND_URL", ""),
    *EXTRA_FRONTEND_URLS,
]
FRONTEND_URLS = [url for url in FRONTEND_URLS if url]

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
_default_ollama_timeout = "12" if IS_VERCEL else "45"
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", _default_ollama_timeout))

_default_ai_provider_timeout = "12" if IS_VERCEL else "45"
AI_PROVIDER_TIMEOUT_SECONDS = float(
    os.getenv("AI_PROVIDER_TIMEOUT_SECONDS", _default_ai_provider_timeout)
)

_default_multi_provider_chain = "false" if IS_VERCEL else "true"
ENABLE_MULTI_PROVIDER_CHAIN = os.getenv(
    "ENABLE_MULTI_PROVIDER_CHAIN", _default_multi_provider_chain
).lower() in ("1", "true", "yes", "on")

if GEMINI_API_KEY:
    print("✅ GEMINI_API_KEY carregada")
else:
    print("⚠️  GEMINI_API_KEY não encontrada no .env")
