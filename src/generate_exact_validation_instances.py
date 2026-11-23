"""Create deterministic small PDVRP subsets for exact-validation experiments."""

import argparse
import json
import math
import os

import pandas as pd


REQUIRED_FILES = ("orders.csv", "drivers.csv", "vehicle_parameters.csv", "distance_matrix.csv")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-manifest", default="data/instances_manifest.csv")
    parser.add_argument("--output-root", default="data/exact_validation")
    parser.add_argument("--sizes", default="4,6,8,10")
    parser.add_argument("--exclude", default="current")
    return parser.parse_args()


def subset_matrix(path, nodes):
    matrix = pd.read_csv(path, index_col=0)
    missing = sorted(set(nodes) - set(matrix.index))
    if missing:
        raise ValueError(f"{path} misses nodes: {missing}")
    return matrix.loc[nodes, nodes]


def main():
    args = parse_args()
    sizes = sorted({int(value) for value in args.sizes.split(",") if value.strip()})
    excluded = {value.strip() for value in args.exclude.split(",") if value.strip()}
    manifest = pd.read_csv(args.source_manifest)
    os.makedirs(args.output_root, exist_ok=True)
    rows = []
    for _, source in manifest.iterrows():
        source_id = str(source["instance_id"])
        if source_id in excluded:
            continue
        source_dir = str(source["data_dir"])
        for filename in REQUIRED_FILES:
            if not os.path.exists(os.path.join(source_dir, filename)):
                raise FileNotFoundError(os.path.join(source_dir, filename))
        orders_all = pd.read_csv(os.path.join(source_dir, "orders.csv"))
        drivers_all = pd.read_csv(os.path.join(source_dir, "drivers.csv"))
        vehicles_all = pd.read_csv(os.path.join(source_dir, "vehicle_parameters.csv"))
        for size in sizes:
            if size > len(orders_all):
                continue
            orders = orders_all.iloc[:size].copy()
            # Reduce identical-vehicle symmetry so CBC can prove optimality. Two
            # vehicles are retained even for n=4 to exercise assignment logic.
            driver_limit = min(len(drivers_all), max(2, math.ceil(size / 4)))
            drivers = drivers_all.iloc[:driver_limit].copy()
            vehicles = vehicles_all.copy()
            counts = drivers["vehicle_type"].value_counts().to_dict()
            if "number" in vehicles.columns:
                vehicles["number"] = vehicles["vehicle_type"].map(counts).fillna(0).astype(int)
            short_source = source_id.replace("_notw_subset12", "")
            instance_id = f"{short_source}_n{size:02d}"
            output_dir = os.path.join(args.output_root, instance_id)
            os.makedirs(output_dir, exist_ok=True)
            nodes = [str(driver_id) + "_START" for driver_id in drivers["driver_id"]]
            for order_id in orders["order_id"].astype(str):
                number = order_id.replace("O", "").zfill(2)
                nodes.extend(["P" + number, "L" + number])
            distance = subset_matrix(os.path.join(source_dir, "distance_matrix.csv"), nodes)
            duration_source = os.path.join(source_dir, "duration_matrix_osrm_seconds.csv")
            if not os.path.exists(duration_source):
                duration_source = os.path.join(source_dir, "duration_matrix.csv")
            duration = subset_matrix(duration_source, nodes)
            orders.to_csv(os.path.join(output_dir, "orders.csv"), index=False)
            drivers.to_csv(os.path.join(output_dir, "drivers.csv"), index=False)
            vehicles.to_csv(os.path.join(output_dir, "vehicle_parameters.csv"), index=False)
            distance.to_csv(os.path.join(output_dir, "distance_matrix.csv"))
            duration.to_csv(os.path.join(output_dir, "duration_matrix_osrm_seconds.csv"))
            metadata = {
                "instance_id": instance_id,
                "source_instance": source_id,
                "orders": size,
                "drivers": len(drivers),
                "purpose": "exact cost-optimality and independent implementation validation",
                "selection_rule": "first N requests from the registered development instance",
            }
            with open(os.path.join(output_dir, "instance_metadata.json"), "w", encoding="utf-8") as file:
                json.dump(metadata, file, indent=2)
            rows.append({
                "instance_id": instance_id,
                "data_dir": os.path.abspath(output_dir),
                "source_instance": source_id,
                "orders": size,
                "drivers": len(drivers),
            })
    result = pd.DataFrame(rows)
    result.to_csv(os.path.join(args.output_root, "manifest.csv"), index=False, encoding="utf-8-sig")
    print(result.to_string(index=False))
    print("Validation manifest: " + os.path.abspath(os.path.join(args.output_root, "manifest.csv")))


if __name__ == "__main__":
    main()
