# Free-End Tail Reassignment in Multi-Objective Adaptive Large Neighborhood Search for Heterogeneous Open Pickup-and-Delivery Routing

## Abstract

Open pickup-and-delivery routes exhibit a structural asymmetry: changing a route suffix incurs no return-to-depot edge. We study a heterogeneous open pickup-and-delivery vehicle routing problem without time windows, minimizing operating cost, maximum route duration, and within-vehicle-type workload imbalance. An objective-scope diagnostic shows that removing imbalance makes 12.5–71.2% of the three-dimensional non-dominated vectors dominated in the cost--duration projection, supporting a genuine three-objective formulation. We propose a multi-objective adaptive large neighborhood search (MOALNS) with a free-end tail-removal operator and a tail-only compatible-driver repair, randomized augmented Tchebycheff scalarization, simulated-annealing acceptance, adaptive operator weights, and a bounded non-dominated archive. In 160 ablation runs on one heterogeneous road-network instance and three time-window-free Li--Lim-derived instances, the complete method increases mean normalized hypervolume from 0.66522 to 0.67936 relative to removing both tail operators, enlarges the mean archive by 31.9%, and wins 27 of 40 paired instance--seed blocks (Holm-adjusted Wilcoxon $p=1.96\times10^{-4}$). An implementation audit independently verifies all 3,584 archived ablation solutions, while a PuLP/CBC model proves cost optimality on three four-request instances, where both ALNS and MOALNS attain zero gap. In a separate 120-run equal-time comparison on the application instance and nine 25-request derivatives, MOALNS obtains the best aggregate mean hypervolume (0.4233), mean rank (1.8000), and empirical union-front contribution. On ten independent instance means it significantly outperforms MOEA/D, NSGA-II, and heuristic epsilon-constraint after Holm correction. These results identify free-end tail reassignment as a concrete, validated neighborhood for open multi-objective pickup-and-delivery routing.

**Keywords:** pickup and delivery; open vehicle routing;
multi-objective optimization; adaptive large neighborhood search; workload
equity; tail reassignment

## Introduction

The pickup-and-delivery vehicle routing problem (PDVRP) underlies courier,
retail, and on-demand logistics. Every request contains two linked service
events: one vehicle must perform both the pickup and delivery, pickup must
precede delivery, and vehicle capacity must hold along the route
[savelsbergh1995general]. Practical dispatch adds heterogeneous vehicle
compatibility, driver-specific origins, and routes that may end at the last
customer rather than return to a depot.

That last feature changes neighborhood design. In a closed route, moving a
suffix changes both its attachment edge and the return edge. In an open route,
the terminal edge does not exist. A self-contained suffix cut at a zero-load
boundary can therefore be removed and reassigned without paying a
return-to-depot penalty. Generic removal and insertion operators can eventually
produce such moves, but they do not target this structural opportunity.

Cost alone is also insufficient for many dispatch settings. A low-cost plan can
leave one driver with a long completion time or concentrate work on a few
workers. Conversely, balancing routes may require additional travel. We model
these concerns by minimizing total operating cost, maximum route duration, and
workload imbalance among drivers with the same vehicle capability. An
a-posteriori method returns non-dominated alternatives before a dispatcher
applies preferences.

Adaptive large neighborhood search (ALNS) is well suited to paired requests
because destroy--repair moves can jointly change request assignment and both
visit positions [ropke2006alns]. Multi-objective search additionally
requires convergence and diversity [jozefowiez2008multi]. We therefore
develop a multi-objective ALNS (MOALNS) with changing augmented Tchebycheff
preferences and an external Pareto archive.

The contributions are:
1. a three-objective formulation of a heterogeneous open PDVRP with driver-specific starts, vehicle compatibility, capacity, precedence, and workload equity within vehicle type;
2. a pair of open-route-specific operators---zero-load tail removal and tail-only compatible-driver repair---that explicitly exploit the free route endpoint;
3. an empirical objective-scope test showing that the equity objective preserves 12.5–71.2% of otherwise lost non-dominated alternatives on the tested fronts;
4. a reproducible validation chain comprising exact small-instance certificates, an independent route checker, a 160-run paired ablation demonstrating the contribution of each tail component, a 120-run equal-time comparison with NSGA-II, MOEA/D, and epsilon-constraint on ten environments, and time-, parameter-, and decision-weight sensitivity analyses.

## Related Work

Savelsbergh and Sol [savelsbergh1995general] characterize the general
pickup-and-delivery problem. Li and Lim [li2003metaheuristic] introduced
widely used pickup-and-delivery problem with time windows (PDPTW) instances,
and Ropke and Pisinger
[ropke2006alns] established ALNS as a strong framework for the PDPTW.
Our setting removes time windows but adds driver-specific origins,
heterogeneous compatibility, open route endpoints, and three objectives.

