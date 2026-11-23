param(
    [string]$InputPath = "paper\manuscript_v2.txt",
    [string]$OutputPath = "paper\manuscript_v2.md"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$inputFile = if ([IO.Path]::IsPathRooted($InputPath)) { $InputPath } else { Join-Path $root $InputPath }
$outputFile = if ([IO.Path]::IsPathRooted($OutputPath)) { $OutputPath } else { Join-Path $root $OutputPath }

$text = Get-Content -LiteralPath $inputFile -Raw -Encoding UTF8
$text = $text -replace "`r`n", "`n"
$text = $text.Trim()

# Remove the unfilled IEEE copyright placeholder from the editable manuscript.
$text = $text -replace "(?m)^XXX-X-XXXX-XXXX-X/XX/\$XX\.00 ©20XX IEEE\s*$", ""
$text = $text.Replace('XXX-X-XXXX-XXXX-X/XX/$XX.00 ©20XX IEEE', '')

$headings = [ordered]@{
    "INTRODUCTION" = "# Introduction"
    "RELATED WORK" = "# Related Work"
    "Problem Definition" = "# Problem Definition"
    "Network and feasibility" = "## Network and Feasibility"
    "Objectives" = "## Objectives"
    "Multi-Objective ALNS" = "# Multi-Objective ALNS"
    "Search control" = "## Search Control"
    "Generic destroy and repair" = "## Generic Destroy and Repair"
    "Free-end tail operators" = "## Free-End Tail Operators"
    "Decision Support" = "# Decision Support"
    "Experimental Design" = "# Experimental Design"
    "Instances and protocol" = "## Instances and Protocol"
    "Implementation validation" = "## Implementation Validation"
    "External comparison" = "## External Comparison"
    "Sensitivity and decision analysis" = "## Sensitivity and Decision Analysis"
    "Results" = "# Results"
    "Does the third objective add information?" = "## Does the Third Objective Add Information?"
    "Exact and independent validation" = "## Exact and Independent Validation"
    "Tail-operator ablation" = "## Tail-Operator Ablation"
    "External algorithm comparison" = "## External Algorithm Comparison"
    "Sensitivity and decision support" = "## Sensitivity and Decision Support"
    "CONCLUSION AND LIMITATIONS" = "# Conclusion and Limitations"
    "References" = "# References"
}
foreach ($entry in $headings.GetEnumerator()) {
    $escaped = [regex]::Escape($entry.Key)
    $text = [regex]::Replace($text, "(?m)^$escaped\s*$", $entry.Value)
}

$title = "Free-End Tail Reassignment in Multi-Objective Adaptive Large Neighborhood Search for Heterogeneous Open Pickup-and-Delivery Routing"
$text = [regex]::Replace($text, "^" + [regex]::Escape($title), "# $title", 1)
$text = $text -replace "(?m)^Abstract - ", "**Abstract—** "
$text = $text -replace "(?m)^Keywords - ", "**Keywords—** "

$table1Pattern = '(?s)TABLE I\. TAIL-OPERATOR ABLATION OVER 40 PAIRED INSTANCE-SEED BLOCKS\..*?(?=\nRemoving both tail operators)'
$table1 = @'
**Table I. Tail-operator ablation over 40 paired instance-seed blocks.**

| Configuration | Mean HV | Archive | Mean ΔHV | W–T–L | Holm-adjusted *p* |
|---|---:|---:|---:|---:|---:|
| Full MOALNS | 0.67936 | 26.25 | — | — | — |
| No tail repair | 0.67267 | 21.90 | −0.00670 | 7–9–24 | 0.002976 |
| No tail removal | 0.66928 | 21.55 | −0.01008 | 6–10–24 | 0.000712 |
| No tail operators | 0.66522 | 19.90 | −0.01414 | 4–9–27 | 1.96 × 10⁻⁴ |
'@
$table1Start = $text.IndexOf("TABLE I. TAIL-OPERATOR ABLATION OVER 40 PAIRED INSTANCE-SEED BLOCKS.")
$table1End = $text.IndexOf("Removing both tail operators", $table1Start)
if ($table1Start -ge 0 -and $table1End -gt $table1Start) {
    $text = $text.Substring(0, $table1Start) + $table1.Trim() + "`n" + $text.Substring($table1End)
}

$table2Pattern = '(?s)TABLE II\. AGGREGATE PERFORMANCE ACROSS 30 INSTANCE-SEED BLOCKS\..*?(?=\nThe Friedman test)'
$table2 = @'
**Table II. Aggregate performance across 30 instance-seed blocks.**

| Method | Mean HV | Mean HV rank | Wins | Mean archive size | Union-front contribution |
|---|---:|---:|---:|---:|---:|
| MOALNS | 0.4233 | 1.8000 | 17 | 8.83 | 185 |
| MOEA/D | 0.2043 | 2.7000 | 3 | 6.30 | 67 |
| NSGA-II | 0.1856 | 3.1667 | 3 | 7.77 | 74 |
| Epsilon-constraint | 0.2355 | 2.3333 | 7 | 8.20 | 100 |
'@
$table2Start = $text.IndexOf("TABLE II. AGGREGATE PERFORMANCE ACROSS 30 INSTANCE-SEED BLOCKS.")
$table2End = $text.IndexOf("The Friedman test", $table2Start)
if ($table2Start -ge 0 -and $table2End -gt $table2Start) {
    $text = $text.Substring(0, $table2Start) + $table2.Trim() + "`n" + $text.Substring($table2End)
}

$equations = [ordered]@{
    '∑_(k∈K)y_rk=1,  y_rk≤a_rk,    r∈R,k∈K,' = '\sum_{k\in K} y_{rk}=1,\qquad y_{rk}\le a_{rk},\quad r\in R,\ k\in K,'
    '∑_j x_ijk=∑_j x_jik=y_rk,    i∈{p_r,d_r}.' = '\sum_j x_{ijk}=\sum_j x_{jik}=y_{rk},\qquad i\in\{p_r,d_r\}.'
    'u_(p_r k)<u_(d_r k),    0≤L_ik≤Q_k.' = 'u_{p_rk}<u_{d_rk},\qquad 0\le L_{ik}\le Q_k.'
    'f_1=∑_(k∈K)∑_i∑_(j≠i)c_k d_ij x_ijk,' = 'f_1=\sum_{k\in K}\sum_i\sum_{j\ne i} c_k d_{ij}x_{ijk},'
    'f_2=max_(k∈K){∑_i∑_j τ_ij x_ijk/60},' = 'f_2=\max_{k\in K}\left\{\frac{\sum_i\sum_j \tau_{ij}x_{ijk}}{60}\right\},'
    'f_3=1/|V| ∑_(v∈V) sqrt(1/|K_v| ∑_(k∈K_v)(n_k-n̄_v)^2),    n_k=∑_r y_rk.' = 'f_3=\frac{1}{|V|}\sum_{v\in V}\sqrt{\frac{1}{|K_v|}\sum_{k\in K_v}(n_k-\bar n_v)^2},\qquad n_k=\sum_r y_{rk}.'
    '\phi \left(s\mid w\right)=\max_{m=1,2,3}{\left\{w_{m}\frac{f_{m}\left(s\right)}{g_{m}}\right\}}+\rho \sum_{m=1}^{3} w_{m}\frac{f_{m}\left(s\right)}{g_{m}}.' = '\phi(s\mid w)=\max_{m=1,2,3}\left\{w_m\frac{f_m(s)}{g_m}\right\}+\rho\sum_{m=1}^{3}w_m\frac{f_m(s)}{g_m}.'
    '{\omega }_{o}\leftarrow \left(1-\lambda \right){\omega }_{o}+\lambda \frac{{\pi }_{o}}{\max{\left(1,{\nu }_{o}\right)}},\quad \quad \lambda =0.25,' = '\omega_o\leftarrow(1-\lambda)\omega_o+\lambda\frac{\pi_o}{\max(1,\nu_o)},\qquad \lambda=0.25,'
}
foreach ($entry in $equations.GetEnumerator()) {
    $escaped = [regex]::Escape($entry.Key)
    $replacement = "`n`$`$`n" + $entry.Value + "`n`$`$`n"
    $text = [regex]::Replace($text, "(?m)^$escaped$", { param($match) $replacement })
}

# Replace the compact Word section with the structured mathematical model and
# algorithm description maintained as a reusable Markdown fragment.
$coreSectionPath = Join-Path $root "paper\sections\problem_and_moalns.md"
$coreSection = Get-Content -LiteralPath $coreSectionPath -Raw -Encoding UTF8
$coreStart = $text.IndexOf("# Problem Definition")
$coreEnd = $text.IndexOf("# Experimental Design", $coreStart)
if ($coreStart -lt 0 -or $coreEnd -le $coreStart) {
    throw "Could not locate the Problem Definition / Experimental Design boundaries."
}
$text = $text.Substring(0, $coreStart) + $coreSection.Trim() + "`n`n" + $text.Substring($coreEnd)

# Normalize excess blank lines while keeping Markdown block separation.
$text = [regex]::Replace($text, "(?m)([^`n])`n(#)", "`$1`n`n`$2")
$text = [regex]::Replace($text, "`n{3,}", "`n`n")
$text = $text.Trim() + "`n"
[IO.File]::WriteAllText($outputFile, $text, [Text.UTF8Encoding]::new($false))
Write-Host "Created $outputFile"
