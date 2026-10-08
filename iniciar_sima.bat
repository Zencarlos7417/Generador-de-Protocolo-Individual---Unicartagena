@echo off
title SIMA UdeC - Iniciando...
cd /d "C:\Users\User\Downloads\protocolo-app"

echo ============================================
echo  SIMA UdeC - Universidad de Cartagena
echo  Iniciando servidor y tunel publico...
echo ============================================
echo.

REM 1) Servidor Flask (entorno virtual)
start "SIMA UdeC - Servidor" .\venv\Scripts\python.exe app.py
echo [1/3] Servidor Flask iniciado. Esperando 6 segundos...
timeout /t 6 /nobreak >nul

REM 2) Tunel publico de Cloudflare + aviso automatico a WhatsApp
where cloudflared >nul 2>nul
if %errorlevel% neq 0 (
  echo [2/3] AVISO: cloudflared no esta instalado. Instala con: winget install Cloudflare.cloudflared
) else (
  start "SIMA UdeC - Tunel Cloudflare" .\venv\Scripts\python.exe publicar_tunel.py
  echo [2/3] Tunel Cloudflare iniciado. El enlace llega solo a tu WhatsApp.
)

REM 3) Abrir la plataforma en el navegador
timeout /t 4 /nobreak >nul
start http://localhost:5000
echo [3/3] Plataforma abierta en el navegador.
echo.
echo Para APAGAR todo: cierra las ventanas "SIMA UdeC - Servidor" y "SIMA UdeC - Tunel Cloudflare".
echo.
pause
