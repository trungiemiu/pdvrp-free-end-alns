param(
    [string]$Archive = "outputs/reports/moalns_pareto_archive.csv",
    [double]$GridStep = 0.10,
    [double]$VikorV = 0.50,
    [string[]]$Methods = @("topsis", "promethee_ii"),
    [string]$OutputDir = "outputs/studies/modm_weight_sensitivity"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $root "scripts\common\moalns_study_common.ps1")
$python = Get-StudyPython $root
$archivePath = if ([System.IO.Path]::IsPathRooted($Archive)) { $Archive } else { Join-Path $root $Archive }
$outputPath = if ([System.IO.Path]::IsPathRooted($OutputDir)) { $OutputDir } else { Join-Path $root $OutputDir }
if (-not (Test-Path -LiteralPath $archivePath)) { throw "Pareto archive not found: $archivePath" }

Invoke-StudyStep @(
    $python, (Join-Path $root "src\modm_weight_sensitivity.py"),
    "--archive", $archivePath,
    "--output-dir", $outputPath,
    "--grid-step", "$GridStep",
    "--vikor-v", "$VikorV"
    "--methods", ($Methods -join ",")
)

Write-Host "MODM weight sensitivity completed: $outputPath"
