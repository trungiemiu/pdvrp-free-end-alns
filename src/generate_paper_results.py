"""Generate reproducible publication tables and figures from benchmark outputs."""

import glob
import argparse
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import friedmanchisquare, wilcoxon

from multiobjective_quality import ALGORITHMS, CRITERIA, nondominated_mask


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPERIMENT_DIR = os.path.join(BASE_DIR, "outputs", "experiments")
SUMMARY_PATH = os.path.join(EXPERIMENT_DIR, "benchmark_summary.csv")
PAPER_DIR = os.path.join(BASE_DIR, "outputs", "paper")
TABLE_DIR = os.path.join(PAPER_DIR, "tables")
FIGURE_DIR = os.path.join(PAPER_DIR, "figures")

ORDER = ["moalns", "moead", "nsga2", "epsilon"]
DISPLAY = {
    "moalns": "MOALNS",
    "moead": "MOEA/D",
    "nsga2": "NSGA-II",
    "epsilon": "Epsilon-constraint",
}
INSTANCE_DISPLAY = {
    "current": "Current",
    "lc101_notw_subset12": "LC101-12",
    "lr101_notw_subset12": "LR101-12",
    "lrc101_notw_subset12": "LRC101-12",
}
COLORS = {
    "moalns": "#0072B2",
    "moead": "#009E73",
    "nsga2": "#E69F00",
    "epsilon": "#CC79A7",
}
MARKERS = {"moalns": "o", "moead": "s", "nsga2": "^", "epsilon": "D"}


def instance_display(name):
    if name in INSTANCE_DISPLAY:
        return INSTANCE_DISPLAY[name]
    match = re.fullmatch(r"(lc|lr|lrc)(\d+)_notw_n(\d+)", str(name), flags=re.IGNORECASE)
    if match:
        return f"{match.group(1).upper()}{match.group(2)}-{match.group(3)}"
    return str(name)


def experiment_scope(summary):
    block_count = summary.groupby(["instance_id", "seed"]).ngroups
    instance_count = summary["instance_id"].nunique()
    seed_counts = summary.groupby("instance_id")["seed"].nunique()
    seed_text = str(int(seed_counts.iloc[0])) if seed_counts.nunique() == 1 else "varying"
    reports = glob.glob(os.path.join(EXPERIMENT_DIR, "*", "seed_*", "*_solver_report.csv"))
    budgets = []
    for path in reports:
        report = pd.read_csv(path, nrows=1)
        if "time_limit_seconds" in report.columns:
            budgets.append(float(report.iloc[0]["time_limit_seconds"]))
    budget = float(np.median(budgets)) if budgets else float("nan")
    return block_count, instance_count, seed_text, budget


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-dir", default=EXPERIMENT_DIR)
    parser.add_argument("--paper-dir", default=PAPER_DIR)
    return parser.parse_args()


def configure_plotting():
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.labelsize": 10,
        "axes.titlesize": 11,
        "legend.fontsize": 9,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "figure.dpi": 120,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
    })


def save_figure(figure, stem):
    figure.savefig(os.path.join(FIGURE_DIR, stem + ".png"), dpi=300, bbox_inches="tight")
    figure.savefig(os.path.join(FIGURE_DIR, stem + ".pdf"), bbox_inches="tight")
    plt.close(figure)


def holm_adjust(rows):
    order = sorted(range(len(rows)), key=lambda index: rows[index]["p_raw"])
    running = 0.0
    for rank, index in enumerate(order):
        adjusted = min(1.0, rows[index]["p_raw"] * (len(rows) - rank))
        running = max(running, adjusted)
        rows[index]["p_holm"] = running
    return rows


