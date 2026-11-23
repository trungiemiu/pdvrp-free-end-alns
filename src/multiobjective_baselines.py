"""NSGA-II, MOEA/D, and heuristic epsilon-constraint baselines for PDVRP."""

import argparse
import math
import os
import random
import time

import numpy as np
import pandas as pd

import alns_pdvrp_solver as single
import moalns_pdvrp_solver as mo


def write_csv_atomic(frame, path):
    """Parse-check a temporary CSV before atomically replacing its destination."""
    temporary = path + f".tmp.{os.getpid()}"
    try:
        for attempt in range(3):
            frame.to_csv(temporary, index=False, encoding="utf-8-sig")
            try:
                check = pd.read_csv(temporary)
                if list(check.columns) != list(frame.columns) or len(check) != len(frame):
                    raise ValueError("CSV round-trip shape mismatch")
                os.replace(temporary, path)
                return
            except (pd.errors.ParserError, UnicodeDecodeError, ValueError, PermissionError):
                if attempt == 2:
                    raise
                time.sleep(0.25 * (attempt + 1))
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def parse_args():
    parser = argparse.ArgumentParser(description="Multi-objective PDVRP baselines.")
    parser.add_argument("--algorithm", required=True, choices=["nsga2", "moead", "epsilon"])
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--time-limit", type=float, default=180.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--population-size", type=int, default=15)
    parser.add_argument("--archive-size", type=int, default=100)
    parser.add_argument("--min-remove", type=int, default=2)
    parser.add_argument("--max-remove", type=int, default=6)
    parser.add_argument("--epsilon-levels", type=int, default=3)
    return parser.parse_args()


def load_instance(data_dir):
    orders, drivers, vehicle_params, distance = single.load_data(data_dir)
    duration, duration_path = mo.load_duration_matrix(data_dir)
    return (
        single.build_order_lookup(orders),
        single.build_driver_lookup(drivers, vehicle_params),
        distance,
        duration,
        duration_path,
    )


def evaluate(routes, context):
    orders, drivers, distance, duration = context
    return mo.multi_metrics(routes, drivers, orders, distance, duration)


def random_weights(rng):
    return mo.random_weights(rng)


def mutate(routes, weights, scales, context, args, rng, deadline=None):
    orders, drivers, distance, duration = context
    count = rng.randint(min(args.min_remove, len(orders)), min(args.max_remove, len(orders)))
    destroy_name = rng.choice(list(single.DESTROY_OPERATORS))
    removed = single.DESTROY_OPERATORS[destroy_name](
        routes, count, rng, driver_lookup=drivers,
        order_lookup=orders, distance_matrix=distance,
    )
    partial = single.clone_routes(routes)
    for driver_id in partial:
        for order_id in removed:
            partial[driver_id] = single.remove_order(partial[driver_id], order_id)
    return mo.repair_multi(
        partial, removed, rng.choice(single.REPAIR_OPERATORS), drivers, orders,
        distance, duration, weights, scales, rng, deadline,
    )


def crossover(left, right, weights, scales, context, rng, deadline=None):
    orders, drivers, distance, duration = context
    driver_ids = list(drivers)
    keep = set(rng.sample(driver_ids, rng.randint(1, max(1, len(driver_ids) - 1))))
    child = {driver_id: [] for driver_id in driver_ids}
    assigned = set()
    for driver_id in keep:
        child[driver_id] = list(left[driver_id])
        assigned.update(single.route_orders(child[driver_id]))
    for driver_id in driver_ids:
        if driver_id in keep:
            continue
        allowed = set(single.route_orders(right[driver_id])) - assigned
        child[driver_id] = [action for action in right[driver_id] if action[0] in allowed]
        assigned.update(allowed)
    missing = [order_id for order_id in orders if order_id not in assigned]
    if missing:
        child = mo.repair_multi(
            child, missing, "regret_2", drivers, orders, distance, duration,
            weights, scales, rng, deadline,
        )
    return child


