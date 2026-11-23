"""Convert Li & Lim PDPTW text instances to this project's no-TW PDVRP schema."""

import argparse
import json
import math
import os
import zipfile

import pandas as pd


def parse_args():
    parser = argparse.ArgumentParser(description="Convert one Li & Lim instance and remove time windows.")
    parser.add_argument("--zip", required=True)
    parser.add_argument("--member", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--max-orders", type=int, default=0,
                        help="Keep the first N pickup-delivery pairs; 0 keeps the full instance.")
    parser.add_argument("--vehicle-limit", type=int, default=0,
                        help="Optional fleet limit for derived subsets; 0 preserves the benchmark fleet.")
    return parser.parse_args()


def read_instance(zip_path, member):
    with zipfile.ZipFile(zip_path) as archive:
        text = archive.read(member).decode("utf-8-sig")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    header = [float(value) for value in lines[0].split()]
    rows = [[float(value) for value in line.split()] for line in lines[1:]]
    if len(header) < 2 or any(len(row) < 9 for row in rows):
        raise ValueError("Unexpected Li & Lim instance format.")
    return int(header[0]), float(header[1]), float(header[2]) if len(header) > 2 else 1.0, rows


def main():
    args = parse_args()
    vehicle_count, capacity, speed, rows = read_instance(args.zip, args.member)
    by_id = {int(row[0]): row for row in rows}
    depot = by_id[0]
    pickups = [row for row in rows if int(row[0]) != 0 and row[3] > 0 and int(row[8]) > 0]
    pickups.sort(key=lambda row: int(row[0]))
    if args.max_orders > 0:
        pickups = pickups[:args.max_orders]
    if not pickups:
        raise ValueError("No pickup-delivery pairs found.")
    if args.vehicle_limit > 0:
        vehicle_count = min(vehicle_count, args.vehicle_limit)

    orders, node_coordinates, mapping = [], {}, []
    for index, pickup in enumerate(pickups, start=1):
        delivery_id = int(pickup[8])
        if delivery_id not in by_id:
            raise ValueError(f"Missing delivery node {delivery_id}.")
        delivery = by_id[delivery_id]
        order_id = f"O{index:02d}"
        pickup_node, delivery_node = f"P{index:02d}", f"L{index:02d}"
        orders.append({
            "order_id": order_id,
            "pickup_address": f"benchmark_node_{int(pickup[0])}",
            "delivery_address": f"benchmark_node_{delivery_id}",
            "store_type": "LiLim",
            "demand_kg": abs(float(pickup[3])),
            "required_vehicle": "benchmark_vehicle",
        })
        node_coordinates[pickup_node] = (float(pickup[1]), float(pickup[2]))
        node_coordinates[delivery_node] = (float(delivery[1]), float(delivery[2]))
        mapping.append({
            "order_id": order_id, "original_pickup_id": int(pickup[0]),
            "original_delivery_id": delivery_id,
            "removed_pickup_tw": [pickup[4], pickup[5]],
            "removed_delivery_tw": [delivery[4], delivery[5]],
            "removed_pickup_service_time": pickup[6],
            "removed_delivery_service_time": delivery[6],
        })

    drivers = []
    for index in range(1, vehicle_count + 1):
        driver_id = f"D{index:02d}"
        drivers.append({"driver_id": driver_id, "vehicle_type": "benchmark_vehicle",
                        "start_lat": depot[1], "start_lon": depot[2]})
        node_coordinates[driver_id + "_START"] = (float(depot[1]), float(depot[2]))

    node_ids = list(node_coordinates)
    distance = pd.DataFrame(index=node_ids, columns=node_ids, dtype=float)
    duration = pd.DataFrame(index=node_ids, columns=node_ids, dtype=float)
    for origin in node_ids:
        for destination in node_ids:
            x1, y1 = node_coordinates[origin]; x2, y2 = node_coordinates[destination]
            value = math.hypot(x1 - x2, y1 - y2)
            distance.loc[origin, destination] = value
            # Li & Lim speed converts coordinate distance to benchmark time units;
            # store seconds so the solver reports the original unit as minutes.
            duration.loc[origin, destination] = value / max(speed, 1e-12) * 60.0

    os.makedirs(args.output_dir, exist_ok=True)
    pd.DataFrame(orders).to_csv(os.path.join(args.output_dir, "orders.csv"), index=False)
    pd.DataFrame(drivers).to_csv(os.path.join(args.output_dir, "drivers.csv"), index=False)
    pd.DataFrame([{
        "vehicle_type": "benchmark_vehicle", "number": vehicle_count,
        "capacity_kg": capacity, "revenue_under_30km_vnd": 0,
        "build_up_revenue_vnd_per_km": 0, "cost_vnd_per_km": 1,
    }]).to_csv(os.path.join(args.output_dir, "vehicle_parameters.csv"), index=False)
    distance.to_csv(os.path.join(args.output_dir, "distance_matrix.csv"))
    duration.to_csv(os.path.join(args.output_dir, "duration_matrix_osrm_seconds.csv"))
    metadata = {
        "instance_id": args.instance_id, "source_zip": os.path.abspath(args.zip),
        "source_member": args.member, "transformation": "PDPTW to PDVRP by removing all time windows and service times",
        "coordinate_metric": "Euclidean", "original_vehicle_count": int(read_instance(args.zip, args.member)[0]),
        "used_vehicle_count": vehicle_count, "capacity": capacity, "speed": speed,
        "orders": len(orders), "is_truncated_subset": args.max_orders > 0,
        "order_mapping": mapping,
    }
    with open(os.path.join(args.output_dir, "instance_metadata.json"), "w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=2, ensure_ascii=False)
    print(f"Created {args.instance_id}: {len(orders)} orders, {vehicle_count} vehicles")


if __name__ == "__main__":
    main()
