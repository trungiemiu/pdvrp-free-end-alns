param(
    [string]$Manifest = "data/instances_manifest.csv",
    [string]$ExperimentsRoot = "outputs/experiments",
    [string]$OutputDir = "outputs/validation/independent_archive_check"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $root "scripts\common\moalns_study_common.ps1")
$python = Get-StudyPython $root
Invoke-StudyStep @(
    $python, (Join-Path $root "src\validate_experiment_archives.py"),
    "--manifest", (Join-Path $root $Manifest),
    "--experiments-root", (Join-Path $root $ExperimentsRoot),
    "--output-dir", (Join-Path $root $OutputDir),
    "--fail-on-error"
)
