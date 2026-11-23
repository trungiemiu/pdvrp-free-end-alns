# Problem Definition

## Assumptions and Scope Exceptions

The problem is static and deterministic: all requests, driver origins, vehicle characteristics, directed distances, and travel times are known before optimization. Each request is indivisible and consists of exactly one pickup and one delivery. Both events must be served by the same compatible driver, the pickup must precede the delivery, and vehicle capacity must be respected throughout the route. Each driver starts from a driver-specific origin and may serve at most one route. Distances and durations can be asymmetric.

Unlike the PDPTW, the studied problem has no time windows or service-time restrictions. Routes are open: a driver finishes at the last delivery and is not required to return to a depot. We represent this free endpoint by a driver-specific artificial sink with zero-cost and zero-time incoming arcs. Split deliveries, request transfers, multiple trips, dynamic arrivals, and stochastic travel times are outside the present scope. Strict vehicle compatibility is enforced, and the available fleet is assumed sufficient to construct at least one feasible solution. Workload equity is measured by the number of assigned requests within each vehicle type and includes idle compatible drivers.

## Sets and Indices

| Symbol | Definition |
|---|---|
| $R$ | Set of pickup-and-delivery requests, indexed by $r$. |
| $K$ | Set of drivers/vehicles, indexed by $k$. |
| $V$ | Set of vehicle types, indexed by $v$. |
| $K_v$ | Drivers having vehicle type $v$, where $K_v=\{k\in K:v_k=v\}$. |
| $P=\{p_r:r\in R\}$ | Set of pickup nodes. |
| $D=\{d_r:r\in R\}$ | Set of delivery nodes. |
| $N=P\cup D$ | Set of service nodes, indexed by $i,j$. |
| $s_k,e_k$ | Driver-specific start node and artificial end sink of driver $k$. |
| $N_k$ | Nodes available to driver $k$: $N_k=\{s_k\}\cup N\cup\{e_k\}$. |
| $A_k$ | Feasible directed arcs for driver $k$; arcs entering $s_k$ or leaving $e_k$ are excluded. |

## Parameters

| Symbol | Definition |
|---|---|
| $q_r$ | Demand of request $r$. |
| $Q_k$ | Capacity of driver $k$'s vehicle. |
| $v_r,v_k$ | Required vehicle type of request $r$ and vehicle type of driver $k$. |
| $a_{rk}$ | Compatibility indicator; one if driver $k$ may serve request $r$, and zero otherwise. |
| $d_{ij}$ | Directed travel distance from node $i$ to node $j$. |
| $\tau_{ij}$ | Directed travel time from node $i$ to node $j$. |
| $c_k$ | Operating cost per distance unit for driver $k$. |
| $b_i$ | Load change at node $i$: $b_{p_r}=q_r$, $b_{d_r}=-q_r$, and $b_{s_k}=b_{e_k}=0$. |
| $M$ | A sufficiently large sequencing constant. |

For every $i\in N$ and $k\in K$, arcs incident to an incompatible request can be omitted during preprocessing. Moreover, $d_{i e_k}=\tau_{i e_k}=0$ implements the free endpoint and prevents a hidden return-to-depot charge.

## Decision Variables

| Variable | Definition |
|---|---|
| $x_{ijk}\in\{0,1\}$ | One if driver $k$ traverses arc $(i,j)\in A_k$. |
| $y_{rk}\in\{0,1\}$ | One if request $r$ is assigned to driver $k$. |
| $h_k\in\{0,1\}$ | One if driver $k$ is used. |
| $u_{ik}\ge0$ | Visit position of node $i$ on driver $k$'s route. |
| $L_{ik}\ge0$ | Vehicle load immediately after visiting node $i$. |
| $T_k\ge0$ | Duration of driver $k$'s open route in minutes. |
| $T_{\max}\ge0$ | Maximum route duration over all drivers. |
| $n_k\ge0$ | Number of requests assigned to driver $k$. |

## Objectives

The problem minimizes the vector $F=(f_1,f_2,f_3)$:

$$
\min f_1=\sum_{k\in K}\sum_{(i,j)\in A_k}c_kd_{ij}x_{ijk},
$$

$$
\min f_2=T_{\max},
$$

