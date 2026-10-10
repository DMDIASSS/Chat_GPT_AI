$ErrorActionPreference = 'Stop'
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$folder = Join-Path $base 'data\afk_runs'
if (!(Test-Path $folder)) { throw "No AFK run folder exists yet: $folder" }
# Resume continues an older run directory. Choose the latest UPDATED report,
# not the newest directory name (which could be an unrelated smoke test).
$latest = Get-ChildItem $folder -Directory | Where-Object {
  Test-Path (Join-Path $_.FullName 'STATUS.json')
} | Sort-Object { (Get-Item (Join-Path $_.FullName 'STATUS.json')).LastWriteTimeUtc } -Descending | Select-Object -First 1
if (!$latest) { throw "No AFK runs found under $folder" }
$destination = Join-Path $base 'AFK_UPLOAD_THIS.zip'
$stage = Join-Path $env:TEMP ('afk_reports_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage -Force | Out-Null
try {
  @('STATUS.json','INPUTS.json','PRE_BENCHMARK.json','POST_BENCHMARK.json',
    'SUMMARY.json','AFK_LOG.txt','ERROR_TRACEBACK.txt','TRAIN_PROGRESS.json') | ForEach-Object {
    $path = Join-Path $latest.FullName $_
    if (Test-Path $path) { Copy-Item -LiteralPath $path -Destination $stage }
  }
  if (Test-Path (Join-Path $latest.FullName 'league\reports')) {
    Copy-Item (Join-Path $latest.FullName 'league\reports') -Destination (Join-Path $stage 'league_reports') -Recurse
  }
  if (Test-Path (Join-Path $latest.FullName 'league\history.jsonl')) {
    Copy-Item (Join-Path $latest.FullName 'league\history.jsonl') -Destination $stage
  }
  if (Test-Path $destination) { Remove-Item $destination -Force }
  Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $destination -Force
  Write-Host "READY TO UPLOAD: $destination"
  Write-Host 'This zip includes reports/logs ONLY, not checkpoint weights.'
} finally {
  Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
}
