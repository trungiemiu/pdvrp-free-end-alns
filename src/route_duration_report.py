import argparse
import os

import pandas as pd


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
ROUTE_DIR = os.path.join(OUTPUT_DIR, "routes")
REPORT_DIR = os.path.join(OUTPUT_DIR, "reports")

DEFAULT_DURATION_MATRIX_PATH = os.path.join(BASE_DIR, "data", "duration_matrix_osrm_seconds.csv")
REPORT_OUTPUT_PATH = os.path.join(REPORT_DIR, "route_duration_summary.csv")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Annotate route steps and summaries with OSRM travel durations."
    )
    parser.add_argument(
        "--duration-matrix",
        default=DEFAULT_DURATION_MATRIX_PATH,
        help="Duration matrix CSV in seconds.",
    )
    parser.add_argument(
        "--method",
        default=None,
        help="Optional single method name. By default every route_steps file is processed.",
    )
    parser.add_argument(
        "--skip-if-missing",
        action="store_true",
        help="Exit successfully if the duration matrix is missing.",
    )
    return parser.parse_args()


def discover_methods(method_name=None):
    if method_name:
        return [method_name]

    if not os.path.exists(ROUTE_DIR):
        return []

    methods = []

    for file_name in os.listdir(ROUTE_DIR):
        if file_name.endswith("_route_steps.csv"):
            methods.append(file_name[:-len("_route_steps.csv")])

    return sorted(set(methods))


def get_duration(duration_matrix, from_node, to_node):
    if pd.isna(from_node) or pd.isna(to_node):
        return None

    from_node = str(from_node)
    to_node = str(to_node)

    if from_node not in duration_matrix.index or to_node not in duration_matrix.columns:
        return None

    value = duration_matrix.loc[from_node, to_node]

    if pd.isna(value):
        return None

    return round(float(value), 1)


def annotate_method(method_name, duration_matrix):
    steps_path = os.path.join(ROUTE_DIR, f"{method_name}_route_steps.csv")
    summary_path = os.path.join(REPORT_DIR, f"{method_name}_summary.csv")

    if not os.path.exists(steps_path):
        return None

    steps_df = pd.read_csv(steps_path)

    required_cols = {"driver_id", "from_node", "to_node"}
    if not required_cols.issubset(steps_df.columns):
        return None

    steps_df["duration_seconds"] = steps_df.apply(
        lambda row: get_duration(duration_matrix, row["from_node"], row["to_node"]),
        axis=1,
    )
    steps_df["duration_minutes"] = (steps_df["duration_seconds"] / 60.0).round(2)
    steps_df.to_csv(steps_path, index=False, encoding="utf-8-sig")

    driver_durations = (
        steps_df.groupby("driver_id", dropna=False)["duration_seconds"]
        .sum(min_count=1)
        .to_dict()
    )

    summary_df = pd.DataFrame()

    if os.path.exists(summary_path):
        summary_df = pd.read_csv(summary_path)

        if "driver_id" in summary_df.columns:
            summary_df["total_duration_seconds"] = summary_df["driver_id"].map(driver_durations).fillna(0.0).round(1)
            summary_df["total_duration_minutes"] = (summary_df["total_duration_seconds"] / 60.0).round(2)
            summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")

    total_duration_seconds = float(steps_df["duration_seconds"].fillna(0.0).sum())
    missing_legs = int(steps_df["duration_seconds"].isna().sum())

    return {
        "method": method_name,
        "route_steps_path": steps_path,
        "summary_path": summary_path if os.path.exists(summary_path) else "",
        "legs": int(len(steps_df)),
        "missing_duration_legs": missing_legs,
        "total_duration_seconds": round(total_duration_seconds, 1),
        "total_duration_minutes": round(total_duration_seconds / 60.0, 2),
    }


def main():
    args = parse_args()

    if not os.path.exists(args.duration_matrix):
        message = f"Duration matrix not found: {args.duration_matrix}"

        if args.skip_if_missing:
            print(message)
            print("Skipping route duration annotation.")
            return

        raise FileNotFoundError(message)

    duration_matrix = pd.read_csv(args.duration_matrix, index_col=0)
    methods = discover_methods(args.method)

    records = []

    for method_name in methods:
        record = annotate_method(method_name, duration_matrix)

        if record is not None:
            records.append(record)
            print(
                f"{method_name}: {record['total_duration_minutes']:.2f} minutes, "
                f"missing legs={record['missing_duration_legs']}"
            )

    os.makedirs(REPORT_DIR, exist_ok=True)
    pd.DataFrame(records).to_csv(REPORT_OUTPUT_PATH, index=False, encoding="utf-8-sig")

    print(f"\nRoute duration summary saved to: {REPORT_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
