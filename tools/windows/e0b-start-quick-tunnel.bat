@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "CLOUDFLARED_EXE=D:\Tools\cloudflared.exe"
set "ORIGIN=http://127.0.0.1:8421"

if not exist "%CLOUDFLARED_EXE%" (
  echo [E0-B] cloudflared not found: "%CLOUDFLARED_EXE%"
  exit /b 2
)

curl.exe --fail --silent --show-error "%ORIGIN%/api/v1/health" >nul
if errorlevel 1 (
  echo [E0-B] Desktop Server health check failed: %ORIGIN%/api/v1/health
  echo [E0-B] Start e0b-start-server.bat first.
  exit /b 3
)

echo [E0-B] cloudflared version:
"%CLOUDFLARED_EXE%" --version
echo [E0-B] Starting one-run Quick Tunnel for %ORIGIN%
echo [E0-B] Copy the printed https://*.trycloudflare.com origin into the Laptop connectivity config.
echo [E0-B] Keep this terminal open. Ctrl+C stops the tunnel.
"%CLOUDFLARED_EXE%" tunnel --url "%ORIGIN%"
exit /b %ERRORLEVEL%
