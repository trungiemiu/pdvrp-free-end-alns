"""Diagnose conflict and information content among the three PDVRP objectives."""

import argparse
import glob
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import spearmanr


CRITERIA = ["total_cost_vnd", "max_route_duration_minutes", "workload_imbalance"]
DISPLAY = ["Cost", "Makespan", "Imbalance"]
ALGORITHMS = ["moalns", "nsga2", "moead", "epsilon"]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiments-root", default="outputs/experiments")
    parser.add_argument("--output-dir", default="outputs/paper/objective_conflict")
    return parser.parse_args()


def dominates(left, right):
    return bool(np.all(left <= right + 1e-12) and np.any(left < right - 1e-12))


def nondominated_mask(values):
    mask = np.ones(len(values), dtype=bool)
    for index in range(len(values)):
        if any(dominates(values[other], values[index]) for other in range(len(values)) if other != index):
            mask[index] = False
    return mask


def collect_instance(instance_dir, algorithms):
    frames = []
    for seed_dir in sorted(glob.glob(os.path.join(instance_dir, "seed_*"))):
        seed = int(os.path.basename(seed_dir).replace("seed_", ""))
        for algorithm in algorithms:
            path = os.path.join(seed_dir, algorithm + "_pareto_archive.csv")
            if not os.path.exists(path):
                continue
            frame = pd.read_csv(path).dropna(subset=CRITERIA)
            tagged = frame[CRITERIA].copy()
            tagged["algorithm"] = algorithm
            tagged["seed"] = seed
            frames.append(tagged)
    if not frames:
        return pd.DataFrame()
    pooled = pd.concat(frames, ignore_index=True)
    # Objective vectors, rather than provenance duplicates, are the analysis unit.
    return pooled.drop_duplicates(subset=CRITERIA).reset_index(drop=True)


def analyze_front(pool, instance_id, scope):
    values = pool[CRITERIA].to_numpy(float)
    front = pool.loc[nondominated_mask(values)].copy().reset_index(drop=True)
    mask_2d = nondominated_mask(front[CRITERIA[:2]].to_numpy(float))
    front["nondominated_after_dropping_imbalance"] = mask_2d
    front["requires_imbalance_objective"] = ~mask_2d
    front.insert(0, "scope", scope)
    front.insert(0, "instance_id", instance_id)

    correlations = []
    for left_index in range(3):
        for right_index in range(left_index + 1, 3):
            rho, p_value = spearmanr(
                front[CRITERIA[left_index]].to_numpy(float),
                front[CRITERIA[right_index]].to_numpy(float),
            )
            correlations.append({
                "instance_id": instance_id,
                "scope": scope,
                "objective_a": CRITERIA[left_index],
                "objective_b": CRITERIA[right_index],
                "spearman_rho": rho,
                "p_value_descriptive_only": p_value,
                "front_points": len(front),
            })
    summary = {
        "instance_id": instance_id,
        "scope": scope,
        "pooled_unique_vectors": len(pool),
        "nondominated_3d": len(front),
        "nondominated_cost_makespan": int(mask_2d.sum()),
        "projection_survival_rate": float(mask_2d.mean()),
        "points_requiring_imbalance": int((~mask_2d).sum()),
        "imbalance_information_rate": float((~mask_2d).mean()),
        "unique_imbalance_values": int(front[CRITERIA[2]].nunique()),
        "imbalance_min": float(front[CRITERIA[2]].min()),
        "imbalance_max": float(front[CRITERIA[2]].max()),
    }
    for row in correlations:
        key = (row["objective_a"], row["objective_b"])
        if key == (CRITERIA[0], CRITERIA[1]):
            summary["rho_cost_makespan"] = row["spearman_rho"]
        elif key == (CRITERIA[0], CRITERIA[2]):
            summary["rho_cost_imbalance"] = row["spearman_rho"]
        else:
            summary["rho_makespan_imbalance"] = row["spearman_rho"]
    return summary, correlations, front


