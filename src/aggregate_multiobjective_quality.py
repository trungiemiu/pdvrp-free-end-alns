"""Recompute all-seed indicators with fixed per-instance normalization bounds."""

import argparse
import glob
import os

import numpy as np
import pandas as pd

from multiobjective_quality import (
    ALGORITHMS, CRITERIA, hypervolume_3d, nondominated_mask, spacing,
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--experiments-root", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    manifest = pd.read_csv(args.manifest)
    rows = []
    for _, instance in manifest.iterrows():
        instance_id = str(instance["instance_id"])
        records = []
        pattern = os.path.join(args.experiments_root, instance_id, "seed_*")
        for seed_dir in sorted(glob.glob(pattern)):
            seed = int(os.path.basename(seed_dir).replace("seed_", ""))
            for algorithm in ALGORITHMS:
                path = os.path.join(seed_dir, algorithm + "_pareto_archive.csv")
                if os.path.exists(path):
                    frame = pd.read_csv(path).dropna(subset=CRITERIA)
                    records.append((seed, algorithm, frame))
        if not records:
            continue
        all_values = np.vstack([frame[CRITERIA].to_numpy(float) for _, _, frame in records])
        ideal, nadir = all_values.min(axis=0), all_values.max(axis=0)
        spread = nadir - ideal
        spread[spread < 1e-12] = 1.0
        reference = np.array([1.1, 1.1, 1.1])
        reference_volume = float(np.prod(reference))
        for seed in sorted({record[0] for record in records}):
            seed_records = [(algorithm, frame) for record_seed, algorithm, frame in records if record_seed == seed]
            seed_union = np.vstack([frame[CRITERIA].to_numpy(float) for _, frame in seed_records])
            seed_union_mask = nondominated_mask(seed_union)
            offset = 0
            for algorithm, frame in seed_records:
                values = frame[CRITERIA].to_numpy(float)
                normalized = (values - ideal) / spread
                own_mask = nondominated_mask(normalized)
                contribution = int(seed_union_mask[offset:offset + len(frame)].sum())
                offset += len(frame)
                ranges = normalized.max(axis=0) - normalized.min(axis=0)
                rows.append({
                    "instance_id": instance_id, "seed": seed, "algorithm": algorithm,
                    "archive_size": len(frame), "internally_nondominated": int(own_mask.sum()),
                    "union_front_contribution": contribution,
                    "hypervolume_normalized": hypervolume_3d(normalized[own_mask], reference) / reference_volume,
                    "spacing_normalized": spacing(normalized[own_mask]),
                    "extent_cost": ranges[0], "extent_duration": ranges[1],
                    "extent_imbalance": ranges[2],
                    "reference_ideal_cost": ideal[0], "reference_ideal_duration": ideal[1],
                    "reference_ideal_imbalance": ideal[2], "reference_nadir_cost": nadir[0],
                    "reference_nadir_duration": nadir[1], "reference_nadir_imbalance": nadir[2],
                })
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    result = pd.DataFrame(rows)
    result.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"Fixed-reference benchmark summary: {args.output} ({len(result)} rows)")


if __name__ == "__main__":
    main()
