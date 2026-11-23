param(
    [Parameter(Position = 0)]
    [string]$Task = "help",

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$TaskArguments
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

$tasks = [ordered]@{
    "core"                  = "scripts\run\run_core.ps1"
    "alns"                  = "scripts\run\run_alns.ps1"
    "moalns"                = "scripts\run\run_moalns.ps1"
    "benchmark"             = "scripts\experiments\run_multiobjective_benchmark.ps1"
    "conference"            = "scripts\experiments\run_conference_production.ps1"
    "corrected-comparison"  = "scripts\experiments\run_corrected_main_comparison.ps1"
    "remaining-work"        = "scripts\experiments\run_remaining_conference_work.ps1"
    "rerun-incomplete"      = "scripts\experiments\rerun_incomplete_benchmark.ps1"
    "prepare-benchmark"     = "scripts\data\prepare_broader_benchmark.ps1"
    "ablation"              = "scripts\studies\run_moalns_ablation.ps1"
    "time-sensitivity"      = "scripts\studies\run_time_budget_sensitivity.ps1"
    "parameter-sensitivity" = "scripts\studies\run_moalns_parameter_sensitivity.ps1"
    "modm-sensitivity"      = "scripts\studies\run_modm_weight_sensitivity.ps1"
    "objective-conflicts"   = "scripts\reporting\analyze_objective_conflicts.ps1"
    "paper-outputs"         = "scripts\reporting\generate_paper_outputs.ps1"
    "exact-validation"      = "scripts\validation\run_exact_validation.ps1"
    "validate-archives"     = "scripts\validation\validate_all_archives.ps1"
    "test"                  = "scripts\validation\run_validation_tests.ps1"
}

if ($Task -in @("help", "-h", "--help")) {
    Write-Host "PDVRP experiment runner"
    Write-Host ""
    Write-Host "Usage:"
    Write-Host "  .\pdvrp.ps1 <task> [task parameters]"
    Write-Host ""
    Write-Host "Available tasks:"
    foreach ($entry in $tasks.GetEnumerator()) {
        Write-Host ("  {0,-22} {1}" -f $entry.Key, $entry.Value)
    }
    Write-Host ""
    Write-Host "Example:"
    Write-Host "  .\pdvrp.ps1 moalns -Iterations 5000 -TimeLimit 180 -Seed 42"
    exit 0
}

if (-not $tasks.Contains($Task)) {
    throw "Unknown task '$Task'. Run '.\pdvrp.ps1 help' to list available tasks."
}

$scriptPath = Join-Path $root $tasks[$Task]

# Reconstruct named parameters before splatting them into the selected script.
# Direct array splatting would treat strings such as "-AnalyzeOnly" as
# positional values instead of PowerShell parameter names.
$boundParameters = @{}
$positionalArguments = @()
for ($index = 0; $index -lt $TaskArguments.Count; $index++) {
    $token = $TaskArguments[$index]
    if ($token -match '^--?([A-Za-z][A-Za-z0-9-]*)$') {
        $name = $Matches[1]
        $values = @()
        while (($index + 1) -lt $TaskArguments.Count -and
               $TaskArguments[$index + 1] -notmatch '^--?[A-Za-z][A-Za-z0-9-]*$') {
            $index++
            foreach ($value in ($TaskArguments[$index] -split ',')) {
                if ($value -ne "") { $values += $value }
            }
        }
        if ($values.Count -eq 0) {
            $boundParameters[$name] = $true
        } elseif ($values.Count -eq 1) {
            $boundParameters[$name] = $values[0]
        } else {
            $boundParameters[$name] = $values
        }
    } else {
        $positionalArguments += $token
    }
}

& $scriptPath @boundParameters @positionalArguments
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
