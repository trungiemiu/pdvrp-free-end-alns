param(
    [string]$OutputRoot = "data/instances_extended",
    [string]$Manifest = "data/broader_instances_manifest.csv"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $root "scripts\common\moalns_study_common.ps1")
$python = Get-StudyPython $root
$zip = Join-Path $root "data\pdptw\pdp_100.zip"
$converter = Join-Path $root "src\convert_lilim_pdptw.py"

$specs = @(
    @{ Id = "lc102_notw_n25";  Member = "pdp_100/lc102.txt";  Orders = 25; Vehicles = 6 },
    @{ Id = "lc105_notw_n25";  Member = "pdp_100/lc105.txt";  Orders = 25; Vehicles = 6 },
    @{ Id = "lc201_notw_n25";  Member = "pdp_100/lc201.txt";  Orders = 25; Vehicles = 6 },
    @{ Id = "lr102_notw_n25";  Member = "pdp_100/lr102.txt";  Orders = 25; Vehicles = 6 },
    @{ Id = "lr105_notw_n25";  Member = "pdp_100/lr105.txt";  Orders = 25; Vehicles = 6 },
    @{ Id = "lr201_notw_n25";  Member = "pdp_100/lr201.txt";  Orders = 25; Vehicles = 6 },
    @{ Id = "lrc102_notw_n25"; Member = "pdp_100/lrc102.txt"; Orders = 25; Vehicles = 6 },
    @{ Id = "lrc105_notw_n25"; Member = "pdp_100/lrc105.txt"; Orders = 25; Vehicles = 6 },
    @{ Id = "lrc201_notw_n25"; Member = "pdp_100/lrc201.txt"; Orders = 25; Vehicles = 6 }
)

$manifestRows = @(
    [PSCustomObject]@{ instance_id = "current"; data_dir = "data" }
)
foreach ($spec in $specs) {
    $relativeDir = "$OutputRoot/$($spec.Id)"
    $absoluteDir = Join-Path $root $relativeDir
    & $python $converter `
        --zip $zip `
        --member $spec.Member `
        --output-dir $absoluteDir `
        --instance-id $spec.Id `
        --max-orders $spec.Orders `
        --vehicle-limit $spec.Vehicles
    if ($LASTEXITCODE -ne 0) {
        throw "Conversion failed for $($spec.Id)"
    }
    $manifestRows += [PSCustomObject]@{
        instance_id = $spec.Id
        data_dir = $relativeDir.Replace("\", "/")
    }
}

$manifestPath = Join-Path $root $Manifest
$manifestRows | Export-Csv -Path $manifestPath -NoTypeInformation -Encoding utf8
Write-Host "Created broader benchmark manifest: $manifestPath"