def nondominated_fronts(individuals):
    dominates_set = [set() for _ in individuals]
    dominated_count = [0] * len(individuals)
    fronts = [[]]
    for p, left in enumerate(individuals):
        for q, right in enumerate(individuals):
            if p == q:
                continue
            if mo.dominates(left["metrics"], right["metrics"]):
                dominates_set[p].add(q)
            elif mo.dominates(right["metrics"], left["metrics"]):
                dominated_count[p] += 1
        if dominated_count[p] == 0:
            fronts[0].append(p)
    level = 0
    while fronts[level]:
        following = []
        for p in fronts[level]:
            for q in dominates_set[p]:
                dominated_count[q] -= 1
                if dominated_count[q] == 0:
                    following.append(q)
        level += 1
        fronts.append(following)
    return fronts[:-1]


def nsga_select(combined, size):
    selected = []
    for front in nondominated_fronts(combined):
        entries = [combined[index] for index in front]
        if len(selected) + len(entries) <= size:
            selected.extend(entries)
        else:
            crowding = mo.crowding_distances(entries)
            order = sorted(range(len(entries)), key=lambda i: crowding[i], reverse=True)
            selected.extend(entries[i] for i in order[:size - len(selected)])
            break
    return selected


def tournament(population, rng):
    sample = rng.sample(population, min(2, len(population)))
    if len(sample) == 1:
        return sample[0]
    if sample[0].get("rank", math.inf) < sample[1].get("rank", math.inf):
        return sample[0]
    if sample[1].get("rank", math.inf) < sample[0].get("rank", math.inf):
        return sample[1]
    if sample[0].get("crowding", 0.0) > sample[1].get("crowding", 0.0):
        return sample[0]
    if sample[1].get("crowding", 0.0) > sample[0].get("crowding", 0.0):
        return sample[1]
    return rng.choice(sample)


def annotate_nsga(population):
    for rank, front in enumerate(nondominated_fronts(population)):
        entries = [population[index] for index in front]
        crowding = mo.crowding_distances(entries)
        for local_index, population_index in enumerate(front):
            population[population_index]["rank"] = rank
            population[population_index]["crowding"] = crowding[local_index]


def initialize_population(base, base_metrics, scales, context, args, rng, deadline):
    population = [{"routes": single.clone_routes(base), "metrics": dict(base_metrics)}]
    attempts = 0
    while len(population) < args.population_size and time.perf_counter() < deadline:
        attempts += 1
        try:
            routes = mutate(base, random_weights(rng), scales, context, args, rng, deadline)
        except mo.SearchTimeLimit:
            break
        metrics = evaluate(routes, context)
        if not any(mo.same_objectives(item["metrics"], metrics) for item in population):
            population.append({"routes": routes, "metrics": metrics})
        if attempts > args.population_size * 4:
            break
    return population


def run_nsga2(base, base_metrics, scales, context, args, rng, deadline):
    population = initialize_population(base, base_metrics, scales, context, args, rng, deadline)
    archive = []
    additions = offspring_count = generations = 0
    for item in population:
        archive, added = mo.update_archive(archive, item["routes"], item["metrics"], args.archive_size)
        additions += int(added)
    while time.perf_counter() < deadline:
        annotate_nsga(population)
        offspring = []
        target = max(1, len(population))
        while len(offspring) < target and time.perf_counter() < deadline:
            left, right = tournament(population, rng), tournament(population, rng)
            weights = random_weights(rng)
            try:
                child = crossover(left["routes"], right["routes"], weights, scales, context, rng, deadline)
                child = mutate(child, weights, scales, context, args, rng, deadline)
            except mo.SearchTimeLimit:
                break
            metrics = evaluate(child, context)
            offspring.append({"routes": child, "metrics": metrics})
            archive, added = mo.update_archive(archive, child, metrics, args.archive_size)
            additions += int(added); offspring_count += 1
        population = nsga_select(population + offspring, args.population_size)
        generations += 1
    return archive, {"generations": generations, "evaluated_offspring": offspring_count,
                     "archive_additions": additions, "population_size_actual": len(population)}


