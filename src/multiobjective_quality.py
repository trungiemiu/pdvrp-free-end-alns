"""Quality indicators for Pareto archives produced on one instance/seed."""

import argparse
import os

import numpy as np
import pandas as pd


CRITERIA = ["total_cost_vnd", "max_route_duration_minutes", "workload_imbalance"]
ALGORITHMS = ["moalns", "nsga2", "moead", "epsilon"]


def parse_args():
    parser = argparse.ArgumentParser(description="Compare multi-objective archives.")
    parser.add_argument("--experiment-dir", required=True)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--seed", type=int, required=True)
    return parser.parse_args()


def dominates(left, right):
    return bool(np.all(left <= right + 1e-12) and np.any(left < right - 1e-12))


def nondominated_mask(values):
    mask = np.ones(len(values), dtype=bool)
    for index in range(len(values)):
        if any(dominates(values[other], values[index]) for other in range(len(values)) if other != index):
            mask[index] = False
    return mask


def area_2d(points, reference):
    best_z = reference[1]
    area = 0.0
    for y, z in sorted(points, key=lambda point: (point[0], point[1])):
        if z < best_z:
            area += max(0.0, reference[0] - y) * (best_z - z)
            best_z = z
    return area


def hypervolume_3d(values, reference):
    values = values[np.all(values < reference, axis=1)]
    if len(values) == 0:
        return 0.0
    levels = sorted(set(values[:, 0].tolist()))
    volume = 0.0
    for position, level in enumerate(levels):
        next_level = levels[position + 1] if position + 1 < len(levels) else reference[0]
        active = values[values[:, 0] <= level + 1e-12][:, 1:]
        volume += max(0.0, next_level - level) * area_2d(active, reference[1:])
    return float(volume)


def spacing(values):
    if len(values) < 2:
        return 0.0
    distances = np.linalg.norm(values[:, None, :] - values[None, :, :], axis=2)
    np.fill_diagonal(distances, np.inf)
    nearest = distances.min(axis=1)
    return float(np.std(nearest, ddof=1)) if len(nearest) > 1 else 0.0


def main():
    args = parse_args()
    archives = {}
    combined_rows = []
    for algorithm in ALGORITHMS:
        path = os.path.join(args.experiment_dir, algorithm + "_pareto_archive.csv")
        if not os.path.exists(path):
            continue
        frame = pd.read_csv(path).dropna(subset=CRITERIA)
        archives[algorithm] = frame
        tagged = frame[["solution_id", *CRITERIA]].copy()
        tagged["algorithm"] = algorithm
        combined_rows.append(tagged)
    if len(archives) < 2:
        raise ValueError("At least two algorithm archives are required.")

    combined = pd.concat(combined_rows, ignore_index=True)
    raw = combined[CRITERIA].to_numpy(float)
    ideal, nadir = raw.min(axis=0), raw.max(axis=0)
    spread = nadir - ideal
    spread[spread < 1e-12] = 1.0
    combined_norm = (raw - ideal) / spread
    union_mask = nondominated_mask(combined_norm)
    combined["nondominated_in_union"] = union_mask
    reference = np.array([1.1, 1.1, 1.1])

    metrics = []
    for algorithm, frame in archives.items():
        values = frame[CRITERIA].to_numpy(float)
        normalized = (values - ideal) / spread
        own_mask = nondominated_mask(normalized)
        algorithm_union_rows = combined["algorithm"].eq(algorithm).to_numpy()
        contribution = int(np.sum(union_mask & algorithm_union_rows))
        ranges = normalized.max(axis=0) - normalized.min(axis=0) if len(normalized) else np.zeros(3)
        metrics.append({
            "instance_id": args.instance_id, "seed": args.seed, "algorithm": algorithm,
            "archive_size": len(frame), "internally_nondominated": int(own_mask.sum()),
            "union_front_contribution": contribution,
            "hypervolume_normalized": hypervolume_3d(normalized[own_mask], reference) / float(np.prod(reference)),
            "spacing_normalized": spacing(normalized[own_mask]),
            "extent_cost": ranges[0], "extent_duration": ranges[1],
            "extent_imbalance": ranges[2],
        })

    coverage = pd.DataFrame(index=archives, columns=archives, dtype=float)
    for left_name, left_frame in archives.items():
        left = left_frame[CRITERIA].to_numpy(float)
        for right_name, right_frame in archives.items():
            right = right_frame[CRITERIA].to_numpy(float)
            coverage.loc[left_name, right_name] = np.mean([
                any(dominates(candidate, target) for candidate in left) for target in right
            ]) if len(right) else np.nan

    os.makedirs(args.experiment_dir, exist_ok=True)
    pd.DataFrame(metrics).to_csv(
        os.path.join(args.experiment_dir, "quality_metrics.csv"), index=False, encoding="utf-8-sig"
    )
    coverage.to_csv(os.path.join(args.experiment_dir, "coverage_matrix.csv"), encoding="utf-8-sig")
    combined[union_mask].sort_values(CRITERIA).to_csv(
        os.path.join(args.experiment_dir, "reference_union_front.csv"), index=False, encoding="utf-8-sig"
    )
    print(pd.DataFrame(metrics).to_string(index=False))


if __name__ == "__main__":
    main()