Open vehicle routing removes the mandatory depot return. Early constructive
work by Sariklis and Powell [sariklis2000open] and tabu search by Brandão
[brandao2004open] show that this endpoint change deserves specialized
algorithmic treatment. Those studies address delivery routing rather than
paired pickup--delivery precedence. Our tail neighborhood transfers the
free-end insight to self-contained request suffixes. More broadly, Pisinger and
Ropke [pisinger2007general] demonstrate how large-neighborhood components
can be shared across VRP variants, while Parragh et al.
[parragh2008survey] survey problems in which transportation occurs between
paired pickup and delivery locations.
Voigt's recent review of 211 ALNS studies finds that sequence-based removal and
foresighted regret insertion are particularly effective and recommends explicit
operator-level testing [voigt2025operators]. This evidence motivates both
the suffix-oriented neighborhood and its paired ablation in our study.

Multi-objective VRPs combine measures such as cost, fleet use, service quality,
and balance [jozefowiez2008multi]. NSGA-II retains elitist non-dominated
fronts using crowding distance [deb2002nsga2]; MOEA/D decomposes a
multi-objective problem into neighboring scalar subproblems
[zhang2007moead]; and epsilon-constraint methods bound secondary objectives
while optimizing a primary one [mavrotas2009epsilon]. These paradigms form
the predeclared external comparison set for the final study.

Equity requires an explicit workload resource and comparison set. Matl et al.
[matl2018equity] show that these choices materially alter a routing
solution's interpretation. We measure assigned request counts and compare
drivers only within vehicle type, including compatible but idle drivers.

## Problem Definition

### Network and feasibility

Let $\R$ be the requests, $\K$ the drivers, and
$\mathcal{N}=\{p_r,d_r:r\in\R\}$ the service nodes. Request $r$ has pickup
$p_r$, delivery $d_r$, demand $q_r$, and required vehicle type $v_r$. Driver
$k$ starts at $s_k$, has vehicle type $v_k$, capacity $Q_k$, and
per-kilometer cost $c_k$. Parameter $a_{rk}$ equals one if driver $k$ is
compatible with request $r$. Directed distance and travel time are $d_{ij}$ and
$\tau_{ij}$.

A solution contains one event sequence per driver and is feasible if every
request appears exactly once, its pickup and delivery use the same compatible
driver, pickup precedes delivery, and cumulative load remains in
$[0,Q_k]$. Routes start at $s_k$ and terminate at their final service event;
there is no return arc.

For each driver, artificial sink $e_k$ has zero-distance and zero-time incoming
arcs and no outgoing arcs. Let
$\mathcal{N}_k=\{s_k\}\cup\mathcal{N}\cup\{e_k\}$. Binary variable
$x_{ijk}$ indicates that driver $k$ traverses arc $(i,j)$,
$y_{rk}$ assigns request $r$ to driver $k$, and $w_k$ indicates that driver
$k$ is used. Assignment, compatibility, and driver activation are
$$
\begin{aligned}
\sum_{k\in\K}y_{rk}&=1 &&\forall r\in\R,\\
 y_{rk}&\le a_{rk} &&\forall r\in\R,\ k\in\K,\\
 w_k\le\sum_{r\in\R}y_{rk}&\le|\R|w_k &&\forall k\in\K.
\end{aligned}
$$
Every used route leaves its driver-specific start once, reaches its artificial
sink once, and visits both nodes of each assigned request:
$$
\begin{aligned}
\sum_{j\in\mathcal{N}_k\setminus\{s_k\}}x_{s_kjk}
   &=w_k &&\forall k\in\K,\\
 \sum_{i\in\mathcal{N}_k\setminus\{e_k\}}x_{ie_kk}
   &=w_k &&\forall k\in\K,\\
 \sum_{j\in\mathcal{N}_k\setminus\{p_r\}}x_{p_rjk}
 =\sum_{i\in\mathcal{N}_k\setminus\{p_r\}}x_{ip_rk}
   &=y_{rk} &&\forall r,k,\\
 \sum_{j\in\mathcal{N}_k\setminus\{d_r\}}x_{d_rjk}
 =\sum_{i\in\mathcal{N}_k\setminus\{d_r\}}x_{id_rk}
   &=y_{rk} &&\forall r,k.
\end{aligned}
$$
Arcs entering $s_k$ and leaving $e_k$ are excluded. Visit-position variables
$u_{ik}$ impose connectivity, eliminate service-node subtours, and enforce
pickup precedence:
$$
\begin{aligned}
u_{s_kk}&=0 &&\forall k,\\
 u_{jk}&\ge u_{ik}+1-M(1-x_{ijk})
   &&\forall k,\ i\ne e_k,\ j\in\mathcal{N},\\
 u_{p_rk}+1&\le u_{d_rk}+M(1-y_{rk})
   &&\forall r,k,\\
 y_{rk}\le u_{p_rk}&\le 2|\R|y_{rk}
   &&\forall r,k,\\
 y_{rk}\le u_{d_rk}&\le 2|\R|y_{rk}
   &&\forall r,k.
\end{aligned}
$$
For load propagation, define $\delta_{p_r}=q_r$ and
$\delta_{d_r}=-q_r$. Continuous load $L_{ik}$ satisfies
$$
\begin{aligned}
L_{s_kk}&=0 &&\forall k,\\
 L_{jk}&\ge L_{ik}+\delta_j-M(1-x_{ijk})
   &&\forall k,\ i\ne e_k,\ j\in\mathcal{N},\\
 L_{jk}&\le L_{ik}+\delta_j+M(1-x_{ijk})
   &&\forall k,\ i\ne e_k,\ j\in\mathcal{N},\\
 0\le L_{ik}&\le Q_k &&\forall k,\ i\in\mathcal{N},\\
 x_{ijk},y_{rk},w_k&\in\{0,1\} &&\forall i,j,r,k.
