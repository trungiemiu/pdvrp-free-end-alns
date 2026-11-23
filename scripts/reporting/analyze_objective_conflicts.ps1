param(
    [string]$ExperimentsRoot = "outputs/experiments",
    [string]$OutputDir = "outputs/paper/objective_conflict"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $root "scripts\common\moalns_study_common.ps1")
$python = Get-StudyPython $root
$experiments = if ([System.IO.Path]::IsPathRooted($ExperimentsRoot)) { $ExperimentsRoot } else { Join-Path $root $ExperimentsRoot }
$output = if ([System.IO.Path]::IsPathRooted($OutputDir)) { $OutputDir } else { Join-Path $root $OutputDir }
Invoke-StudyStep @(
    $python, (Join-Path $root "src\objective_conflict_analysis.py"),
    "--experiments-root", $experiments,
    "--output-dir", $output
)
