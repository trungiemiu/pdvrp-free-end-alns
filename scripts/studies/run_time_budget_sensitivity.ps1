param(
    [string]$Manifest = "data/instances_manifest.csv",
    [int[]]$Seeds = @(42, 43, 44),
    [int[]]$TimeBudgets = @(60, 180, 300, 600),
    [int]$Iterations = 1000000,
    [string[]]$Instances = @(),
    [string]$StudyRoot = "",
    [switch]$Force,
    [switch]$AnalyzeOnly
)

$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $root "scripts\common\moalns_study_common.ps1")
$python = Get-StudyPython $root
if ($StudyRoot -eq "") { $StudyRoot = Join-Path $root "outputs\studies\time_budget_sensitivity" }
if ($TimeBudgets.Count -eq 0 -or ($TimeBudgets | Where-Object { $_ -le 0 })) {
    throw "TimeBudgets must contain positive integers."
}

if (-not $AnalyzeOnly) {
    foreach ($budget in ($TimeBudgets | Sort-Object -Unique)) {
        $configId = "time_$budget"
        Invoke-MoalnsStudyConfiguration -Root $root -Python $python -Manifest $Manifest `
            -StudyRoot $StudyRoot -ConfigId $configId -Seeds $Seeds -Iterations $Iterations `
            -TimeLimit $budget -ExtraArgs @() -Instances $Instances -Force:$Force
    }
}
$maxBudget = ($TimeBudgets | Measure-Object -Maximum).Maximum
Invoke-MoalnsStudyAnalysis -Root $root -Python $python -StudyRoot $StudyRoot `
    -BaselineConfig "time_$maxBudget" -StudyLabel "MOALNS time-budget sensitivity"

Write-Host "Time-budget sensitivity completed: $StudyRoot"