\end{aligned}
$$
Together with binary domains for $x$, $y$, and $w$, these constraints ensure
complete assignment, same-driver pairing, compatibility, precedence,
capacity, and one connected open route per used driver. The artificial sink
terminates a route without adding a return-to-depot distance or duration.

### Objectives

The problem is
$$
\min\ \bigl(f_1(x),f_2(x),f_3(y)\bigr)
$$
subject to the preceding feasibility constraints. Operating cost is
$$
f_1(x)=\sum_{k\in\K}\sum_i\sum_{j\ne i}c_kd_{ij}x_{ijk}.
$$
Because all requests are mandatory and vehicle compatibility fixes their
revenue class, profit maximization is equivalent to cost minimization in the
application instance.

Driver travel time in minutes is
$T_k=\sum_{i,j}\tau_{ij}x_{ijk}/60$. With auxiliary variable $Z$,
the completion bottleneck is represented by
$$
\begin{aligned}
Z&\ge T_k &&\forall k\in\K,\\
 f_2(x)&=Z.
\end{aligned}
$$
Equivalently,
$$
f_2(x)=\max_{k\in\K}T_k.
$$

Let $n_k=\sum_ry_{rk}$, $\K_v=\{k:v_k=v\}$, and
$\bar n_v=|\K_v|^{-1}\sum_{k\in\K_v}n_k$. Workload imbalance is
$$
f_3(y)=\frac{1}{|\V|}\sum_{v\in\V}
 \sqrt{\frac{1}{|\K_v|}\sum_{k\in\K_v}(n_k-\bar n_v)^2}.
$$
Idle compatible drivers remain in $\K_v$ so that concentrating all work on one
driver cannot appear balanced. This standard-deviation objective is evaluated
directly by the metaheuristic and makes the full three-objective formulation
nonlinear. The PuLP/CBC validation model optimizes the $f_1$ specialization on
small instances; it is an exact implementation certificate, not an exact
solver for the complete three-objective formulation.

## Multi-Objective ALNS

### Search control

The route representation stores paired pickup/delivery events by driver. A
regret insertion heuristic constructs an initial solution. At each iteration,
a weight vector $w$ is sampled from the three-dimensional simplex. For scale
vector $g$ and $\rho=0.05$, candidate $s$ is evaluated by
$$
\phi(s\mid w)=
 \max_{m=1,2,3}\left\{w_m\frac{f_m(s)}{g_m}\right\}
 +\rho\sum_{m=1}^{3}w_m\frac{f_m(s)}{g_m}.
$$
Changing $w$ exposes different trade-off regions, while augmented Tchebycheff
scalarization can reach non-supported portions that a weighted sum can miss.

The bounded archive retains non-dominated objective vectors. Dominated and
duplicate vectors are rejected; crowding control removes a solution from the
densest finite-crowding region when size exceeds 100. With probability 0.35,
the search restarts an iteration from an archive member. Simulated annealing
accepts a scalar worsening $\Delta$ with probability
$\exp[-\Delta/\max(T,10^{-9})]$. Temperature starts at 0.05 and cools by 0.995.

Operators receive reward 10 for an archive addition, 5 for a dominating
candidate, and 1 for another accepted move. Every 15 iterations, operator
weight $\omega_o$ is updated as
$$
\omega_o\leftarrow(1-\lambda)\omega_o+
 \lambda\frac{\pi_o}{\max(1,\nu_o)},\qquad\lambda=0.25,
$$
where $\pi_o$ and $\nu_o$ are segment reward and usage count.

### Generic destroy and repair

The generic destroy set contains random removal, marginal-cost worst removal,
spatial related-request removal, and route removal. Spatial relatedness uses
pickup-to-pickup and delivery-to-delivery distance plus a vehicle-type
incompatibility penalty; it is not a full positional Shaw measure. Repair uses
greedy, noisy greedy, regret-2, and regret-3 insertion. Every compatible driver
and every feasible pickup/delivery position pair is evaluated, including
pickup at the current endpoint and delivery at the resulting endpoint. Route
evaluation never adds a final-to-depot edge.

### Free-end tail operators

For route $k=(s_k,e_1,\ldots,e_h)$, let $L_t$ denote load immediately after
event $e_t$. A cut after $e_t$ with $L_t=0$ separates a self-contained suffix:
no request picked before the cut can be delivered after it. The
*tail-removal* operator searches internal zero-load boundaries and removes
the largest self-contained suffix not exceeding the sampled destroy size. If no
such suffix exists, it selects requests with the latest delivery positions and
removes both events of each request.

The *tail-repair* operator considers only the append pattern
\[
 (s_k,e_1,\ldots,e_h,p_r,d_r)
\]
over compatible drivers. Its incremental route cost contains the edge from
$e_h$ to $p_r$ and from $p_r$ to $d_r$, but no return edge. It directly tests
whether a removed request or suffix is better assigned after another driver's
free endpoint. Strict compatibility means reassignment occurs among compatible
drivers, not arbitrarily across vehicle classes.

