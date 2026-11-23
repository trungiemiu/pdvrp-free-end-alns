$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $root "scripts\common\moalns_study_common.ps1")
$python = Get-StudyPython $root

& $python (Join-Path $root "src\generate_paper_results.py")
if ($LASTEXITCODE -ne 0) {
    throw "Paper-output generation failed with exit code $LASTEXITCODE"
}

Write-Host ""
Write-Host "Paper tables and figures are ready under outputs\paper."
