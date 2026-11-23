param(
    [string]$Manifest = "data/instances_manifest.csv",
    [int[]]$Seeds = @(42,43,44,45,46,47,48,49,50,51),
    [double]$TimePerMethod = 600,
    [int]$Iterations = 5000,
    [int]$PopulationSize = 50,
    [int]$EpsilonLevels = 5,
    [string]$OutputRoot = "outputs/conference_experiments",
    [string]$PaperOutputRoot = "outputs/conference_paper",
    [switch]$Force,
    [switch]$AnalyzeOnly
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $root "scripts\common\moalns_study_common.ps1")
$python = Get-StudyPython $root
$manifestPath = Join-Path $root $Manifest
$experimentRoot = Join-Path $root $OutputRoot

function Test-ConferenceRun {
    param([string]$Algorithm, [string]$Directory)
    return ((Test-Path (Join-Path $Directory ($Algorithm + "_pareto_archive.csv"))) -and
            (Test-Path (Join-Path $Directory ($Algorithm + "_solver_report.csv"))))
}

if (-not $AnalyzeOnly) {
    foreach ($instance in Import-Csv $manifestPath) {
        $dataDir = Join-Path $root $instance.data_dir
        foreach ($seed in $Seeds) {
            $outputDir = Join-Path $experimentRoot "$($instance.instance_id)\seed_$seed"
            New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
            if ($Force -or -not (Test-ConferenceRun "moalns" $outputDir)) {
                Invoke-StudyStep @(
                    $python, (Join-Path $root "src\moalns_pdvrp_solver.py"),
                    "--data-dir", $dataDir, "--output-dir", $outputDir,
                    "--instance-id", $instance.instance_id, "--variant-id", "conference_tail",
                    "--iterations", "$Iterations", "--time-limit", "$TimePerMethod", "--seed", "$seed"
                )
            } else { Write-Host "SKIP moalns / $($instance.instance_id) / $seed" }
            foreach ($algorithm in @("nsga2", "moead", "epsilon")) {
                if ($Force -or -not (Test-ConferenceRun $algorithm $outputDir)) {
                    Invoke-StudyStep @(
                        $python, (Join-Path $root "src\multiobjective_baselines.py"),
                        "--algorithm", $algorithm, "--data-dir", $dataDir,
                        "--output-dir", $outputDir, "--instance-id", $instance.instance_id,
                        "--time-limit", "$TimePerMethod", "--seed", "$seed",
                        "--population-size", "$PopulationSize", "--epsilon-levels", "$EpsilonLevels"
                    )
                } else { Write-Host "SKIP $algorithm / $($instance.instance_id) / $seed" }
            }
            Invoke-StudyStep @(
                $python, (Join-Path $root "src\multiobjective_quality.py"),
                "--experiment-dir", $outputDir, "--instance-id", $instance.instance_id,
                "--seed", "$seed"
            )
        }
    }
}

Invoke-StudyStep @(
    $python, (Join-Path $root "src\aggregate_multiobjective_quality.py"),
    "--manifest", $manifestPath, "--experiments-root", $experimentRoot,
    "--output", (Join-Path $experimentRoot "benchmark_summary.csv")
)
Invoke-StudyStep @(
    $python, (Join-Path $root "src\validate_experiment_archives.py"),
    "--manifest", $manifestPath, "--experiments-root", $experimentRoot,
    "--output-dir", (Join-Path $experimentRoot "independent_validation"), "--fail-on-error"
)
Invoke-StudyStep @(
    $python, (Join-Path $root "src\objective_conflict_analysis.py"),
    "--experiments-root", $experimentRoot,
    "--output-dir", (Join-Path $root "$PaperOutputRoot\objective_conflict")
)
Invoke-StudyStep @(
    $python, (Join-Path $root "src\generate_paper_results.py"),
    "--experiment-dir", $experimentRoot,
    "--paper-dir", (Join-Path $root $PaperOutputRoot)
)

Write-Host "Conference production/analysis completed: $experimentRoot"