$$
\min f_3=\frac{1}{|V|}\sum_{v\in V}
\sqrt{\frac{1}{|K_v|}\sum_{k\in K_v}(n_k-\bar n_v)^2},
\qquad
\bar n_v=\frac{1}{|K_v|}\sum_{k\in K_v}n_k.
$$

The first objective minimizes vehicle-specific operating cost. The second minimizes the makespan, thereby limiting the completion time of the longest route. The third minimizes the mean within-type standard deviation of assigned-request counts. Comparing drivers only within the same vehicle type avoids treating incompatible workloads as interchangeable; including idle drivers prevents concentrated assignments from appearing artificially balanced.

## Constraints

Every request is assigned exactly once and only to a compatible driver:

$$
\sum_{k\in K}y_{rk}=1, \qquad r\in R,
$$

$$
y_{rk}\le a_{rk}, \qquad r\in R,\ k\in K.
$$

Assignment is linked to exactly one incoming and one outgoing visit at both request nodes:

$$
\sum_{j:(p_r,j)\in A_k}x_{p_rjk}
=\sum_{i:(i,p_r)\in A_k}x_{ip_rk}=y_{rk},
\qquad r\in R,\ k\in K,
$$

$$
\sum_{j:(d_r,j)\in A_k}x_{d_rjk}
=\sum_{i:(i,d_r)\in A_k}x_{id_rk}=y_{rk},
\qquad r\in R,\ k\in K.
$$

Each used route leaves its driver-specific start once and enters its artificial sink once:

$$
\sum_{j:(s_k,j)\in A_k}x_{s_kjk}=h_k,
\qquad
\sum_{i:(i,e_k)\in A_k}x_{i e_k k}=h_k,
\qquad k\in K.
$$

Vehicle use and assignment are linked by

$$
h_k\le\sum_{r\in R}y_{rk}\le |R|h_k,
\qquad k\in K.
$$

The following sequencing constraints eliminate disconnected subtours and enforce pickup-before-delivery precedence:

$$
u_{jk}\ge u_{ik}+1-M(1-x_{ijk}),
\qquad (i,j)\in A_k,\ j\ne e_k,\ k\in K,
$$

$$
u_{p_rk}+1\le u_{d_rk}+M(1-y_{rk}),
\qquad r\in R,\ k\in K,
$$

$$
u_{s_k k}=0, \qquad k\in K.
$$

Load is propagated along every selected service arc and bounded by vehicle capacity:

$$
L_{jk}\ge L_{ik}+b_j-2Q_k(1-x_{ijk}),
\qquad (i,j)\in A_k,\ j\ne e_k,
$$

$$
L_{jk}\le L_{ik}+b_j+2Q_k(1-x_{ijk}),
\qquad (i,j)\in A_k,\ j\ne e_k,
$$

$$
0\le L_{ik}\le Q_k,\qquad L_{s_k k}=L_{e_k k}=0,
\qquad i\in N_k,\ k\in K.
$$

Finally, route durations, makespan, and request counts are defined by

$$
T_k=\frac{1}{60}\sum_{(i,j)\in A_k}\tau_{ij}x_{ijk},
\qquad T_{\max}\ge T_k,\qquad k\in K,
$$

$$
n_k=\sum_{r\in R}y_{rk},\qquad k\in K.
$$

The degree and start/end constraints create one open route for every used driver. Sequencing connects visited service nodes to that route and enforces precedence. Load propagation guarantees nonnegative loads and capacity feasibility. The last two equations provide the quantities used by the duration and equity objectives. The resulting formulation is a mixed-integer nonlinear multi-objective model because $f_3$ contains square roots; the implemented MOALNS evaluates the three objectives directly, while the PuLP/CBC certificate solves the $f_1$ specialization on small instances.

# Multi-Objective Adaptive Large Neighborhood Search

## Search Control

Following the ALNS framework [3], a solution is represented by one ordered pickup/delivery event sequence per driver; empty sequences represent idle drivers. Regret-3 insertion constructs an initial feasible solution. Its objective vector also provides positive scale values $g_m=\max\{1,f_m(s^0)\}$ for the three criteria.

At every iteration, MOALNS samples a weight vector $w$ from the three-dimensional simplex and evaluates a feasible solution $s$ using the augmented Tchebycheff scalarization

$$
\phi(s\mid w)=\max_{m\in\{1,2,3\}}
\left\{w_m\frac{f_m(s)}{g_m}\right\}
+\rho\sum_{m=1}^{3}w_m\frac{f_m(s)}{g_m},
\qquad \rho=0.05.
$$

