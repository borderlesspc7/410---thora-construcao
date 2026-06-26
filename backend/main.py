"""Ponto de entrada da API Thora."""

import os

import uvicorn

from app.main import app

__all__ = ["app"]

if __name__ == "__main__":
    default_port = "8001" if os.getenv("ENVIRONMENT", "development") == "development" else "8000"
    port = int(os.getenv("PORT", default_port))
    reload = os.getenv("ENVIRONMENT", "development") == "development"
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=reload)