The pair is structurally motivated: tail removal exposes a large assignment
move at a capacity-safe cut, while tail repair cheaply explores alternate free
endpoints. The full search contains five destroy and five repair operators.

## Decision Support

The optimizer returns a non-dominated archive rather than one imposed
compromise. A dispatcher may first apply hard operational thresholds and then
rank the remaining alternatives. The conference scope retains two
complementary methods: the technique for order preference by similarity to an
ideal solution (TOPSIS), a compensatory distance-based method, and PROMETHEE II
(Preference Ranking Organization Method for Enrichment Evaluations), a
pairwise outranking method
[hwang1981topsis,brans1985promethee]. They operate only on feasible archive
members and do not modify routes.

For alternative $i$, TOPSIS vector-normalizes each minimizing criterion,
applies decision weights, and computes distances $D_i^+$ and $D_i^-$ from the
componentwise ideal and anti-ideal. Its closeness score is
$$
C_i=\frac{D_i^-}{D_i^++D_i^-},
$$
which is maximized. PROMETHEE II first min--max transforms each criterion into
a benefit score $b_{im}$. With the linear preference used here,
$$
\pi(i,j)=\sum_m w_m\max(b_{im}-b_{jm},0),\qquad
 \Phi_i=\frac{1}{n}\sum_j\pi(i,j)-\frac{1}{n}\sum_j\pi(j,i),
$$
and the alternative with the largest net flow $\Phi_i$ is selected.
Preference-learning models and the larger multicriteria decision-making (MCDM)
suite are excluded from this study.

## Experimental Design

### Instances and protocol

The Current instance contains 27 requests and nine drivers (six motorcycles and
three pickup trucks), driver-specific origins, and directed OSRM road distances
and durations. Three ablation instances retain 12 requests from the clustered
LC101, random LR101, and mixed LRC101 Li--Lim families
[li2003metaheuristic]. The broader comparison uses nine 25-request
derivatives: LC102, LC105, LC201, LR102, LR105, LR201, LRC102, LRC105, and
LRC201. In every derivative, time windows and service times are removed and
four homogeneous vehicles are supplied. These are controlled no-time-window
derivatives, not results on the original PDPTW benchmarks.

<a id="tab-instances"></a>
**Table — Experimental instance groups.**

| Group | Instances | Requests | Drivers | Travel data |
|---|---|---|---|---|
| Application | 1 | 27 | 9 heterogeneous | OSRM road network |
| Tail ablation | 3 | 12 | 4 homogeneous | Euclidean |
| Broader comparison | 9 | 25 | 4 homogeneous | Euclidean |

The ablation compares the full method with removal of tail destroy, tail
repair, and both. Each configuration uses seeds 42--51, 5,000 maximum
iterations, and 600 seconds per instance--seed run. This gives
$4\times4\times10=160$ runs. All configurations share initialization,
scalarization, generic operators, acceptance, adaptation, and archive settings.

For normalized hypervolume (HV), all relevant archives in an instance--seed
block use common componentwise bounds and reference point $(1.1,1.1,1.1)$;
higher is better [zitzler1999multiobjective]. We also report archive size,
spacing, and contribution to the empirical union front. Paired differences use
two-sided Wilcoxon signed-rank tests with Holm correction over the three
predeclared tail ablations.

### Implementation validation

Validation is deliberately independent of the solver's feasibility functions.
The checker deserializes raw routes and separately verifies coverage, duplicate
events, same-driver pairing, precedence, compatibility, capacity, open-route
distance, duration, and all three reported objectives.

A PuLP/CBC arc-flow model supplies exact cost certificates on three
four-request instances. These small cases test formulation and implementation;
they are not evidence of large-instance performance.

### External comparison

The production benchmark compares tail-enabled MOALNS with route-based
NSGA-II, MOEA/D, and heuristic epsilon-constraint. All methods use the same
route representation, feasibility evaluator, objective functions, initial
construction, and wall-clock limit. NSGA-II applies non-dominated sorting,
crowding distance, route inheritance, and destroy--repair mutation with a
population of 50. MOEA/D uses 50 simplex weights, five-neighbor scalar
subproblems, route crossover, and destroy--repair mutation. Epsilon-constraint
minimizes cost while bounding duration and imbalance on a $5\times5$ grid; it
is a heuristic baseline rather than exact AUGMECON.

The external comparison uses the Current instance and nine 25-request
derivatives, seeds 42--44, and an equal 180-second wall-clock limit:
$10\times3\times4=120$ runs. Fixed
per-instance normalization bounds are pooled across every algorithm and seed.
We report normalized HV, spacing, archive size, empirical coverage, and
contribution to the instance--seed union front.

The omnibus comparison uses a Friedman test over 30 paired instance--seed
blocks. Because repeated seeds from one instance are not independent routing
environments, the primary confirmatory analysis first averages seeds within
each instance and applies a Friedman test to ten independent instance means.
Six pairwise Wilcoxon tests on these means use Holm correction. Block-level
tests are retained as supporting stochastic-run analyses.

### Sensitivity and decision analysis

