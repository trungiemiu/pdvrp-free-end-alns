param()

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$lockPath = Join-Path $root "outputs\logs\remaining_conference_work.lock"
New-Item -ItemType Directory -Force -Path (Split-Path $lockPath) | Out-Null

if (Test-Path -LiteralPath $lockPath) {
    $ownerText = (Get-Content -LiteralPath $lockPath -Raw).Trim()
    if ($ownerText -match '^[0-9]+$') {
        $taskList = & "$env:SystemRoot\System32\tasklist.exe" `
            /FI "PID eq $ownerText" /FO CSV /NH 2>$null
        $ownerPattern = '*","' + $ownerText + '","*'
        if ($taskList -like $ownerPattern) {
            throw "The conference pipeline is already running with PID $ownerText. Do not start a second copy."
        }
    }
    Remove-Item -LiteralPath $lockPath -Force
}
Set-Content -LiteralPath $lockPath -Value $PID -Encoding ascii

try {

& (Join-Path $root "scripts\experiments\run_corrected_main_comparison.ps1")
if ($LASTEXITCODE -ne 0) { throw "Corrected main comparison failed." }

& (Join-Path $root "scripts\experiments\run_conference_production.ps1") `
    -Manifest "data/broader_instances_manifest.csv" `
    -Seeds @(42,43,44) `
    -TimePerMethod 180 `
    -Iterations 5000 `
    -PopulationSize 50 `
    -EpsilonLevels 5 `
    -OutputRoot "outputs/broader_experiments" `
    -PaperOutputRoot "outputs/broader_paper"
if ($LASTEXITCODE -ne 0) { throw "Broader benchmark failed." }

& (Join-Path $root "scripts\studies\run_moalns_parameter_sensitivity.ps1") `
    -Manifest "data/instances_manifest.csv" `
    -Seeds @(42,43,44) `
    -Iterations 5000 `
    -TimeLimit 120 `
    -Instances @(
        "lc101_notw_subset12",
        "lr101_notw_subset12",
        "lrc101_notw_subset12"
    ) `
    -StudyRoot "outputs/studies/moalns_parameter_sensitivity_wallclock"
if ($LASTEXITCODE -ne 0) { throw "Parameter sensitivity failed." }

Write-Host "All remaining conference studies completed."
}
finally {
    if (Test-Path -LiteralPath $lockPath) {
        $ownerText = (Get-Content -LiteralPath $lockPath -Raw).Trim()
        if ($ownerText -eq "$PID") {
            Remove-Item -LiteralPath $lockPath -Force
        }
    }
}
