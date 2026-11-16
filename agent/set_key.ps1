# set_key.ps1 — 安全写入 DEEPSEEK_API_KEY 到 agent/.env
# 用法：右键「使用 PowerShell 运行」，或在 PowerShell 里执行  .\set_key.ps1
# 特性：输入不回显、不进剪贴板历史、终端只显示掩码；.env 已被 agent/.gitignore 排除，不会误提交。

$envPath = Join-Path $PSScriptRoot ".env"

$sec = Read-Host "粘贴 DEEPSEEK_API_KEY（输入不回显）" -AsSecureString
$b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
$key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b)

if ([string]::IsNullOrWhiteSpace($key)) { Write-Host "未输入，退出。" -ForegroundColor Yellow; exit 1 }
if ($key -notmatch '^sk-[A-Za-z0-9_\-]{20,}$') {
    Write-Host "格式不像 key（应以 sk- 开头、长度足够），未写入。检查后重跑。" -ForegroundColor Red
    exit 1
}

$baseInput = Read-Host "BASE_URL（回车 = 官方默认 https://api.deepseek.com）"
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

Set-Content -Path $envPath -Value $lines -Encoding utf8
Write-Host ""
Write-Host ("OK：已写入 {0}" -f $envPath) -ForegroundColor Green
Write-Host ("    DEEPSEEK_API_KEY = {0}...（共 {1} 位，{2}）" -f $key.Substring(0, 4), $key.Length, $(if ($foundKey) { "已更新" } else { "新增" }))
if ($baseUrl) { Write-Host ("    DEEPSEEK_BASE_URL = {0}" -f $baseUrl) }
Write-Host "明文只存在于 agent/.env（已被 gitignore），聊天记录与终端均未落明文。"
