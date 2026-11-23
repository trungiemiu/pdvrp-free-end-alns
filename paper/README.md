# Conference paper draft

Working title:

> Free-End Tail Reassignment in Multi-Objective Adaptive Large Neighborhood
> Search for Heterogeneous Open Pickup-and-Delivery Routing

The main manuscript is `main.tex`; bibliography records are in
`references.bib`. The earlier numerical draft is preserved as
`archive/main-pre-tail-draft.tex`. The supplied IEEE Word template is preserved
as `template/ieee-conference-letter.docx`.

Readable exports are available as `manuscript.md` and `manuscript.txt`. Regenerate
both after editing `main.tex` with:

```powershell
.\.venv\Scripts\python.exe .\src\export_manuscript.py
```

The current manuscript reports verified evidence from the objective-scope
analysis, exact/independent validation, clean four-configuration tail ablation,
the final ten-instance equal-time comparison, time-budget and parameter
sensitivity, and TOPSIS/PROMETHEE II weight sensitivity.

Before submission:

1. Replace the author, affiliation, and e-mail placeholders.
2. Select a conference and replace the neutral `article` class with its official
   template.
3. Regenerate the clean tail-ablation artifacts from the project root:

   ```powershell
   .\.venv\Scripts\python.exe .\src\analyze_moalns_study.py `
     --study-root .\outputs\studies\moalns_ablation `
     --baseline-config baseline `
     --include-configs baseline,no_tail_removal,no_tail_repair,no_tail_operator `
     --output-dir .\outputs\paper\tail_ablation `
     --study-label "Open-route tail operator ablation"
   ```

4. Regenerate the completed broader tail-enabled comparison if its archives
change:

   ```powershell
   .\scripts\experiments\run_conference_production.ps1 `
     -Manifest "data/broader_instances_manifest.csv" `
     -Seeds @(42,43,44) `
     -TimePerMethod 180 `
     -OutputRoot "outputs/broader_experiments" `
     -PaperOutputRoot "outputs/broader_paper"
   ```

5. Regenerate the sensitivity studies, when needed, with
   `scripts/studies/run_time_budget_sensitivity.ps1`,
   `scripts/studies/run_moalns_parameter_sensitivity.ps1`, and
   `scripts/studies/run_modm_weight_sensitivity.ps1`.

6. Compile from this directory after installing a LaTeX distribution:

   ```powershell
   pdflatex main.tex
   bibtex main
   pdflatex main.tex
   pdflatex main.tex
   ```

The current machine does not expose `pdflatex`, `bibtex`, or `latexmk` on PATH,
so a PDF cannot be built locally until TeX Live, MiKTeX, or another compatible
LaTeX toolchain is installed.

The draft deliberately states that all Li--Lim-derived instances are
time-window-free derivatives, not the original PDPTW benchmarks. Computational
experiments are complete. Author metadata, the official venue template, venue
page-limit editing, and final PDF compilation remain submission tasks.
