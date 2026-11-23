import argparse
import math
import os
import random
import time

import numpy as np
import pandas as pd

from routing_economics import build_order_revenue_lookup, sum_order_revenue


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
ROUTE_DIR = os.path.join(BASE_DIR, "outputs", "routes")
REPORT_DIR = os.path.join(BASE_DIR, "outputs", "reports")

METHOD_NAME = "alns_pdvrp"
ROUTES_PATH = os.path.join(ROUTE_DIR, METHOD_NAME + "_routes.csv")
STEPS_PATH = os.path.join(ROUTE_DIR, METHOD_NAME + "_route_steps.csv")
SUMMARY_PATH = os.path.join(REPORT_DIR, METHOD_NAME + "_summary.csv")
SEARCH_LOG_PATH = os.path.join(REPORT_DIR, METHOD_NAME + "_search_log.csv")
SOLVER_REPORT_PATH = os.path.join(REPORT_DIR, METHOD_NAME + "_solver_report.csv")

EPSILON = 1e-9


def parse_args():
    parser = argparse.ArgumentParser(
        description="Adaptive Large Neighborhood Search for heterogeneous open PDVRP."
    )
    parser.add_argument("--iterations", type=int, default=5000)
    parser.add_argument("--time-limit", type=float, default=120.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-remove", type=int, default=2)
    parser.add_argument("--max-remove", type=int, default=7)
    parser.add_argument("--cooling-rate", type=float, default=0.999)
    parser.add_argument("--initial-temperature-ratio", type=float, default=0.03)
    parser.add_argument("--segment-length", type=int, default=20)
    parser.add_argument("--reaction-factor", type=float, default=0.25)
    parser.add_argument(
        "--balance-penalty-vnd",
        type=float,
        default=0.0,
        help="Optional penalty multiplied by the standard deviation of orders per used driver.",
    )
    parser.add_argument("--data-dir", default=DATA_DIR)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--instance-id", default="current")
    return parser.parse_args()


def normalize_vehicle_type(value):
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def load_data(data_dir=None):
    data_dir = data_dir or DATA_DIR
    orders = pd.read_csv(os.path.join(data_dir, "orders.csv"))
    drivers = pd.read_csv(os.path.join(data_dir, "drivers.csv"))
    vehicle_params = pd.read_csv(os.path.join(data_dir, "vehicle_parameters.csv"))
    distance_matrix = pd.read_csv(
        os.path.join(data_dir, "distance_matrix.csv"), index_col=0
    )

    orders["required_vehicle"] = orders["required_vehicle"].apply(
        normalize_vehicle_type
    )
    drivers["vehicle_type"] = drivers["vehicle_type"].apply(normalize_vehicle_type)
    vehicle_params["vehicle_type"] = vehicle_params["vehicle_type"].apply(
        normalize_vehicle_type
    )
    return orders, drivers, vehicle_params, distance_matrix


def build_order_lookup(orders):
    result = {}
    for _, row in orders.iterrows():
        order_id = str(row["order_id"])
        number = order_id.replace("O", "").zfill(2)
        result[order_id] = {
            "order_id": order_id,
            "pickup_node": "P" + number,
            "delivery_node": "L" + number,
            "demand_kg": float(row["demand_kg"]),
            "required_vehicle": row["required_vehicle"],
        }
    return result


def build_driver_lookup(drivers, vehicle_params):
    capacity = dict(zip(vehicle_params["vehicle_type"], vehicle_params["capacity_kg"]))
    cost = dict(zip(vehicle_params["vehicle_type"], vehicle_params["cost_vnd_per_km"]))
    result = {}
    for _, row in drivers.iterrows():
        driver_id = str(row["driver_id"])
        vehicle_type = row["vehicle_type"]
        result[driver_id] = {
            "driver_id": driver_id,
            "vehicle_type": vehicle_type,
            "start_node": driver_id + "_START",
            "capacity_kg": float(capacity[vehicle_type]),
            "cost_per_km": float(cost[vehicle_type]),
        }
    return result


def action_node(action, order_lookup):
    order_id, action_type = action
    order = order_lookup[order_id]
    return order["pickup_node"] if action_type == "pickup" else order["delivery_node"]


def sequence_metrics(sequence, driver, order_lookup, distance_matrix):
    current = driver["start_node"]
    load = 0.0
    picked = set()
    delivered = set()
    distance = 0.0

    for order_id, action_type in sequence:
        if order_id not in order_lookup:
            return None
        order = order_lookup[order_id]
        if order["required_vehicle"] != driver["vehicle_type"]:
            return None

        if action_type == "pickup":
            if order_id in picked:
                return None
            load += order["demand_kg"]
            if load > driver["capacity_kg"] + EPSILON:
                return None
            picked.add(order_id)
        elif action_type == "delivery":
            if order_id not in picked or order_id in delivered:
                return None
            load -= order["demand_kg"]
            if load < -EPSILON:
                return None
            delivered.add(order_id)
        else:
            return None

        node = action_node((order_id, action_type), order_lookup)
        distance += float(distance_matrix.loc[current, node])
        current = node

    if picked != delivered or len(sequence) != 2 * len(picked):
        return None
    return {"distance": distance, "cost": distance * driver["cost_per_km"]}


def route_orders(sequence):
    return sorted({order_id for order_id, _ in sequence})


def clone_routes(routes):
    return {driver_id: list(sequence) for driver_id, sequence in routes.items()}


def remove_order(sequence, order_id):
    return [action for action in sequence if action[0] != order_id]


def best_insertions_for_order(
    order_id, routes, driver_lookup, order_lookup, distance_matrix, noise, rng,
    tail_only=False,
):
    order = order_lookup[order_id]
    options = []
    for driver_id, driver in driver_lookup.items():
        if driver["vehicle_type"] != order["required_vehicle"]:
            continue
        base = routes[driver_id]
        before = sequence_metrics(base, driver, order_lookup, distance_matrix)["cost"]
        pickup_positions = [len(base)] if tail_only else range(len(base) + 1)
        for pickup_position in pickup_positions:
            for delivery_position in range(pickup_position + 1, len(base) + 2):
                if tail_only and delivery_position != len(base) + 1:
                    continue
                candidate = list(base)
                candidate.insert(pickup_position, (order_id, "pickup"))
                candidate.insert(delivery_position, (order_id, "delivery"))
                metrics = sequence_metrics(
                    candidate, driver, order_lookup, distance_matrix
                )
                if metrics is None:
                    continue
                delta = metrics["cost"] - before
                score = delta
                if noise > 0.0:
                    score *= rng.uniform(1.0 - noise, 1.0 + noise)
                options.append(
                    {
                        "driver_id": driver_id,
                        "sequence": candidate,
                        "delta": delta,
                        "score": score,
                    }
                )
    options.sort(key=lambda option: (option["score"], option["delta"]))
    return options


def repair_routes(
    partial_routes,
    removed_orders,
    repair_name,
    driver_lookup,
    order_lookup,
    distance_matrix,
    rng,
):
    routes = clone_routes(partial_routes)
    unassigned = list(removed_orders)

    while unassigned:
        candidates = []
        for order_id in unassigned:
            noise = 0.20 if repair_name == "noisy_greedy" else 0.0
            options = best_insertions_for_order(
                order_id,
                routes,
                driver_lookup,
                order_lookup,
                distance_matrix,
                noise,
                rng,
                tail_only=repair_name == "tail_greedy",
            )
            if not options:
                raise RuntimeError("No feasible insertion for " + order_id)
            best = options[0]
            second = options[1] if len(options) > 1 else options[0]
            third = options[2] if len(options) > 2 else second
            if repair_name == "regret_2":
                priority = second["delta"] - best["delta"]
            elif repair_name == "regret_3":
                priority = (
                    second["delta"] - best["delta"]
                    + third["delta"] - best["delta"]
                )
            else:
                priority = -best["score"]
            candidates.append((priority, order_id, best))

        _, selected_order, selected_option = max(
            candidates, key=lambda item: (item[0], item[1])
        )
        routes[selected_option["driver_id"]] = selected_option["sequence"]
        unassigned.remove(selected_order)
    return routes


def solution_metrics(
    routes, driver_lookup, order_lookup, distance_matrix, balance_penalty_vnd
):
    total_distance = 0.0
    total_cost = 0.0
    used_counts = []
    assigned = []
    for driver_id, sequence in routes.items():
        metrics = sequence_metrics(
            sequence, driver_lookup[driver_id], order_lookup, distance_matrix
        )
        if metrics is None:
            return None
        total_distance += metrics["distance"]
        total_cost += metrics["cost"]
        orders = route_orders(sequence)
        assigned.extend(orders)
        if orders:
            used_counts.append(len(orders))

    if len(assigned) != len(set(assigned)):
        return None
    imbalance = float(np.std(used_counts)) if used_counts else 0.0
    return {
        "distance": total_distance,
        "cost": total_cost,
        "used_drivers": len(used_counts),
        "max_orders": max(used_counts) if used_counts else 0,
        "imbalance": imbalance,
        "objective": total_cost + balance_penalty_vnd * imbalance,
    }


def build_initial_solution(
    order_lookup, driver_lookup, distance_matrix, rng, balance_penalty_vnd
):
    routes = {driver_id: [] for driver_id in driver_lookup}
    order_ids = list(order_lookup)
    # Difficult/high-demand orders enter the regret construction first through its priorities.
    routes = repair_routes(
        routes,
        order_ids,
        "regret_3",
        driver_lookup,
        order_lookup,
        distance_matrix,
        rng,
    )
    metrics = solution_metrics(
        routes, driver_lookup, order_lookup, distance_matrix, balance_penalty_vnd
    )
    return routes, metrics


def assigned_orders(routes):
    result = []
    for sequence in routes.values():
        result.extend(route_orders(sequence))
    return result


def destroy_random(routes, count, rng, **kwargs):
    orders = assigned_orders(routes)
    return rng.sample(orders, min(count, len(orders)))


def destroy_worst(
    routes, count, rng, driver_lookup, order_lookup, distance_matrix, **kwargs
):
    savings = []
    for driver_id, sequence in routes.items():
        driver = driver_lookup[driver_id]
        before = sequence_metrics(sequence, driver, order_lookup, distance_matrix)["cost"]
        for order_id in route_orders(sequence):
            candidate = remove_order(sequence, order_id)
            after = sequence_metrics(candidate, driver, order_lookup, distance_matrix)["cost"]
            savings.append((before - after, rng.random(), order_id))
    savings.sort(reverse=True)
    return [order_id for _, _, order_id in savings[:count]]


def destroy_related(
    routes, count, rng, driver_lookup, order_lookup, distance_matrix, **kwargs
):
    orders = assigned_orders(routes)
    seed = rng.choice(orders)
    seed_order = order_lookup[seed]

    def relatedness(order_id):
        order = order_lookup[order_id]
        type_penalty = 0.0 if order["required_vehicle"] == seed_order["required_vehicle"] else 1000.0
        return (
            float(distance_matrix.loc[seed_order["pickup_node"], order["pickup_node"]])
            + float(distance_matrix.loc[seed_order["delivery_node"], order["delivery_node"]])
            + type_penalty
        )

    return sorted(orders, key=relatedness)[:count]


def destroy_route(routes, count, rng, **kwargs):
    used = [driver_id for driver_id, sequence in routes.items() if sequence]
    driver_id = rng.choice(used)
    orders = route_orders(routes[driver_id])
    if len(orders) <= count:
        return orders
    return rng.sample(orders, count)


def destroy_tail(routes, count, rng, order_lookup, **kwargs):
    """Remove a self-contained zero-load suffix, with a late-delivery fallback."""
    candidates = []
    late_fallback = []
    for driver_id, sequence in routes.items():
        if not sequence:
            continue
        load = 0.0
        boundaries = []
        delivery_positions = []
        for position, (order_id, action) in enumerate(sequence, start=1):
            demand = float(order_lookup[order_id]["demand_kg"])
            load += demand if action == "pickup" else -demand
            if action == "delivery":
                delivery_positions.append((position, order_id))
            if abs(load) <= EPSILON and position < len(sequence):
                boundaries.append(position)
        for cut in boundaries:
            suffix_orders = list(dict.fromkeys(order_id for order_id, _ in sequence[cut:]))
            if 1 <= len(suffix_orders) <= count:
                candidates.append((len(suffix_orders), rng.random(), suffix_orders))
        if delivery_positions:
            latest = [order_id for _, order_id in sorted(delivery_positions, reverse=True)[:count]]
            late_fallback.append((rng.random(), latest))
    if candidates:
        # Prefer the largest admissible self-contained suffix; randomize ties.
        return max(candidates, key=lambda item: (item[0], item[1]))[2]
    if late_fallback:
        return max(late_fallback, key=lambda item: item[0])[1]
    return destroy_random(routes, count, rng)


DESTROY_OPERATORS = {
    "random": destroy_random,
    "worst": destroy_worst,
    "related": destroy_related,
    "route": destroy_route,
    "tail": destroy_tail,
}

REPAIR_OPERATORS = ["greedy", "regret_2", "regret_3", "noisy_greedy", "tail_greedy"]


def weighted_choice(names, weights, rng):
    return rng.choices(names, weights=[weights[name] for name in names], k=1)[0]


def update_weights(weights, rewards, uses, reaction_factor):
    for name in weights:
        if uses[name] > 0:
            observed = rewards[name] / uses[name]
            weights[name] = max(
                0.1,
                (1.0 - reaction_factor) * weights[name]
                + reaction_factor * observed,
            )
        rewards[name] = 0.0
        uses[name] = 0


def run_alns(
    order_lookup,
    driver_lookup,
    distance_matrix,
    args,
):
    rng = random.Random(args.seed)
    current, current_metrics = build_initial_solution(
        order_lookup,
        driver_lookup,
        distance_matrix,
        rng,
        args.balance_penalty_vnd,
    )
    best = clone_routes(current)
    best_metrics = dict(current_metrics)
    initial_metrics = dict(current_metrics)

    destroy_weights = {name: 1.0 for name in DESTROY_OPERATORS}
    repair_weights = {name: 1.0 for name in REPAIR_OPERATORS}
    destroy_rewards = {name: 0.0 for name in DESTROY_OPERATORS}
    repair_rewards = {name: 0.0 for name in REPAIR_OPERATORS}
    destroy_uses = {name: 0 for name in DESTROY_OPERATORS}
    repair_uses = {name: 0 for name in REPAIR_OPERATORS}

    temperature = max(
        1.0, current_metrics["objective"] * args.initial_temperature_ratio
    )
    started = time.perf_counter()
    log_records = []
    accepted_count = 0
    completed_iterations = 0

    for iteration in range(1, args.iterations + 1):
        elapsed = time.perf_counter() - started
        if args.time_limit > 0 and elapsed >= args.time_limit:
            break

        destroy_name = weighted_choice(
            list(DESTROY_OPERATORS), destroy_weights, rng
        )
        repair_name = weighted_choice(REPAIR_OPERATORS, repair_weights, rng)
        destroy_uses[destroy_name] += 1
        repair_uses[repair_name] += 1

        max_remove = min(args.max_remove, len(order_lookup))
        min_remove = min(args.min_remove, max_remove)
        removal_count = rng.randint(min_remove, max_remove)
        removed = DESTROY_OPERATORS[destroy_name](
            current,
            removal_count,
            rng,
            driver_lookup=driver_lookup,
            order_lookup=order_lookup,
            distance_matrix=distance_matrix,
        )
        partial = clone_routes(current)
        for driver_id in partial:
            for order_id in removed:
                partial[driver_id] = remove_order(partial[driver_id], order_id)

        candidate = repair_routes(
            partial,
            removed,
            repair_name,
            driver_lookup,
            order_lookup,
            distance_matrix,
            rng,
        )
        candidate_metrics = solution_metrics(
            candidate,
            driver_lookup,
            order_lookup,
            distance_matrix,
            args.balance_penalty_vnd,
        )

        delta = candidate_metrics["objective"] - current_metrics["objective"]
        accepted = delta <= 0.0 or rng.random() < math.exp(-delta / temperature)
        reward = 0.0
        if candidate_metrics["objective"] < best_metrics["objective"] - EPSILON:
            best = clone_routes(candidate)
            best_metrics = dict(candidate_metrics)
            reward = 10.0
        elif candidate_metrics["objective"] < current_metrics["objective"] - EPSILON:
            reward = 5.0
        elif accepted:
            reward = 1.0

        if accepted:
            current = candidate
            current_metrics = candidate_metrics
            accepted_count += 1

        destroy_rewards[destroy_name] += reward
        repair_rewards[repair_name] += reward
        temperature = max(0.01, temperature * args.cooling_rate)
        completed_iterations = iteration

        if iteration % args.segment_length == 0:
            update_weights(
                destroy_weights,
                destroy_rewards,
                destroy_uses,
                args.reaction_factor,
            )
            update_weights(
                repair_weights,
                repair_rewards,
                repair_uses,
                args.reaction_factor,
            )

        if iteration == 1 or iteration % 25 == 0:
            log_records.append(
                {
                    "iteration": iteration,
                    "elapsed_seconds": round(elapsed, 3),
                    "current_cost_vnd": round(current_metrics["cost"], 3),
                    "best_cost_vnd": round(best_metrics["cost"], 3),
                    "current_objective": round(current_metrics["objective"], 3),
                    "best_objective": round(best_metrics["objective"], 3),
                    "temperature": round(temperature, 6),
                    "destroy_operator": destroy_name,
                    "repair_operator": repair_name,
                    "accepted": accepted,
                    "used_drivers": best_metrics["used_drivers"],
                }
            )

    elapsed = time.perf_counter() - started
    report = {
        "method": METHOD_NAME,
        "seed": args.seed,
        "requested_iterations": args.iterations,
        "completed_iterations": completed_iterations,
        "time_limit_seconds": args.time_limit,
        "runtime_seconds": round(elapsed, 3),
        "accepted_solutions": accepted_count,
        "initial_distance_km": round(initial_metrics["distance"], 3),
        "initial_cost_vnd": round(initial_metrics["cost"], 0),
        "best_distance_km": round(best_metrics["distance"], 3),
        "best_cost_vnd": round(best_metrics["cost"], 0),
        "used_drivers": best_metrics["used_drivers"],
        "max_orders_per_driver": best_metrics["max_orders"],
        "workload_std": round(best_metrics["imbalance"], 4),
        "balance_penalty_vnd": args.balance_penalty_vnd,
        "destroy_weights": ";".join(
            "{}={:.4f}".format(name, value)
            for name, value in sorted(destroy_weights.items())
        ),
        "repair_weights": ";".join(
            "{}={:.4f}".format(name, value)
            for name, value in sorted(repair_weights.items())
        ),
    }
    return best, best_metrics, pd.DataFrame(log_records), pd.DataFrame([report])


def routes_to_outputs(
    routes,
    driver_lookup,
    order_lookup,
    order_revenue_lookup,
    distance_matrix,
):
    steps = []
    summaries = []

    for driver_id, driver in driver_lookup.items():
        sequence = routes[driver_id]
        current = driver["start_node"]
        load = 0.0
        route_nodes = [current]
        distance = 0.0
        order_ids = route_orders(sequence)

        for step_number, (order_id, action_type) in enumerate(sequence, start=1):
            node = action_node((order_id, action_type), order_lookup)
            leg_distance = float(distance_matrix.loc[current, node])
            load_before = load
            if action_type == "pickup":
                load += order_lookup[order_id]["demand_kg"]
            else:
                load -= order_lookup[order_id]["demand_kg"]
            steps.append(
                {
                    "driver_id": driver_id,
                    "step": step_number,
                    "from_node": current,
                    "to_node": node,
                    "order_id": order_id,
                    "action": action_type,
                    "distance_km": round(leg_distance, 3),
                    "cost_vnd": round(leg_distance * driver["cost_per_km"], 0),
                    "load_before_kg": round(load_before, 3),
                    "load_after_kg": round(load, 3),
                    "capacity_kg": driver["capacity_kg"],
                }
            )
            distance += leg_distance
            current = node
            route_nodes.append(node)

        cost = distance * driver["cost_per_km"]
        revenue = sum_order_revenue(order_ids, order_revenue_lookup)
        summaries.append(
            {
                "driver_id": driver_id,
                "vehicle_type": driver["vehicle_type"],
                "num_orders": len(order_ids),
                "assigned_orders": " -> ".join(order_ids),
                "route": " -> ".join(route_nodes),
                "total_distance_km": round(distance, 3),
                "total_cost_vnd": round(cost, 0),
                "total_revenue_vnd": round(revenue, 0),
                "net_profit_vnd": round(revenue - cost, 0),
            }
        )

    steps_df = pd.DataFrame(steps)
    summary_df = pd.DataFrame(summaries)
    route_rows = []
    for order_id, order in order_lookup.items():
        pickup = steps_df[
            (steps_df["order_id"] == order_id) & (steps_df["action"] == "pickup")
        ]
        delivery = steps_df[
            (steps_df["order_id"] == order_id) & (steps_df["action"] == "delivery")
        ]
        if pickup.empty or delivery.empty:
            route_rows.append(
                {
                    "order_id": order_id,
                    "driver_id": None,
                    "vehicle_type": None,
                    "pickup_node": order["pickup_node"],
                    "delivery_node": order["delivery_node"],
                    "pickup_step": None,
                    "delivery_step": None,
                    "status": "unassigned_or_incomplete",
                }
            )
            continue
        pickup_row = pickup.iloc[0]
        delivery_row = delivery.iloc[0]
        driver_id = str(pickup_row["driver_id"])
        route_rows.append(
            {
                "order_id": order_id,
                "driver_id": driver_id,
                "vehicle_type": driver_lookup[driver_id]["vehicle_type"],
                "pickup_node": order["pickup_node"],
                "delivery_node": order["delivery_node"],
                "pickup_step": int(pickup_row["step"]),
                "delivery_step": int(delivery_row["step"]),
                "status": "assigned",
            }
        )
    return pd.DataFrame(route_rows), steps_df, summary_df


def validate_args(args):
    if args.iterations < 1:
        raise ValueError("--iterations must be positive.")
    if args.min_remove < 1 or args.max_remove < args.min_remove:
        raise ValueError("Require 1 <= --min-remove <= --max-remove.")
    if not 0.0 < args.cooling_rate <= 1.0:
        raise ValueError("--cooling-rate must be in (0, 1].")
    if args.segment_length < 1:
        raise ValueError("--segment-length must be positive.")


def main():
    args = parse_args()
    validate_args(args)
    orders, drivers, vehicle_params, distance_matrix = load_data(args.data_dir)
    order_lookup = build_order_lookup(orders)
    driver_lookup = build_driver_lookup(drivers, vehicle_params)
    order_revenue_lookup = build_order_revenue_lookup(
        orders, vehicle_params, distance_matrix
    )

    print("Adaptive Large Neighborhood Search — Heterogeneous Open PDVRP")
    print("Orders: {} | Drivers: {} | Seed: {}".format(
        len(order_lookup), len(driver_lookup), args.seed
    ))
    print("Iterations: {} | Time limit: {} seconds".format(
        args.iterations, args.time_limit
    ))

    routes, metrics, search_log, solver_report = run_alns(
        order_lookup, driver_lookup, distance_matrix, args
    )
    routes_df, steps_df, summary_df = routes_to_outputs(
        routes,
        driver_lookup,
        order_lookup,
        order_revenue_lookup,
        distance_matrix,
    )

    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
        routes_path = os.path.join(args.output_dir, METHOD_NAME + "_routes.csv")
        steps_path = os.path.join(args.output_dir, METHOD_NAME + "_route_steps.csv")
        summary_path = os.path.join(args.output_dir, METHOD_NAME + "_summary.csv")
        search_log_path = os.path.join(args.output_dir, METHOD_NAME + "_search_log.csv")
        solver_report_path = os.path.join(args.output_dir, METHOD_NAME + "_solver_report.csv")
    else:
        os.makedirs(ROUTE_DIR, exist_ok=True)
        os.makedirs(REPORT_DIR, exist_ok=True)
        routes_path, steps_path, summary_path = ROUTES_PATH, STEPS_PATH, SUMMARY_PATH
        search_log_path, solver_report_path = SEARCH_LOG_PATH, SOLVER_REPORT_PATH
    solver_report["instance_id"] = args.instance_id
    solver_report["data_dir"] = os.path.abspath(args.data_dir)
    routes_df.to_csv(routes_path, index=False, encoding="utf-8-sig")
    steps_df.to_csv(steps_path, index=False, encoding="utf-8-sig")
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    search_log.to_csv(search_log_path, index=False, encoding="utf-8-sig")
    solver_report.to_csv(solver_report_path, index=False, encoding="utf-8-sig")

    print("\nALNS completed.")
    print("Distance: {:.3f} km".format(metrics["distance"]))
    print("Cost: {:,.0f} VND".format(metrics["cost"]))
    print("Used drivers: {}".format(metrics["used_drivers"]))
    print("Max orders/driver: {}".format(metrics["max_orders"]))
    print("Routes: " + routes_path)
    print("Search report: " + solver_report_path)


if __name__ == "__main__":
    main()
