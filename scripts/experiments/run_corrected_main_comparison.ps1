param(
    [string]$Manifest = "data/instances_manifest.csv",
    [int[]]$Seeds = @(42,43,44,45,46,47,48,49,50,51),
    [double]$TimePerMethod = 600,
    [int]$Iterations = 5000,
    [string]$SourceRoot = "outputs/conference_experiments",
    [string]$OutputRoot = "outputs/conference_experiments_wallclock",
    [string]$PaperOutputRoot = "outputs/conference_paper_wallclock",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $root "scripts\common\moalns_study_common.ps1")
$python = Get-StudyPython $root
$manifestPath = Join-Path $root $Manifest
$sourceRootPath = Join-Path $root $SourceRoot
$outputRootPath = Join-Path $root $OutputRoot

foreach ($instance in Import-Csv $manifestPath) {
    $dataDir = Join-Path $root $instance.data_dir
    foreach ($seed in $Seeds) {
        $sourceDir = Join-Path $sourceRootPath "$($instance.instance_id)\seed_$seed"
        $outputDir = Join-Path $outputRootPath "$($instance.instance_id)\seed_$seed"
        New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

        $moalnsArchive = Join-Path $outputDir "moalns_pareto_archive.csv"
        $moalnsReport = Join-Path $outputDir "moalns_solver_report.csv"
        if ($Force -or -not ((Test-Path $moalnsArchive) -and (Test-Path $moalnsReport))) {
            Invoke-StudyStep @(
                $python, (Join-Path $root "src\moalns_pdvrp_solver.py"),
                "--data-dir", $dataDir, "--output-dir", $outputDir,
                "--instance-id", $instance.instance_id,
                "--variant-id", "conference_tail_total_wallclock",
                "--iterations", "$Iterations", "--time-limit", "$TimePerMethod",
                "--seed", "$seed"
            )
        } else {
            Write-Host "SKIP corrected MOALNS / $($instance.instance_id) / $seed"
        }

        foreach ($algorithm in @("nsga2", "moead", "epsilon")) {
            foreach ($suffix in @("pareto_archive.csv", "solver_report.csv")) {
                $name = "${algorithm}_${suffix}"
                $source = Join-Path $sourceDir $name
                if (-not (Test-Path -LiteralPath $source)) {
                    throw "Missing source baseline artifact: $source"
                }
                Copy-Item -LiteralPath $source -Destination (Join-Path $outputDir $name) -Force
            }
        }

        Invoke-StudyStep @(
            $python, (Join-Path $root "src\multiobjective_quality.py"),
            "--experiment-dir", $outputDir,
            "--instance-id", $instance.instance_id, "--seed", "$seed"
        )
    }
}

& (Join-Path $root "scripts\experiments\run_conference_production.ps1") `
    -AnalyzeOnly -Manifest $Manifest -OutputRoot $OutputRoot `
    -PaperOutputRoot $PaperOutputRoot
if ($LASTEXITCODE -ne 0) {
    throw "Corrected main-comparison analysis failed."
}

Write-Host "Corrected total-wall-clock comparison completed: $outputRootPath"
