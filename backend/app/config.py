import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

IS_VERCEL = os.getenv("VERCEL", "").strip().lower() in {"1", "true", "yes", "on"}
IS_RENDER = (
    os.getenv("RENDER", "").strip().lower() in {"1", "true", "yes", "on"}
    or bool(os.getenv("RENDER_SERVICE_NAME") or os.getenv("RENDER_SERVICE_ID"))
)

if not IS_VERCEL and not IS_RENDER:
    load_dotenv(BASE_DIR.parent / ".env")
    load_dotenv(BASE_DIR / ".env")
    load_dotenv()

RUNTIME_BASE_DIR = Path("/tmp/thora") if (IS_VERCEL or IS_RENDER) else BASE_DIR / "data"
UPLOAD_DIR = RUNTIME_BASE_DIR / "uploads"
CACHE_DIR = RUNTIME_BASE_DIR / "cache"

for folder in (UPLOAD_DIR, CACHE_DIR):
    folder.mkdir(parents=True, exist_ok=True)

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DEBUG = ENVIRONMENT == "development"

_default_max_file_size = 8 * 1024 * 1024 if IS_VERCEL else 50 * 1024 * 1024
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", _default_max_file_size))

EXTRA_FRONTEND_URLS = [
    url.strip() for url in os.getenv("FRONTEND_URLS", "").split(",") if url.strip()
]

FRONTEND_URLS = [
    url
    for url in [
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
        "https://borderless-410-thora.netlify.app",
        os.getenv("FRONTEND_URL", ""),
        *EXTRA_FRONTEND_URLS,
    ]
    if url
]

CORS_ORIGIN_REGEX = os.getenv("CORS_ORIGIN_REGEX", r"https://[\w-]+\.netlify\.app")

API_TITLE = "Thora Construção API"
API_VERSION = "2.0.0"
API_DESCRIPTION = "API para leitura de PDFs e orçamentos de obras"

_default_detect_pages = "30" if (IS_RENDER or IS_VERCEL) else "60"
DETECT_TABLES_MAX_PAGES = int(os.getenv("DETECT_TABLES_MAX_PAGES", _default_detect_pages))
DETECT_TABLES_MAX_CANDIDATES = int(os.getenv("DETECT_TABLES_MAX_CANDIDATES", "40"))
DETECT_TABLES_THUMB_SCALE = float(os.getenv("DETECT_TABLES_THUMB_SCALE", "2.0"))
DETECT_TABLES_CACHE_VERSION = int(os.getenv("DETECT_TABLES_CACHE_VERSION", "7"))

# Prévia de tabelas: largura alvo em pixels (maior = zoom nítido no frontend)
TABLE_PREVIEW_TARGET_WIDTH_PX = int(os.getenv("TABLE_PREVIEW_TARGET_WIDTH_PX", "3200"))
TABLE_PREVIEW_MIN_SCALE = float(os.getenv("TABLE_PREVIEW_MIN_SCALE", "2.5"))
TABLE_PREVIEW_MAX_SCALE = float(os.getenv("TABLE_PREVIEW_MAX_SCALE", "6.0"))
TABLE_PREVIEW_PAGE_SCALE = float(os.getenv("TABLE_PREVIEW_PAGE_SCALE", "2.5"))

_default_disable_camelot = "true" if (IS_RENDER or IS_VERCEL) else "false"
DISABLE_CAMELOT = os.getenv("DISABLE_CAMELOT", _default_disable_camelot).lower() in {
    "1",
    "true",
    "yes",
    "on",
}

FIREBASE_DISABLED = os.getenv("FIREBASE_DISABLED", "").lower() in {"1", "true", "yes", "on"}
FIREBASE_CREDENTIALS = os.getenv("FIREBASE_CREDENTIALS", "")
