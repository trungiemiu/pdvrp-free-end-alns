import os
import argparse
import pandas as pd
import numpy as np

from routing_economics import build_order_revenue_lookup, sum_order_revenue


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
ROUTE_DIR = os.path.join(OUTPUT_DIR, "routes")
REPORT_DIR = os.path.join(OUTPUT_DIR, "reports")

ORDERS_PATH = os.path.join(DATA_DIR, "orders.csv")
DRIVERS_PATH = os.path.join(DATA_DIR, "drivers.csv")
VEHICLE_PARAMS_PATH = os.path.join(DATA_DIR, "vehicle_parameters.csv")
DISTANCE_MATRIX_PATH = os.path.join(DATA_DIR, "distance_matrix.csv")


def normalize_vehicle_type(value):
    value = str(value).strip().lower()
    value = value.replace("-", "_").replace(" ", "_")
    return value


def make_method_config(method_name):
    return {
        "routes_path": os.path.join(ROUTE_DIR, f"{method_name}_routes.csv"),
        "summary_path": os.path.join(REPORT_DIR, f"{method_name}_summary.csv"),
        "steps_path": os.path.join(ROUTE_DIR, f"{method_name}_route_steps.csv"),
        "feasibility_output_path": os.path.join(REPORT_DIR, f"{method_name}_feasibility_report.csv"),
        "driver_check_output_path": os.path.join(REPORT_DIR, f"{method_name}_driver_check_report.csv"),
    }


# Retained comparison methods plus the single proposed solver.
ALL_METHODS = [
    "baseline",
    "improved_baseline",
    "balanced_improved",
    "ortools",
    "milp_pulp",
    "alns_pdvrp",
    "moalns_weighted_sum",
    "moalns_topsis",
    "moalns_vikor",
    "moalns_promethee_ii",
    "moalns_waspas",
    "moalns_borda",
    "moalns_ridge_ml",
    "moalns_mlp_dl",
]
METHOD_CONFIG = {name: make_method_config(name) for name in ALL_METHODS}


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate routing method feasibility.")

    parser.add_argument(
        "--method",
        type=str,
        default=None,
        help="Method name to evaluate.",
    )

    parser.add_argument(
        "--list-methods",
        action="store_true",
        help="List available method names.",
    )

    return parser.parse_args()


def load_input_data():
    if not os.path.exists(ORDERS_PATH):
        raise FileNotFoundError(f"Orders file not found: {ORDERS_PATH}")

    if not os.path.exists(DRIVERS_PATH):
        raise FileNotFoundError(f"Drivers file not found: {DRIVERS_PATH}")

    if not os.path.exists(VEHICLE_PARAMS_PATH):
        raise FileNotFoundError(f"Vehicle parameter file not found: {VEHICLE_PARAMS_PATH}")

    orders_df = pd.read_csv(ORDERS_PATH)
    drivers_df = pd.read_csv(DRIVERS_PATH)
    vehicle_params_df = pd.read_csv(VEHICLE_PARAMS_PATH)

    orders_df["required_vehicle"] = orders_df["required_vehicle"].apply(normalize_vehicle_type)
    drivers_df["vehicle_type"] = drivers_df["vehicle_type"].apply(normalize_vehicle_type)
    vehicle_params_df["vehicle_type"] = vehicle_params_df["vehicle_type"].apply(normalize_vehicle_type)

    return orders_df, drivers_df, vehicle_params_df


def load_distance_matrix():
    if not os.path.exists(DISTANCE_MATRIX_PATH):
        raise FileNotFoundError(f"Distance matrix file not found: {DISTANCE_MATRIX_PATH}")

    return pd.read_csv(DISTANCE_MATRIX_PATH, index_col=0)


def build_order_lookup(orders_df):
    lookup = {}

    for _, row in orders_df.iterrows():
        order_id = str(row["order_id"])
        order_num = order_id.replace("O", "").zfill(2)

        lookup[order_id] = {
            "order_id": order_id,
            "pickup_node": f"P{order_num}",
            "delivery_node": f"L{order_num}",
            "demand_kg": float(row["demand_kg"]),
            "required_vehicle": row["required_vehicle"],
        }

    return lookup


