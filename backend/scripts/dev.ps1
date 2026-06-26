# Inicia o backend Thora na porta 8001 (Windows)
$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RootDir

$env:PORT = if ($env:PORT) { $env:PORT } else { "8001" }
$env:ENVIRONMENT = if ($env:ENVIRONMENT) { $env:ENVIRONMENT } else { "development" }

Write-Host "[backend] Thora API em http://localhost:$($env:PORT)"
python main.py
