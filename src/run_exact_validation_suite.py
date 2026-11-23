"""Compare ALNS/MOALNS cost extremes with proven PuLP/CBC small-instance optima."""

import argparse
import json
import os
import subprocess
import sys
import time

import numpy as np
import pandas as pd

import milp_pulp_solver as milp
from independent_route_checker import check_solution, deserialize_routes, load_instance


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="data/exact_validation/manifest.csv")
    parser.add_argument("--output-root", default="outputs/validation/exact_suite")
    parser.add_argument("--seeds", default="42,43,44")
    parser.add_argument("--heuristic-time", type=float, default=60.0)
    parser.add_argument("--milp-time", type=int, default=600)
    parser.add_argument("--iterations", type=int, default=5000)
    parser.add_argument("--instance-pattern", default="")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def normalize_inputs(data_dir):
    drivers = pd.read_csv(os.path.join(data_dir, "drivers.csv"))
    orders = pd.read_csv(os.path.join(data_dir, "orders.csv"))
    vehicles = pd.read_csv(os.path.join(data_dir, "vehicle_parameters.csv"))
    distance = pd.read_csv(os.path.join(data_dir, "distance_matrix.csv"), index_col=0)
    for frame, column in ((drivers, "vehicle_type"), (orders, "required_vehicle"), (vehicles, "vehicle_type")):
        frame[column] = frame[column].map(milp.normalize_vehicle_type)
    return drivers, orders, vehicles, distance


def routes_from_steps(steps, driver_ids):
    routes = {str(driver_id): [] for driver_id in driver_ids}
    if steps.empty:
        return routes
    for driver_id, frame in steps.sort_values(["driver_id", "step"]).groupby("driver_id"):
        routes[str(driver_id)] = [
            (str(row["order_id"]), str(row["action"]).lower()) for _, row in frame.iterrows()
            if pd.notna(row.get("order_id")) and pd.notna(row.get("action"))
        ]
    return routes


def run_command(command):
    started = time.perf_counter()
    subprocess.run(command, check=True)
    return time.perf_counter() - started


