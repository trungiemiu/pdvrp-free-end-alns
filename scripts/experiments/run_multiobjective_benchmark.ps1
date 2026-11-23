param(
    [string]$Manifest = "data/instances_manifest.csv",
    [int[]]$Seeds = @(42),
    [double]$TimePerMethod = 180,
    [int]$Iterations = 5000,
    [int]$PopulationSize = 15,
    [int]$EpsilonLevels = 3
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $root "scripts\common\moalns_study_common.ps1")
$python = Get-StudyPython $root
$manifestPath = if ([System.IO.Path]::IsPathRooted($Manifest)) { $Manifest } else { Join-Path $root $Manifest }
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Manifest not found: $manifestPath"
}

function Invoke-Step {
    param([Parameter(Mandatory = $true)][string[]]$Command)
    Write-Host ""
    Write-Host ("> " + ($Command -join " "))
    & $Command[0] @($Command[1..($Command.Length - 1)])
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $($Command -join ' ')"
    }
}

$required = @("orders.csv", "drivers.csv", "vehicle_parameters.csv", "distance_matrix.csv")
$allMetrics = @()
foreach ($instance in Import-Csv $manifestPath) {
    $dataDir = Join-Path $root $instance.data_dir
    foreach ($file in $required) {
        if (-not (Test-Path -LiteralPath (Join-Path $dataDir $file))) {
            throw "Instance $($instance.instance_id) is missing $file"
        }
    }
    if (-not ((Test-Path (Join-Path $dataDir "duration_matrix_osrm_seconds.csv")) -or
              (Test-Path (Join-Path $dataDir "duration_matrix.csv")))) {
        throw "Instance $($instance.instance_id) has no duration matrix."
    }

    foreach ($seed in $Seeds) {
        $outputDir = Join-Path $root ("outputs/experiments/{0}/seed_{1}" -f $instance.instance_id, $seed)
        New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
        Invoke-Step @(
            $python, (Join-Path $root "src\moalns_pdvrp_solver.py"), "--data-dir", $dataDir,
            "--output-dir", $outputDir, "--instance-id", $instance.instance_id,
            "--iterations", "$Iterations", "--time-limit", "$TimePerMethod", "--seed", "$seed"
        )
        foreach ($algorithm in @("nsga2", "moead", "epsilon")) {
            Invoke-Step @(
                $python, (Join-Path $root "src\multiobjective_baselines.py"), "--algorithm", $algorithm,
                "--data-dir", $dataDir, "--output-dir", $outputDir,
                "--instance-id", $instance.instance_id, "--time-limit", "$TimePerMethod",
                "--seed", "$seed", "--population-size", "$PopulationSize",
                "--epsilon-levels", "$EpsilonLevels"
            )
        }
        Invoke-Step @(
            $python, (Join-Path $root "src\multiobjective_quality.py"), "--experiment-dir", $outputDir,
            "--instance-id", $instance.instance_id, "--seed", "$seed"
        )
        $allMetrics += Import-Csv (Join-Path $outputDir "quality_metrics.csv")
    }
}

$summaryPath = Join-Path $root "outputs/experiments/benchmark_summary.csv"
Invoke-Step @(
    $python, (Join-Path $root "src\aggregate_multiobjective_quality.py"), "--manifest", $manifestPath,
    "--experiments-root", (Join-Path $root "outputs/experiments"), "--output", $summaryPath
)
Write-Host ""
Write-Host "Benchmark completed: $summaryPath"