def weight_vectors(size, rng):
    anchors = [np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 1.0])]
    result = anchors[:min(size, 3)]
    while len(result) < size:
        result.append(random_weights(rng))
    result = np.maximum(np.array(result), 1e-6)
    return result / result.sum(axis=1, keepdims=True)


def run_moead(base, base_metrics, scales, context, args, rng, deadline):
    weights = weight_vectors(args.population_size, rng)
    population = initialize_population(base, base_metrics, scales, context, args, rng, deadline)
    weights = weights[:len(population)]
    vectors = np.array([mo.objective_vector(item["metrics"]) for item in population])
    ideal = vectors.min(axis=0)
    distances = np.linalg.norm(weights[:, None, :] - weights[None, :, :], axis=2)
    neighborhood_size = min(5, len(population))
    neighborhoods = np.argsort(distances, axis=1)[:, :neighborhood_size]
    archive, additions = [], 0
    for item in population:
        archive, added = mo.update_archive(archive, item["routes"], item["metrics"], args.archive_size)
        additions += int(added)
    evaluations = sweeps = 0
    while time.perf_counter() < deadline:
        for index in rng.sample(range(len(population)), len(population)):
            if time.perf_counter() >= deadline:
                break
            neighbor_ids = neighborhoods[index].tolist()
            left_id, right_id = rng.choices(neighbor_ids, k=2)
            try:
                child = crossover(population[left_id]["routes"], population[right_id]["routes"],
                                  weights[index], scales, context, rng, deadline)
                child = mutate(child, weights[index], scales, context, args, rng, deadline)
            except mo.SearchTimeLimit:
                break
            metrics = evaluate(child, context)
            vector = mo.objective_vector(metrics)
            ideal = np.minimum(ideal, vector)
            for neighbor in neighbor_ids:
                old = np.max(weights[neighbor] * np.abs(mo.objective_vector(population[neighbor]["metrics"]) - ideal) / scales)
                new = np.max(weights[neighbor] * np.abs(vector - ideal) / scales)
                if new <= old:
                    population[neighbor] = {"routes": single.clone_routes(child), "metrics": dict(metrics)}
            archive, added = mo.update_archive(archive, child, metrics, args.archive_size)
            additions += int(added); evaluations += 1
        sweeps += 1
    return archive, {"sweeps": sweeps, "evaluated_offspring": evaluations,
                     "archive_additions": additions, "population_size_actual": len(population)}


def constraint_key(metrics, duration_epsilon, imbalance_epsilon, scales):
    duration_violation = max(0.0, metrics["max_route_duration_minutes"] - duration_epsilon) / scales[1]
    imbalance_violation = max(0.0, metrics["workload_imbalance"] - imbalance_epsilon) / scales[2]
    return duration_violation + imbalance_violation, metrics["total_cost_vnd"]


