#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -x "$ROOT_DIR/venv/bin/python" ]]; then
  echo "[backend] Ambiente virtual não encontrado. Executando setup..."
  bash "$ROOT_DIR/scripts/setup.sh"
fi

export PORT="${PORT:-8001}"

echo "[backend] Iniciando Thora API em http://localhost:${PORT}"
exec "$ROOT_DIR/venv/bin/python" main.py
