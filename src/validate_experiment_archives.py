"""Run the independent checker over every benchmark archive."""

import argparse
import glob
import os

import pandas as pd

from independent_route_checker import check_solution, deserialize_routes, load_instance


ALGORITHMS = ("moalns", "nsga2", "moead", "epsilon")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="data/instances_manifest.csv")
    parser.add_argument("--experiments-root", default="outputs/experiments")
    parser.add_argument("--output-dir", default="outputs/validation/independent_archive_check")
    parser.add_argument("--fail-on-error", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    manifest = pd.read_csv(args.manifest)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(args.output_dir, exist_ok=True)
    all_rows = []
    for _, instance_row in manifest.iterrows():
        instance_id = str(instance_row["instance_id"])
        data_dir = str(instance_row["data_dir"])
        if not os.path.isabs(data_dir):
            data_dir = os.path.join(project_root, data_dir)
        instance = load_instance(data_dir)
        for seed_dir in sorted(glob.glob(os.path.join(args.experiments_root, instance_id, "seed_*"))):
            seed = int(os.path.basename(seed_dir).replace("seed_", ""))
            for algorithm in ALGORITHMS:
                path = os.path.join(seed_dir, algorithm + "_pareto_archive.csv")
                if not os.path.exists(path):
                    continue
                archive = pd.read_csv(path)
                for index, row in archive.iterrows():
                    result = check_solution(instance, deserialize_routes(row["routes_json"]), row.to_dict())
                    all_rows.append({
                        "instance_id": instance_id,
                        "seed": seed,
                        "algorithm": algorithm,
                        "solution_id": row.get("solution_id", index + 1),
                        **result,
                    })
    report = pd.DataFrame(all_rows)
    report.to_csv(
        os.path.join(args.output_dir, "independent_solution_checks.csv"),
        index=False, encoding="utf-8-sig",
    )
    summary = report.groupby(["instance_id", "algorithm"]).agg(
        solutions=("solution_id", "size"),
        feasible=("feasible", "sum"),
        objective_matches=("objectives_match", "sum"),
        all_checks_pass=("all_checks_pass", "sum"),
    ).reset_index()
    summary.to_csv(
        os.path.join(args.output_dir, "independent_check_summary.csv"),
        index=False, encoding="utf-8-sig",
    )
    failures = int((~report["all_checks_pass"]).sum())
    print(summary.to_string(index=False))
    print(f"Checked {len(report)} solutions; failures={failures}")
    if args.fail_on_error and failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
