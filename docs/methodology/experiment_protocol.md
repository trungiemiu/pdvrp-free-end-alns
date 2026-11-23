# Experimental protocol

The proposed algorithm is three-objective MOALNS followed by MODM/MCDM selection.
Single-objective ALNS and the remaining solvers are reference baselines/ablations.

## Reproducibility

Report the instance files, Python/package versions, hardware, random seeds,
iteration limit, wall-clock limit, and ALNS parameters. Run at least 10 seeds
per instance and report mean, standard deviation, best objective, feasibility,
and runtime. Never select a seed after observing test results.

```powershell
.\scripts\run\run_moalns.ps1 -Iterations 5000 -TimeLimit 180 -Seed 42
.\scripts\run\run_alns.ps1 -Iterations 5000 -TimeLimit 120 -Seed 42
```

For a paper, separate parameter tuning instances from final test instances.
Compare against the retained constructive heuristics and OR-Tools/PuLP under
clearly stated time limits. Use the same directed matrices, fleet, and objective
for every method.

## Required ablations

Run ALNS after disabling one component at a time:

- adaptive operator weights;
- simulated-annealing acceptance;
- related removal;
- worst removal;
- regret repair (replace it with greedy repair).

Also include convergence curves from `alns_pdvrp_search_log.csv` and a sensitivity
analysis for time limit, removal range, and workload-balance penalty.

## Metrics

Always report feasibility first, followed by total operating cost, total distance,
runtime, number of used drivers, maximum orders per driver, and workload spread.
Revenue/profit may be reported as business KPIs but should not replace the routing
objective unless the mathematical model is changed accordingly.
