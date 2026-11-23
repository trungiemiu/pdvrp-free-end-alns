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
if ($StudyRoot -eq "") { $StudyRoot = Join-Path $root "outputs\studies\moalns_ablation" }

$configs = @(
    @{ Id = "baseline"; Args = @() },
    @{ Id = "no_adaptation"; Args = @("--disable-adaptation") },
    @{ Id = "no_sa"; Args = @("--disable-sa") },
    @{ Id = "no_archive_parent"; Args = @("--archive-parent-prob", "0") },
    @{ Id = "weighted_sum"; Args = @("--scalarization", "weighted_sum") },
    @{ Id = "no_random_removal"; Args = @("--destroy-operators", "worst,related,route,tail") },
    @{ Id = "no_worst_removal"; Args = @("--destroy-operators", "random,related,route,tail") },
    @{ Id = "no_related_removal"; Args = @("--destroy-operators", "random,worst,route,tail") },
    @{ Id = "no_route_removal"; Args = @("--destroy-operators", "random,worst,related,tail") },
    @{ Id = "no_tail_removal"; Args = @("--destroy-operators", "random,worst,related,route") },
    @{ Id = "no_noisy_greedy"; Args = @("--repair-operators", "greedy,regret_2,regret_3,tail_greedy") },
    @{ Id = "no_regret_2"; Args = @("--repair-operators", "greedy,regret_3,noisy_greedy,tail_greedy") },
    @{ Id = "no_regret_3"; Args = @("--repair-operators", "greedy,regret_2,noisy_greedy,tail_greedy") },
    @{ Id = "no_tail_repair"; Args = @("--repair-operators", "greedy,regret_2,regret_3,noisy_greedy") },
    @{ Id = "no_tail_operator"; Args = @(
        "--destroy-operators", "random,worst,related,route",
        "--repair-operators", "greedy,regret_2,regret_3,noisy_greedy"
    ) },
    @{ Id = "greedy_only"; Args = @("--repair-operators", "greedy") }
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
    -BaselineConfig "baseline" -StudyLabel "MOALNS ablation study"

Write-Host "Ablation completed: $StudyRoot"
