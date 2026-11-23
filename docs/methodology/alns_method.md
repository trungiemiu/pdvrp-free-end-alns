# Proposed ALNS method for PDVRP without time windows

## Problem handled

Each request has one pickup and one delivery. Both must be served by the same
driver, pickup must occur first, vehicle type must be compatible, and vehicle
load must remain between zero and capacity. A driver starts at its own depot and
does not have to return, so routes are open. No earliest/latest service times are
used.

## Algorithm

1. **Initial solution.** Regret-3 insertion assigns every request to a feasible
   driver and inserts pickup and delivery at the best positions.
2. **Destroy.** Random, worst-contribution, related, or whole-route removal takes
   a subset of requests out of the current solution.
3. **Repair.** Greedy, regret-2, regret-3, or noisy-greedy insertion reconstructs
   a feasible solution.
4. **Acceptance.** Better candidates are accepted; worse candidates can be
   accepted with a temperature-dependent simulated-annealing probability.
5. **Adaptation.** Operators earn scores when they produce a new global best,
   improve the current solution, or are accepted. Weights are updated every
   segment, so the search learns which operators work for the current instance.
6. **Termination.** Stop at the iteration or wall-clock limit and output the best
   feasible solution observed.

This is learning inside one optimization run, not ML training across a dataset.

## Main parameters

- `Iterations`: maximum search iterations.
- `TimeLimit`: wall-clock budget checked between ALNS iterations; one in-progress
  neighborhood evaluation may finish slightly after the requested limit.
- `Seed`: reproducible random seed.
- `MinRemove`, `MaxRemove`: neighborhood size.
- `CoolingRate`: how quickly acceptance becomes stricter.
- `BalancePenaltyVnd`: penalty on the standard deviation of orders per active
  driver; zero optimizes only travel cost.

## Applying it in practice

At the start of a planning period, export accepted orders and available drivers.
Build directed road distance/duration matrices with the routing engine used by
operations (for example OSRM or a commercial map API), then run ALNS within the
dispatch time budget. Validate the generated feasibility report before publishing
the ordered stops to drivers.

During operations, freeze completed stops and the driver’s actual current
position. When a new order, cancellation, breakdown, or traffic update arrives,
rebuild only the remaining problem and warm-start/re-run ALNS. Production systems
should log the input snapshot, seed, parameters, objective, runtime, and manual
dispatcher overrides for auditability.

Before deployment, replace average cost coefficients with the company’s actual
fuel, wage, toll, and vehicle costs. Add constraints that exist in the business
(shift end, maximum route duration, driver skill, service time, breaks) before
claiming operational feasibility. If customers have promised service intervals,
the problem becomes PDVRPTW and this no-time-window solver is not sufficient.

## Conference-ready evaluation

Use public PDVRP instances without time windows or convert benchmark instances by
explicitly removing time-window constraints and documenting that transformation.
Test many sizes and fleet mixes, run multiple seeds, compare equal-time budgets,
and include statistical tests, operator ablations, convergence plots, sensitivity
analysis, and computational complexity. Keep tuning and final test instances
separate.