Changing $w$ exposes different trade-off regions, while the augmented term helps distinguish solutions tied on the largest weighted deviation. With probability 0.35, an archive member replaces the current solution as the iteration parent; otherwise the current solution is retained. A destroy and a repair operator are sampled according to adaptive weights, and the destroy size is sampled from the configured interval.

The candidate is always considered for the external Pareto archive. Duplicate and dominated objective vectors are rejected, and vectors dominated by the candidate are removed. The archive is bounded at 100 solutions; if necessary, one member from the densest finite-crowding region is discarded. A candidate becomes the current solution if it dominates the current solution, improves the current scalar value, or passes simulated-annealing acceptance,

$$
P(\text{accept})=\exp\left(-\frac{\Delta}{\max(T,10^{-9})}\right),
\qquad \Delta=\phi(s'\mid w)-\phi(s\mid w).
$$

Operators receive rewards of 10 for adding a solution to the archive, 5 for producing a dominating candidate, and 1 for another accepted candidate. Every 15 iterations, each operator weight is updated as

$$
\omega_o\leftarrow(1-\lambda)\omega_o+
\lambda\frac{\pi_o}{\max(1,\nu_o)},
\qquad \lambda=0.25,
$$

where $\pi_o$ and $\nu_o$ are the operator's accumulated reward and usage count in the segment. The temperature is multiplied by 0.995 after each iteration. Search stops at the iteration or wall-clock limit and returns the non-dominated archive.

## Generic Destroy and Repair Operators

The generic destroy set contains four operators [3], [16]:

1. **Random removal** uniformly samples assigned requests.
2. **Worst removal** removes requests with the largest operating-cost saving when both events are deleted.
3. **Related removal** starts from a seed request and selects spatially related requests using pickup-to-pickup distance, delivery-to-delivery distance, and a vehicle-type incompatibility penalty.
4. **Route removal** selects a used driver and removes either its complete request set or a random subset up to the destroy size.

All destroy operators remove pickup and delivery jointly, so partial solutions cannot contain half-served requests. The generic repair set contains greedy, noisy greedy, regret-2, and regret-3 insertion. For each unassigned request, every compatible driver and every feasible pickup/delivery position pair is evaluated, including insertion after the current last event. Greedy selects the best scalarized insertion; noisy greedy perturbs its score to diversify search. Regret-$q$ prioritizes a request according to the loss incurred if its best insertion becomes unavailable, with $q\in\{2,3\}$. Route evaluation does not add a last-node-to-depot edge.

## Free-End Tail Operators

Consider route $k=(s_k,e_1,\ldots,e_h)$, and let $L_t$ be the load immediately after event $e_t$. A cut after position $t<h$ satisfying $L_t=0$ separates a self-contained suffix: every request picked before the cut is also delivered before it. The **tail-removal** operator enumerates such internal zero-load boundaries and removes the largest suffix whose number of requests does not exceed the sampled destroy size. When no admissible boundary exists, it falls back to removing requests having the latest delivery positions.

The **tail-only repair** operator tests only the append pattern

$$
(s_k,e_1,\ldots,e_h,p_r,d_r)
$$

over compatible drivers. Its incremental distance contains the edge from $e_h$ to $p_r$ and the pickup-to-delivery edge, but no return edge. Consequently, the destroy operator exposes a large capacity-safe suffix move, and the repair operator explicitly evaluates alternate free endpoints. Generic operators may reproduce an equivalent reassignment by chance, whereas this pair increases the frequency with which the search exploits the defining structure of an open route. The complete method therefore contains five destroy and five repair operators.

## Decision Support

MOALNS first generates feasible non-dominated routes without imposing a final decision-maker preference. TOPSIS [14] and PROMETHEE II [15] are subsequently applied to normalized cost, maximum-duration, and workload-imbalance values using a user-specified weight vector. TOPSIS is compensatory and ranks alternatives by relative distance from ideal and anti-ideal points. PROMETHEE II is an outranking method based on pairwise preference flows. Both methods rank existing archive members only; they neither modify routes nor affect the optimization comparison.

## Algorithm Flowchart

![MOALNS optimization and decision-support workflow.](figures/moalns_flowchart.svg)

**Figure 1.** MOALNS optimization and post-optimization decision-support workflow.
