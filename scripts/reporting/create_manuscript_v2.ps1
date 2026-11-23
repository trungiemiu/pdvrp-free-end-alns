param(
    [string]$Source = "paper\paper.docx",
    [string]$Output = "paper\manuscript_v2.docx"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$sourcePath = if ([IO.Path]::IsPathRooted($Source)) { $Source } else { Join-Path $root $Source }
$outputPath = if ([IO.Path]::IsPathRooted($Output)) { $Output } else { Join-Path $root $Output }
$pdfPath = [IO.Path]::ChangeExtension($outputPath, ".pdf")

Copy-Item -LiteralPath $sourcePath -Destination $outputPath -Force

$word = $null
$doc = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $doc = $word.Documents.Open($outputPath, $false, $false)

    function Find-Range([string]$Text) {
        $range = $script:doc.Content.Duplicate
        $find = $range.Find
        $find.ClearFormatting()
        $find.Text = $Text
        $find.Forward = $true
        $find.Wrap = 0
        $find.MatchCase = $false
        if ($find.Execute()) { return $range }
        return $null
    }

    function Find-Range-After([string]$Text, [int]$Start) {
        $range = $script:doc.Range($Start, $script:doc.Content.End)
        $find = $range.Find
        $find.ClearFormatting()
        $find.Text = $Text
        $find.Forward = $true
        $find.Wrap = 0
        $find.MatchCase = $false
        if ($find.Execute()) { return $range }
        return $null
    }

    function Replace-All([string]$Old, [string]$New) {
        $range = $script:doc.Content.Duplicate
        $find = $range.Find
        $find.ClearFormatting()
        $find.Replacement.ClearFormatting()
        $find.Text = $Old
        $find.Replacement.Text = $New
        $find.Forward = $true
        $find.Wrap = 1
        $find.Format = $false
        $find.MatchCase = $false
        [void]$find.Execute($Old, $false, $false, $false, $false, $false,
            $true, 1, $false, $New, 2)
    }

    function Delete-Paragraph-Containing([string]$Text) {
        $range = Find-Range $Text
        if ($range) { [void]$range.Paragraphs.Item(1).Range.Delete() }
    }

    function Replace-Paragraph-Containing([string]$Text, [string]$NewText) {
        $range = Find-Range $Text
        if (-not $range) { throw "Paragraph not found: $Text" }
        $paragraph = $range.Paragraphs.Item(1)
        $style = $paragraph.Range.Style
        $paragraph.Range.Text = $NewText + "`r"
        $paragraph.Range.Style = $style
    }

    function Replace-Section-Body([string]$Heading, [string]$NextHeading,
                                  [string]$Body) {
        $headingRange = Find-Range $Heading
        $nextRange = Find-Range $NextHeading
        if (-not $headingRange -or -not $nextRange) {
            throw "Section boundary not found: $Heading / $NextHeading"
        }
        $start = $headingRange.Paragraphs.Item(1).Range.End
        $end = $nextRange.Paragraphs.Item(1).Range.Start
        $span = $script:doc.Range($start, $end)
        $span.Text = $Body + "`r"
        try { $span.Paragraphs.Item(1).Range.Style = $script:doc.Styles.Item("BodyText") } catch {}
    }

    function Insert-Table-Caption([int]$TableIndex, [string]$Caption) {
        $table = $script:doc.Tables.Item($TableIndex)
        $newRow = $table.Rows.Add($table.Rows.Item(1))
        $firstCell = $newRow.Cells.Item(1)
        $lastCell = $newRow.Cells.Item($newRow.Cells.Count)
        if ($newRow.Cells.Count -gt 1) { $firstCell.Merge($lastCell) }
        $newRow.Cells.Item(1).Range.Text = $Caption
        $newRow.Cells.Item(1).Range.ParagraphFormat.Alignment = 1
        $newRow.Cells.Item(1).Range.Font.Bold = $true
        $newRow.Cells.Item(1).Range.Font.Size = 8
    }

    Write-Host "Removing author metadata..."
    $author = Find-Range "Quang Trung Le"
    if ($author) { [void]$author.Paragraphs.Item(1).Range.Delete() }

    Write-Host "Correcting language..."
    $corrections = [ordered]@{
        "analyses.." = "analyses."
        "Generics destroy and repair" = "Generic destroy and repair"
        "spatial-requited-request" = "spatial related-request"
        "component wise" = "componentwise"
        "destroying size" = "destroy size"
        "standard deviation of over" = "standard deviation over"
        "all 933 passes" = "all 933 pass"
        "post-hoc returning" = "post-hoc retuning"
        "not statistically justified post-hoc parameter replacement" = "no statistically justified post-hoc parameter replacement"
        '$w$' = "w"
    }
    foreach ($item in $corrections.GetEnumerator()) {
        Replace-All $item.Key $item.Value
    }

    Write-Host "Condensing literature and decision support..."
    $related = @"
The PDVRP couples request assignment with pickup--delivery precedence and capacity feasibility [1]. Li and Lim introduced widely used PDPTW benchmarks [2], while Ropke and Pisinger established ALNS as a strong solution framework [3]. Our setting removes time windows but adds driver-specific starts, heterogeneous compatibility, open endpoints, and three objectives.

Open VRP studies show that eliminating the depot return changes route structure [10], [11]. We transfer this free-end insight to paired-request suffixes. The broader pickup-and-delivery and ALNS literature supports problem-specific large neighborhoods and explicit operator testing [12], [13], [16]. Multi-objective routing motivates the cost, duration, and equity criteria and the NSGA-II, MOEA/D, and epsilon-constraint comparison [4]--[9].
"@
    Replace-Section-Body "RELATED WORK" "Problem Definition" $related.Trim()

    $decision = "TOPSIS and PROMETHEE II rank feasible archive members using decision-maker-specified cost, duration, and workload-equity weights [14], [15]. TOPSIS is a compensatory distance-to-ideal method, whereas PROMETHEE II uses pairwise outranking. Neither method changes the routes."
    Replace-Section-Body "Decision Support" "Experimental Design" $decision

    Write-Host "Condensing mathematical formulation..."
    $networkHeading = Find-Range "Network and feasibility"
    $methodHeading = Find-Range-After "Multi-Objective ALNS" $networkHeading.Paragraphs.Item(1).Range.End
    if (-not $networkHeading -or -not $methodHeading) {
        throw "Mathematical-model boundary not found."
    }
    $modelText = @"
Let R be the request set, K the driver set, and N={p_r,d_r:r∈R} the service nodes. Request r has demand q_r and required vehicle type v_r. Driver k starts at s_k and has type v_k, capacity Q_k, and per-kilometer cost c_k. Compatibility parameter a_rk equals one when driver k can serve request r; d_ij and τ_ij denote directed distance and travel time.

Binary y_rk assigns request r to driver k, and x_ijk selects arc (i,j) for driver k. The core assignment, compatibility, and visit constraints are

∑_(k∈K)y_rk=1,  y_rk≤a_rk,    r∈R,k∈K,

∑_j x_ijk=∑_j x_jik=y_rk,    i∈{p_r,d_r}.

Each used route leaves s_k once and terminates at an artificial zero-cost sink, so no return arc is charged. Standard position u_ik and load L_ik propagation enforce

u_(p_r k)<u_(d_r k),    0≤L_ik≤Q_k.

Objectives

The multi-objective problem minimizes F=(f_1,f_2,f_3), where

f_1=∑_(k∈K)∑_i∑_(j≠i)c_k d_ij x_ijk,

f_2=max_(k∈K){∑_i∑_j τ_ij x_ijk/60},

f_3=1/|V| ∑_(v∈V) sqrt(1/|K_v| ∑_(k∈K_v)(n_k-n̄_v)^2),    n_k=∑_r y_rk.

Idle compatible drivers remain in K_v, preventing concentrated assignments from appearing balanced. The metaheuristic evaluates all three objectives directly; the PuLP/CBC certificate optimizes the f_1 specialization on small instances.
"@
    $modelStart = $networkHeading.Paragraphs.Item(1).Range.End
    $modelEnd = $methodHeading.Paragraphs.Item(1).Range.Start
    Write-Host "Model range: $modelStart .. $modelEnd / $($doc.Content.End)"
    $modelSpan = $doc.Range($modelStart, $modelEnd)
    $modelSpan.Text = $modelText.Trim() + "`r"
    Write-Host "Model text replaced."
    foreach ($paragraph in $modelSpan.Paragraphs) {
        try { $paragraph.Range.Style = $doc.Styles.Item("BodyText") } catch {}
    }
    Write-Host "Model paragraph styles applied."
    $networkHeading = Find-Range "Network and feasibility"
    Write-Host "Network heading reacquired: $($networkHeading.Start) .. $($networkHeading.End) / $($doc.Content.End)"
    $objectiveHeading = Find-Range-After "Objectives" $networkHeading.Paragraphs.Item(1).Range.End
    if ($objectiveHeading) {
        try { $objectiveHeading.Paragraphs.Item(1).Range.Style = $doc.Styles.Item("Heading2") } catch {}
    }

    Write-Host "Removing redundant tables..."
    foreach ($index in @(8, 7, 5, 3, 2, 1)) {
        $doc.Tables.Item($index).Delete()
    }
    foreach ($caption in @(
        "Table - Experimental instance groups.",
        "Table - Information contributed by workload imbalance",
        "Table - Small-instance exact cost validation.",
        "Table - Normalized HV by instance",
        "Table - Paired Wilcoxon comparisons",
        "Table - Time-budget sensitivity over nine paired blocks."
    )) { Delete-Paragraph-Containing $caption }

    $doc.Tables.Item(1).Cell(4, 1).Range.Text = "Mean ΔHV"
    $doc.Tables.Item(2).Cell(1, 2).Range.Text = "Mean HV"
    Delete-Paragraph-Containing "Table - Tail ablation over 40 paired"
    Delete-Paragraph-Containing "Table - Aggregate performance across 30"
    Insert-Table-Caption 1 "TABLE I. TAIL-OPERATOR ABLATION OVER 40 PAIRED INSTANCE-SEED BLOCKS."
    Insert-Table-Caption 2 "TABLE II. AGGREGATE PERFORMANCE ACROSS 30 INSTANCE-SEED BLOCKS."

    Write-Host "Removing figures for the six-page version..."
    foreach ($index in @(5, 4, 3, 2, 1)) {
        [void]$doc.InlineShapes.Item($index).Range.Delete()
    }
    foreach ($caption in @(
        "Figure - Survival of three-objective",
        "Figure - Paired hypervolume change",
        "Figure - Normalized hypervolume by instance",
        "Figure - Mean normalized hypervolume",
        "Figure - Selection stability of TOPSIS"
    )) { Delete-Paragraph-Containing $caption }

    Write-Host "Condensing validation and results references..."
    $validation = "CBC proved cost optimality on three four-request instances, and both ALNS and the minimum-cost MOALNS archive member attained zero gap. The independent checker verified all 3,584 ablation and 933 production archive solutions without a feasibility or objective mismatch."
    Replace-Section-Body "Exact and independent validation" "Tail-operator ablation" $validation
    Replace-All "As shown in Table, 12.5–71.2%" "Across the tested environments, 12.5–71.2%"
    Replace-All "Table reports on the broader benchmark." "In the broader benchmark,"
    Replace-All "As Table shows, MOALNS exceeds" "At the instance level, MOALNS exceeds"
    Replace-All "Increasing the budget improves front quality (Table)." "Increasing the budget improves front quality."

    Write-Host "Condensing sensitivity analysis..."
    $sensitivityHeading = Find-Range "Time and parameter sensitivity"
    $limitationsHeading = Find-Range "Limitations"
    if (-not $sensitivityHeading -or -not $limitationsHeading) {
        throw "Sensitivity-section boundary not found."
    }
    $sensitivityText = "Sensitivity and decision support`rMean HV rises from 0.6700 at 60 s to 0.7373 at 180 s and 0.7525 at 600 s; both shorter budgets differ from 600 s after Holm correction (p=0.00781). None of 17 parameter variants differs significantly from the baseline after correction, although removing Tchebycheff augmentation yields the largest mean loss. Across 231 weight vectors, TOPSIS and PROMETHEE II agree on 41.1% of selections and choose 16 and 10 distinct plans, respectively, confirming that deployment is preference dependent.`r"
    $sensitivitySpan = $doc.Range($sensitivityHeading.Paragraphs.Item(1).Range.Start,
                                   $limitationsHeading.Paragraphs.Item(1).Range.Start)
    $sensitivitySpan.Text = $sensitivityText
    try { $sensitivitySpan.Paragraphs.Item(1).Range.Style = $doc.Styles.Item("Heading2") } catch {}
    try { $sensitivitySpan.Paragraphs.Item(2).Range.Style = $doc.Styles.Item("BodyText") } catch {}

    Write-Host "Condensing conclusion and removing template text..."
    $limitations = Find-Range "Limitations"
    $references = Find-Range-After "References" $limitations.Paragraphs.Item(1).Range.End
    if (-not $limitations -or -not $references) {
        throw "Closing-section boundary not found."
    }
    $closing = "This study introduces free-end tail removal and tail-only repair for a three-objective heterogeneous open PDVRP. Workload imbalance preserves 12.5--71.2% of empirical alternatives lost under a cost--duration projection, while paired ablation confirms that the tail operators improve hypervolume and archive diversity. MOALNS achieves the best aggregate HV in the equal-time comparison and significantly outperforms all three baselines on independent instance means. Limitations include three production seeds, nine time-window-free derivatives, one heterogeneous road-network instance, and shared implementation components across algorithms. Future work should evaluate larger independent benchmarks, alternative equity measures, and dynamic travel conditions."
    $span = $doc.Range($limitations.Paragraphs.Item(1).Range.Start,
                       $references.Paragraphs.Item(1).Range.Start)
    $span.Text = "CONCLUSION AND LIMITATIONS`r$closing`r"
    try { $span.Paragraphs.Item(1).Range.Style = $doc.Styles.Item("Heading1") } catch {}
    try { $span.Paragraphs.Item(2).Range.Style = $doc.Styles.Item("BodyText") } catch {}

    Write-Host "Replacing references with IEEE format..."
    $referenceHeading = Find-Range-After "References" $span.End
    if (-not $referenceHeading) { throw "References heading not found." }
    $referenceLines = Get-Content -LiteralPath (Join-Path $root "paper\references_ieee.txt")
    $referenceBody = ($referenceLines | Select-Object -Skip 2 |
        Where-Object { $_ -ne "" }) -join "`r"
    $referenceRange = $doc.Range($referenceHeading.Paragraphs.Item(1).Range.End,
                                  $doc.Content.End - 1)
    $referenceRange.Text = $referenceBody + "`r"
    foreach ($paragraph in $referenceRange.Paragraphs) {
        try { $paragraph.Range.Style = $doc.Styles.Item("references") } catch {}
        $paragraph.Range.Font.Size = 8
        $paragraph.Format.SpaceAfter = 0
        $paragraph.Format.LineSpacingRule = 0
    }

    $doc.Repaginate()
    $doc.Save()
    $doc.ExportAsFixedFormat($pdfPath, 17)
    $doc.Repaginate()

    [pscustomobject]@{
        Docx = $outputPath
        Pdf = $pdfPath
        Pages = $doc.ComputeStatistics(2)
        Words = $doc.ComputeStatistics(0)
        Tables = $doc.Tables.Count
        Figures = $doc.InlineShapes.Count
        Equations = $doc.OMaths.Count
        AuthorsPresent = ($doc.Content.Text -match
            "Quang Trung Le|Minh Hieu Le|Nguyen Ky Phuc Phan")
    } | Format-List
}
catch {
    Write-Error ($_.Exception.ToString())
    throw
}
finally {
    if ($doc) { $doc.Close($false) }
    if ($word) { $word.Quit() }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
