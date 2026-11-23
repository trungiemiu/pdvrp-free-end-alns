# Mathematical Model - Heterogeneous Multi-Driver Pickup and Delivery Routing

## Context

The competition instance is modeled as a heterogeneous multi-driver pickup and
delivery routing problem. Each order has one pickup node, one delivery node, a
demand in kilograms, and a required vehicle type. Each driver has a start
location, vehicle type, vehicle capacity, vehicle operating cost per kilometer,
and vehicle revenue parameters.

Routes are open: a driver starts from their own start node and is not required
to return to that start node. To model open routes cleanly, each driver has an
artificial zero-cost end node.

Distances can be generated in two ways. The original fallback matrix is
Haversine distance from geocoded coordinates. The current active matrix can also
be replaced by OSRM road-network distances from OpenStreetMap using
`src/osrm_matrix.py`. When OSRM is used, travel durations are stored separately
in `data/duration_matrix_osrm_seconds.csv` and documented in
`data/osrm_matrix_metadata.json`.

## Sets

- `K`: set of drivers/vehicles.
- `R`: set of pickup-delivery orders.
- `P`: set of pickup nodes.
- `D`: set of delivery nodes.
- `N = P union D`: set of service nodes.
- `S = {s_k | k in K}`: driver-specific start nodes.
- `E = {e_k | k in K}`: driver-specific artificial end nodes.
- `V_k = {s_k} union N union {e_k}`: nodes available to driver `k`.

For each order `r in R`:

- `p_r`: pickup node of order `r`.
- `d_r`: delivery node of order `r`.

## Parameters

- `dist_ij`: distance from node `i` to node `j`, in kilometers.
- `tau_ij`: optional travel duration from node `i` to node `j`, in seconds,
  used for reporting when an OSRM duration matrix is available.
- `cost_k`: operating cost per kilometer for driver `k`.
- `c_ijk = dist_ij * cost_k`: travel cost for driver `k` on arc `(i,j)`.
- `q_r`: demand of order `r`.
- `Q_k`: capacity of driver `k`.
- `a_rk`: compatibility parameter, equal to 1 if driver `k` can serve order `r`,
  otherwise 0.
- `base_rev_k`: revenue for an order served by driver `k` up to 30 km.
- `extra_rev_k`: build-up revenue per kilometer beyond 30 km for driver `k`.
- `rev_rk = base_rev_k + max(0, dist_{p_r,d_r} - 30) * extra_rev_k` if
  `a_rk = 1`.
- `M`: sufficiently large constant.

Because each order is required to be served exactly once and vehicle
compatibility fixes the vehicle type, total order revenue is constant across all
feasible solutions in the current dataset. Therefore maximizing net profit is
equivalent to minimizing total travel cost, while revenue and profit are still
reported for competition context.

## Decision Variables

- `x_ijk in {0,1}`: 1 if driver `k` travels directly from node `i` to node `j`.
- `y_rk in {0,1}`: 1 if order `r` is assigned to driver `k`.
- `u_ik >= 0`: visit sequence position of node `i` in driver `k` route.
- `L_ik >= 0`: load carried by driver `k` after visiting node `i`.
- `w_k in {0,1}`: 1 if driver `k` is used.

## Objective

Primary equivalent objective used by the code:

```text
minimize sum_{k in K} sum_{i in V_k} sum_{j in V_k, j != i} c_ijk x_ijk
```

Competition profit reporting:

```text
total_revenue = sum_{r in R} sum_{k in K} rev_rk y_rk
total_cost    = sum_{k in K} sum_{i in V_k} sum_{j in V_k, j != i} c_ijk x_ijk
net_profit    = total_revenue - total_cost
```

If optional order rejection is introduced later, the objective should become:

```text
maximize total_revenue - total_cost
```

## Constraints

Each order is assigned exactly once:

```text
sum_{k in K} y_rk = 1                         for all r in R
```

Vehicle compatibility:

```text
y_rk <= a_rk                                  for all r in R, k in K
```

Driver start and artificial end:

```text
sum_{j in V_k, j != s_k} x_{s_k,j,k} = w_k    for all k in K
sum_{i in V_k, i != e_k} x_{i,e_k,k} = w_k    for all k in K
```

No arcs enter a start node and no arcs leave an artificial end node:

```text
sum_{i in V_k, i != s_k} x_{i,s_k,k} = 0      for all k in K
sum_{j in V_k, j != e_k} x_{e_k,j,k} = 0      for all k in K
```

Pickup and delivery visits follow assignment:

```text
sum_{j in V_k, j != p_r} x_{p_r,j,k} = y_rk   for all r in R, k in K
sum_{i in V_k, i != p_r} x_{i,p_r,k} = y_rk   for all r in R, k in K
sum_{j in V_k, j != d_r} x_{d_r,j,k} = y_rk   for all r in R, k in K
sum_{i in V_k, i != d_r} x_{i,d_r,k} = y_rk   for all r in R, k in K
```

Flow conservation at service nodes:

```text
sum_{i in V_k, i != n} x_{i,n,k}
=
sum_{j in V_k, j != n} x_{n,j,k}              for all n in N, k in K
```

Pickup and delivery must be served by the same driver. This is enforced by
using the same assignment variable `y_rk` for both nodes.

Pickup-before-delivery:

```text
u_{p_r,k} + 1 <= u_{d_r,k} + M(1 - y_rk)      for all r in R, k in K
```

Sequence propagation and subtour elimination:

```text
u_{j,k} >= u_{i,k} + 1 - M(1 - x_{i,j,k})     for all k in K, i,j in V_k
```

Initial load:

```text
L_{s_k,k} = 0                                 for all k in K
```

Load propagation for every traveled arc:

Let `delta_j = q_r` if `j = p_r`, `delta_j = -q_r` if `j = d_r`, and
`delta_j = 0` for start/end nodes.

```text
L_{j,k} >= L_{i,k} + delta_j - M(1 - x_{i,j,k})
L_{j,k} <= L_{i,k} + delta_j + M(1 - x_{i,j,k})
                                             for all k in K, i,j in V_k
```

Capacity bounds:

```text
0 <= L_{i,k} <= Q_k                           for all k in K, i in V_k
```

Driver-use linking:

```text
sum_{r in R} y_rk <= |R| w_k                  for all k in K
```

## Implementation Notes

- `src/milp_pulp_solver.py` implements the artificial end node formulation.
- `src/ortools_solver.py` implements open routes with dummy end nodes.
- `src/osrm_matrix.py` builds road-distance and travel-time matrices from the
  OSRM Table API. The public OSRM demo server is suitable for small test runs;
  self-hosted OSRM is preferred for reproducible production experiments.
- `src/route_duration_report.py` annotates route step and summary outputs with
  OSRM travel durations when `data/duration_matrix_osrm_seconds.csv` exists.
- The proposed ALNS solver and retained reference solvers produce the same route,
  step, and summary schema and are checked by `src/evaluator.py`.
- The evaluator reports feasibility, total distance, total cost, total revenue,
  net profit, and travel duration when available.

## References

- Li, H., & Lim, A. (2001). A metaheuristic for the pickup and delivery problem
  with time windows.
- Savelsbergh, M. W. P., & Sol, M. (1995). The general pickup and delivery
  problem.
- Ropke, S., & Pisinger, D. (2006). An adaptive large neighborhood search
  heuristic for the pickup and delivery problem with time windows.