def validate_summary(frame):
    required = {
        "instance_id", "seed", "algorithm", "hypervolume_normalized",
        "spacing_normalized", "archive_size", "union_front_contribution",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError("Missing summary columns: " + ", ".join(sorted(missing)))
    counts = frame.groupby(["instance_id", "seed"])["algorithm"].nunique()
    if not (counts == len(ORDER)).all():
        raise ValueError("The benchmark is incomplete for one or more instance-seed blocks.")
    if set(frame["algorithm"]) != set(ORDER):
        raise ValueError("Unexpected algorithm set in benchmark summary.")


def write_table(frame, stem, caption, label, float_format="%.4f", escape=True):
    frame.to_csv(os.path.join(TABLE_DIR, stem + ".csv"), index=True, encoding="utf-8-sig")
    latex = frame.to_latex(
        index=True, escape=escape, float_format=float_format,
        caption=caption, label=label, position="tbp",
    )
    with open(os.path.join(TABLE_DIR, stem + ".tex"), "w", encoding="utf-8") as file:
        file.write(latex)


def create_tables(summary):
    block_count, instance_count, seed_text, _ = experiment_scope(summary)
    grouped = summary.groupby(["instance_id", "algorithm"])
    per_instance = grouped["hypervolume_normalized"].agg(["mean", "std"])
    hv_numeric = pd.DataFrame(index=[instance_display(name) for name in summary["instance_id"].unique()])
    hv_formatted = hv_numeric.copy()
    for algorithm in ORDER:
        numeric_values, formatted_values = [], []
        for instance in summary["instance_id"].unique():
            mean = per_instance.loc[(instance, algorithm), "mean"]
            std = per_instance.loc[(instance, algorithm), "std"]
            numeric_values.append(mean)
            formatted_values.append(f"{mean:.4f} $\\pm$ {std:.4f}")
        hv_numeric[DISPLAY[algorithm]] = numeric_values
        hv_formatted[DISPLAY[algorithm]] = formatted_values
    hv_numeric.to_csv(os.path.join(TABLE_DIR, "table_hypervolume_by_instance.csv"), encoding="utf-8-sig")
    per_instance.reset_index().rename(columns={
        "instance_id": "instance", "algorithm": "algorithm",
        "mean": "mean_hypervolume", "std": "std_hypervolume",
    }).to_csv(
        os.path.join(TABLE_DIR, "table_hypervolume_by_instance_long.csv"),
        index=False, encoding="utf-8-sig",
    )
    latex_frame = hv_formatted.copy()
    for index in latex_frame.index:
        best = hv_numeric.loc[index].max()
        for column in latex_frame.columns:
            if abs(hv_numeric.loc[index, column] - best) < 1e-12:
                latex_frame.loc[index, column] = "\\textbf{" + latex_frame.loc[index, column] + "}"
    with open(os.path.join(TABLE_DIR, "table_hypervolume_by_instance.tex"), "w", encoding="utf-8") as file:
        file.write(latex_frame.to_latex(
            escape=False, caption=f"Normalized hypervolume by instance (mean $\\pm$ standard deviation over {seed_text} seeds).",
            label="tab:hv-instance", position="tbp",
        ))

    work = summary.copy()
    work["hv_rank"] = work.groupby(["instance_id", "seed"])["hypervolume_normalized"].rank(
        ascending=False, method="average"
    )
    work["spacing_rank"] = work.groupby(["instance_id", "seed"])["spacing_normalized"].rank(
        ascending=True, method="average"
    )
    overall = work.groupby("algorithm").agg(
        mean_hv=("hypervolume_normalized", "mean"),
        std_hv=("hypervolume_normalized", "std"),
        mean_hv_rank=("hv_rank", "mean"),
        hv_wins=("hv_rank", lambda values: int((values == 1).sum())),
        mean_spacing=("spacing_normalized", "mean"),
        mean_spacing_rank=("spacing_rank", "mean"),
        mean_archive_size=("archive_size", "mean"),
        union_contribution=("union_front_contribution", "sum"),
    ).reindex(ORDER)
    overall.index = [DISPLAY[name] for name in overall.index]
    overall.to_csv(os.path.join(TABLE_DIR, "table_overall_performance.csv"), encoding="utf-8-sig")
    overall_tex = overall.rename(columns={
        "mean_hv": "Mean HV", "std_hv": "HV SD", "mean_hv_rank": "HV rank",
        "hv_wins": "Wins", "mean_spacing": "Spacing",
        "mean_spacing_rank": "Spacing rank", "mean_archive_size": "Archive size",
        "union_contribution": "Union contribution",
    }).copy()
    best_rules = {
        "Mean HV": "max", "HV rank": "min", "Wins": "max", "Spacing": "min",
        "Spacing rank": "min", "Archive size": "max", "Union contribution": "max",
    }
    for column in overall_tex.columns:
        raw_column = overall_tex[column].astype(float)
        target = raw_column.max() if best_rules.get(column) == "max" else raw_column.min() if best_rules.get(column) == "min" else None
        overall_tex[column] = [f"{value:.4f}" if column not in {"Wins", "Union contribution"} else f"{int(value)}" for value in raw_column]
        if target is not None:
            for index in overall_tex.index:
                if abs(raw_column.loc[index] - target) < 1e-12:
                    overall_tex.loc[index, column] = "\\textbf{" + overall_tex.loc[index, column] + "}"
    with open(os.path.join(TABLE_DIR, "table_overall_performance.tex"), "w", encoding="utf-8") as file:
        file.write(overall_tex.to_latex(
            escape=False, caption=f"Overall multi-objective performance across {block_count} paired instance-seed blocks.",
            label="tab:overall-performance", position="tbp",
        ))

    pivot = work.pivot(
        index=["instance_id", "seed"], columns="algorithm", values="hypervolume_normalized"
    )[ORDER]
    friedman_stat, friedman_p = friedmanchisquare(*[pivot[name] for name in ORDER])
    pairwise = []
    for left_index, left in enumerate(ORDER):
        for right in ORDER[left_index + 1:]:
            difference = pivot[left] - pivot[right]
            statistic, p_value = wilcoxon(pivot[left], pivot[right], alternative="two-sided")
            pairwise.append({
                "Comparison": f"{DISPLAY[left]} vs {DISPLAY[right]}",
                "Mean HV difference": difference.mean(),
                "Wins": int((difference > 1e-12).sum()),
                "Ties": int((difference.abs() <= 1e-12).sum()),
                "Losses": int((difference < -1e-12).sum()),
                "Wilcoxon W": statistic,
                "p_raw": p_value,
            })
    pairwise = holm_adjust(pairwise)
    statistical = pd.DataFrame(pairwise).set_index("Comparison")
    statistical.to_csv(os.path.join(TABLE_DIR, "table_pairwise_statistics.csv"), encoding="utf-8-sig")
    statistics_tex = pd.DataFrame(index=statistical.index)
    statistics_tex.index.name = None
    statistics_tex["Mean $\\Delta$HV"] = statistical["Mean HV difference"].map(lambda value: f"{value:.4f}")
    statistics_tex["W--T--L"] = statistical.apply(
        lambda row: f"{int(row['Wins'])}--{int(row['Ties'])}--{int(row['Losses'])}", axis=1
    )
    statistics_tex["Wilcoxon $W$"] = statistical["Wilcoxon W"].map(lambda value: f"{value:.1f}")
    statistics_tex["Raw $p$"] = statistical["p_raw"].map(lambda value: f"{value:.3e}")
    statistics_tex["Holm $p$"] = statistical["p_holm"].map(
        lambda value: "\\textbf{" + f"{value:.3e}" + "}" if value < 0.05 else f"{value:.3e}"
    )
    with open(os.path.join(TABLE_DIR, "table_pairwise_statistics.tex"), "w", encoding="utf-8") as file:
        file.write(statistics_tex.to_latex(
            escape=False,
            caption="Pairwise Wilcoxon signed-rank tests on normalized hypervolume with Holm correction.",
            label="tab:pairwise-statistics", position="tbp",
        ))
    pd.DataFrame([{
        "Analysis unit": f"{block_count} instance-seed blocks",
        "Friedman chi-square": friedman_stat,
        "Friedman p-value": friedman_p,
    }]).to_csv(os.path.join(TABLE_DIR, "table_friedman_summary.csv"), index=False)

    instance_means = summary.groupby(["instance_id", "algorithm"])["hypervolume_normalized"].mean().unstack()
    instance_stat, instance_p = friedmanchisquare(*[instance_means[name] for name in ORDER])
    pd.DataFrame([{
        "Analysis unit": f"{instance_count} independent instance means",
        "Friedman chi-square": instance_stat,
        "Friedman p-value": instance_p,
        "Pairwise Wilcoxon minimum attainable p": 2.0 ** (1 - instance_count),
    }]).to_csv(os.path.join(TABLE_DIR, "table_instance_level_statistics.csv"), index=False)
    instance_pairwise = []
    for left_index, left in enumerate(ORDER):
        for right in ORDER[left_index + 1:]:
            difference = instance_means[left] - instance_means[right]
            statistic, p_value = wilcoxon(difference, alternative="two-sided")
            instance_pairwise.append({
                "Comparison": f"{DISPLAY[left]} vs {DISPLAY[right]}",
                "Mean HV difference": difference.mean(),
                "Wins": int((difference > 1e-12).sum()),
                "Ties": int((difference.abs() <= 1e-12).sum()),
                "Losses": int((difference < -1e-12).sum()),
                "Wilcoxon W": statistic,
                "p_raw": p_value,
            })
    instance_pairwise = pd.DataFrame(holm_adjust(instance_pairwise)).set_index("Comparison")
    write_table(
        instance_pairwise,
        "table_instance_level_pairwise_statistics",
        "Pairwise Wilcoxon tests on independent instance-mean hypervolume with Holm correction.",
        "tab:instance-pairwise-statistics",
    )

    runtime_rows = []
    for path in glob.glob(os.path.join(EXPERIMENT_DIR, "*", "seed_*", "*_solver_report.csv")):
        algorithm = os.path.basename(path).replace("_solver_report.csv", "")
        report = pd.read_csv(path).iloc[0]
        runtime_rows.append({"algorithm": algorithm, "runtime_seconds": float(report["runtime_seconds"])})
    runtime = pd.DataFrame(runtime_rows).groupby("algorithm")["runtime_seconds"].agg(
        ["mean", "std", "min", "max"]
    ).reindex(ORDER)
    runtime.index = [DISPLAY[name] for name in runtime.index]
    write_table(
        runtime, "table_runtime",
        f"Wall-clock runtime summary over {block_count} runs per algorithm.",
        "tab:runtime",
    )

    current_extremes = []
    for algorithm in ORDER:
        frames = [
            pd.read_csv(os.path.join(EXPERIMENT_DIR, "current", f"seed_{seed}", f"{algorithm}_pareto_archive.csv"))
            for seed in sorted(summary[summary["instance_id"] == "current"]["seed"].unique())
        ]
        archive = pd.concat(frames, ignore_index=True)
        current_extremes.append({
            "Algorithm": DISPLAY[algorithm],
            "Minimum cost (VND)": archive["total_cost_vnd"].min(),
            "Minimum maximum duration (min)": archive["max_route_duration_minutes"].min(),
            "Minimum imbalance": archive["workload_imbalance"].min(),
        })
    extremes = pd.DataFrame(current_extremes).set_index("Algorithm")
    write_table(
        extremes, "table_current_extremes",
        "Best single-criterion values found for the current real-world instance.",
        "tab:current-extremes", float_format="%.3f",
    )
    return work, overall, statistical, friedman_stat, friedman_p, instance_stat, instance_p


def mean_coverage(summary):
    records = []
    for instance in summary["instance_id"].unique():
        for seed in sorted(summary[summary["instance_id"] == instance]["seed"].unique()):
            path = os.path.join(EXPERIMENT_DIR, instance, f"seed_{seed}", "coverage_matrix.csv")
            matrix = pd.read_csv(path, index_col=0).loc[ALGORITHMS, ALGORITHMS]
            records.append(matrix)
    values = np.mean([record.to_numpy(float) for record in records], axis=0)
    return pd.DataFrame(values, index=ALGORITHMS, columns=ALGORITHMS).reindex(index=ORDER, columns=ORDER)


def create_figures(summary, work, overall):
    instances = list(summary["instance_id"].unique())
    x = np.arange(len(instances))
    width = 0.19
    figure, axis = plt.subplots(figsize=(8.2, 4.6))
    for position, algorithm in enumerate(ORDER):
        subset = summary[summary["algorithm"] == algorithm]
        means = subset.groupby("instance_id")["hypervolume_normalized"].mean().reindex(instances)
        errors = subset.groupby("instance_id")["hypervolume_normalized"].std().reindex(instances)
        axis.bar(
            x + (position - 1.5) * width, means, width, yerr=errors,
            color=COLORS[algorithm], label=DISPLAY[algorithm], capsize=3,
            edgecolor="white", linewidth=0.6,
        )
    axis.set_ylabel("Normalized hypervolume")
    axis.set_xticks(x, [instance_display(name) for name in instances])
    axis.set_ylim(0, 1.02)
    axis.grid(axis="y", alpha=0.25)
    axis.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.14), frameon=False)
    save_figure(figure, "fig_hypervolume_by_instance")

    figure, axis = plt.subplots(figsize=(6.6, 4.5))
    values = [summary[summary["algorithm"] == algorithm]["hypervolume_normalized"].values for algorithm in ORDER]
    box = axis.boxplot(values, tick_labels=[DISPLAY[name] for name in ORDER], patch_artist=True,
                       widths=0.58, showmeans=True,
                       meanprops={"marker": "o", "markerfacecolor": "white", "markeredgecolor": "black", "markersize": 4})
    for patch, algorithm in zip(box["boxes"], ORDER):
        patch.set_facecolor(COLORS[algorithm]); patch.set_alpha(0.75)
    axis.set_ylabel("Normalized hypervolume")
    axis.grid(axis="y", alpha=0.25)
    save_figure(figure, "fig_hypervolume_distribution")

    figure, axis = plt.subplots(figsize=(6.4, 3.8))
    ranks = overall["mean_hv_rank"]
    algorithms = [name for name in ORDER]
    y = np.arange(len(algorithms))
    axis.barh(y, [ranks.loc[DISPLAY[name]] for name in algorithms], color=[COLORS[name] for name in algorithms])
    axis.set_yticks(y, [DISPLAY[name] for name in algorithms])
    axis.invert_yaxis()
    axis.set_xlabel("Mean hypervolume rank (lower is better)")
    axis.set_xlim(0, 4.1)
    axis.grid(axis="x", alpha=0.25)
    for index, algorithm in enumerate(algorithms):
        value = ranks.loc[DISPLAY[algorithm]]
        axis.text(value + 0.05, index, f"{value:.2f}", va="center")
    save_figure(figure, "fig_average_hypervolume_rank")

    coverage = mean_coverage(summary)
    coverage_display = coverage.copy()
    coverage_display.index = [DISPLAY[name] for name in coverage.index]
    coverage_display.columns = [DISPLAY[name] for name in coverage.columns]
    coverage_display.to_csv(os.path.join(TABLE_DIR, "table_mean_coverage_matrix.csv"), encoding="utf-8-sig")
    figure, axis = plt.subplots(figsize=(6.2, 5.2))
    image = axis.imshow(coverage.to_numpy(), cmap="Blues", vmin=0, vmax=max(0.5, np.nanmax(coverage.to_numpy())))
    axis.set_xticks(range(len(ORDER)), [DISPLAY[name] for name in ORDER], rotation=25, ha="right")
    axis.set_yticks(range(len(ORDER)), [DISPLAY[name] for name in ORDER])
    axis.set_xlabel("Solutions being dominated (B)")
    axis.set_ylabel("Dominating algorithm (A)")
    for row in range(len(ORDER)):
        for column in range(len(ORDER)):
            if row == column:
                text = "—"
            else:
                text = f"{coverage.iloc[row, column]:.2f}"
            axis.text(column, row, text, ha="center", va="center",
                      color="white" if row != column and coverage.iloc[row, column] > 0.28 else "black")
    figure.colorbar(image, ax=axis, label="Mean coverage C(A,B)", fraction=0.046, pad=0.04)
    save_figure(figure, "fig_mean_coverage_heatmap")

    figure, axis = plt.subplots(figsize=(8.2, 4.4))
    for position, algorithm in enumerate(ORDER):
        subset = summary[summary["algorithm"] == algorithm]
        means = subset.groupby("instance_id")["union_front_contribution"].mean().reindex(instances)
        axis.bar(x + (position - 1.5) * width, means, width, color=COLORS[algorithm],
                 label=DISPLAY[algorithm], edgecolor="white", linewidth=0.6)
    axis.set_ylabel("Mean union-front contribution")
    axis.set_xticks(x, [instance_display(name) for name in instances])
    axis.grid(axis="y", alpha=0.25)
    axis.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.14), frameon=False)
    save_figure(figure, "fig_union_front_contribution")

    current_rows = []
    for algorithm in ORDER:
        for seed in sorted(summary[summary["instance_id"] == "current"]["seed"].unique()):
            frame = pd.read_csv(os.path.join(
                EXPERIMENT_DIR, "current", f"seed_{seed}", f"{algorithm}_pareto_archive.csv"
            ))
            frame["algorithm"] = algorithm
            current_rows.append(frame)
    current = pd.concat(current_rows, ignore_index=True)
    values = current[CRITERIA].to_numpy(float)
    current = current[nondominated_mask(values)].copy()
    pairs = [
        ("total_cost_vnd", "max_route_duration_minutes", "Total cost (VND)", "Maximum route duration (min)"),
        ("total_cost_vnd", "workload_imbalance", "Total cost (VND)", "Workload imbalance"),
        ("max_route_duration_minutes", "workload_imbalance", "Maximum route duration (min)", "Workload imbalance"),
    ]
    figure, axes = plt.subplots(1, 3, figsize=(13.5, 4.0))
    for axis, (x_column, y_column, x_label, y_label) in zip(axes, pairs):
        for algorithm in ORDER:
            subset = current[current["algorithm"] == algorithm]
            axis.scatter(subset[x_column], subset[y_column], s=23, alpha=0.65,
                         c=COLORS[algorithm], marker=MARKERS[algorithm], label=DISPLAY[algorithm],
                         edgecolors="none")
        axis.set_xlabel(x_label); axis.set_ylabel(y_label); axis.grid(alpha=0.2)
    handles, labels = axes[0].get_legend_handles_labels()
    figure.legend(handles, labels, ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.04), frameon=False)
    figure.tight_layout(rect=(0, 0, 1, 0.93))
    save_figure(figure, "fig_current_empirical_pareto_front")


