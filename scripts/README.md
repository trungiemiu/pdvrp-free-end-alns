# Script map

Run `.\pdvrp.ps1 help` from the repository root for the unified interface.
Every script can also be called directly.

| Directory | Purpose | Main scripts |
|---|---|---|
| `run/` | Small end-to-end workflows | `run_core.ps1`, `run_alns.ps1`, `run_moalns.ps1` |
| `experiments/` | Benchmark and production experiments | `run_multiobjective_benchmark.ps1`, `run_conference_production.ps1` |
| `studies/` | Scientific robustness studies | ablation, time-budget, parameter, and MODM-weight sensitivity |
| `validation/` | Correctness checks | exact MILP comparison, independent archive feasibility, automated tests |
| `reporting/` | Analysis and publication artifacts | objective-conflict analysis and paper-output generation |
| `data/` | Dataset preparation | broader benchmark preparation |
| `common/` | Shared helpers | Python discovery and resumable study execution |

Long experiments are resumable: completed archives are skipped unless the
relevant runner is invoked with its force option. Use each script's parameter
block as the authoritative list of accepted options:

```powershell
Get-Help .\scripts\experiments\run_conference_production.ps1 -Full
```
