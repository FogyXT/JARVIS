Set-Location D:\JARVIS

$envPath = Join-Path (Get-Location) ".env"
if (Test-Path $envPath) {
    $envContent = Get-Content $envPath -Raw
    if ($envContent -match 'ANTHROPIC_API_KEY=(.+)') {
        $env:ANTHROPIC_API_KEY = $matches[1].Trim()
    }
} else {
    Write-Host "⚠️  .env subor nebol najdeny v D:\JARVIS" -ForegroundColor Yellow
}

Remove-Item Env:ANTHROPIC_BASE_URL   -ErrorAction SilentlyContinue
Remove-Item Env:ANTHROPIC_AUTH_TOKEN -ErrorAction SilentlyContinue

$env:CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Claude Code - Anthropic default"       -ForegroundColor Cyan
Write-Host "  Effort: medium"                           -ForegroundColor Cyan
Write-Host "  Projekt: D:\JARVIS"                    -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Pre ukoncenie napis /exit" -ForegroundColor Yellow
Write-Host ""

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