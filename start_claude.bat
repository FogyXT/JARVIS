@echo off
title Claude Code - DeepSeek V4 Flash
cd /d D:\JARVIS

:: Nacitaj DeepSeek API kluc z .env ak existuje
if exist .env (
    for /f "tokens=2 delims==" %%a in ('findstr /b "DEEPSEEK_API_KEY" .env') do set "DEEPSEEK_API_KEY=%%a"
)

echo ========================================
echo   Claude Code s DeepSeek V4 Flash
echo   Model:  deepseek-v4-flash (nie Pro)
echo   Projekt: D:\JARVIS
echo ========================================
echo.
echo - /exit pre ukoncenie
echo.
claude --model deepseek-v4-flash %*
echo.
pause