def build_driver_lookup(drivers_df, vehicle_params_df):
    capacity_lookup = dict(zip(vehicle_params_df["vehicle_type"], vehicle_params_df["capacity_kg"]))
    cost_lookup = dict(zip(vehicle_params_df["vehicle_type"], vehicle_params_df["cost_vnd_per_km"]))

    lookup = {}

    for _, row in drivers_df.iterrows():
        driver_id = str(row["driver_id"])
        vehicle_type = row["vehicle_type"]

        lookup[driver_id] = {
            "driver_id": driver_id,
            "vehicle_type": vehicle_type,
            "start_node": f"{driver_id}_START",
            "capacity_kg": float(capacity_lookup.get(vehicle_type, np.inf)),
            "cost_per_km": float(cost_lookup.get(vehicle_type, 0.0)),
        }

    return lookup


def read_routes_file(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Routes file not found: {path}")

    return pd.read_csv(path)


def read_summary_file(path):
    if not os.path.exists(path):
        return pd.DataFrame()

    return pd.read_csv(path)


def read_steps_file(path):
    if not os.path.exists(path):
        return pd.DataFrame()

    return pd.read_csv(path)


def get_assigned_routes(routes_df):
    if routes_df.empty:
        return routes_df

    if "status" in routes_df.columns:
        return routes_df[routes_df["status"] == "assigned"].copy()

    if "driver_id" in routes_df.columns:
        return routes_df.dropna(subset=["driver_id"]).copy()

    return routes_df.copy()


def check_all_orders_assigned(routes_df, order_lookup):
    assigned = get_assigned_routes(routes_df)

    if "order_id" not in assigned.columns:
        assigned_orders = set()
    else:
        assigned_orders = set(assigned["order_id"].dropna().astype(str).tolist())

    all_orders = set(order_lookup.keys())

    missing_orders = sorted(list(all_orders - assigned_orders))
    extra_orders = sorted(list(assigned_orders - all_orders))

    return {
        "assigned_orders_count": len(assigned_orders),
        "missing_orders": ";".join(missing_orders),
        "extra_orders": ";".join(extra_orders),
        "all_orders_assigned": len(missing_orders) == 0 and len(extra_orders) == 0,
    }


def check_duplicate_orders(routes_df):
    assigned = get_assigned_routes(routes_df)

    if assigned.empty or "order_id" not in assigned.columns:
        return {
            "no_duplicate_orders": True,
            "duplicate_orders": "",
        }

    counts = assigned["order_id"].dropna().astype(str).value_counts()
    duplicates = counts[counts > 1].index.tolist()

    return {
        "no_duplicate_orders": len(duplicates) == 0,
        "duplicate_orders": ";".join(duplicates),
    }


def check_vehicle_compatibility(routes_df, order_lookup, driver_lookup):
    assigned = get_assigned_routes(routes_df)

    violations = []

    if assigned.empty:
        return {
            "vehicle_compatible": True,
            "vehicle_violations": "",
        }

    for _, row in assigned.iterrows():
        order_id = str(row.get("order_id", ""))
        driver_id = str(row.get("driver_id", ""))

        if order_id not in order_lookup:
            continue

        if driver_id not in driver_lookup:
            violations.append(f"{order_id}:{driver_id}:unknown_driver")
            continue

        required = order_lookup[order_id]["required_vehicle"]
        actual = driver_lookup[driver_id]["vehicle_type"]

        if required != actual:
            violations.append(f"{order_id}:{driver_id}:{actual}_required_{required}")

    return {
        "vehicle_compatible": len(violations) == 0,
        "vehicle_violations": ";".join(violations),
    }


def check_pickup_before_delivery(routes_df, steps_df, order_lookup):
    violations = []

    if not steps_df.empty and {"order_id", "action", "step"}.issubset(steps_df.columns):
        for order_id in order_lookup.keys():
            order_steps = steps_df[steps_df["order_id"].astype(str) == str(order_id)]

            pickup_steps = order_steps[order_steps["action"].astype(str).str.lower() == "pickup"]["step"]
            delivery_steps = order_steps[order_steps["action"].astype(str).str.lower() == "delivery"]["step"]

            if pickup_steps.empty or delivery_steps.empty:
                violations.append(f"{order_id}:missing_pickup_or_delivery")
                continue

            if float(pickup_steps.min()) >= float(delivery_steps.min()):
                violations.append(f"{order_id}:pickup_not_before_delivery")

        return {
            "pickup_before_delivery": len(violations) == 0,
            "pickup_delivery_violations": ";".join(violations),
        }

    assigned = get_assigned_routes(routes_df)

    if {"pickup_step", "delivery_step"}.issubset(assigned.columns):
        for _, row in assigned.iterrows():
            order_id = str(row["order_id"])

            if pd.isna(row["pickup_step"]) or pd.isna(row["delivery_step"]):
                violations.append(f"{order_id}:missing_step")
                continue

            if float(row["pickup_step"]) >= float(row["delivery_step"]):
                violations.append(f"{order_id}:pickup_not_before_delivery")

    return {
        "pickup_before_delivery": len(violations) == 0,
        "pickup_delivery_violations": ";".join(violations),
    }


def check_capacity(steps_df, driver_lookup):
    violations = []

    if steps_df.empty:
        return {
            "capacity_feasible": True,
            "capacity_violations": "",
        }

    if {"driver_id", "load_after_kg"}.issubset(steps_df.columns):
        for _, row in steps_df.iterrows():
            driver_id = str(row["driver_id"])

            if driver_id not in driver_lookup:
                continue

            load_after = float(row["load_after_kg"])
            capacity = float(driver_lookup[driver_id]["capacity_kg"])

            if load_after < -1e-6 or load_after > capacity + 1e-6:
                violations.append(f"{driver_id}:step_{row.get('step', '')}:load_{load_after}_cap_{capacity}")

    return {
        "capacity_feasible": len(violations) == 0,
        "capacity_violations": ";".join(violations),
    }


def compute_assigned_revenue(routes_df, order_revenue_lookup):
    assigned = get_assigned_routes(routes_df)

    if assigned.empty or "order_id" not in assigned.columns:
        return 0.0

    assigned_order_ids = sorted(set(assigned["order_id"].dropna().astype(str).tolist()))
    return sum_order_revenue(assigned_order_ids, order_revenue_lookup)


def build_driver_check(summary_df, steps_df, routes_df, driver_lookup, order_revenue_lookup):
    assigned = get_assigned_routes(routes_df)
    records = []

    for driver_id, driver in driver_lookup.items():
        if not summary_df.empty and "driver_id" in summary_df.columns:
            summary_rows = summary_df[summary_df["driver_id"].astype(str) == str(driver_id)]
        else:
            summary_rows = pd.DataFrame()

        if not steps_df.empty and "driver_id" in steps_df.columns:
            driver_steps = steps_df[steps_df["driver_id"].astype(str) == str(driver_id)].copy()
        else:
            driver_steps = pd.DataFrame()

        if not summary_rows.empty:
            s = summary_rows.iloc[0]
            num_orders = int(s.get("num_orders", 0))
            total_distance = float(s.get("total_distance_km", 0.0))
            total_cost = float(s.get("total_cost_vnd", 0.0))
            driver_assigned = assigned[
                assigned["driver_id"].astype(str) == str(driver_id)
            ] if not assigned.empty and "driver_id" in assigned.columns else pd.DataFrame()
            assigned_order_ids = (
                sorted(set(driver_assigned["order_id"].dropna().astype(str).tolist()))
                if "order_id" in driver_assigned.columns
                else []
            )
            total_revenue = (
                float(s.get("total_revenue_vnd"))
                if "total_revenue_vnd" in summary_rows.columns
                else sum_order_revenue(assigned_order_ids, order_revenue_lookup)
            )
            net_profit = float(s.get("net_profit_vnd", total_revenue - total_cost))
            total_duration_seconds = (
                float(s.get("total_duration_seconds"))
                if "total_duration_seconds" in summary_rows.columns
                else (
                    float(driver_steps["duration_seconds"].sum())
                    if "duration_seconds" in driver_steps.columns
                    else 0.0
                )
            )
        else:
            num_orders = 0
            total_distance = float(driver_steps["distance_km"].sum()) if "distance_km" in driver_steps.columns else 0.0
            total_cost = float(driver_steps["cost_vnd"].sum()) if "cost_vnd" in driver_steps.columns else 0.0
            total_duration_seconds = (
                float(driver_steps["duration_seconds"].sum())
                if "duration_seconds" in driver_steps.columns
                else 0.0
            )
            driver_assigned = assigned[
                assigned["driver_id"].astype(str) == str(driver_id)
            ] if not assigned.empty and "driver_id" in assigned.columns else pd.DataFrame()
            assigned_order_ids = (
                sorted(set(driver_assigned["order_id"].dropna().astype(str).tolist()))
                if "order_id" in driver_assigned.columns
                else []
            )
            num_orders = len(assigned_order_ids) if assigned_order_ids else num_orders
            total_revenue = sum_order_revenue(assigned_order_ids, order_revenue_lookup)
            net_profit = total_revenue - total_cost

        max_load_after = float(driver_steps["load_after_kg"].max()) if "load_after_kg" in driver_steps.columns and not driver_steps.empty else 0.0

        records.append({
            "driver_id": driver_id,
            "vehicle_type": driver["vehicle_type"],
            "capacity_kg": driver["capacity_kg"],
            "num_orders": num_orders,
            "total_distance_km": round(total_distance, 3),
            "total_cost_vnd": round(total_cost, 0),
            "total_revenue_vnd": round(total_revenue, 0),
            "net_profit_vnd": round(net_profit, 0),
            "total_duration_seconds": round(total_duration_seconds, 1),
            "total_duration_minutes": round(total_duration_seconds / 60.0, 2),
            "max_load_after_kg": round(max_load_after, 3),
            "capacity_ok": max_load_after <= driver["capacity_kg"] + 1e-6,
        })

    return pd.DataFrame(records)


def evaluate_method(method_name):
    config = METHOD_CONFIG.get(method_name, make_method_config(method_name))

    print(f"Selected method: {method_name}")
    print(f"Routes path: {config['routes_path']}")
    print(f"Summary path: {config['summary_path']}")

    if config.get("steps_path"):
        print(f"Steps path: {config['steps_path']}")

    orders_df, drivers_df, vehicle_params_df = load_input_data()
    distance_matrix = load_distance_matrix()
    order_lookup = build_order_lookup(orders_df)
    driver_lookup = build_driver_lookup(drivers_df, vehicle_params_df)
    order_revenue_lookup = build_order_revenue_lookup(
        orders_df,
        vehicle_params_df,
        distance_matrix,
    )

    routes_df = read_routes_file(config["routes_path"])
    summary_df = read_summary_file(config["summary_path"])
    steps_df = read_steps_file(config["steps_path"])

    assignment_result = check_all_orders_assigned(routes_df, order_lookup)
    duplicate_result = check_duplicate_orders(routes_df)
    vehicle_result = check_vehicle_compatibility(routes_df, order_lookup, driver_lookup)
    precedence_result = check_pickup_before_delivery(routes_df, steps_df, order_lookup)
    capacity_result = check_capacity(steps_df, driver_lookup)

    assigned = get_assigned_routes(routes_df)

    used_drivers = 0
    max_orders_per_driver = 0
    total_distance = 0.0
    total_cost = 0.0
    total_revenue = 0.0
    net_profit = 0.0
    total_duration_seconds = 0.0

    if not summary_df.empty:
        if "num_orders" in summary_df.columns:
            used_drivers = int((summary_df["num_orders"] > 0).sum())
            max_orders_per_driver = int(summary_df["num_orders"].max()) if len(summary_df) else 0

        if "total_distance_km" in summary_df.columns:
            total_distance = float(summary_df["total_distance_km"].sum())

        if "total_cost_vnd" in summary_df.columns:
            total_cost = float(summary_df["total_cost_vnd"].sum())

        if "total_revenue_vnd" in summary_df.columns:
            total_revenue = float(summary_df["total_revenue_vnd"].sum())
        else:
            total_revenue = compute_assigned_revenue(routes_df, order_revenue_lookup)

        if "net_profit_vnd" in summary_df.columns:
            net_profit = float(summary_df["net_profit_vnd"].sum())
        else:
            net_profit = total_revenue - total_cost

        if "total_duration_seconds" in summary_df.columns:
            total_duration_seconds = float(summary_df["total_duration_seconds"].sum())
    else:
        if not assigned.empty and "driver_id" in assigned.columns:
            used_drivers = int(assigned["driver_id"].nunique())

        if not steps_df.empty:
            if "distance_km" in steps_df.columns:
                total_distance = float(steps_df["distance_km"].sum())

            if "cost_vnd" in steps_df.columns:
                total_cost = float(steps_df["cost_vnd"].sum())

            if "duration_seconds" in steps_df.columns:
                total_duration_seconds = float(steps_df["duration_seconds"].sum())

        total_revenue = compute_assigned_revenue(routes_df, order_revenue_lookup)
        net_profit = total_revenue - total_cost

    feasibility = {
        "method": method_name,
        "total_orders": len(order_lookup),
        "assigned_orders": assignment_result["assigned_orders_count"],
        "unassigned_orders": len([x for x in assignment_result["missing_orders"].split(";") if x]),
        "used_drivers": used_drivers,
        "max_orders_per_driver": max_orders_per_driver,
        "total_distance_km": round(total_distance, 3),
        "total_cost_vnd": round(total_cost, 0),
        "total_revenue_vnd": round(total_revenue, 0),
        "net_profit_vnd": round(net_profit, 0),
        "total_duration_seconds": round(total_duration_seconds, 1),
        "total_duration_minutes": round(total_duration_seconds / 60.0, 2),
        "all_orders_assigned": assignment_result["all_orders_assigned"],
        "missing_orders": assignment_result["missing_orders"],
        "extra_orders": assignment_result["extra_orders"],
        "no_duplicate_orders": duplicate_result["no_duplicate_orders"],
        "duplicate_orders": duplicate_result["duplicate_orders"],
        "vehicle_compatible": vehicle_result["vehicle_compatible"],
        "vehicle_violations": vehicle_result["vehicle_violations"],
        "pickup_before_delivery": precedence_result["pickup_before_delivery"],
        "pickup_delivery_violations": precedence_result["pickup_delivery_violations"],
        "capacity_feasible": capacity_result["capacity_feasible"],
        "capacity_violations": capacity_result["capacity_violations"],
    }

    feasibility_df = pd.DataFrame([feasibility])
    driver_check_df = build_driver_check(
        summary_df,
        steps_df,
        routes_df,
        driver_lookup,
        order_revenue_lookup,
    )

    os.makedirs(REPORT_DIR, exist_ok=True)

    feasibility_df.to_csv(config["feasibility_output_path"], index=False, encoding="utf-8-sig")
    driver_check_df.to_csv(config["driver_check_output_path"], index=False, encoding="utf-8-sig")

    print("\nEvaluation completed.")
    print(f"Feasibility report saved to: {config['feasibility_output_path']}")
    print(f"Driver check report saved to: {config['driver_check_output_path']}")
    print("\nFeasibility summary:")
    print(feasibility_df.T)

    return feasibility_df, driver_check_df


def main():
    args = parse_args()

    if args.list_methods:
        print("Available methods:")
        for method_name in sorted(METHOD_CONFIG.keys()):
            print(f"  - {method_name}")
        return

    if args.method is None:
        raise ValueError("Please provide --method or use --list-methods.")

    evaluate_method(args.method)


if __name__ == "__main__":
    main()
