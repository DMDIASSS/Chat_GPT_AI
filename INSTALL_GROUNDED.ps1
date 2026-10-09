$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$files = @('config.py', 'curriculum_config.py', 'env.py', 'grounded_rewards.py')
$dest = Join-Path $root 'chatgpt_ai'
if (!(Test-Path (Join-Path $root 'train.py'))) { throw 'Extract the addon into the project folder alongside train.py first.' }
if (!(Test-Path $dest)) { throw 'chatgpt_ai folder missing.' }
$backup = Join-Path $root ("backup_before_grounded_" + (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $backup | Out-Null
foreach ($name in $files) {
    $from = Join-Path $root "patch\chatgpt_ai\$name"
    $to = Join-Path $dest $name
    if (!(Test-Path $from)) { throw "Patch file missing: $from" }
    if (Test-Path $to) { Copy-Item $to (Join-Path $backup $name) }
    Copy-Item $from $to -Force
    Write-Host "Installed: $name"
}
Write-Host "Your prior source files are backed up at: $backup"
Write-Host "Installed 'grounded' preset. Existing checkpoints are unchanged."