def main():
    args = parse_args()
    seeds = [int(value) for value in args.seeds.split(",") if value.strip()]
    manifest = pd.read_csv(args.manifest)
    if args.instance_pattern:
        manifest = manifest[manifest["instance_id"].astype(str).str.contains(args.instance_pattern, regex=False)]
    os.makedirs(args.output_root, exist_ok=True)
    src_dir = os.path.dirname(os.path.abspath(__file__))
    rows = []
    exact_rows = []
    for _, item in manifest.iterrows():
        instance_id, data_dir = str(item["instance_id"]), str(item["data_dir"])
        instance_output = os.path.join(args.output_root, instance_id)
        os.makedirs(instance_output, exist_ok=True)
        independent_instance = load_instance(data_dir)
        exact_path = os.path.join(instance_output, "milp_exact_report.csv")
        if args.force or not os.path.exists(exact_path):
            drivers, orders, vehicles, distance = normalize_inputs(data_dir)
            started = time.perf_counter()
            cbc_log_path = os.path.join(instance_output, "cbc.log")
            result = milp.solve_milp(
                drivers, orders, vehicles, distance,
                time_limit=args.milp_time if args.milp_time > 0 else None,
                solution_limit=None,
                log_path=cbc_log_path,
            )
            runtime = time.perf_counter() - started
            cbc_log = ""
            if os.path.exists(cbc_log_path):
                with open(cbc_log_path, encoding="utf-8", errors="replace") as file:
                    cbc_log = file.read()
            cbc_proved_optimal = "Result - Optimal solution found" in cbc_log
            exact_check = {"all_checks_pass": False, "violations": "not_extracted"}
            if result["status"] in {"Optimal", "Feasible"}:
                _, steps, _ = milp.extract_solution(result, distance)
                routes = routes_from_steps(steps, independent_instance.drivers)
                exact_check = check_solution(
                    independent_instance, routes, {"total_cost_vnd": result["objective"]}
                )
            exact_frame = pd.DataFrame([{
                "instance_id": instance_id,
                "orders": len(independent_instance.orders),
                "status": result["status"],
                "objective_value": result["objective"],
                "runtime_seconds": runtime,
                "proven_optimal": result["status"] == "Optimal" and cbc_proved_optimal,
                "cbc_optimal_marker": cbc_proved_optimal,
                "independent_check_pass": exact_check["all_checks_pass"],
                "independent_check_violations": exact_check["violations"],
            }])
            exact_frame.to_csv(exact_path, index=False, encoding="utf-8-sig")
        exact = pd.read_csv(exact_path).iloc[0]
        exact_rows.append(exact.to_dict())
        proven_optimal = str(exact["proven_optimal"]).strip().lower() == "true"
        optimum = float(exact["objective_value"]) if proven_optimal else np.nan

        for seed in seeds:
            seed_dir = os.path.join(instance_output, f"seed_{seed}")
            os.makedirs(seed_dir, exist_ok=True)
            mo_report_path = os.path.join(seed_dir, "moalns_solver_report.csv")
            if args.force or not os.path.exists(mo_report_path):
                run_command([
                    sys.executable, os.path.join(src_dir, "moalns_pdvrp_solver.py"),
                    "--data-dir", data_dir, "--output-dir", seed_dir,
                    "--instance-id", instance_id, "--variant-id", "exact_validation",
                    "--iterations", str(args.iterations), "--time-limit", str(args.heuristic_time),
                    "--seed", str(seed),
                ])
            mo_archive = pd.read_csv(os.path.join(seed_dir, "moalns_pareto_archive.csv"))
            mo_checks = [
                check_solution(independent_instance, deserialize_routes(row["routes_json"]), row.to_dict())
                for _, row in mo_archive.iterrows()
            ]
            mo_cost = float(mo_archive["total_cost_vnd"].min())
            rows.append({
                "instance_id": instance_id, "orders": len(independent_instance.orders),
                "algorithm": "moalns", "seed": seed, "milp_status": exact["status"],
                "proven_optimum": optimum, "heuristic_cost": mo_cost,
                "gap_percent": 100 * (mo_cost - optimum) / optimum if np.isfinite(optimum) else np.nan,
                "matches_optimum": bool(np.isfinite(optimum) and abs(mo_cost - optimum) <= 1e-6 * max(1, optimum)),
                "independent_feasibility_pass": all(check["all_checks_pass"] for check in mo_checks),
            })

            alns_report_path = os.path.join(seed_dir, "alns_pdvrp_solver_report.csv")
            if args.force or not os.path.exists(alns_report_path):
                run_command([
                    sys.executable, os.path.join(src_dir, "alns_pdvrp_solver.py"),
                    "--data-dir", data_dir, "--output-dir", seed_dir,
                    "--instance-id", instance_id, "--iterations", str(args.iterations),
                    "--time-limit", str(args.heuristic_time), "--seed", str(seed),
                    "--balance-penalty-vnd", "0",
                ])
            alns_report = pd.read_csv(alns_report_path).iloc[0]
            alns_steps = pd.read_csv(os.path.join(seed_dir, "alns_pdvrp_route_steps.csv"))
            alns_routes = routes_from_steps(alns_steps, independent_instance.drivers)
            # Solver reports are rounded for business display; exact comparison uses
            # the independently recomputed cost from the raw event sequence.
            alns_check = check_solution(independent_instance, alns_routes)
            alns_cost = float(alns_check["recomputed_total_cost_vnd"])
            rows.append({
                "instance_id": instance_id, "orders": len(independent_instance.orders),
                "algorithm": "alns", "seed": seed, "milp_status": exact["status"],
                "proven_optimum": optimum, "heuristic_cost": alns_cost,
                "gap_percent": 100 * (alns_cost - optimum) / optimum if np.isfinite(optimum) else np.nan,
                "matches_optimum": bool(np.isfinite(optimum) and abs(alns_cost - optimum) <= 1e-6 * max(1, optimum)),
                "independent_feasibility_pass": alns_check["all_checks_pass"],
            })

    exact_summary = pd.DataFrame(exact_rows)
    comparisons = pd.DataFrame(rows)
    exact_summary.to_csv(os.path.join(args.output_root, "milp_exact_summary.csv"), index=False, encoding="utf-8-sig")
    comparisons.to_csv(os.path.join(args.output_root, "heuristic_optimality_gaps.csv"), index=False, encoding="utf-8-sig")
    aggregate = comparisons.groupby("algorithm").agg(
        runs=("gap_percent", "size"), proven_comparisons=("gap_percent", "count"),
        optimal_matches=("matches_optimum", "sum"), mean_gap_percent=("gap_percent", "mean"),
        max_gap_percent=("gap_percent", "max"), feasibility_passes=("independent_feasibility_pass", "sum"),
    ).reset_index()
    aggregate.to_csv(os.path.join(args.output_root, "exact_validation_aggregate.csv"), index=False, encoding="utf-8-sig")
    print(exact_summary.to_string(index=False))
    print(comparisons.to_string(index=False))
    print(aggregate.to_string(index=False))


if __name__ == "__main__":
    main()
