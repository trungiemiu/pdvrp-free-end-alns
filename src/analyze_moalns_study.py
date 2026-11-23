"""Aggregate MOALNS ablation and sensitivity experiments with fixed bounds."""

import argparse
import glob
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

from multiobjective_quality import CRITERIA, hypervolume_3d, nondominated_mask, spacing


REFERENCE = np.array([1.1, 1.1, 1.1])


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--study-root", required=True)
    parser.add_argument("--baseline-config", default="baseline")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--study-label", default="MOALNS study")
    parser.add_argument(
        "--include-configs",
        default="",
        help="Optional comma-separated configuration IDs to include.",
    )
    return parser.parse_args()


def holm_adjust(frame):
    if frame.empty:
        return frame
    order = np.argsort(frame["p_raw"].to_numpy(float))
    adjusted = np.empty(len(frame))
    running = 0.0
    for rank, index in enumerate(order):
        value = min(1.0, frame.iloc[index]["p_raw"] * (len(frame) - rank))
        running = max(running, value)
        adjusted[index] = running
    result = frame.copy()
    result["p_holm"] = adjusted
    return result


def collect(study_root, include_configs=None):
    records = []
    pattern = os.path.join(study_root, "*", "*", "seed_*", "moalns_pareto_archive.csv")
    for archive_path in sorted(glob.glob(pattern)):
        seed_dir = os.path.dirname(archive_path)
        instance_dir = os.path.dirname(seed_dir)
        config_dir = os.path.dirname(instance_dir)
        config_id = os.path.basename(config_dir)
        if include_configs and config_id not in include_configs:
            continue
        instance_id = os.path.basename(instance_dir)
        seed = int(os.path.basename(seed_dir).replace("seed_", ""))
        report_path = os.path.join(seed_dir, "moalns_solver_report.csv")
        if not os.path.exists(report_path):
            continue
        archive = pd.read_csv(archive_path).dropna(subset=CRITERIA)
        report = pd.read_csv(report_path).iloc[0].to_dict()
        records.append({
            "config_id": config_id,
            "instance_id": instance_id,
            "seed": seed,
            "archive": archive,
            "report": report,
        })
    if not records:
        raise FileNotFoundError("No completed study archives found under " + study_root)
    return records


def compute_metrics(records):
    rows = []
    for instance_id in sorted({item["instance_id"] for item in records}):
        instance_records = [item for item in records if item["instance_id"] == instance_id]
        all_values = np.vstack([item["archive"][CRITERIA].to_numpy(float) for item in instance_records])
        ideal, nadir = all_values.min(axis=0), all_values.max(axis=0)
        spread = nadir - ideal
        spread[spread < 1e-12] = 1.0
        for seed in sorted({item["seed"] for item in instance_records}):
            block = [item for item in instance_records if item["seed"] == seed]
            combined = np.vstack([item["archive"][CRITERIA].to_numpy(float) for item in block])
            union_mask = nondominated_mask(combined)
            offset = 0
            for item in block:
                frame = item["archive"]
                values = frame[CRITERIA].to_numpy(float)
                normalized = (values - ideal) / spread
                own_mask = nondominated_mask(normalized)
                contribution = int(union_mask[offset:offset + len(frame)].sum())
                offset += len(frame)
                report = item["report"]
                rows.append({
                    "config_id": item["config_id"],
                    "instance_id": instance_id,
                    "seed": seed,
                    "hypervolume_normalized": hypervolume_3d(
                        normalized[own_mask], REFERENCE
                    ) / float(np.prod(REFERENCE)),
                    "spacing_normalized": spacing(normalized[own_mask]),
                    "archive_size": len(frame),
                    "union_front_contribution": contribution,
                    "runtime_seconds": float(report.get("runtime_seconds", np.nan)),
                    "completed_iterations": float(report.get("completed_iterations", np.nan)),
                    "accepted_solutions": float(report.get("accepted_solutions", np.nan)),
                    "archive_additions": float(report.get("archive_additions", np.nan)),
                })
    result = pd.DataFrame(rows)
    result["hv_rank"] = result.groupby(["instance_id", "seed"])[
        "hypervolume_normalized"
    ].rank(ascending=False, method="average")
    return result


def paired_statistics(metrics, baseline):
    base = metrics[metrics["config_id"] == baseline][
        ["instance_id", "seed", "hypervolume_normalized"]
    ].rename(columns={"hypervolume_normalized": "baseline_hv"})
    rows = []
    for config in sorted(set(metrics["config_id"]) - {baseline}):
        candidate = metrics[metrics["config_id"] == config][
            ["instance_id", "seed", "hypervolume_normalized"]
        ].rename(columns={"hypervolume_normalized": "candidate_hv"})
        paired = base.merge(candidate, on=["instance_id", "seed"], how="inner")
        if paired.empty:
            continue
        delta = paired["candidate_hv"] - paired["baseline_hv"]
        if np.allclose(delta, 0.0):
            statistic, p_value = 0.0, 1.0
        else:
            statistic, p_value = wilcoxon(delta, alternative="two-sided")
        rows.append({
            "config_id": config,
            "paired_blocks": len(paired),
            "mean_delta_hv_vs_baseline": delta.mean(),
            "wins": int((delta > 1e-12).sum()),
            "ties": int((np.abs(delta) <= 1e-12).sum()),
            "losses": int((delta < -1e-12).sum()),
            "wilcoxon_w": statistic,
            "p_raw": p_value,
        })
    return holm_adjust(pd.DataFrame(rows))


