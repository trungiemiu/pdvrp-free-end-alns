"""Pareto-based multi-objective ALNS for heterogeneous open PDVRP."""

import argparse
import json
import math
import os
import random
import time

import numpy as np
import pandas as pd

import alns_pdvrp_solver as single


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
REPORT_DIR = os.path.join(BASE_DIR, "outputs", "reports")
ARCHIVE_PATH = os.path.join(REPORT_DIR, "moalns_pareto_archive.csv")
LOG_PATH = os.path.join(REPORT_DIR, "moalns_search_log.csv")
REPORT_PATH = os.path.join(REPORT_DIR, "moalns_solver_report.csv")
OBJECTIVES = ("total_cost_vnd", "max_route_duration_minutes", "workload_imbalance")
EPSILON = 1e-9


class SearchTimeLimit(RuntimeError):
    """Raised when an in-progress destroy/repair operation reaches its deadline."""


def parse_args():
    parser = argparse.ArgumentParser(description="Three-objective MOALNS for open PDVRP.")
    parser.add_argument("--iterations", type=int, default=5000)
    parser.add_argument("--time-limit", type=float, default=180.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-remove", type=int, default=2)
    parser.add_argument("--max-remove", type=int, default=7)
    parser.add_argument("--archive-size", type=int, default=100)
    parser.add_argument("--segment-length", type=int, default=15)
    parser.add_argument("--reaction-factor", type=float, default=0.25)
    parser.add_argument("--cooling-rate", type=float, default=0.995)
    parser.add_argument("--initial-temperature", type=float, default=0.05)
    parser.add_argument("--archive-parent-prob", type=float, default=0.35)
    parser.add_argument("--tchebycheff-rho", type=float, default=0.05)
    parser.add_argument("--scalarization", choices=["tchebycheff", "weighted_sum"],
                        default="tchebycheff")
    parser.add_argument("--disable-adaptation", action="store_true")
    parser.add_argument("--disable-sa", action="store_true")
    parser.add_argument("--destroy-operators", default=",".join(single.DESTROY_OPERATORS))
    parser.add_argument("--repair-operators", default=",".join(single.REPAIR_OPERATORS))
    parser.add_argument("--variant-id", default="baseline")
    parser.add_argument("--data-dir", default=DATA_DIR)
    parser.add_argument("--output-dir", default=REPORT_DIR)
    parser.add_argument("--instance-id", default="current")
    return parser.parse_args()


def load_duration_matrix(data_dir=DATA_DIR):
    candidates = [
        os.path.join(data_dir, "duration_matrix_osrm_seconds.csv"),
        os.path.join(data_dir, "duration_matrix.csv"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return pd.read_csv(path, index_col=0), path
    raise FileNotFoundError("No duration matrix found in data/.")


def route_duration_seconds(sequence, driver, order_lookup, duration_matrix):
    current = driver["start_node"]
    duration = 0.0
    for action in sequence:
        node = single.action_node(action, order_lookup)
        duration += float(duration_matrix.loc[current, node])
        current = node
    return duration


def workload_imbalance(counts, driver_lookup):
    """Mean within-vehicle-type stddev, including idle eligible drivers."""
    groups = {}
    for driver_id, driver in driver_lookup.items():
        groups.setdefault(driver["vehicle_type"], []).append(float(counts[driver_id]))
    return float(np.mean([np.std(values) for values in groups.values()]))


def multi_metrics(routes, driver_lookup, order_lookup, distance_matrix, duration_matrix):
    total_cost = 0.0
    total_distance = 0.0
    durations = {}
    counts = {}
    assigned = []
    for driver_id, sequence in routes.items():
        route_metrics = single.sequence_metrics(
            sequence, driver_lookup[driver_id], order_lookup, distance_matrix
        )
        if route_metrics is None:
            return None
        total_cost += route_metrics["cost"]
        total_distance += route_metrics["distance"]
        durations[driver_id] = route_duration_seconds(
            sequence, driver_lookup[driver_id], order_lookup, duration_matrix
        )
        counts[driver_id] = len(single.route_orders(sequence))
        assigned.extend(single.route_orders(sequence))
    if len(assigned) != len(order_lookup) or len(assigned) != len(set(assigned)):
        return None
    return {
        "total_cost_vnd": total_cost,
        "max_route_duration_minutes": max(durations.values(), default=0.0) / 60.0,
        "workload_imbalance": workload_imbalance(counts, driver_lookup),
        "total_distance_km": total_distance,
        "used_drivers": sum(count > 0 for count in counts.values()),
        "max_orders_per_driver": max(counts.values(), default=0),
    }


def objective_vector(metrics):
    return np.array([metrics[name] for name in OBJECTIVES], dtype=float)


def dominates(left, right):
    a, b = objective_vector(left), objective_vector(right)
    return bool(np.all(a <= b + EPSILON) and np.any(a < b - EPSILON))


def same_objectives(left, right):
    return bool(np.allclose(objective_vector(left), objective_vector(right), rtol=0, atol=1e-7))


def crowding_distances(entries):
    size = len(entries)
    if size <= 2:
        return [math.inf] * size
    crowding = np.zeros(size)
    values = np.array([objective_vector(entry["metrics"]) for entry in entries])
    for column in range(values.shape[1]):
        order = np.argsort(values[:, column])
        crowding[order[0]] = crowding[order[-1]] = math.inf
        spread = values[order[-1], column] - values[order[0], column]
        if spread <= EPSILON:
            continue
        for position in range(1, size - 1):
            crowding[order[position]] += (
                values[order[position + 1], column] - values[order[position - 1], column]
            ) / spread
    return crowding.tolist()


def update_archive(archive, routes, metrics, limit):
    if any(same_objectives(entry["metrics"], metrics) for entry in archive):
        return archive, False
    if any(dominates(entry["metrics"], metrics) for entry in archive):
        return archive, False
    survivors = [entry for entry in archive if not dominates(metrics, entry["metrics"])]
    survivors.append({"routes": single.clone_routes(routes), "metrics": dict(metrics)})
    if len(survivors) > limit:
        crowding = crowding_distances(survivors)
        remove_index = min(range(len(survivors)), key=lambda index: crowding[index])
        added = remove_index != len(survivors) - 1
        survivors.pop(remove_index)
        return survivors, added
    return survivors, True


def random_weights(rng):
    draws = np.array([rng.expovariate(1.0) for _ in OBJECTIVES])
    return draws / draws.sum()


def scalar_value(metrics, weights, scales, scalarization="tchebycheff", rho=0.05):
    normalized = objective_vector(metrics) / scales
    weighted = weights * normalized
    if scalarization == "weighted_sum":
        return float(np.sum(weighted))
    # Augmented Tchebycheff improves coverage of non-convex Pareto regions.
    return float(np.max(weighted) + rho * np.sum(weighted))


def partial_values(routes, driver_lookup, order_lookup, distance_matrix, duration_matrix):
    costs, durations, counts = {}, {}, {}
    for driver_id, sequence in routes.items():
        route_metrics = single.sequence_metrics(
            sequence, driver_lookup[driver_id], order_lookup, distance_matrix
        )
        costs[driver_id] = route_metrics["cost"]
        durations[driver_id] = route_duration_seconds(
            sequence, driver_lookup[driver_id], order_lookup, duration_matrix
        ) / 60.0
        counts[driver_id] = len(single.route_orders(sequence))
    return costs, durations, counts


def insertion_options(
    order_id, routes, driver_lookup, order_lookup, distance_matrix,
    duration_matrix, weights, scales, noise, rng, deadline=None,
    scalarization="tchebycheff", rho=0.05, tail_only=False,
):
    order = order_lookup[order_id]
    costs, durations, counts = partial_values(
        routes, driver_lookup, order_lookup, distance_matrix, duration_matrix
    )
    base_total_cost = sum(costs.values())
    options = []
    for driver_id, driver in driver_lookup.items():
        if deadline is not None and time.perf_counter() >= deadline:
            raise SearchTimeLimit()
        if driver["vehicle_type"] != order["required_vehicle"]:
            continue
        base = routes[driver_id]
        pickup_positions = [len(base)] if tail_only else range(len(base) + 1)
        for pickup_position in pickup_positions:
            if deadline is not None and time.perf_counter() >= deadline:
                raise SearchTimeLimit()
            for delivery_position in range(pickup_position + 1, len(base) + 2):
                if tail_only and delivery_position != len(base) + 1:
                    continue
                sequence = list(base)
                sequence.insert(pickup_position, (order_id, "pickup"))
                sequence.insert(delivery_position, (order_id, "delivery"))
                route_metrics = single.sequence_metrics(
                    sequence, driver, order_lookup, distance_matrix
                )
                if route_metrics is None:
                    continue
                candidate_durations = dict(durations)
                candidate_counts = dict(counts)
                candidate_durations[driver_id] = route_duration_seconds(
                    sequence, driver, order_lookup, duration_matrix
                ) / 60.0
                candidate_counts[driver_id] += 1
                metrics = {
                    "total_cost_vnd": base_total_cost - costs[driver_id] + route_metrics["cost"],
                    "max_route_duration_minutes": max(candidate_durations.values()),
                    "workload_imbalance": workload_imbalance(candidate_counts, driver_lookup),
                }
                score = scalar_value(metrics, weights, scales, scalarization, rho)
                if noise:
                    score *= rng.uniform(1.0 - noise, 1.0 + noise)
                options.append({"driver_id": driver_id, "sequence": sequence, "score": score})
    return sorted(options, key=lambda option: option["score"])


def repair_multi(
    partial, removed, repair_name, driver_lookup, order_lookup,
    distance_matrix, duration_matrix, weights, scales, rng, deadline=None,
    scalarization="tchebycheff", rho=0.05,
):
    routes = single.clone_routes(partial)
    unassigned = list(removed)
    while unassigned:
        if deadline is not None and time.perf_counter() >= deadline:
            raise SearchTimeLimit()
        candidates = []
        for order_id in unassigned:
            options = insertion_options(
                order_id, routes, driver_lookup, order_lookup, distance_matrix,
                duration_matrix, weights, scales,
                0.15 if repair_name == "noisy_greedy" else 0.0, rng, deadline,
                scalarization, rho,
                repair_name == "tail_greedy",
            )
            if not options:
                raise RuntimeError("No feasible insertion for " + order_id)
            best = options[0]
            second = options[min(1, len(options) - 1)]
            third = options[min(2, len(options) - 1)]
            if repair_name == "regret_2":
                priority = second["score"] - best["score"]
            elif repair_name == "regret_3":
                priority = second["score"] + third["score"] - 2 * best["score"]
            else:
                priority = -best["score"]
            candidates.append((priority, order_id, best))
        _, selected_order, selected = max(candidates, key=lambda item: (item[0], item[1]))
        routes[selected["driver_id"]] = selected["sequence"]
        unassigned.remove(selected_order)
    return routes


def archive_ranges(archive):
    values = np.array([objective_vector(entry["metrics"]) for entry in archive])
    return values.min(axis=0), values.max(axis=0)


def run_moalns(order_lookup, driver_lookup, distance_matrix, duration_matrix, args):
    rng = random.Random(args.seed)
    started = time.perf_counter()
    deadline = started + args.time_limit if args.time_limit > 0 else None
    initial_routes, _ = single.build_initial_solution(
        order_lookup, driver_lookup, distance_matrix, rng, 0.0
    )
    initialization_seconds = time.perf_counter() - started
    initial_metrics = multi_metrics(
        initial_routes, driver_lookup, order_lookup, distance_matrix, duration_matrix
    )
    scales = np.maximum(objective_vector(initial_metrics), np.array([1.0, 1.0, 1.0]))
    current, current_metrics = single.clone_routes(initial_routes), dict(initial_metrics)
    archive = [{"routes": single.clone_routes(current), "metrics": dict(current_metrics)}]

    destroy_names = [name.strip() for name in args.destroy_operators.split(",") if name.strip()]
    repair_names = [name.strip() for name in args.repair_operators.split(",") if name.strip()]
    destroy_weights = {name: 1.0 for name in destroy_names}
    repair_weights = {name: 1.0 for name in repair_names}
    destroy_rewards = {name: 0.0 for name in destroy_weights}
    repair_rewards = {name: 0.0 for name in repair_weights}
    destroy_uses = {name: 0 for name in destroy_weights}
    repair_uses = {name: 0 for name in repair_weights}
    temperature = args.initial_temperature
    accepted_count = archive_additions = completed = 0
    logs = []

    for iteration in range(1, args.iterations + 1):
        elapsed = time.perf_counter() - started
        if args.time_limit > 0 and elapsed >= args.time_limit:
            break
        if len(archive) > 1 and rng.random() < args.archive_parent_prob:
            parent = rng.choice(archive)
            current = single.clone_routes(parent["routes"])
            current_metrics = dict(parent["metrics"])
        weights = random_weights(rng)
        destroy_name = single.weighted_choice(destroy_names, destroy_weights, rng)
        repair_name = single.weighted_choice(repair_names, repair_weights, rng)
        destroy_uses[destroy_name] += 1
        repair_uses[repair_name] += 1
        removal_count = rng.randint(
            min(args.min_remove, len(order_lookup)), min(args.max_remove, len(order_lookup))
        )
        removed = single.DESTROY_OPERATORS[destroy_name](
            current, removal_count, rng, driver_lookup=driver_lookup,
            order_lookup=order_lookup, distance_matrix=distance_matrix,
        )
        partial = single.clone_routes(current)
        for driver_id in partial:
            for order_id in removed:
                partial[driver_id] = single.remove_order(partial[driver_id], order_id)
        try:
            candidate = repair_multi(
                partial, removed, repair_name, driver_lookup, order_lookup,
                distance_matrix, duration_matrix, weights, scales, rng, deadline,
                args.scalarization, args.tchebycheff_rho,
            )
        except SearchTimeLimit:
            break
        candidate_metrics = multi_metrics(
            candidate, driver_lookup, order_lookup, distance_matrix, duration_matrix
        )
        archive, archive_added = update_archive(
            archive, candidate, candidate_metrics, args.archive_size
        )
        current_scalar = scalar_value(
            current_metrics, weights, scales, args.scalarization, args.tchebycheff_rho
        )
        candidate_scalar = scalar_value(
            candidate_metrics, weights, scales, args.scalarization, args.tchebycheff_rho
        )
        delta = candidate_scalar - current_scalar
        accepted = (
            dominates(candidate_metrics, current_metrics)
            or delta <= 0
            or (not args.disable_sa and rng.random() < math.exp(-delta / max(temperature, 1e-9)))
        )
        reward = 10.0 if archive_added else (5.0 if dominates(candidate_metrics, current_metrics) else (1.0 if accepted else 0.0))
        if accepted:
            current, current_metrics = candidate, candidate_metrics
            accepted_count += 1
        if archive_added:
            archive_additions += 1
        destroy_rewards[destroy_name] += reward
        repair_rewards[repair_name] += reward
        temperature = max(1e-5, temperature * args.cooling_rate)
        completed = iteration
        if not args.disable_adaptation and iteration % args.segment_length == 0:
            single.update_weights(destroy_weights, destroy_rewards, destroy_uses, args.reaction_factor)
            single.update_weights(repair_weights, repair_rewards, repair_uses, args.reaction_factor)
        if iteration == 1 or iteration % 10 == 0:
            ideal, nadir = archive_ranges(archive)
            logs.append({
                "iteration": iteration, "elapsed_seconds": round(elapsed, 3),
                "archive_size": len(archive), "accepted": accepted,
                "archive_added": archive_added, "temperature": temperature,
                "ideal_cost_vnd": ideal[0], "ideal_max_duration_minutes": ideal[1],
                "ideal_workload_imbalance": ideal[2], "nadir_cost_vnd": nadir[0],
                "nadir_max_duration_minutes": nadir[1], "nadir_workload_imbalance": nadir[2],
                "destroy_operator": destroy_name, "repair_operator": repair_name,
                "weight_cost": weights[0], "weight_duration": weights[1],
                "weight_imbalance": weights[2],
            })

    elapsed = time.perf_counter() - started
    archive.sort(key=lambda entry: tuple(objective_vector(entry["metrics"])))
    report = {
        "method": "moalns_pdvrp", "variant_id": args.variant_id, "seed": args.seed,
        "requested_iterations": args.iterations, "completed_iterations": completed,
        "time_limit_seconds": args.time_limit, "runtime_seconds": round(elapsed, 3),
        "initialization_seconds": round(initialization_seconds, 3),
        "search_seconds": round(max(0.0, elapsed - initialization_seconds), 3),
        "pareto_solutions": len(archive), "archive_additions": archive_additions,
        "accepted_solutions": accepted_count,
        "min_remove": args.min_remove, "max_remove": args.max_remove,
        "archive_size_limit": args.archive_size,
        "archive_parent_prob": args.archive_parent_prob,
        "segment_length": args.segment_length, "reaction_factor": args.reaction_factor,
        "cooling_rate": args.cooling_rate, "initial_temperature": args.initial_temperature,
        "scalarization": args.scalarization, "tchebycheff_rho": args.tchebycheff_rho,
        "adaptation_enabled": not args.disable_adaptation,
        "simulated_annealing_enabled": not args.disable_sa,
        "destroy_operators_enabled": ";".join(destroy_names),
        "repair_operators_enabled": ";".join(repair_names),
        "destroy_weights": ";".join(f"{k}={v:.4f}" for k, v in sorted(destroy_weights.items())),
        "repair_weights": ";".join(f"{k}={v:.4f}" for k, v in sorted(repair_weights.items())),
    }
    return archive, pd.DataFrame(logs), pd.DataFrame([report])


def serialize_archive(archive):
    rows = []
    for index, entry in enumerate(archive, start=1):
        metrics = entry["metrics"]
        routes = {
            driver_id: [[order_id, action] for order_id, action in sequence]
            for driver_id, sequence in entry["routes"].items()
        }
        row = {"solution_id": f"P{index:03d}", **metrics, "routes_json": json.dumps(routes)}
        rows.append(row)
    return pd.DataFrame(rows)


def validate_args(args):
    if args.iterations < 1 or args.archive_size < 2 or args.segment_length < 1:
        raise ValueError("Iterations/segment must be positive and archive size >= 2.")
    if args.min_remove < 1 or args.max_remove < args.min_remove:
        raise ValueError("Require 1 <= min-remove <= max-remove.")
    if not 0.0 <= args.archive_parent_prob <= 1.0:
        raise ValueError("--archive-parent-prob must be in [0, 1].")
    if args.tchebycheff_rho < 0.0:
        raise ValueError("--tchebycheff-rho must be non-negative.")
    if not 0.0 < args.cooling_rate <= 1.0:
        raise ValueError("--cooling-rate must be in (0, 1].")
    destroy_names = [name.strip() for name in args.destroy_operators.split(",") if name.strip()]
    repair_names = [name.strip() for name in args.repair_operators.split(",") if name.strip()]
    unknown_destroy = sorted(set(destroy_names) - set(single.DESTROY_OPERATORS))
    unknown_repair = sorted(set(repair_names) - set(single.REPAIR_OPERATORS))
    if not destroy_names or unknown_destroy:
        raise ValueError("Invalid destroy operators: " + ",".join(unknown_destroy or ["none"]))
    if not repair_names or unknown_repair:
        raise ValueError("Invalid repair operators: " + ",".join(unknown_repair or ["none"]))


def main():
    args = parse_args()
    validate_args(args)
    orders, drivers, vehicle_params, distance_matrix = single.load_data(args.data_dir)
    duration_matrix, duration_path = load_duration_matrix(args.data_dir)
    order_lookup = single.build_order_lookup(orders)
    driver_lookup = single.build_driver_lookup(drivers, vehicle_params)
    print("MOALNS — cost, maximum route duration, workload equity")
    print(f"Orders: {len(order_lookup)} | Drivers: {len(driver_lookup)} | Seed: {args.seed}")
    archive, log, report = run_moalns(
        order_lookup, driver_lookup, distance_matrix, duration_matrix, args
    )
    os.makedirs(args.output_dir, exist_ok=True)
    archive_frame = serialize_archive(archive)
    archive_path = os.path.join(args.output_dir, "moalns_pareto_archive.csv")
    log_path = os.path.join(args.output_dir, "moalns_search_log.csv")
    report_path = os.path.join(args.output_dir, "moalns_solver_report.csv")
    archive_frame.to_csv(archive_path, index=False, encoding="utf-8-sig")
    log.to_csv(log_path, index=False, encoding="utf-8-sig")
    report["instance_id"] = args.instance_id
    report["duration_matrix_path"] = duration_path
    report.to_csv(report_path, index=False, encoding="utf-8-sig")
    print(f"Completed with {len(archive_frame)} non-dominated solutions.")
    print(archive_frame[["solution_id", *OBJECTIVES]].to_string(index=False))
    print("Pareto archive: " + archive_path)


if __name__ == "__main__":
    main()
