$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$root = $PSScriptRoot
if (-not (Test-Path (Join-Path $root 'train.py'))) {
  throw 'This is an ADD-ON: extract ALL files into your EXISTING Chat_GPT_AI folder (same place as train.py), then run again.'
}
if (-not (Test-Path (Join-Path $root '.venv\Scripts\python.exe'))) {
  throw 'Existing Python environment not found. Do not overwrite your old project with a new extraction folder.'
}
$files = @('config.py', 'curriculum_config.py', 'env.py', 'grounded_rewards.py')
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss_ffff'
$backup = Join-Path $root ('backups\before_fast_track_' + $stamp)
New-Item -ItemType Directory -Force $backup | Out-Null
foreach ($name in $files) {
  $src = Join-Path $root ("patch\chatgpt_ai\" + $name)
  $dest = Join-Path $root ("chatgpt_ai\" + $name)
  if (-not (Test-Path $src)) { throw "Missing patch source $src" }
  if (Test-Path $dest) { Copy-Item -LiteralPath $dest -Destination (Join-Path $backup $name) -ErrorAction Stop }
  Copy-Item -LiteralPath $src -Destination $dest -Force -ErrorAction Stop
  Write-Host "Patched $name" -ForegroundColor Green
}
Write-Host "Source backups: $backup"
Write-Host 'Existing checkpoint folders, datasets and .venv were NOT changed.' -ForegroundColor Green
Write-Host 'Next: FAST_TRACK_DOCTOR.bat' -ForegroundColor Yellow