def save_plots(summary, output_dir, label):
    order = summary.sort_values("mean_hv", ascending=True)
    fig, ax = plt.subplots(figsize=(max(7, len(order) * 0.38), max(4, len(order) * 0.28)))
    ax.barh(order["config_id"], order["mean_hv"], xerr=order["std_hv"], color="#0072B2")
    ax.set_xlabel("Normalized hypervolume (mean ± SD)")
    ax.set_title(label)
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, "mean_hypervolume.png"), dpi=300, bbox_inches="tight")
    fig.savefig(os.path.join(output_dir, "mean_hypervolume.pdf"), bbox_inches="tight")
    plt.close(fig)


def save_paired_delta_plot(metrics, baseline, output_dir):
    base = metrics[metrics["config_id"] == baseline][
        ["instance_id", "seed", "hypervolume_normalized"]
    ].rename(columns={"hypervolume_normalized": "baseline_hv"})
    labels, values = [], []
    for config in sorted(set(metrics["config_id"]) - {baseline}):
        candidate = metrics[metrics["config_id"] == config][
            ["instance_id", "seed", "hypervolume_normalized"]
        ].rename(columns={"hypervolume_normalized": "candidate_hv"})
        paired = base.merge(candidate, on=["instance_id", "seed"], how="inner")
        labels.append(config.replace("_", " "))
        values.append((paired["candidate_hv"] - paired["baseline_hv"]).to_numpy())
    if not values:
        return
    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    ax.boxplot(
        values,
        tick_labels=labels,
        showmeans=True,
        meanprops={"marker": "D", "markerfacecolor": "#D55E00", "markeredgecolor": "#D55E00"},
        medianprops={"color": "#0072B2", "linewidth": 1.8},
    )
    ax.axhline(0.0, color="black", linewidth=1.0, linestyle="--")
    ax.set_ylabel(r"Paired $\Delta$HV (ablation $-$ full MOALNS)")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(
        os.path.join(output_dir, "paired_hv_delta_vs_baseline.png"),
        dpi=300, bbox_inches="tight",
    )
    fig.savefig(
        os.path.join(output_dir, "paired_hv_delta_vs_baseline.pdf"),
        bbox_inches="tight",
    )
    plt.close(fig)


def main():
    args = parse_args()
    study_root = os.path.abspath(args.study_root)
    output_dir = os.path.abspath(args.output_dir or os.path.join(study_root, "analysis"))
    os.makedirs(output_dir, exist_ok=True)
    include_configs = {
        value.strip() for value in args.include_configs.split(",") if value.strip()
    }
    records = collect(study_root, include_configs or None)
    metrics = compute_metrics(records)
    metrics.to_csv(os.path.join(output_dir, "run_metrics.csv"), index=False, encoding="utf-8-sig")

    summary = metrics.groupby("config_id").agg(
        runs=("hypervolume_normalized", "size"),
        mean_hv=("hypervolume_normalized", "mean"),
        std_hv=("hypervolume_normalized", "std"),
        mean_hv_rank=("hv_rank", "mean"),
        mean_spacing=("spacing_normalized", "mean"),
        mean_archive_size=("archive_size", "mean"),
        union_front_contribution=("union_front_contribution", "sum"),
        mean_runtime_seconds=("runtime_seconds", "mean"),
        mean_iterations=("completed_iterations", "mean"),
    ).reset_index()
    summary.to_csv(os.path.join(output_dir, "config_summary.csv"), index=False, encoding="utf-8-sig")

    per_instance = metrics.groupby(["config_id", "instance_id"])["hypervolume_normalized"].agg(
        ["mean", "std", "count"]
    ).reset_index()
    per_instance.to_csv(
        os.path.join(output_dir, "hypervolume_by_instance.csv"), index=False, encoding="utf-8-sig"
    )
    statistics = paired_statistics(metrics, args.baseline_config)
    statistics.to_csv(
        os.path.join(output_dir, "paired_statistics_vs_baseline.csv"),
        index=False, encoding="utf-8-sig",
    )
    save_plots(summary, output_dir, args.study_label)
    save_paired_delta_plot(metrics, args.baseline_config, output_dir)
    print(summary.sort_values("mean_hv", ascending=False).to_string(index=False))
    print("Analysis: " + output_dir)


if __name__ == "__main__":
    main()
