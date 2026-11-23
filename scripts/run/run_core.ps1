param(
    [switch]$SkipMaps,
    [switch]$ContinueOnError
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $root "scripts\common\moalns_study_common.ps1")
$python = Get-StudyPython $root

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Command
    )

    Write-Host ""
    Write-Host ("> " + ($Command -join " "))

    & $Command[0] @($Command[1..($Command.Length - 1)])
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        $message = "Command failed with exit code ${exitCode}: $($Command -join ' ')"

        if ($ContinueOnError) {
            Write-Warning $message
            return
        }

        throw $message
    }
}

Invoke-Step @($python, (Join-Path $root "src\baseline_solver.py"))
Invoke-Step @($python, (Join-Path $root "src\improved_baseline_solver.py"))
Invoke-Step @($python, (Join-Path $root "src\balanced_improved_solver.py"))
Invoke-Step @($python, (Join-Path $root "src\route_duration_report.py"), "--skip-if-missing")
Invoke-Step @($python, (Join-Path $root "src\evaluate_all_outputs.py"), "--continue-on-error")
Invoke-Step @($python, (Join-Path $root "src\compare_results.py"))

if (-not $SkipMaps) {
    Invoke-Step @($python, (Join-Path $root "src\visualization.py"), "--method", "baseline")
    Invoke-Step @($python, (Join-Path $root "src\visualization.py"), "--method", "improved_baseline")
    Invoke-Step @($python, (Join-Path $root "src\visualization.py"), "--method", "balanced_improved")
}
