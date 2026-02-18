@echo off
REM Script para rodar Frontend + Backend na mesma porta (8000)
REM Windows Batch

echo ============================================================
echo Starting Thora Construction - Unified Server
echo ============================================================

REM Mudar para o diretório do projeto
cd /d "%~dp0"

REM Step 1:Verificar se frontend foi buildado
if not exist "frontend\dist" (
    echo.
    echo [1/3] Building frontend...
    cd frontend
    call npm run build
    cd ..
) else (
    echo [1/3] Frontend já está buildado
)

REM Step 2: Verificar e instalar dependências do backend
echo.
echo [2/3] Preparando backend...
cd backend

REM Verificar se requirements.txt foi instalado
python -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo Instalando dependências...
    python -m pip install -q -r requirements.txt
)

REM Step 3: Rodar backend
echo.
echo [3/3] Iniciando servidor unificado...
echo.
echo ============================================================
echo ✅ Servidor rodando em: http://localhost:8000
echo ============================================================
echo.

python main.py

pause
