# set_key.ps1 - write DEEPSEEK_API_KEY into agent/.env safely (ASCII-only to avoid encoding issues)
# Usage: powershell -ExecutionPolicy Bypass -File set_key.ps1
# Notes: input is hidden (SecureString); terminal shows mask only; agent/.env is gitignored.

$envPath = Join-Path $PSScriptRoot ".env"

$sec = Read-Host "Paste DEEPSEEK_API_KEY (input hidden)" -AsSecureString
$b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
$key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b)

if ([string]::IsNullOrWhiteSpace($key)) { Write-Host "Empty input, exit." -ForegroundColor Yellow; exit 1 }
if ($key -notmatch '^sk-[A-Za-z0-9_\-]{20,}$') {
    Write-Host "Does not look like a key (expect sk- prefix + length >= 20). Nothing written." -ForegroundColor Red
    exit 1
}

$baseInput = Read-Host "BASE_URL (press Enter = official default https://api.deepseek.com)"
$baseUrl = if ([string]::IsNullOrWhiteSpace($baseInput)) { "" } else { $baseInput.TrimEnd('/') }

$lines = @(Get-Content $envPath -ErrorAction SilentlyContinue | Where-Object { $_ -match '\S' })
$foundKey = $false
$foundUrl = $false
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^\s*DEEPSEEK_API_KEY\s*=') { $lines[$i] = "DEEPSEEK_API_KEY=$key"; $foundKey = $true }
    elseif ($baseUrl -and $lines[$i] -match '^\s*DEEPSEEK_BASE_URL\s*=') { $lines[$i] = "DEEPSEEK_BASE_URL=$baseUrl"; $foundUrl = $true }
}
if (-not $foundKey) { $lines += "DEEPSEEK_API_KEY=$key" }
if ($baseUrl -and -not $foundUrl) { $lines += "DEEPSEEK_BASE_URL=$baseUrl" }

Set-Content -Path $envPath -Value $lines -Encoding ascii
Write-Host ""
Write-Host ("OK: written to {0}" -f $envPath) -ForegroundColor Green
Write-Host ("    DEEPSEEK_API_KEY = {0}... ({1} chars, {2})" -f $key.Substring(0, 4), $key.Length, $(if ($foundKey) { "updated" } else { "added" }))
if ($baseUrl) { Write-Host ("    DEEPSEEK_BASE_URL = {0}" -f $baseUrl) }
Write-Host "Plaintext exists only in agent/.env (gitignored). Nothing printed in chat or terminal history."
