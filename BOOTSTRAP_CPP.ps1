# Run from PowerShell with: powershell -ExecutionPolicy Bypass -File .\BOOTSTRAP_CPP.ps1
$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {throw 'Install Git for Windows first: https://git-scm.com/downloads/win'}
if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) {Write-Warning 'CMake not in PATH. Install Visual Studio 2022/2026 with Desktop development with C++ and CMake.'}
$dest=Join-Path $PSScriptRoot 'cpp_backend\RLGymPPO_CPP'
if (Test-Path (Join-Path $dest '.git')) {
 Write-Host "Existing C++ repo found at $dest; leaving it unchanged."
} else {
 New-Item -ItemType Directory -Force (Split-Path $dest) | Out-Null
 git clone --recurse-submodules https://github.com/ZealanL/RLGymPPO_CPP.git $dest
 if ($LASTEXITCODE -ne 0) {throw 'Git clone failed. Check network and Git.'}
}
Write-Host '\nCloned source, but NOT built. Requirements from upstream:'
Write-Host '  1. Visual Studio with C++ Desktop workload'
Write-Host '  2. CUDA 11.8 toolkit matching NVIDIA driver (if GPU enabled)'
Write-Host '  3. CUDA 11.8 LibTorch folder within RLGymPPO_CPP/RLGymPPO_CPP/'
Write-Host '  4. CMake RelWithDebInfo build + collision_meshes beside executable'
Write-Host 'CAUTION: This is a separate trainer. It does not automatically load our Python student.'
Write-Host 'Checkpoint conversion requires identical observation/action implementation in C++.'
Write-Host 'Read docs/CPP_MIGRATION.md before running multi-million-step training.'
