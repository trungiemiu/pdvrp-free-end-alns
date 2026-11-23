"""Independent feasibility/objective checker that does not import solver logic."""

import argparse
import json
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd


OBJECTIVES = ("total_cost_vnd", "max_route_duration_minutes", "workload_imbalance")


def normalize_vehicle(value):
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


@dataclass
class Instance:
    orders: dict
    drivers: dict
    distance: pd.DataFrame
    duration: pd.DataFrame


def load_instance(data_dir):
    orders_df = pd.read_csv(os.path.join(data_dir, "orders.csv"))
    drivers_df = pd.read_csv(os.path.join(data_dir, "drivers.csv"))
    vehicle_df = pd.read_csv(os.path.join(data_dir, "vehicle_parameters.csv"))
    distance = pd.read_csv(os.path.join(data_dir, "distance_matrix.csv"), index_col=0)
    duration_path = os.path.join(data_dir, "duration_matrix_osrm_seconds.csv")
    if not os.path.exists(duration_path):
        duration_path = os.path.join(data_dir, "duration_matrix.csv")
    duration = pd.read_csv(duration_path, index_col=0)
    vehicle_df["vehicle_type"] = vehicle_df["vehicle_type"].map(normalize_vehicle)
    capacities = dict(zip(vehicle_df["vehicle_type"], vehicle_df["capacity_kg"].astype(float)))
    costs = dict(zip(vehicle_df["vehicle_type"], vehicle_df["cost_vnd_per_km"].astype(float)))
    orders = {}
    for _, row in orders_df.iterrows():
        order_id = str(row["order_id"])
        number = order_id.replace("O", "").zfill(2)
        orders[order_id] = {
            "pickup_node": "P" + number,
            "delivery_node": "L" + number,
            "demand": float(row["demand_kg"]),
            "required_vehicle": normalize_vehicle(row["required_vehicle"]),
        }
    drivers = {}
    for _, row in drivers_df.iterrows():
        driver_id = str(row["driver_id"])
        vehicle_type = normalize_vehicle(row["vehicle_type"])
        drivers[driver_id] = {
            "start_node": driver_id + "_START",
            "vehicle_type": vehicle_type,
            "capacity": float(capacities[vehicle_type]),
            "cost_per_km": float(costs[vehicle_type]),
        }
    return Instance(orders, drivers, distance, duration)


def deserialize_routes(text):
    raw = json.loads(text) if isinstance(text, str) else text
    return {
        str(driver_id): [(str(event[0]), str(event[1]).lower()) for event in sequence]
        for driver_id, sequence in raw.items()
    }


def matrix_value(matrix, origin, destination, violations, label):
    if origin not in matrix.index or destination not in matrix.columns:
        violations.append(f"missing_{label}_arc:{origin}->{destination}")
        return 0.0
    value = float(matrix.loc[origin, destination])
    if not np.isfinite(value) or value < 0:
        violations.append(f"invalid_{label}_arc:{origin}->{destination}:{value}")
        return 0.0
    return value


