$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $root "scripts\common\moalns_study_common.ps1")
$python = Get-StudyPython $root
Invoke-StudyStep @(
    $python, "-m", "unittest",
    "tests.test_independent_route_checker",
    "tests.test_open_route_operators",
    "-v"
)
Invoke-StudyStep @(
    $python, (Join-Path $root "src\validate_experiment_archives.py"),
    "--manifest", (Join-Path $root "data\instances_manifest.csv"),
    "--experiments-root", (Join-Path $root "outputs\experiments"),
    "--output-dir", (Join-Path $root "outputs\validation\independent_archive_check"),
    "--fail-on-error"
)
