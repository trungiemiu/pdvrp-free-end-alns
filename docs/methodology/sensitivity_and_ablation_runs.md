# MOALNS ablation and sensitivity experiments

All commands below are run from the project root in PowerShell. The scripts use
`.venv\Scripts\python.exe` when it exists and otherwise use `python` from PATH.
Completed archive/report pairs are skipped automatically. Add `-Force` only when
you intentionally want to overwrite a completed configuration.

Do not run multiple study scripts concurrently on the same machine. CPU
contention would make the wall-clock comparison unfair.

## 1. MOALNS ablation

Quick screening on one development instance and three seeds:

```powershell
.\scripts\studies\run_moalns_ablation.ps1 `
  -Instances @('lc101_notw_subset12') `
  -Seeds @(42,43,44) `
  -TimeLimit 180
```

Conference-scale run on all manifest instances:

```powershell
.\scripts\studies\run_moalns_ablation.ps1 -Seeds (42..51) -TimeLimit 600
```

The configurations are baseline, no adaptation, no simulated annealing, no
archive-parent sampling, weighted-sum scalarization, five destroy-operator
ablations (including tail removal), four repair-operator ablations (including
tail repair), a joint no-tail case, and greedy-only repair. To run only
selected configurations:

```powershell
.\scripts\studies\run_moalns_ablation.ps1 `
  -ConfigIds @('baseline','no_adaptation','no_sa','no_archive_parent','weighted_sum') `
  -Seeds (42..51) -TimeLimit 600
```

## 2. Time-budget sensitivity

```powershell
.\scripts\studies\run_time_budget_sensitivity.ps1 `
  -TimeBudgets @(60,180,300,600,1200) `
  -Seeds (42..51)
```

The iteration limit defaults to one million so the wall-clock budget is the
binding stopping condition. The largest requested budget is used as the paired
reference configuration in the statistical comparison.

## 3. MODM weight sensitivity

This analysis does not rerun MOALNS. It ranks every solution in an existing
Pareto archive over all simplex weights at the chosen step.

```powershell
.\scripts\studies\run_modm_weight_sensitivity.ps1 `
  -Archive 'outputs/reports/moalns_pareto_archive.csv' `
  -GridStep 0.10 `
  -VikorV 0.50
```

A step of 0.10 produces 66 weight combinations; 0.05 produces 231. The output
reports every selected solution, selection frequency, unique selections per
method, modal-selection share, objective ranges, and a stability chart.

## 4. Detailed parameter sensitivity

The script uses a one-factor-at-a-time design around the baseline:

- removal ranges: 1--3, 2--7, 4--10;
- archive sizes: 50, 100, 200;
- archive-parent probabilities: 0, 0.20, 0.35, 0.50;
- reaction factors: 0.10, 0.25, 0.50;
- cooling rates: 0.990, 0.995, 0.999;
- initial temperatures: 0.01, 0.05, 0.10;
- segment lengths: 10, 15, 30;
- Tchebycheff augmentation: 0, 0.05, 0.10.

Screen on development/tuning instances first:

```powershell
.\scripts\studies\run_moalns_parameter_sensitivity.ps1 `
  -Instances @('lc101_notw_subset12','lr101_notw_subset12') `
  -Seeds @(42,43,44) `
  -TimeLimit 180
```

After selecting parameters, lock them before evaluating final test instances.
Do not select the best parameter values on the same runs used for the final
performance claim.

## Resume and re-analysis

Rerun the same command to resume missing configurations. To regenerate analysis
without running the solver:

```powershell
.\scripts\studies\run_moalns_ablation.ps1 -AnalyzeOnly
.\scripts\studies\run_time_budget_sensitivity.ps1 -AnalyzeOnly
.\scripts\studies\run_moalns_parameter_sensitivity.ps1 -AnalyzeOnly
```

When `-AnalyzeOnly` is used for the time study, pass the same `-TimeBudgets` list
used in the experiment so the intended largest-budget reference is selected.

## Outputs

Each optimization study is stored under `outputs/studies/<study>/` with the
layout `config/instance/seed/`. Its `analysis/` directory contains:

- `run_metrics.csv`: per-run fixed-reference HV, spacing, archive size, runtime,
  iterations, and union-front contribution;
- `config_summary.csv`: aggregate means, standard deviations, ranks, and totals;
- `hypervolume_by_instance.csv`: per-instance mean/SD;
- `paired_statistics_vs_baseline.csv`: paired Wilcoxon tests with Holm correction;
- `mean_hypervolume.png` and `.pdf`: publication-ready summary chart.

All configurations of one instance share fixed normalization bounds constructed
from all configurations and seeds in that study. Consequently, do not add a new
configuration after freezing paper tables without regenerating the analysis.

## Approximate compute cost

With four instances, ten seeds, and 600 seconds per run, the complete 16-case
ablation requires about 106.7 solver-hours and the 18-case parameter study about
120 solver-hours, before initialization and small deadline overshoots. Use the
screening commands first, retain scientifically important cases, and run final
experiments sequentially on an otherwise idle machine.
