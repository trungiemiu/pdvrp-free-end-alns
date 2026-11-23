# Conference scope lock

## Included

- Three objectives: operating cost, maximum route duration, and within-type
  workload imbalance.
- Primary objective-scope evidence: Spearman matrices and the percentage of the
  empirical 3D front dominated after projection onto cost--makespan.
- MOALNS with open-route tail removal and tail-only compatible-driver repair.
- NSGA-II, MOEA/D, and heuristic epsilon-constraint baselines under equal time.
- Independent raw-route feasibility/objective checking and exact small-instance
  cost-optimality gaps.
- Two decision methods only: TOPSIS (compensatory) and PROMETHEE II
  (outranking).

## Excluded from the conference paper

- Ridge preference regression.
- MLP preference learning.
- Weighted Sum, VIKOR, WASPAS, and Borda result sections.

The excluded code remains in the repository for a journal extension. It must not
appear in the conference abstract, contributions, experiments, or conclusions.

## Claim decision from objective analysis

The third objective is retained. Across the four empirical union fronts,
removing workload imbalance causes 40.0%--80.2% of the 3D non-dominated vectors
to become dominated in the cost--makespan projection. This supports the claim
that a single cost--balance penalty or a two-objective formulation omits a
material portion of the attainable trade-off set.

## Required before final writing

1. Complete exact validation on the predeclared small-instance suite.
2. Run the tail/no-tail ablation with the same seed and time protocol.
3. Run the conference-scale benchmark in a fresh output directory.
4. Regenerate all tables, figures, statistics, and objective-conflict results
   from the new tail-enabled runs.
