param(
    [string]$Manifest = "data/instances_manifest.csv",
    [int[]]$Seeds = @(42, 43, 44),
    [int]$Iterations = 5000,
    [double]$TimeLimit = 180,
    [string[]]$Instances = @(),
    [string[]]$ConfigIds = @(),
    [string]$StudyRoot = "",
    [switch]$Force,
    [switch]$AnalyzeOnly
)

$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $root "scripts\common\moalns_study_common.ps1")
$python = Get-StudyPython $root
if ($StudyRoot -eq "") { $StudyRoot = Join-Path $root "outputs\studies\moalns_parameter_sensitivity" }

# One-factor-at-a-time design around the baseline configuration.
$configs = @(
    @{ Id = "baseline"; Args = @() },
    @{ Id = "remove_1_3"; Args = @("--min-remove", "1", "--max-remove", "3") },
    @{ Id = "remove_4_10"; Args = @("--min-remove", "4", "--max-remove", "10") },
    @{ Id = "archive_50"; Args = @("--archive-size", "50") },
    @{ Id = "archive_200"; Args = @("--archive-size", "200") },
    @{ Id = "parent_0"; Args = @("--archive-parent-prob", "0") },
    @{ Id = "parent_0p20"; Args = @("--archive-parent-prob", "0.20") },
    @{ Id = "parent_0p50"; Args = @("--archive-parent-prob", "0.50") },
    @{ Id = "reaction_0p10"; Args = @("--reaction-factor", "0.10") },
    @{ Id = "reaction_0p50"; Args = @("--reaction-factor", "0.50") },
    @{ Id = "cooling_0p990"; Args = @("--cooling-rate", "0.990") },
    @{ Id = "cooling_0p999"; Args = @("--cooling-rate", "0.999") },
    @{ Id = "temperature_0p01"; Args = @("--initial-temperature", "0.01") },
    @{ Id = "temperature_0p10"; Args = @("--initial-temperature", "0.10") },
    @{ Id = "segment_10"; Args = @("--segment-length", "10") },
    @{ Id = "segment_30"; Args = @("--segment-length", "30") },
    @{ Id = "rho_0"; Args = @("--tchebycheff-rho", "0") },
    @{ Id = "rho_0p10"; Args = @("--tchebycheff-rho", "0.10") }
)

if (-not $AnalyzeOnly) {
    foreach ($config in $configs) {
        if ($ConfigIds.Count -gt 0 -and $config.Id -notin $ConfigIds) { continue }
        Invoke-MoalnsStudyConfiguration -Root $root -Python $python -Manifest $Manifest `
            -StudyRoot $StudyRoot -ConfigId $config.Id -Seeds $Seeds -Iterations $Iterations `
            -TimeLimit $TimeLimit -ExtraArgs $config.Args -Instances $Instances -Force:$Force
    }
}
Invoke-MoalnsStudyAnalysis -Root $root -Python $python -StudyRoot $StudyRoot `
    -BaselineConfig "baseline" -StudyLabel "MOALNS parameter sensitivity (OFAT)"

Write-Host "Parameter sensitivity completed: $StudyRoot"
