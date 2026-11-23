import argparse
import os
import pandas as pd

from evaluator import ROUTE_DIR, REPORT_DIR, evaluate_method


def parse_args():
    parser = argparse.ArgumentParser(
        description="Evaluate every method that has an outputs/routes/*_routes.csv file."
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Keep evaluating remaining methods if one method fails.",
    )
    return parser.parse_args()


def discover_methods():
    if not os.path.exists(ROUTE_DIR):
        return []

    methods = []

    for file_name in os.listdir(ROUTE_DIR):
        if file_name.endswith("_routes.csv"):
            methods.append(file_name[:-len("_routes.csv")])

    return sorted(set(methods))


def main():
    args = parse_args()
    os.makedirs(REPORT_DIR, exist_ok=True)

    records = []

    for method_name in discover_methods():
        print("=" * 100)
        print(f"Evaluating: {method_name}")
        print("=" * 100)

        try:
            evaluate_method(method_name)
            status = "ok"
            error = ""
        except Exception as exc:
            status = "failed"
            error = str(exc)
            print(f"Evaluation failed for {method_name}: {error}")

            if not args.continue_on_error:
                raise

        records.append({
            "method": method_name,
            "status": status,
            "error": error,
        })

    status_path = os.path.join(REPORT_DIR, "evaluate_all_status.csv")
    pd.DataFrame(records).to_csv(status_path, index=False, encoding="utf-8-sig")
    print(f"\nEvaluation status saved to: {status_path}")


if __name__ == "__main__":
    main()
