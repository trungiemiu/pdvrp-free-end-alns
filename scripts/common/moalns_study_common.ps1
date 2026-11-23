$ErrorActionPreference = "Stop"

function Get-StudyPython {
    param([string]$Root)
    $venvPython = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) { return $venvPython }
    $systemPython = Get-Command python -ErrorAction SilentlyContinue
    if ($systemPython) { return $systemPython.Source }
    throw "Python was not found in .venv or PATH."
}

function Invoke-StudyStep {
    param([Parameter(Mandatory = $true)][string[]]$Command)
    Write-Host ""
    Write-Host ("> " + ($Command -join " "))
    & $Command[0] @($Command[1..($Command.Length - 1)])
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $($Command -join ' ')"
    }
}

function Invoke-MoalnsStudyConfiguration {
    param(
        [string]$Root,
        [string]$Python,
        [string]$Manifest,
        [string]$StudyRoot,
        [string]$ConfigId,
        [int[]]$Seeds,
        [int]$Iterations,
        [double]$TimeLimit,
        [string[]]$ExtraArgs,
        [string[]]$Instances,
        [switch]$Force
    )
    $manifestPath = if ([System.IO.Path]::IsPathRooted($Manifest)) { $Manifest } else { Join-Path $Root $Manifest }
    foreach ($instance in Import-Csv $manifestPath) {
        if ($Instances.Count -gt 0 -and $instance.instance_id -notin $Instances) { continue }
        $dataDir = if ([System.IO.Path]::IsPathRooted($instance.data_dir)) {
            $instance.data_dir
        } else {
            Join-Path $Root $instance.data_dir
        }
        foreach ($seed in $Seeds) {
            $outputDir = Join-Path $StudyRoot "$ConfigId\$($instance.instance_id)\seed_$seed"
            $archivePath = Join-Path $outputDir "moalns_pareto_archive.csv"
            $reportPath = Join-Path $outputDir "moalns_solver_report.csv"
            if (-not $Force -and (Test-Path $archivePath) -and (Test-Path $reportPath)) {
                Write-Host "SKIP completed: $ConfigId / $($instance.instance_id) / seed $seed"
                continue
            }
            New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
            $command = @(
                $Python, (Join-Path $Root "src\moalns_pdvrp_solver.py"),
                "--data-dir", $dataDir,
                "--output-dir", $outputDir,
                "--instance-id", $instance.instance_id,
                "--variant-id", $ConfigId,
                "--iterations", "$Iterations",
                "--time-limit", "$TimeLimit",
                "--seed", "$seed"
            ) + $ExtraArgs
            Invoke-StudyStep $command
        }
    }
}

function Invoke-MoalnsStudyAnalysis {
    param(
        [string]$Root,
        [string]$Python,
        [string]$StudyRoot,
        [string]$BaselineConfig,
        [string]$StudyLabel
    )
    Invoke-StudyStep @(
        $Python, (Join-Path $Root "src\analyze_moalns_study.py"),
        "--study-root", $StudyRoot,
        "--baseline-config", $BaselineConfig,
        "--study-label", $StudyLabel
    )
}