def run_epsilon(base, base_metrics, scales, context, args, rng, deadline):
    sample_deadline = min(deadline, time.perf_counter() + args.time_limit * 0.25)
    pool = initialize_population(base, base_metrics, scales, context, args, rng, sample_deadline)
    durations = [item["metrics"]["max_route_duration_minutes"] for item in pool]
    imbalances = [item["metrics"]["workload_imbalance"] for item in pool]
    duration_levels = np.linspace(min(durations), max(durations), args.epsilon_levels)
    imbalance_levels = np.linspace(min(imbalances), max(imbalances), args.epsilon_levels)
    cells = [(d, i) for d in duration_levels for i in imbalance_levels]
    archive, additions, evaluations, feasible_cells = [], 0, 0, 0
    for item in pool:
        archive, added = mo.update_archive(archive, item["routes"], item["metrics"], args.archive_size)
        additions += int(added)
    for cell_index, (duration_epsilon, imbalance_epsilon) in enumerate(cells):
        remaining_cells = len(cells) - cell_index
        cell_deadline = time.perf_counter() + max(0.0, deadline - time.perf_counter()) / remaining_cells
        current = min(pool, key=lambda item: constraint_key(item["metrics"], duration_epsilon, imbalance_epsilon, scales))
        current = {"routes": single.clone_routes(current["routes"]), "metrics": dict(current["metrics"])}
        best_feasible = None
        while time.perf_counter() < cell_deadline:
            weights = np.array([0.90, 0.05, 0.05])
            try:
                candidate_routes = mutate(current["routes"], weights, scales, context, args, rng, cell_deadline)
            except mo.SearchTimeLimit:
                break
            candidate_metrics = evaluate(candidate_routes, context)
            if constraint_key(candidate_metrics, duration_epsilon, imbalance_epsilon, scales) <= constraint_key(current["metrics"], duration_epsilon, imbalance_epsilon, scales):
                current = {"routes": candidate_routes, "metrics": candidate_metrics}
            if constraint_key(candidate_metrics, duration_epsilon, imbalance_epsilon, scales)[0] <= 1e-12:
                if best_feasible is None or candidate_metrics["total_cost_vnd"] < best_feasible["metrics"]["total_cost_vnd"]:
                    best_feasible = {"routes": single.clone_routes(candidate_routes), "metrics": dict(candidate_metrics)}
            archive, added = mo.update_archive(archive, candidate_routes, candidate_metrics, args.archive_size)
            additions += int(added); evaluations += 1
        if best_feasible is not None:
            feasible_cells += 1
            pool.append(best_feasible)
    return archive, {"epsilon_cells": len(cells), "feasible_cells": feasible_cells,
                     "evaluated_candidates": evaluations, "archive_additions": additions,
                     "duration_epsilon_min": min(duration_levels), "duration_epsilon_max": max(duration_levels),
                     "imbalance_epsilon_min": min(imbalance_levels), "imbalance_epsilon_max": max(imbalance_levels)}


def main():
    args = parse_args()
    if args.population_size < 3 or args.epsilon_levels < 2:
        raise ValueError("population-size >= 3 and epsilon-levels >= 2 are required.")
    orders, drivers, distance, duration, duration_path = load_instance(args.data_dir)
    context = (orders, drivers, distance, duration)
    rng = random.Random(args.seed)
    started = time.perf_counter(); deadline = started + args.time_limit
    base, _ = single.build_initial_solution(orders, drivers, distance, rng, 0.0)
    initialization_seconds = time.perf_counter() - started
    base_metrics = evaluate(base, context)
    scales = np.maximum(mo.objective_vector(base_metrics), np.ones(3))
    if args.algorithm == "nsga2":
        archive, details = run_nsga2(base, base_metrics, scales, context, args, rng, deadline)
    elif args.algorithm == "moead":
        archive, details = run_moead(base, base_metrics, scales, context, args, rng, deadline)
    else:
        archive, details = run_epsilon(base, base_metrics, scales, context, args, rng, deadline)
    elapsed = time.perf_counter() - started
    archive.sort(key=lambda entry: tuple(mo.objective_vector(entry["metrics"])))
    frame = mo.serialize_archive(archive)
    os.makedirs(args.output_dir, exist_ok=True)
    archive_path = os.path.join(args.output_dir, args.algorithm + "_pareto_archive.csv")
    report_path = os.path.join(args.output_dir, args.algorithm + "_solver_report.csv")
    write_csv_atomic(frame, archive_path)
    report = {"algorithm": args.algorithm, "instance_id": args.instance_id,
              "seed": args.seed, "runtime_seconds": round(elapsed, 3),
              "time_limit_seconds": args.time_limit,
              "initialization_seconds": round(initialization_seconds, 3),
              "search_seconds": round(max(0.0, elapsed - initialization_seconds), 3),
              "pareto_solutions": len(frame),
              "duration_matrix_path": duration_path, **details}
    write_csv_atomic(pd.DataFrame([report]), report_path)
    print(f"{args.algorithm.upper()} completed: {len(frame)} Pareto solutions in {elapsed:.2f}s")
    print("Archive: " + archive_path)


if __name__ == "__main__":
    main()
