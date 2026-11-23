param(
    [int]$Iterations = 5000,
    [double]$TimeLimit = 180,
    [int]$Seed = 42,
    [double]$CostWeight = 0.50,
    [double]$DurationWeight = 0.30,
    [double]$ImbalanceWeight = 0.20,
    [string]$PreferenceData = ""
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $root "scripts\common\moalns_study_common.ps1")
$python = Get-StudyPython $root

function Invoke-Step {
    param([Parameter(Mandatory = $true)][string[]]$Command)
    Write-Host ""
    Write-Host ("> " + ($Command -join " "))
    & $Command[0] @($Command[1..($Command.Length - 1)])
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $($Command -join ' ')"
    }
}

Invoke-Step @(
    $python, (Join-Path $root "src\moalns_pdvrp_solver.py"),
    "--iterations", "$Iterations",
    "--time-limit", "$TimeLimit",
    "--seed", "$Seed"
)

$decisionCommand = @(
    $python, (Join-Path $root "src\modm_decision.py"),
    "--cost-weight", "$CostWeight",
    "--duration-weight", "$DurationWeight",
    "--imbalance-weight", "$ImbalanceWeight",
    "--seed", "$Seed"
)
if ($PreferenceData -ne "") {
    $decisionCommand += @("--preference-data", $PreferenceData)
}
Invoke-Step $decisionCommand

$methods = @(
    "moalns_weighted_sum", "moalns_topsis", "moalns_vikor",
    "moalns_promethee_ii", "moalns_waspas", "moalns_borda"
)
if ($PreferenceData -ne "") {
    $methods += @("moalns_ridge_ml", "moalns_mlp_dl")
}

foreach ($method in $methods) {
    Invoke-Step @($python, (Join-Path $root "src\route_duration_report.py"), "--method", $method)
    Invoke-Step @($python, (Join-Path $root "src\evaluator.py"), "--method", $method)
}
Invoke-Step @($python, (Join-Path $root "src\compare_results.py"))
Invoke-Step @($python, (Join-Path $root "src\visualization.py"), "--method", "moalns_borda")
Invoke-Step @($python, (Join-Path $root "src\pareto_visualization.py"))

Write-Host ""
Write-Host "MOALNS + MODM pipeline completed."