def write_summary(summary, overall, statistical, friedman_stat, friedman_p, instance_stat, instance_p):
    block_count, instance_count, seed_text, budget = experiment_scope(summary)
    best = overall["mean_hv_rank"].idxmin()
    moalns = overall.loc["MOALNS"]
    moead = overall.loc["MOEA/D"]
    nsga = overall.loc["NSGA-II"]
    epsilon = overall.loc["Epsilon-constraint"]
    instance_means = summary.groupby(["instance_id", "algorithm"])["hypervolume_normalized"].mean().unstack()
    moalns_instance_wins = int((instance_means.idxmax(axis=1) == "moalns").sum())
    significant_better = []
    for algorithm in ORDER[1:]:
        row = statistical.loc[f"MOALNS vs {DISPLAY[algorithm]}"]
        if row["Mean HV difference"] > 0 and row["p_holm"] < 0.05:
            significant_better.append(DISPLAY[algorithm])
    significance_text = (
        "Holm-adjusted pairwise tests found a significant MOALNS advantage over "
        + ", ".join(significant_better) + "."
        if significant_better
        else "No MOALNS pairwise advantage was significant after Holm correction."
    )
    budget_text = f"{budget:g}-second" if np.isfinite(budget) else "equal"
    text = f"""# Paper-ready benchmark results

## Experimental scope

The final benchmark contains {len(summary)} runs: {summary['instance_id'].nunique()} instances,
{seed_text} seeds per instance, and {summary['algorithm'].nunique()} algorithms.
Each run used a {budget_text} wall-clock budget. Normalized hypervolume uses fixed
per-instance reference bounds across all seeds and algorithms.

## Main result

{best} achieved the best mean hypervolume rank. MOALNS obtained mean normalized
hypervolume {moalns['mean_hv']:.4f}, mean rank {moalns['mean_hv_rank']:.4f}, and
{int(moalns['hv_wins'])} first-place results across {block_count} paired blocks. The corresponding
mean hypervolumes were {moead['mean_hv']:.4f} for MOEA/D, {nsga['mean_hv']:.4f}
for NSGA-II, and {epsilon['mean_hv']:.4f} for epsilon-constraint.

The Friedman test over {block_count} instance-seed blocks gave
($\\chi^2={friedman_stat:.4f}$, $p={friedman_p:.3e}$). Holm-adjusted pairwise
Wilcoxon results are reported in `table_pairwise_statistics`. Because seeds from
the same instance are not fully independent, an instance-level Friedman analysis
was also performed ($\\chi^2={instance_stat:.4f}$, $p={instance_p:.4f}$).

## Recommended claim

“{best} achieved the best average hypervolume rank in the equal-time comparison.
MOALNS obtained the highest instance-level mean on {moalns_instance_wins} of
{instance_count} tested instances. {significance_text} These results should be
interpreted together with the instance-level analysis, which treats benchmark
instances—not repeated random seeds—as the independent experimental units.”

## Files

- `tables/table_hypervolume_by_instance.*`: primary results table.
- `tables/table_overall_performance.*`: aggregate performance.
- `tables/table_pairwise_statistics.*`: Wilcoxon-Holm comparisons.
- `tables/table_runtime.*`: time-budget verification.
- `tables/table_current_extremes.*`: real-instance payoff extremes.
- `figures/fig_hypervolume_by_instance.*`: grouped mean/std chart.
- `figures/fig_hypervolume_distribution.*`: distribution across blocks.
- `figures/fig_average_hypervolume_rank.*`: average-rank chart.
- `figures/fig_mean_coverage_heatmap.*`: average dominance coverage.
- `figures/fig_union_front_contribution.*`: useful archive contribution.
- `figures/fig_current_empirical_pareto_front.*`: current-instance trade-offs.
"""
    with open(os.path.join(PAPER_DIR, "paper_results_summary.md"), "w", encoding="utf-8") as file:
        file.write(text)


