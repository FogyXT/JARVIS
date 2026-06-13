@echo off
title Restart Claude Code
cd /d D:\JARVIS

:: Nacitaj DeepSeek API kluc z .env
if exist .env (
    for /f "tokens=2 delims==" %%a in ('findstr /b "DEEPSEEK_API_KEY" .env') do set "DEEPSEEK_API_KEY=%%a"
)

echo ========================================
echo   RESTART Claude Code - DeepSeek V4 Flash
echo ========================================
echo.

:: Kill running Python processes (web UI, jarvis)
echo [1/3] Ukoncujem Python procesy...
taskkill /f /im python.exe /t 2>nul
timeout /t 2 /nobreak >nul

:: Kill stale Claude Code processes
echo [2/3] Ukoncujem stare Claude Code procesy...
taskkill /f /im node.exe /fi "WindowTitle eq Claude*" 2>nul
timeout /t 1 /nobreak >nul

:: Start fresh
echo [3/3] Otvaram nove okno Claude Code s DeepSeek V4 Flash...
echo.
start "" cmd /k "title Claude Code - DeepSeek V4 Flash && cd /d D:\JARVIS && color 0a && echo Vitaj spat, Fogy! && echo Model: deepseek-v4-flash && echo. && claude --model deepseek-v4-flash"

echo.
echo ✅ Hotovo - nove okno by malo byt otvorene.
pause
