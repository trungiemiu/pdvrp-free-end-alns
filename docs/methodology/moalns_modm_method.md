# MOALNS + MODM/MCDM methodology

## Three minimized objectives

1. **Total operating cost (VND):** route distance multiplied by each vehicle's
   per-kilometre cost.
2. **Maximum route duration (minutes):** the longest driver route, using the
   directed OSRM duration matrix. This is a makespan/service-capacity objective.
3. **Workload imbalance:** mean standard deviation of assigned order counts
   computed separately inside each vehicle type and including idle eligible
   drivers. Separating vehicle types avoids comparing drivers who cannot serve
   the same requests.

All original PDVRP requirements remain hard constraints: complete assignment,
same-driver pickup and delivery, pickup precedence, compatibility, and capacity.

## MOALNS

Each iteration samples a weight vector and uses an augmented Tchebycheff scalar
function during repair and acceptance. Tchebycheff scalarization can reach
non-convex regions that a plain weighted sum may miss. A bounded archive retains
only non-dominated solutions; crowding distance preserves diversity when the
archive is full. Search parents are periodically sampled from the archive.

The destroy operators are random, worst-cost, related-request, route removal,
and open-route tail removal. Repair operators are greedy, noisy greedy,
regret-2, regret-3, and tail-only compatible-driver insertion.
Operator weights adapt from archive additions, dominance improvements, and
accepted moves. Simulated annealing provides diversification.

## Decision methods compared

The conference configuration retains only TOPSIS and PROMETHEE II. The broader
list below remains implemented for a journal extension.

- Weighted Sum: transparent compensatory utility.
- TOPSIS: closest to the ideal and farthest from the anti-ideal alternative.
- VIKOR: compromise between group utility and worst-criterion regret.
- PROMETHEE II: pairwise outranking/net flow.
- WASPAS: combined additive and multiplicative utility.
- Borda: consensus aggregation of the five classical rankings.

The output includes rankings, selected alternatives, and Spearman correlations.
Decision weights default to cost/duration/imbalance = 0.50/0.30/0.20 and are
normalized automatically. Sensitivity analysis should repeat decisions across a
predeclared weight grid.

## ML/DL preference selectors

`modm_decision.py` optionally compares Ridge regression and a two-hidden-layer
MLP. They predict a higher-is-better decision-maker preference score from three
instance-normalized criteria:

```text
cost_norm,duration_norm,imbalance_norm,preference_score
```

At least 12 labeled rows are required, but a conference experiment needs many
more labels across multiple **training instances**. The current test instance
must not be used to both train and claim predictive performance. The script uses
a deterministic 80/20 split and reports test RMSE. Prefer grouped cross-validation
by instance in the final paper.

Without `--preference-data`, ML/DL is deliberately skipped and
`modm_preference_template.csv` is generated for labeling. Treating a classical
MCDM score as a training label would only distill that method and is not an
independent comparison.

## Outputs

- `moalns_pareto_archive.csv`: objectives and serialized routes.
- `moalns_search_log.csv`: convergence and adaptive-operator trace.
- `modm_rankings.csv`: scores and ranks for every alternative.
- `modm_selections.csv`: selected solution for each decision method.
- `modm_rank_correlation.csv`: Spearman agreement between rankings.
- `modm_learning_report.csv`: ML/DL holdout error when labels are supplied.
- `moalns_pareto_front.html`: pairwise Pareto plots and selected alternatives.

## Paper evaluation

Use multiple PDVRP instances and at least 10 seeds. Report archive size,
hypervolume with a fixed reference point, inverted generational distance when a
reference front can be constructed, spacing/diversity, runtime, and feasibility.
Compare MOALNS with NSGA-II, MOEA/D, epsilon-constraint, and repeated weighted-sum
ALNS under equal time budgets. Ablate archive parent sampling, Tchebycheff repair,
adaptive operator weights, simulated annealing, and each destroy/repair family.
