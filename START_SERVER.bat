@echo off
title OPTIGLASSWEAR AI Server ^& Tunnel Launcher
echo =======================================================
echo     OPTIGLASSWEAR - Smart Wearable Glasses Console
echo =======================================================
echo.

cd /d "%~dp0"

echo [*] Starting Python AI Server on port 8080...
start "OPTIGLASSWEAR Python Engine" cmd /k "python webserver.py"

timeout /t 3 /nobreak >nul

echo [*] Starting Cloudflare Public Tunnel...
del /q cf_tunnel_live.log 2>nul
start "OPTIGLASSWEAR Cloudflare Tunnel" cmd /k "cloudflared.exe tunnel --url http://127.0.0.1:8080 --logfile cf_tunnel_live.log"

echo [*] Waiting for public link generation...
timeout /t 5 /nobreak >nul

echo.
echo =======================================================
echo   Server is running! Access Options:
echo   1. Local Network (Same Wi-Fi): http://10.119.226.1:8080/
echo   2. Public Internet Link: Check cf_tunnel_live.log or the Tunnel window!
echo =======================================================
pause
