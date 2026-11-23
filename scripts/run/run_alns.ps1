param(
    [int]$Iterations = 5000,
    [double]$TimeLimit = 120,
    [int]$Seed = 42,
    [double]$BalancePenaltyVnd = 0
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
    $python, (Join-Path $root "src\alns_pdvrp_solver.py"),
    "--iterations", "$Iterations",
    "--time-limit", "$TimeLimit",
    "--seed", "$Seed",
    "--balance-penalty-vnd", "$BalancePenaltyVnd"
)
Invoke-Step @($python, (Join-Path $root "src\route_duration_report.py"), "--method", "alns_pdvrp")
Invoke-Step @($python, (Join-Path $root "src\evaluator.py"), "--method", "alns_pdvrp")
Invoke-Step @($python, (Join-Path $root "src\compare_results.py"))
Invoke-Step @($python, (Join-Path $root "src\visualization.py"), "--method", "alns_pdvrp")

Write-Host ""
Write-Host "ALNS pipeline completed."
