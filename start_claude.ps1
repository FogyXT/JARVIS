# Spustí Claude Code s DeepSeek V4 Pro v D:\JARVIS
Set-Location D:\JARVIS

# Načítaj DeepSeek API kľúč z .env
$envPath = Join-Path (Get-Location) ".env"
if (Test-Path $envPath) {
    $envContent = Get-Content $envPath -Raw
    if ($envContent -match 'DEEPSEEK_API_KEY=(.+)') {
        $env:ANTHROPIC_AUTH_TOKEN = $matches[1].Trim()
    }
} else {
    Write-Host "⚠️  .env subor nebol najdeny v D:\JARVIS" -ForegroundColor Yellow
}

# Nastav DeepSeek endpoint a modely
$env:ANTHROPIC_BASE_URL                  = "https://api.deepseek.com/anthropic"
$env:ANTHROPIC_MODEL                     = "deepseek-v4-pro[1m]"
$env:ANTHROPIC_DEFAULT_OPUS_MODEL        = "deepseek-v4-pro[1m]"
$env:ANTHROPIC_DEFAULT_SONNET_MODEL      = "deepseek-v4-pro[1m]"
$env:ANTHROPIC_DEFAULT_HAIKU_MODEL       = "deepseek-v4-flash"
$env:CLAUDE_CODE_SUBAGENT_MODEL          = "deepseek-v4-flash"
$env:CLAUDE_CODE_EFFORT_LEVEL            = "max"
$env:CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Claude Code - DeepSeek V4 Pro [1M]"    -ForegroundColor Cyan
Write-Host "  Subagent: deepseek-v4-flash"            -ForegroundColor Cyan
Write-Host "  Effort: max"                            -ForegroundColor Cyan
Write-Host "  Projekt: D:\JARVIS"                     -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Pre ukoncenie napis /exit" -ForegroundColor Yellow
Write-Host ""

# Spustenie Claude Code
try {
    & claude @args
    if ($LASTEXITCODE -ne 0) { throw "nenulovy exit kod" }
} catch {
    Write-Host "claude nie je v PATH, skusam npx..." -ForegroundColor Yellow
    try {
        & npx claude @args
    } catch {
        Write-Host "❌ Nepodarilo sa spustit Claude Code." -ForegroundColor Red
        Write-Host "Skus: npm install -g @anthropic-ai/claude-code" -ForegroundColor Yellow
        Read-Host "Stlac Enter pre zavretie"
    }
}