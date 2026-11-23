# Multi-objective benchmark methods and batch instances

## Algorithms

- **MOALNS:** proposed adaptive destroy/repair method with a non-dominated archive.
- **NSGA-II:** route-inheritance crossover, feasibility-preserving destroy/repair
  mutation, non-dominated sorting, and crowding-distance survival.
- **MOEA/D:** simplex/reference weight subproblems, weight-space neighborhoods,
  augmented Tchebycheff replacement, and a shared external archive.
- **Epsilon-constraint ALNS:** cost is the primary objective; a grid constrains
  maximum duration and workload imbalance. Constraint violation is minimized
  before cost. This is a heuristic epsilon-constraint baseline, not an exact MILP.

All four methods use identical route representation, hard feasibility checks,
three objective definitions, input matrices, random seed, and wall-clock budget.

## Instance schema

Each instance directory must contain:

```text
orders.csv
drivers.csv
vehicle_parameters.csv
distance_matrix.csv
duration_matrix_osrm_seconds.csv
```

Register directories in `data/instances_manifest.csv`. Paths are relative to the
project root. The default manifest contains the current real-world instance.

## Batch run

```powershell
.\scripts\experiments\run_multiobjective_benchmark.ps1 `
    -Seeds 42,43,44 `
    -TimePerMethod 180 `
    -PopulationSize 15 `
    -EpsilonLevels 3
```

Each instance/seed receives four archives, solver reports, an empirical union
reference front, normalized hypervolume, spacing, front contribution, and a
pairwise coverage matrix. `benchmark_summary.csv` combines all runs.

For publication, use at least 10 seeds and report paired statistics across the
same instance-seed blocks. Do not interpret one short run as an algorithm ranking.

To repair the two observed LC101 runtime outliers and resume the unfinished
LRC101 seeds without rerunning completed valid blocks:

```powershell
.\scripts\experiments\rerun_incomplete_benchmark.ps1 -TimePerMethod 600
```

The repair/insertion loops now check the wall-clock deadline internally. An
in-progress candidate is discarded at the deadline and the existing archive is
saved, preventing a single neighborhood evaluation from running for hours.

## Converting Li & Lim PDPTW data

The converter deliberately removes time windows and service times, preserves
pickup-delivery pairing/capacity, and builds Euclidean distance and duration
matrices:

```powershell
python src/convert_lilim_pdptw.py `
  --zip data/pdptw/pdp_100.zip `
  --member pdp_100/lc101.txt `
  --output-dir data/instances/lc101_notw `
  --instance-id lc101_notw
```

This transformation must be disclosed in a paper: the resulting instance is a
no-time-window derivative, not the original PDPTW experiment. `--max-orders` and
`--vehicle-limit` can create development subsets, but those subsets are not
standard benchmark results and must be labeled accordingly.
