"""Sensitivity of classical MODM selections to the three criterion weights."""

import argparse
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from modm_decision import CLASSICAL_METHODS, CRITERIA, rank_classical


METHODS = CLASSICAL_METHODS + ["borda"]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--grid-step", type=float, default=0.1)
    parser.add_argument("--vikor-v", type=float, default=0.5)
    parser.add_argument("--methods", default="topsis,promethee_ii")
    return parser.parse_args()


def weight_grid(step):
    levels = round(1.0 / step)
    if levels < 2 or not math.isclose(levels * step, 1.0, abs_tol=1e-9):
        raise ValueError("--grid-step must divide 1.0 exactly, e.g. 0.05, 0.1, 0.2, 0.25.")
    for cost_units in range(levels + 1):
        for duration_units in range(levels - cost_units + 1):
            imbalance_units = levels - cost_units - duration_units
            yield np.array([cost_units, duration_units, imbalance_units], float) / levels


def ranks_from_scores(scores):
    ranks = {
        method: pd.Series(score).rank(ascending=False, method="min").astype(int).to_numpy()
        for method, score in scores.items()
    }
    rank_matrix = np.column_stack([ranks[method] for method in CLASSICAL_METHODS])
    ranks["borda"] = pd.Series(rank_matrix.sum(axis=1)).rank(method="min").astype(int).to_numpy()
    return ranks


def main():
    args = parse_args()
    archive = pd.read_csv(args.archive).dropna(subset=CRITERIA).reset_index(drop=True)
    if len(archive) < 2:
        raise ValueError("At least two Pareto alternatives are required.")
    values = archive[CRITERIA].to_numpy(float)
    selected_methods = [method.strip() for method in args.methods.split(",") if method.strip()]
    unknown = sorted(set(selected_methods) - set(METHODS))
    if not selected_methods or unknown:
        raise ValueError("Invalid decision methods: " + ",".join(unknown or ["none"]))
    rows = []
    for grid_id, weights in enumerate(weight_grid(args.grid_step), start=1):
        scores, _ = rank_classical(values, weights, args.vikor_v)
        ranks = ranks_from_scores(scores)
        for method in selected_methods:
            selected_index = int(np.flatnonzero(ranks[method] == ranks[method].min())[0])
            selected = archive.iloc[selected_index]
            rows.append({
                "grid_id": grid_id,
                "decision_method": method,
                "cost_weight": weights[0],
                "duration_weight": weights[1],
                "imbalance_weight": weights[2],
                "solution_id": selected["solution_id"],
                **{criterion: selected[criterion] for criterion in CRITERIA},
            })
    os.makedirs(args.output_dir, exist_ok=True)
    selections = pd.DataFrame(rows)
    selections.to_csv(
        os.path.join(args.output_dir, "weight_grid_selections.csv"),
        index=False, encoding="utf-8-sig",
    )
    frequency = selections.groupby(["decision_method", "solution_id"]).size().rename("count").reset_index()
    frequency["share"] = frequency["count"] / frequency.groupby("decision_method")["count"].transform("sum")
    frequency.to_csv(
        os.path.join(args.output_dir, "selection_frequency.csv"), index=False, encoding="utf-8-sig"
    )
    stability = frequency.groupby("decision_method").agg(
        unique_selected_solutions=("solution_id", "nunique"),
        modal_selection_share=("share", "max"),
    ).reindex(selected_methods).reset_index()
    stability.to_csv(
        os.path.join(args.output_dir, "method_stability.csv"), index=False, encoding="utf-8-sig"
    )
    objective_summary = selections.groupby("decision_method")[CRITERIA].agg(["mean", "min", "max"])
    objective_summary.columns = [
        f"{criterion}_{statistic}" for criterion, statistic in objective_summary.columns
    ]
    objective_summary = objective_summary.reset_index()
    objective_summary.to_csv(
        os.path.join(args.output_dir, "selected_objective_ranges.csv"),
        index=False, encoding="utf-8-sig",
    )

    choice_pivot = selections.pivot(
        index="grid_id", columns="decision_method", values="solution_id"
    )
    agreement_rows = []
    for left_index, left in enumerate(selected_methods):
        for right in selected_methods[left_index + 1:]:
            comparable = choice_pivot[[left, right]].dropna()
            same = int((comparable[left] == comparable[right]).sum())
            agreement_rows.append({
                "method_a": left,
                "method_b": right,
                "weight_vectors": len(comparable),
                "same_selection": same,
                "same_selection_share": same / max(1, len(comparable)),
            })
    pd.DataFrame(agreement_rows).to_csv(
        os.path.join(args.output_dir, "method_agreement.csv"),
        index=False, encoding="utf-8-sig",
    )

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    axes[0].bar(stability["decision_method"], stability["unique_selected_solutions"], color="#0072B2")
    axes[0].set_ylabel("Unique selected solutions")
    axes[0].tick_params(axis="x", rotation=35)
    axes[0].grid(axis="y", alpha=0.25)
    axes[1].bar(stability["decision_method"], stability["modal_selection_share"], color="#009E73")
    axes[1].set_ylabel("Modal selection share")
    axes[1].set_ylim(0, 1)
    axes[1].tick_params(axis="x", rotation=35)
    axes[1].grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(os.path.join(args.output_dir, "modm_weight_stability.png"), dpi=300, bbox_inches="tight")
    fig.savefig(os.path.join(args.output_dir, "modm_weight_stability.pdf"), bbox_inches="tight")
    plt.close(fig)
    print(stability.to_string(index=False))
    print("Weight combinations: " + str(selections["grid_id"].nunique()))
    print("Analysis: " + os.path.abspath(args.output_dir))


if __name__ == "__main__":
    main()