def write_captions(summary):
    block_count, _, seed_text, budget = experiment_scope(summary)
    budget_text = f"{budget:g}-second" if np.isfinite(budget) else "equal"
    captions = f"""# Suggested figure captions

1. **Hypervolume by instance.** Mean normalized hypervolume and standard deviation over {seed_text} random seeds under an equal {budget_text} wall-clock budget. Higher values indicate better convergence and coverage.
2. **Hypervolume distribution.** Distribution of normalized hypervolume over all {block_count} paired instance-seed blocks. White circles denote arithmetic means.
3. **Average hypervolume rank.** Mean within-block rank over {block_count} paired runs; lower values are better.
4. **Coverage heatmap.** Mean empirical coverage $C(A,B)$, defined as the proportion of solutions produced by algorithm B that are dominated by at least one solution produced by algorithm A.
5. **Union-front contribution.** Mean number of solutions from each algorithm that remain non-dominated after merging all four archives for the same instance and seed.
6. **Current-instance Pareto front.** Pairwise projections of the empirical non-dominated union obtained over all seeds for the current heterogeneous open PDVRP instance. All three objectives are minimized.
"""
    with open(os.path.join(PAPER_DIR, "figure_captions.md"), "w", encoding="utf-8") as file:
        file.write(captions)


def main():
    global EXPERIMENT_DIR, SUMMARY_PATH, PAPER_DIR, TABLE_DIR, FIGURE_DIR
    args = parse_args()
    EXPERIMENT_DIR = os.path.abspath(args.experiment_dir)
    SUMMARY_PATH = os.path.join(EXPERIMENT_DIR, "benchmark_summary.csv")
    PAPER_DIR = os.path.abspath(args.paper_dir)
    TABLE_DIR = os.path.join(PAPER_DIR, "tables")
    FIGURE_DIR = os.path.join(PAPER_DIR, "figures")
    os.makedirs(TABLE_DIR, exist_ok=True)
    os.makedirs(FIGURE_DIR, exist_ok=True)
    configure_plotting()
    summary = pd.read_csv(SUMMARY_PATH)
    validate_summary(summary)
    work, overall, statistical, friedman_stat, friedman_p, instance_stat, instance_p = create_tables(summary)
    create_figures(summary, work, overall)
    write_summary(summary, overall, statistical, friedman_stat, friedman_p, instance_stat, instance_p)
    write_captions(summary)
    print(f"Paper outputs generated in: {PAPER_DIR}")
    print(f"Tables: {len(glob.glob(os.path.join(TABLE_DIR, '*')))} files")
    print(f"Figures: {len(glob.glob(os.path.join(FIGURE_DIR, '*')))} files")


if __name__ == "__main__":
    main()