def save_plots(summary, fronts, output_dir):
    union = summary[summary["scope"] == "all_algorithms"].copy()
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(
        union["instance_id"], 100 * union["projection_survival_rate"],
        color="#0072B2", label="Still non-dominated in cost--makespan",
    )
    ax.bar(
        union["instance_id"], 100 * union["imbalance_information_rate"],
        bottom=100 * union["projection_survival_rate"], color="#D55E00",
        label="Dominated when imbalance is removed",
    )
    ax.set_ylabel("Share of empirical 3D Pareto front (%)")
    ax.set_ylim(0, 100)
    ax.tick_params(axis="x", rotation=15)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.17), ncol=2)
    fig.tight_layout()
    for extension in ("png", "pdf"):
        fig.savefig(os.path.join(output_dir, "fig_projection_survival." + extension), dpi=300, bbox_inches="tight")
    plt.close(fig)

    union_fronts = fronts[fronts["scope"] == "all_algorithms"]
    instances = union["instance_id"].tolist()
    fig, axes = plt.subplots(1, len(instances), figsize=(4.2 * len(instances), 3.8), squeeze=False)
    for axis, instance_id in zip(axes[0], instances):
        frame = union_fronts[union_fronts["instance_id"] == instance_id]
        colors = np.where(frame["requires_imbalance_objective"], "#D55E00", "#0072B2")
        axis.scatter(frame[CRITERIA[0]], frame[CRITERIA[1]], c=colors, s=25, alpha=0.75)
        axis.set_title(instance_id)
        axis.set_xlabel("Cost")
        axis.set_ylabel("Makespan")
        axis.grid(alpha=0.2)
    fig.tight_layout()
    for extension in ("png", "pdf"):
        fig.savefig(os.path.join(output_dir, "fig_cost_makespan_projection." + extension), dpi=300, bbox_inches="tight")
    plt.close(fig)


def write_claim(summary, output_dir):
    union = summary[summary["scope"] == "all_algorithms"]
    low = 100 * union["imbalance_information_rate"].min()
    high = 100 * union["imbalance_information_rate"].max()
    decision = "retain the three-objective formulation" if low >= 20 else "reassess the third objective"
    text = f"""# Objective-scope decision

Decision: **{decision}**.

Across the empirical union fronts, removing workload imbalance causes
{low:.1f}%--{high:.1f}% of the three-objective non-dominated vectors to become
dominated in the cost--makespan projection. Therefore, imbalance materially
changes the trade-off set on the present instances.

Recommended claim skeleton:

> Across the four empirical union fronts, removing workload imbalance causes
> {low:.1f}%--{high:.1f}% of the three-objective non-dominated solutions to
> become dominated in the cost--makespan projection, demonstrating that the
> equity objective materially changes the attainable trade-off set.

Spearman coefficients are descriptive because points sampled from an empirical
Pareto front are neither independent nor a random population sample. The
projection-survival result is the primary scope diagnostic.
"""
    with open(os.path.join(output_dir, "claim_decision.md"), "w", encoding="utf-8") as file:
        file.write(text)


def main():
    args = parse_args()
    root = os.path.abspath(args.experiments_root)
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)
    summary_rows, correlation_rows, front_rows = [], [], []
    for instance_dir in sorted(path for path in glob.glob(os.path.join(root, "*")) if os.path.isdir(path)):
        instance_id = os.path.basename(instance_dir)
        for scope, algorithms in (("moalns_only", ["moalns"]), ("all_algorithms", ALGORITHMS)):
            pool = collect_instance(instance_dir, algorithms)
            if pool.empty:
                continue
            summary, correlations, front = analyze_front(pool, instance_id, scope)
            summary_rows.append(summary)
            correlation_rows.extend(correlations)
            front_rows.append(front)
    summary = pd.DataFrame(summary_rows)
    correlations = pd.DataFrame(correlation_rows)
    fronts = pd.concat(front_rows, ignore_index=True)
    summary.to_csv(os.path.join(output_dir, "objective_conflict_summary.csv"), index=False, encoding="utf-8-sig")
    correlations.to_csv(os.path.join(output_dir, "spearman_correlations.csv"), index=False, encoding="utf-8-sig")
    fronts.to_csv(os.path.join(output_dir, "empirical_front_projection_labels.csv"), index=False, encoding="utf-8-sig")
    union_table = summary[summary["scope"] == "all_algorithms"].set_index("instance_id")[[
        "nondominated_3d", "nondominated_cost_makespan", "projection_survival_rate",
        "points_requiring_imbalance", "imbalance_information_rate",
        "rho_cost_makespan", "rho_cost_imbalance", "rho_makespan_imbalance",
    ]]
    with open(os.path.join(output_dir, "table_objective_conflict.tex"), "w", encoding="utf-8") as file:
        file.write(union_table.to_latex(float_format=lambda value: f"{value:.3f}",
                                        caption="Objective-conflict and projection-survival diagnostics.",
                                        label="tab:objective-conflict"))
    save_plots(summary, fronts, output_dir)
    write_claim(summary, output_dir)
    print(summary.to_string(index=False))
    print("Objective conflict analysis: " + output_dir)


if __name__ == "__main__":
    main()
