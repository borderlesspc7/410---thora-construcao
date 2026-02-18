import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
TEMP_FOLDER = BASE_DIR / "temp"

# Criar pastas se não existirem
UPLOAD_FOLDER.mkdir(exist_ok=True)
TEMP_FOLDER.mkdir(exist_ok=True)

# Ambiente
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DEBUG = ENVIRONMENT == "development"

# Upload
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 52428800))  # 50MB default

# CORS
FRONTEND_URLS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
    "https://410-thora.netlify.app",  # Frontend Netlify
    os.getenv("FRONTEND_URL", ""),  # Production frontend URL via env var
]
# Remove empty strings
FRONTEND_URLS = [url for url in FRONTEND_URLS if url]

# Server
API_TITLE = "Automação de Orçamentos"
API_VERSION = "1.0.0"
API_DESCRIPTION = "API para processar e gerar orçamentos de obras"

# AI (OpenAI)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Debug: verificar se chave foi carregada
if OPENAI_API_KEY:
    print(f"✅ OPENAI_API_KEY carregada (primeiros 10 chars): {OPENAI_API_KEY[:10]}...")
else:
    print("⚠️  OPENAI_API_KEY NÃO encontrada no .env")
