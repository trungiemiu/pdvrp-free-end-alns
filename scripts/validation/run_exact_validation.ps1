param(
    [int[]]$Sizes = @(4,6,8,10),
    [int[]]$Seeds = @(42,43,44),
    [double]$HeuristicTime = 60,
    [int]$MilpTime = 600,
    [int]$Iterations = 5000,
    [string]$InstancePattern = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $root "scripts\common\moalns_study_common.ps1")
$python = Get-StudyPython $root
$sizeText = ($Sizes -join ",")
Invoke-StudyStep @(
    $python, (Join-Path $root "src\generate_exact_validation_instances.py"),
    "--source-manifest", (Join-Path $root "data\instances_manifest.csv"),
    "--output-root", (Join-Path $root "data\exact_validation"),
    "--sizes", $sizeText,
    "--exclude", "current"
)
$command = @(
    $python, (Join-Path $root "src\run_exact_validation_suite.py"),
    "--manifest", (Join-Path $root "data\exact_validation\manifest.csv"),
    "--output-root", (Join-Path $root "outputs\validation\exact_suite"),
    "--seeds", ($Seeds -join ","),
    "--heuristic-time", "$HeuristicTime",
    "--milp-time", "$MilpTime",
    "--iterations", "$Iterations"
)
if ($InstancePattern -ne "") { $command += @("--instance-pattern", $InstancePattern) }
if ($Force) { $command += "--force" }
Invoke-StudyStep $command
