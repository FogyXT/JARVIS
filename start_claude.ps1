@echo off
title Claude Code - DeepSeek V4 Pro
cd /d D:\JARVIS

:: Nacitaj DeepSeek API kluc z .env
if exist .env (
    for /f "tokens=2 delims==" %%a in ('findstr /b "DEEPSEEK_API_KEY" .env') do set "ANTHROPIC_AUTH_TOKEN=%%a"
)

:: DeepSeek endpoint a modely
set ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
set ANTHROPIC_MODEL=deepseek-v4-pro[1m]
set ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-v4-pro[1m]
set ANTHROPIC_DEFAULT_SONNET_MODEL=deepseek-v4-pro[1m]
set ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-v4-flash
set CLAUDE_CODE_SUBAGENT_MODEL=deepseek-v4-flash
set CLAUDE_CODE_EFFORT_LEVEL=max

echo ========================================
echo   Claude Code - DeepSeek V4 Pro [1M]
echo   Subagent: deepseek-v4-flash
echo   Projekt: D:\JARVIS
echo ========================================
echo.

claude %*
pause