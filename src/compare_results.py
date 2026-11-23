import os

import numpy as np
import pandas as pd


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_DIR = os.path.join(BASE_DIR, "outputs", "reports")
OUTPUT_PATH = os.path.join(REPORT_DIR, "method_comparison.csv")

METHODS = {
    "baseline": ("Baseline: Immediate Pickup-Delivery", "traditional_heuristic"),
    "improved_baseline": ("Improved Baseline", "traditional_heuristic"),
    "balanced_improved": ("Balanced Improved Baseline", "traditional_heuristic"),
    "ortools": ("OR-Tools Reference", "cp_solver"),
    "milp_pulp": ("PuLP MILP Reference", "exact_solver"),
    "alns_pdvrp": ("Proposed ALNS-PDVRP", "adaptive_metaheuristic"),
    "moalns_weighted_sum": ("MOALNS + Weighted Sum", "multiobjective_modm"),
    "moalns_topsis": ("MOALNS + TOPSIS", "multiobjective_modm"),
    "moalns_vikor": ("MOALNS + VIKOR", "multiobjective_modm"),
    "moalns_promethee_ii": ("MOALNS + PROMETHEE II", "multiobjective_modm"),
    "moalns_waspas": ("MOALNS + WASPAS", "multiobjective_modm"),
    "moalns_borda": ("MOALNS + Borda Consensus", "multiobjective_modm"),
    "moalns_ridge_ml": ("MOALNS + Ridge Preference Learning", "preference_learning"),
    "moalns_mlp_dl": ("MOALNS + MLP Preference Learning", "preference_learning"),
}


def first_value(frame, column, default=np.nan):
    if frame is None or frame.empty or column not in frame.columns:
        return default
    values = frame[column].dropna()
    return values.iloc[0] if not values.empty else default


def aggregate_summary(path):
    if not os.path.exists(path):
        return None
    frame = pd.read_csv(path)
    if frame.empty:
        return {}

    def total(column):
        return float(frame[column].fillna(0).sum()) if column in frame.columns else np.nan

    used = frame
    if "num_orders" in frame.columns:
        used = frame[frame["num_orders"].fillna(0) > 0]
    return {
        "used_drivers": len(used),
        "max_orders_per_driver": int(frame["num_orders"].max()) if "num_orders" in frame else np.nan,
        "total_distance_km": total("total_distance_km"),
        "total_cost_vnd": total("total_cost_vnd"),
        "total_revenue_vnd": total("total_revenue_vnd"),
        "net_profit_vnd": total("net_profit_vnd"),
    }


def feasibility(path):
    if not os.path.exists(path):
        return {}
    frame = pd.read_csv(path)
    fields = [
        "all_orders_assigned",
        "no_duplicate_orders",
        "vehicle_compatible",
        "pickup_before_delivery",
        "capacity_feasible",
        "total_duration_seconds",
        "total_duration_minutes",
    ]
    return {field: first_value(frame, field) for field in fields}


def main():
    rows = []
    for method, (display_name, category) in METHODS.items():
        summary = aggregate_summary(os.path.join(REPORT_DIR, f"{method}_summary.csv"))
        if summary is None:
            continue
        checks = feasibility(os.path.join(REPORT_DIR, f"{method}_feasibility_report.csv"))
        row = {"method": method, "display_name": display_name, "category": category}
        row.update(summary)
        row.update(checks)
        flags = [
            row.get("all_orders_assigned"),
            row.get("no_duplicate_orders"),
            row.get("vehicle_compatible"),
            row.get("pickup_before_delivery"),
            row.get("capacity_feasible"),
        ]
        row["feasible_score"] = sum(str(value).strip().lower() in {"true", "1"} for value in flags)
        rows.append(row)

    result = pd.DataFrame(rows)
    if result.empty:
        raise FileNotFoundError("No retained method summaries were found.")

    baseline = result[result["method"] == "baseline"]
    if not baseline.empty:
        base_cost = float(baseline.iloc[0]["total_cost_vnd"])
        base_distance = float(baseline.iloc[0]["total_distance_km"])
        result["cost_saving_vs_baseline_vnd"] = base_cost - result["total_cost_vnd"]
        result["cost_saving_vs_baseline_pct"] = 100 * result["cost_saving_vs_baseline_vnd"] / base_cost
        result["distance_saving_vs_baseline_km"] = base_distance - result["total_distance_km"]
        result["distance_saving_vs_baseline_pct"] = 100 * result["distance_saving_vs_baseline_km"] / base_distance

    result = result.sort_values(
        ["feasible_score", "total_cost_vnd", "total_distance_km"],
        ascending=[False, True, True],
    ).reset_index(drop=True)
    os.makedirs(REPORT_DIR, exist_ok=True)
    result.to_csv(OUTPUT_PATH, index=False)
    print("Comparison completed.")
    print(f"Saved to: {OUTPUT_PATH}\n")
    print(result[["method", "total_distance_km", "total_cost_vnd", "feasible_score"]])


if __name__ == "__main__":
    main()