Time-budget sensitivity uses the three 12-request derivatives, seeds 42--44,
and limits of 60, 180, and 600 seconds. One-factor-at-a-time parameter
sensitivity evaluates the baseline and 17 alternatives on the same three
instances and seeds under 120-second limits, giving 162 runs. The factors are
destroy size, archive size, archive-parent probability, reaction factor,
cooling, initial temperature, adaptation-segment length, and augmented
Tchebycheff parameter $\rho$.

Finally, TOPSIS and PROMETHEE II are applied to the feasible Current-instance
archive over 231 simplex-grid weight vectors. We report selection agreement,
the number of distinct selected plans, and the objective ranges induced by
preference changes. This layer ranks existing routes only; it does not enter
algorithm-performance testing.

## Results

### Does the third objective add information?

For each instance, all unique archive vectors are filtered in three dimensions
and then projected onto cost--maximum-duration. A vector that becomes dominated
after projection was non-dominated only because of workload imbalance. As shown
in [Table](#tab-objective-scope), 12.5–71.2% of the
three-objective front is lost under the two-objective projection. At least one
point is lost on every instance. Imbalance therefore adds information
throughout the test set, although its contribution is much stronger on Current
and the LC and LRC105 derivatives than on LRC102 and LRC201.

<a id="tab-objective-scope"></a>
**Table — Information contributed by workload imbalance on empirical union fronts. ``Required'' is the percentage of 3D non-dominated vectors dominated after projection onto cost--duration.**

| Instance | 3D front | 2D survivors | Required (\ |
|---|---|---|---|
| Current | 66 | 19 | 71.2 |
| LC102-25 | 9 | 5 | 44.4 |
| LC105-25 | 11 | 6 | 45.5 |
| LC201-25 | 12 | 7 | 41.7 |
| LR102-25 | 10 | 7 | 30.0 |
| LR105-25 | 7 | 5 | 28.6 |
| LR201-25 | 9 | 7 | 22.2 |
| LRC102-25 | 8 | 7 | 12.5 |
| LRC105-25 | 10 | 5 | 50.0 |
| LRC201-25 | 8 | 7 | 12.5 |

<a id="fig-projection"></a>
![Survival of three-objective non-dominated vectors after projection onto cost--maximum-duration. Lower survival means that imbalance preserves more otherwise dominated alternatives.](../outputs/broader_paper/objective_conflict/fig_projection_survival.pdf)

*Figure — Survival of three-objective non-dominated vectors after projection onto cost--maximum-duration. Lower survival means that imbalance preserves more otherwise dominated alternatives.*

Spearman coefficients on Pareto points are descriptive rather than
population-level tests because front points are dependent. Cost--duration
correlations range from $-0.527$ to $-0.992$ on the all-algorithm fronts, while
cost--imbalance correlations range from $-0.911$ to $-1.000$. Strong
correlation does not make an objective redundant: the projection test directly
counts vectors whose status depends on imbalance and is consequently the
primary objective-scope evidence.

### Exact and independent validation

CBC proves optimality for all three four-request instances
([Table](#tab-exact)). Both single-objective ALNS and the minimum-cost member
of the MOALNS archive match each optimum, and the independent checker
accepts every route.

<a id="tab-exact"></a>
**Table — Small-instance exact cost validation.**

| Instance | CBC optimum | MOALNS gap (\ |  |
|---|---|---|---|
| LC101-4 | 40.4967 | 0.0 | 0.0 |
| LR101-4 | 145.4274 | 0.0 | 0.0 |
| LRC101-4 | 63.3284 | 0.0 | 0.0 |

Across the 160 tail-ablation runs, the checker independently evaluates 3,584
archived solutions. All 3,584 are feasible and all recomputed objective vectors
match the solver outputs. This rules out feasibility leakage as an explanation
for the ablation result.

### Tail-operator ablation

<a id="tab-tail-ablation"></a>
**Table — Tail ablation over 40 paired instance--seed blocks. Mean $\Delta$HV is configuration minus full MOALNS; W--T--L counts the ablated configuration against the full method.**

| Configuration | Mean HV | Archive | Mean | W--T--L | Holm p |
|---|---|---|---|---|---|
| Full MOALNS | **0.67936** | **26.25** | --- | --- | --- |
| No tail repair | 0.67267 | 21.90 | -0.00670 | 7--9--24 | 0.002976 |
| No tail removal | 0.66928 | 21.55 | -0.01008 | 6--10--24 | 0.000712 |
| No tail operators | 0.66522 | 19.90 | -0.01414 | 4--9--27 | 1.96×10^-4 |

Removing both tail operators reduces mean HV by 0.01414; equivalently, the full
method improves mean HV by 2.13% relative to the joint ablation. Mean archive
size increases from 19.90 to 26.25 (31.9%), and empirical union-front
contribution increases from 408 to 712 (74.5%). The full method wins 27
blocks, ties nine, and loses four. The adjusted test is significant.

Both components matter independently. Removing tail removal produces the
larger mean loss, while removing tail repair also causes a significant
decrease. The joint loss is smaller than the sum of individual losses, which is
consistent with partial overlap: generic operators can occasionally reproduce
a tail move, but not with the same search frequency.

<a id="fig-tail-hv"></a>
![Paired hypervolume change of each ablation relative to full MOALNS. Diamonds indicate means, horizontal blue lines indicate medians, and the dashed line marks no change. Negative values favor the full method.](../outputs/paper/tail_ablation/paired_hv_delta_vs_baseline.pdf)

*Figure — Paired hypervolume change of each ablation relative to full MOALNS. Diamonds indicate means, horizontal blue lines indicate medians, and the dashed line marks no change. Negative values favor the full method.*

The benefit is instance-dependent. The largest absolute gain over the joint
ablation is on Current (0.04337 HV), followed by LC101-12 (0.00744) and
LR101-12 (0.00566). LRC101-12 is nearly invariant across configurations and
contributes little discrimination. This pattern supports the structural
argument: tail reassignment is most useful when heterogeneous assignments and
driver-specific starts create meaningful endpoint choices.

### External algorithm comparison

[Table](#tab-hv-instance) reports the broader benchmark. MOALNS has the
highest mean HV on nine of ten instances; NSGA-II leads on LRC201-25. Relative
standard deviations are large on several derivatives because only three seeds
are available, so inference is based on paired instance means rather than on
the aggregate mean alone.

<a id="tab-hv-instance"></a>
**Table — Normalized HV by instance (mean over three seeds). Best means are bold.**

|  | MOALNS | MOEA/D | NSGA-II | Epsilon |
|---|---|---|---|---|
| Current | **.7328** | .6735 | .5879 | .4216 |
| LC102-25 | **.5149** | .1074 | .0889 | .1697 |
| LC105-25 | **.5346** | .0981 | .0727 | .1181 |
| LC201-25 | **.4499** | .1223 | .1359 | .3268 |
| LR102-25 | **.3968** | .2019 | .1633 | .2423 |
| LR105-25 | **.3645** | .2444 | .1864 | .3218 |
| LR201-25 | **.3528** | .1836 | .1240 | .2321 |
| LRC102-25 | **.2456** | .0708 | .0841 | .0562 |
| LRC105-25 | **.3629** | .1731 | .0857 | .1475 |
| LRC201-25 | .2778 | .1678 | **.3269** | .3193 |

<a id="fig-production-hv"></a>
![Normalized hypervolume by instance under equal 180-second budgets. Error bars show one standard deviation over three seeds.](../outputs/broader_paper/figures/fig_hypervolume_by_instance.pdf)

*Figure — Normalized hypervolume by instance under equal 180-second budgets. Error bars show one standard deviation over three seeds.*

Aggregating the 30 paired blocks, MOALNS obtains the highest mean HV
(0.4233), best mean rank (1.8000), most first-place results (17), largest mean
archive (8.83), and largest empirical union-front contribution (185).
NSGA-II has the smallest spacing, illustrating why spacing alone is not a
convergence measure: its mean HV is the lowest.

<a id="tab-production-overall"></a>
**Table — Aggregate performance across 30 instance--seed blocks. HV, wins, archive size, and union contribution are maximized; rank is minimized.**

| Method | Mean HV | HV rank | Wins | Archive | Union |
|---|---|---|---|---|---|
| MOALNS | **.4233** | **1.8000** | **17** | **8.83** | **185** |
| MOEA/D | .2043 | 2.7000 | 3 | 6.30 | 67 |
| NSGA-II | .1856 | 3.1667 | 3 | 7.77 | 74 |
| Epsilon | .2355 | 2.3333 | 7 | 8.20 | 100 |

The Friedman test on the ten independent instance means rejects equal
performance ($\chi^2=15.48$, $p=0.00145$). As
[Table](#tab-production-stats) shows, MOALNS exceeds MOEA/D on all ten
instances and exceeds NSGA-II and epsilon-constraint on nine. All three
comparisons remain significant after Holm correction. The supporting
block-level analysis reaches the same conclusion
($\chi^2=18.04$, $p=4.32\times10^{-4}$); adjusted pairwise $p$-values are
$2.20\times10^{-4}$, $5.53\times10^{-5}$, and 0.01195, respectively.

<a id="tab-production-stats"></a>
**Table — Paired Wilcoxon comparisons on ten independent instance-mean hypervolumes with Holm correction over all six algorithm pairs. W--T--L is for MOALNS.**

| Comparator | Mean | W--T--L | Holm p |
|---|---|---|---|
| MOEA/D | .2190 | 10--0--0 | .01172 |
| NSGA-II | .2377 | 9--0--1 | .01953 |
| Epsilon | .1877 | 9--0--1 | .01953 |

Coverage supports the same interpretation. On average, MOALNS dominates
35.0% of MOEA/D, 37.7% of NSGA-II, and 33.5% of epsilon archive members.
The reverse coverages are 21.4%, 16.9%, and 18.9%, respectively. These
nonzero reverse values prevent a claim of universal dominance.

Mean runtimes are 180.024, 180.045, 180.037, and 180.040 seconds for
MOALNS, MOEA/D, NSGA-II, and epsilon-constraint. The independent checker
recomputes all constraints and objectives for 933 production archive members;
all 933 pass.

### Time and parameter sensitivity

Increasing the budget improves front quality
([Table](#tab-time-sensitivity)). Relative to 600 seconds, the 180-second
setting loses 0.0152 mean HV and the 60-second setting loses 0.0825; both paired
differences are significant after Holm correction ($p=0.00781$). Thus the
broader 180-second comparison is a fair equal-time test, not evidence that
MOALNS has converged.

<a id="tab-time-sensitivity"></a>
**Table — Time-budget sensitivity over nine paired blocks.**

| Budget (s) | Mean HV | Mean rank | Archive | Holm p vs 600 |
|---|---|---|---|---|
| 60 | .6700 | 3.000 | 8.33 | .00781 |
| 180 | .7373 | 1.944 | 12.00 | .00781 |
| 600 | **.7525** | **1.056** | **15.44** | --- |

The 162-run one-factor-at-a-time study finds no alternative significantly
different from the baseline after correcting 17 comparisons. Reducing destroy
size from 2--7 to 1--3 is the only variant with a higher mean HV
(0.8045 versus 0.8007), but it wins only four of nine paired blocks
($p_{\mathrm{Holm}}=1.0$). Removing the Tchebycheff augmentation
($\rho=0$) causes the largest mean loss, $-0.0705$, and loses all nine blocks,
although the adjusted $p=0.0664$ narrowly exceeds 0.05. The predeclared
baseline is therefore retained; the study suggests that augmentation matters
and that small destroy sizes deserve a larger confirmatory experiment, rather
than supporting post-hoc retuning.

<a id="fig-parameter-sensitivity"></a>
![Mean normalized hypervolume in the one-factor-at-a-time parameter study. Error bars represent variation over the nine instance--seed blocks.](../outputs/studies/moalns_parameter_sensitivity_wallclock/analysis/mean_hypervolume.pdf)

*Figure — Mean normalized hypervolume in the one-factor-at-a-time parameter study. Error bars represent variation over the nine instance--seed blocks.*

### Decision-weight sensitivity

Across 231 weight vectors, TOPSIS selects 16 distinct plans and PROMETHEE II
selects ten. Their modal plans account for 45.0% and 24.7% of weight vectors,
respectively, and both methods choose the same plan for only 95 vectors
(41.1%). Selected TOPSIS plans span costs of 150,052--186,784 VND, maximum
durations of 50.54--104.27 minutes, and imbalance of 0.471--3.392; PROMETHEE II
spans the same extremes. The selected route is consequently preference
dependent, which supports retaining the Pareto archive and reporting both a
compensatory and an outranking decision aid instead of declaring one universal
compromise.

<a id="fig-modm-sensitivity"></a>
![Selection stability of TOPSIS and PROMETHEE II over 231 cost--duration--imbalance weight vectors.](../outputs/studies/modm_weight_sensitivity/modm_weight_stability.pdf)

*Figure — Selection stability of TOPSIS and PROMETHEE II over 231 cost--duration--imbalance weight vectors.*

## Operational Use

For deployment, the system receives requests, compatible vehicle availability,
driver origins, and directed road distance/time matrices. Each archive member
is a feasible dispatch plan. A dispatcher may first reject solutions exceeding
a duration or cost threshold, then use TOPSIS or PROMETHEE II to select a
compromise. The selected route list can be dispatched directly because the
decision layer never synthesizes or alters routes.

The open-route assumption fits operations in which a driver may finish at the
last delivery. If a depot return is mandatory, the tail neighborhood loses its
free-end rationale and the evaluator must include the closing edge. Rolling
horizon use should freeze executed events, update travel matrices, and rerun
the optimizer for remaining requests.

## Limitations

The broader comparison contains ten routing environments, but nine are
25-request time-window-free derivatives rather than untouched standard
benchmarks, and only three seeds were affordable. The Current instance is the
only heterogeneous road-network case. The exact certificate covers
four-request cases only, and the objective-conflict analysis is empirical and
depends on the discovered union front. NSGA-II, MOEA/D, and epsilon-constraint
share the route representation, initialization, feasibility evaluator, and
some neighborhood code with MOALNS; this controls implementation
differences but is weaker than comparison with independent mature solvers.
Moreover, the epsilon-constraint implementation is heuristic rather than an
exact AUGMECON method.

Request count is an interpretable equity resource but does not reflect demand,
distance, or service difficulty. Future work should compare count-, duration-,
and income-based equity. Service times, time-dependent congestion, breaks, and
shift limits are absent. The parameter study has only nine paired blocks and
the decision-weight sensitivity study uses one application archive, so both are
diagnostic rather than definitive. Larger independent open-PDVRP benchmarks,
more heterogeneous fleets, and confirmatory testing of the 1--3 destroy-size
variant are the main next steps.

## Conclusion

This paper identifies a free-end structural opportunity in heterogeneous open
pickup-and-delivery routing and encodes it as tail removal and tail-only repair
within a three-objective ALNS. Workload imbalance preserves 12.5--71.2% of the
empirical three-objective fronts that would be lost in a cost--duration model.
The tail pair significantly improves hypervolume, archive size, and empirical
front contribution, while independent and exact checks support implementation
correctness. In the ten-environment external comparison, MOALNS has the best
aggregate mean HV and rank and significantly exceeds all three baselines on
independent instance means. Sensitivity results show continued gains with time,
no statistically justified post-hoc parameter replacement, and substantial
dependence of the final dispatch on decision weights. Together, the evidence
supports tail reassignment as a useful open-route neighborhood while preserving
clear limits on benchmark scale and baseline independence.

## Reproducibility Statement

The repository provides source code, instance manifests, seeds, raw Pareto
archives, per-run reports, an independent checker, a PuLP/CBC exact model, and
scripts for the objective-conflict analysis, tail ablation, and production
comparison. The ablation is launched with
`scripts/studies/run_moalns_ablation.ps1`; the external benchmark uses
`scripts/experiments/run_conference_production.ps1`. Time, parameter,
and decision-weight
sensitivity are reproduced by
`scripts/studies/run_time_budget_sensitivity.ps1`,
`scripts/studies/run_moalns_parameter_sensitivity.ps1`, and
`scripts/studies/run_modm_weight_sensitivity.ps1`, respectively.

## References

- **savelsbergh1995general.** Savelsbergh, Martin W. P.; Sol, Marc (1995). The General Pickup and Delivery Problem. *Transportation Science, 29(1), 17–29*. https://doi.org/10.1287/trsc.29.1.17
- **li2003metaheuristic.** Li, Haibing; Lim, Andrew (2003). A Metaheuristic for the Pickup and Delivery Problem with Time Windows. *International Journal on Artificial Intelligence Tools, 12(2), 173–186*. https://doi.org/10.1142/S0218213003001186
- **ropke2006alns.** Ropke, Stefan; Pisinger, David (2006). An Adaptive Large Neighborhood Search Heuristic for the Pickup and Delivery Problem with Time Windows. *Transportation Science, 40(4), 455–472*. https://doi.org/10.1287/trsc.1050.0135
- **jozefowiez2008multi.** Jozefowiez, Nicolas; Semet, Frédéric; Talbi, El-Ghazali (2008). Multi-objective Vehicle Routing Problems. *European Journal of Operational Research, 189(2), 293–309*. https://doi.org/10.1016/j.ejor.2007.05.055
- **deb2002nsga2.** Deb, Kalyanmoy; Pratap, Amrit; Agarwal, Sameer; Meyarivan, T. (2002). A Fast and Elitist Multiobjective Genetic Algorithm: NSGA-II. *IEEE Transactions on Evolutionary Computation, 6(2), 182–197*. https://doi.org/10.1109/4235.996017
- **zhang2007moead.** Zhang, Qingfu; Li, Hui (2007). MOEA/D: A Multiobjective Evolutionary Algorithm Based on Decomposition. *IEEE Transactions on Evolutionary Computation, 11(6), 712–731*. https://doi.org/10.1109/TEVC.2007.892759
- **mavrotas2009epsilon.** Mavrotas, George (2009). Effective Implementation of the Epsilon-Constraint Method in Multi-Objective Mathematical Programming Problems. *Applied Mathematics and Computation, 213(2), 455–465*. https://doi.org/10.1016/j.amc.2009.03.037
- **zitzler1999multiobjective.** Zitzler, Eckart; Thiele, Lothar (1999). Multiobjective Evolutionary Algorithms: A Comparative Case Study and the Strength Pareto Approach. *IEEE Transactions on Evolutionary Computation, 3(4), 257–271*. https://doi.org/10.1109/4235.797969
- **matl2018equity.** Matl, Piotr; Hartl, Richard F.; Vidal, Thibaut (2018). Workload Equity in Vehicle Routing Problems: A Survey and Analysis. *Transportation Science, 52(2), 239–260*. https://doi.org/10.1287/trsc.2017.0744
- **sariklis2000open.** Sariklis, D.; Powell, S. (2000). A Heuristic Method for the Open Vehicle Routing Problem. *Journal of the Operational Research Society, 51(5), 564–573*. https://doi.org/10.2307/254187
- **brandao2004open.** Brandão, José (2004). A Tabu Search Algorithm for the Open Vehicle Routing Problem. *European Journal of Operational Research, 157(3), 552–564*. https://doi.org/10.1016/S0377-2217(03)00238-8
- **pisinger2007general.** Pisinger, David; Røpke, Stefan (2007). A General Heuristic for Vehicle Routing Problems. *Computers & Operations Research, 34(8), 2403–2435*. https://doi.org/10.1016/j.cor.2005.09.012
- **parragh2008survey.** Parragh, Sophie N.; Doerner, Karl F.; Hartl, Richard F. (2008). A Survey on Pickup and Delivery Problems. Part II: Transportation between Pickup and Delivery Locations. *Journal für Betriebswirtschaft, 58(2), 81–117*. https://doi.org/10.1007/s11301-008-0036-4
- **hwang1981topsis.** Hwang, Ching-Lai; Yoon, Kwangsun (1981). Multiple Attribute Decision Making: Methods and Applications---A State-of-the-Art Survey. *, 186*. https://doi.org/10.1007/978-3-642-48318-9
- **brans1985promethee.** Brans, Jean-Pierre; Vincke, Philippe (1985). Note---A Preference Ranking Organisation Method. *Management Science, 31(6), 647–656*. https://doi.org/10.1287/mnsc.31.6.647
- **voigt2025operators.** Voigt, Stefan (2025). A Review and Ranking of Operators in Adaptive Large Neighborhood Search for Vehicle Routing Problems. *European Journal of Operational Research, 322(2), 357–375*. https://doi.org/10.1016/j.ejor.2024.05.033