def check_solution(instance, routes, stored=None, tolerance=1e-6):
    stored = stored or {}
    violations = []
    occurrences = {order_id: [] for order_id in instance.orders}
    total_cost = total_distance = 0.0
    durations = {driver_id: 0.0 for driver_id in instance.drivers}
    counts = {driver_id: 0 for driver_id in instance.drivers}

    unknown_drivers = sorted(set(routes) - set(instance.drivers))
    violations.extend("unknown_driver:" + driver_id for driver_id in unknown_drivers)

    for driver_id, driver in instance.drivers.items():
        sequence = routes.get(driver_id, [])
        current = driver["start_node"]
        load = 0.0
        picked_here = set()
        delivered_here = set()
        route_orders = set()
        for position, (order_id, action) in enumerate(sequence, start=1):
            if order_id not in instance.orders:
                violations.append(f"unknown_order:{driver_id}:{position}:{order_id}")
                continue
            order = instance.orders[order_id]
            if action not in {"pickup", "delivery"}:
                violations.append(f"invalid_action:{driver_id}:{position}:{order_id}:{action}")
                continue
            node = order["pickup_node"] if action == "pickup" else order["delivery_node"]
            arc_distance = matrix_value(instance.distance, current, node, violations, "distance")
            total_distance += arc_distance
            total_cost += arc_distance * driver["cost_per_km"]
            durations[driver_id] += matrix_value(instance.duration, current, node, violations, "duration")
            current = node
            occurrences[order_id].append((driver_id, action, position))
            route_orders.add(order_id)
            if order["required_vehicle"] != driver["vehicle_type"]:
                violations.append(
                    f"vehicle_incompatible:{order_id}:{driver_id}:{driver['vehicle_type']}"
                )
            if action == "pickup":
                if order_id in picked_here:
                    violations.append(f"duplicate_pickup:{order_id}:{driver_id}")
                picked_here.add(order_id)
                load += order["demand"]
            else:
                if order_id not in picked_here:
                    violations.append(f"delivery_before_pickup:{order_id}:{driver_id}")
                if order_id in delivered_here:
                    violations.append(f"duplicate_delivery:{order_id}:{driver_id}")
                delivered_here.add(order_id)
                load -= order["demand"]
            if load < -tolerance or load > driver["capacity"] + tolerance:
                violations.append(
                    f"capacity:{driver_id}:{position}:load={load}:capacity={driver['capacity']}"
                )
        if abs(load) > tolerance:
            violations.append(f"nonzero_final_load:{driver_id}:{load}")
        if picked_here != delivered_here:
            violations.append(
                f"route_pair_mismatch:{driver_id}:picked={sorted(picked_here)}:delivered={sorted(delivered_here)}"
            )
        counts[driver_id] = len(route_orders)

    for order_id, events in occurrences.items():
        pickups = [event for event in events if event[1] == "pickup"]
        deliveries = [event for event in events if event[1] == "delivery"]
        if len(pickups) != 1:
            violations.append(f"pickup_count:{order_id}:{len(pickups)}")
        if len(deliveries) != 1:
            violations.append(f"delivery_count:{order_id}:{len(deliveries)}")
        if len(pickups) == 1 and len(deliveries) == 1 and pickups[0][0] != deliveries[0][0]:
            violations.append(f"different_drivers:{order_id}:{pickups[0][0]}:{deliveries[0][0]}")

    groups = {}
    for driver_id, driver in instance.drivers.items():
        groups.setdefault(driver["vehicle_type"], []).append(float(counts[driver_id]))
    imbalance = float(np.mean([np.std(values) for values in groups.values()])) if groups else 0.0
    recomputed = {
        "total_cost_vnd": total_cost,
        "max_route_duration_minutes": max(durations.values(), default=0.0) / 60.0,
        "workload_imbalance": imbalance,
        "total_distance_km": total_distance,
    }
    objective_mismatches = []
    for objective in OBJECTIVES:
        if objective not in stored or pd.isna(stored[objective]):
            continue
        expected, actual = float(stored[objective]), recomputed[objective]
        allowed = tolerance * max(1.0, abs(expected), abs(actual))
        if abs(expected - actual) > allowed:
            objective_mismatches.append(f"{objective}:stored={expected}:recomputed={actual}")
    violations.extend("objective_mismatch:" + item for item in objective_mismatches)
    return {
        "feasible": not any(not item.startswith("objective_mismatch:") for item in violations),
        "objectives_match": len(objective_mismatches) == 0,
        "all_checks_pass": len(violations) == 0,
        "violations": ";".join(violations),
        **{"recomputed_" + key: value for key, value in recomputed.items()},
    }


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--tolerance", type=float, default=1e-6)
    parser.add_argument("--fail-on-error", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    instance = load_instance(args.data_dir)
    archive = pd.read_csv(args.archive)
    if "routes_json" not in archive.columns:
        raise ValueError("Archive must contain routes_json.")
    rows = []
    for index, row in archive.iterrows():
        result = check_solution(
            instance, deserialize_routes(row["routes_json"]), row.to_dict(), args.tolerance
        )
        rows.append({"solution_id": row.get("solution_id", index + 1), **result})
    report = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    report.to_csv(args.output, index=False, encoding="utf-8-sig")
    failures = int((~report["all_checks_pass"]).sum())
    print(f"Independent checker: {len(report)} solutions, {failures} failures")
    print("Report: " + os.path.abspath(args.output))
    if args.fail_on_error and failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
