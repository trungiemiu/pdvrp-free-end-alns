param(
    [double]$TimePerMethod = 600,
    [int]$Iterations = 5000,
    [int]$PopulationSize = 50,
    [int]$EpsilonLevels = 5,
    [bool]$RepairOutliers = $true,
    [bool]$CompleteLrc = $true
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $root "scripts\common\moalns_study_common.ps1")
$python = Get-StudyPython $root
$experiments = Join-Path $root "outputs\experiments"

function Invoke-Step {
    param([Parameter(Mandatory = $true)][string[]]$Command)
    Write-Host ""
    Write-Host ("> " + ($Command -join " "))
    & $Command[0] @($Command[1..($Command.Length - 1)])
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $($Command -join ' ')"
    }
}

function Invoke-Moalns {
    param([string]$InstanceId, [string]$DataDir, [int]$Seed, [string]$OutputDir)
    Invoke-Step @(
        $python, (Join-Path $root "src\moalns_pdvrp_solver.py"),
        "--data-dir", $DataDir, "--output-dir", $OutputDir,
        "--instance-id", $InstanceId, "--iterations", "$Iterations",
        "--time-limit", "$TimePerMethod", "--seed", "$Seed"
    )
}

function Invoke-Baseline {
    param([string]$Algorithm, [string]$InstanceId, [string]$DataDir,
          [int]$Seed, [string]$OutputDir)
    Invoke-Step @(
        $python, (Join-Path $root "src\multiobjective_baselines.py"),
        "--algorithm", $Algorithm, "--data-dir", $DataDir,
        "--output-dir", $OutputDir, "--instance-id", $InstanceId,
        "--time-limit", "$TimePerMethod", "--seed", "$Seed",
        "--population-size", "$PopulationSize", "--epsilon-levels", "$EpsilonLevels"
    )
}

function Test-CompletedRun {
    param([string]$Algorithm, [string]$OutputDir)
    $archive = Join-Path $OutputDir ($Algorithm + "_pareto_archive.csv")
    $report = Join-Path $OutputDir ($Algorithm + "_solver_report.csv")
    if (-not ((Test-Path $archive) -and (Test-Path $report))) { return $false }
    $row = Import-Csv $report | Select-Object -First 1
    $runtime = [double]$row.runtime_seconds
    return ($runtime -ge 0.90 * $TimePerMethod -and $runtime -le 1.20 * $TimePerMethod)
}

function Update-Quality {
    param([string]$InstanceId, [int]$Seed, [string]$OutputDir)
    $complete = @("moalns", "nsga2", "moead", "epsilon") | ForEach-Object {
        Test-Path (Join-Path $OutputDir ($_ + "_pareto_archive.csv"))
    }
    if ($complete -notcontains $false) {
        Invoke-Step @(
            $python, (Join-Path $root "src\multiobjective_quality.py"),
            "--experiment-dir", $OutputDir, "--instance-id", $InstanceId,
            "--seed", "$Seed"
        )
    }
}

if ($RepairOutliers) {
    $instanceId = "lc101_notw_subset12"
    $dataDir = Join-Path $root "data\instances\lc101_notw_subset12"

    # MOALNS seed 46 previously ran 5,476 s and returned only one solution.
    $outputDir = Join-Path $experiments "$instanceId\seed_46"
    if (-not (Test-CompletedRun "moalns" $outputDir)) {
        Invoke-Moalns $instanceId $dataDir 46 $outputDir
    }
    Update-Quality $instanceId 46 $outputDir

    # Epsilon seed 45 previously ran 11,300 s.
    $outputDir = Join-Path $experiments "$instanceId\seed_45"
    if (-not (Test-CompletedRun "epsilon" $outputDir)) {
        Invoke-Baseline "epsilon" $instanceId $dataDir 45 $outputDir
    }
    Update-Quality $instanceId 45 $outputDir
}

if ($CompleteLrc) {
    $instanceId = "lrc101_notw_subset12"
    $dataDir = Join-Path $root "data\instances\lrc101_notw_subset12"

    # Seed 42 has 600-s results for three algorithms, but epsilon is still 30 s.
    $outputDir = Join-Path $experiments "$instanceId\seed_42"
    if (-not (Test-CompletedRun "epsilon" $outputDir)) {
        Invoke-Baseline "epsilon" $instanceId $dataDir 42 $outputDir
    }
    Update-Quality $instanceId 42 $outputDir

    foreach ($seed in 43..51) {
        $outputDir = Join-Path $experiments "$instanceId\seed_$seed"
        New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
        if (-not (Test-CompletedRun "moalns" $outputDir)) {
            Invoke-Moalns $instanceId $dataDir $seed $outputDir
        }
        foreach ($algorithm in @("nsga2", "moead", "epsilon")) {
            if (-not (Test-CompletedRun $algorithm $outputDir)) {
                Invoke-Baseline $algorithm $instanceId $dataDir $seed $outputDir
            }
        }
        Update-Quality $instanceId $seed $outputDir
    }
}

Invoke-Step @(
    $python, (Join-Path $root "src\aggregate_multiobjective_quality.py"),
    "--manifest", (Join-Path $root "data\instances_manifest.csv"),
    "--experiments-root", $experiments,
    "--output", (Join-Path $experiments "benchmark_summary.csv")
)

Write-Host ""
Write-Host "Targeted rerun and fixed-reference aggregation completed."
