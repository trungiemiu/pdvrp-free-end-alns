"""Compare MCDM/MODM decision rules on the MOALNS Pareto archive."""

import argparse
import json
import os

import numpy as np
import pandas as pd

import alns_pdvrp_solver as routing


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_DIR = os.path.join(BASE_DIR, "outputs", "reports")
ROUTE_DIR = os.path.join(BASE_DIR, "outputs", "routes")
ARCHIVE_PATH = os.path.join(REPORT_DIR, "moalns_pareto_archive.csv")
RANKING_PATH = os.path.join(REPORT_DIR, "modm_rankings.csv")
SELECTION_PATH = os.path.join(REPORT_DIR, "modm_selections.csv")
CORRELATION_PATH = os.path.join(REPORT_DIR, "modm_rank_correlation.csv")
PREFERENCE_TEMPLATE_PATH = os.path.join(REPORT_DIR, "modm_preference_template.csv")
LEARNING_REPORT_PATH = os.path.join(REPORT_DIR, "modm_learning_report.csv")
CRITERIA = ["total_cost_vnd", "max_route_duration_minutes", "workload_imbalance"]
CLASSICAL_METHODS = ["weighted_sum", "topsis", "vikor", "promethee_ii", "waspas"]


def parse_args():
    parser = argparse.ArgumentParser(description="Rank MOALNS Pareto solutions.")
    parser.add_argument("--cost-weight", type=float, default=0.50)
    parser.add_argument("--duration-weight", type=float, default=0.30)
    parser.add_argument("--imbalance-weight", type=float, default=0.20)
    parser.add_argument("--vikor-v", type=float, default=0.50)
    parser.add_argument("--preference-data", default=None,
                        help="Optional labeled CSV enabling Ridge-ML and MLP-DL selectors.")
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def minmax_badness(values):
    minimum = values.min(axis=0)
    spread = values.max(axis=0) - minimum
    spread[spread < 1e-12] = 1.0
    return (values - minimum) / spread


def rank_classical(values, weights, vikor_v):
    bad = minmax_badness(values)
    good = 1.0 - bad
    scores = {}
    scores["weighted_sum"] = good @ weights

    norm = np.sqrt((values ** 2).sum(axis=0))
    norm[norm < 1e-12] = 1.0
    weighted = values / norm * weights
    ideal, anti = weighted.min(axis=0), weighted.max(axis=0)
    d_ideal = np.linalg.norm(weighted - ideal, axis=1)
    d_anti = np.linalg.norm(weighted - anti, axis=1)
    scores["topsis"] = d_anti / np.maximum(d_ideal + d_anti, 1e-12)

    group_utility = (bad * weights).sum(axis=1)
    individual_regret = (bad * weights).max(axis=1)
    s_range = max(group_utility.max() - group_utility.min(), 1e-12)
    r_range = max(individual_regret.max() - individual_regret.min(), 1e-12)
    q = (
        vikor_v * (group_utility - group_utility.min()) / s_range
        + (1.0 - vikor_v) * (individual_regret - individual_regret.min()) / r_range
    )
    scores["vikor"] = 1.0 - q

    pairwise = good[:, None, :] - good[None, :, :]
    preference = np.maximum(pairwise, 0.0) @ weights
    scores["promethee_ii"] = preference.mean(axis=1) - preference.mean(axis=0)

    multiplicative = np.prod(np.clip(good, 1e-9, 1.0) ** weights, axis=1)
    scores["waspas"] = 0.5 * (good @ weights) + 0.5 * multiplicative
    return scores, bad


def ridge_fit_predict(train_x, train_y, test_x, alpha=1.0):
    x = np.column_stack([np.ones(len(train_x)), train_x])
    penalty = np.eye(x.shape[1]) * alpha
    penalty[0, 0] = 0.0
    coefficients = np.linalg.solve(x.T @ x + penalty, x.T @ train_y)
    return np.column_stack([np.ones(len(test_x)), test_x]) @ coefficients


def mlp_fit_predict(train_x, train_y, test_x, seed, epochs=2000, learning_rate=0.01):
    """Small two-hidden-layer preference network implemented with NumPy."""
    rng = np.random.default_rng(seed)
    w1 = rng.normal(0, 0.25, (train_x.shape[1], 16)); b1 = np.zeros((1, 16))
    w2 = rng.normal(0, 0.25, (16, 8)); b2 = np.zeros((1, 8))
    w3 = rng.normal(0, 0.25, (8, 1)); b3 = np.zeros((1, 1))
    target = train_y.reshape(-1, 1)
    for _ in range(epochs):
        z1 = train_x @ w1 + b1; h1 = np.maximum(z1, 0)
        z2 = h1 @ w2 + b2; h2 = np.maximum(z2, 0)
        prediction = h2 @ w3 + b3
        dp = 2.0 * (prediction - target) / len(train_x)
        dw3 = h2.T @ dp; db3 = dp.sum(axis=0, keepdims=True)
        dh2 = dp @ w3.T; dz2 = dh2 * (z2 > 0)
        dw2 = h1.T @ dz2; db2 = dz2.sum(axis=0, keepdims=True)
        dh1 = dz2 @ w2.T; dz1 = dh1 * (z1 > 0)
        dw1 = train_x.T @ dz1; db1 = dz1.sum(axis=0, keepdims=True)
        for parameter, gradient in ((w1, dw1), (b1, db1), (w2, dw2),
                                    (b2, db2), (w3, dw3), (b3, db3)):
            np.clip(gradient, -5.0, 5.0, out=gradient)
            parameter -= learning_rate * gradient
    h1 = np.maximum(test_x @ w1 + b1, 0)
    h2 = np.maximum(h1 @ w2 + b2, 0)
    return (h2 @ w3 + b3).ravel()


def learning_scores(path, current_badness, seed):
    if not path:
        return {}, []
    data = pd.read_csv(path).dropna(
        subset=["cost_norm", "duration_norm", "imbalance_norm", "preference_score"]
    )
    if len(data) < 12:
        raise ValueError("Preference learning needs at least 12 labeled rows from training instances.")
    features = data[["cost_norm", "duration_norm", "imbalance_norm"]].to_numpy(float)
    target = data["preference_score"].to_numpy(float)
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(data))
    split = max(8, int(0.8 * len(data)))
    train_idx, test_idx = order[:split], order[split:]
    mean, std = features[train_idx].mean(axis=0), features[train_idx].std(axis=0)
    std[std < 1e-12] = 1.0
    train_x = (features[train_idx] - mean) / std
    test_x = (features[test_idx] - mean) / std
    current_x = (current_badness - mean) / std
    reports, scores = [], {}
    ridge_test = ridge_fit_predict(train_x, target[train_idx], test_x)
    scores["ridge_ml"] = ridge_fit_predict(train_x, target[train_idx], current_x)
    reports.append({"method": "ridge_ml", "training_rows": len(train_idx),
                    "test_rows": len(test_idx),
                    "test_rmse": float(np.sqrt(np.mean((ridge_test - target[test_idx]) ** 2)))})
    mlp_test = mlp_fit_predict(train_x, target[train_idx], test_x, seed)
    scores["mlp_dl"] = mlp_fit_predict(train_x, target[train_idx], current_x, seed)
    reports.append({"method": "mlp_dl", "training_rows": len(train_idx),
                    "test_rows": len(test_idx),
                    "test_rmse": float(np.sqrt(np.mean((mlp_test - target[test_idx]) ** 2)))})
    return scores, reports


def deserialize_routes(text):
    raw = json.loads(text)
    return {driver_id: [(str(order), str(action)) for order, action in sequence]
            for driver_id, sequence in raw.items()}


def materialize_solution(method, archive_row, data):
    orders, drivers, vehicle_params, distance_matrix = data
    order_lookup = routing.build_order_lookup(orders)
    driver_lookup = routing.build_driver_lookup(drivers, vehicle_params)
    revenue_lookup = routing.build_order_revenue_lookup(orders, vehicle_params, distance_matrix)
    routes = deserialize_routes(archive_row["routes_json"])
    routes_frame, steps_frame, summary_frame = routing.routes_to_outputs(
        routes, driver_lookup, order_lookup, revenue_lookup, distance_matrix
    )
    method_name = "moalns_" + method
    routes_frame.to_csv(os.path.join(ROUTE_DIR, method_name + "_routes.csv"), index=False, encoding="utf-8-sig")
    steps_frame.to_csv(os.path.join(ROUTE_DIR, method_name + "_route_steps.csv"), index=False, encoding="utf-8-sig")
    summary_frame.to_csv(os.path.join(REPORT_DIR, method_name + "_summary.csv"), index=False, encoding="utf-8-sig")
    return method_name


def main():
    args = parse_args()
    weights = np.array([args.cost_weight, args.duration_weight, args.imbalance_weight], dtype=float)
    if np.any(weights < 0) or weights.sum() <= 0:
        raise ValueError("Decision weights must be non-negative and not all zero.")
    weights /= weights.sum()
    archive = pd.read_csv(ARCHIVE_PATH)
    if len(archive) < 2:
        raise ValueError("At least two Pareto alternatives are required for MODM comparison.")
    values = archive[CRITERIA].to_numpy(float)
    scores, badness = rank_classical(values, weights, args.vikor_v)
    learned_scores, learning_report = learning_scores(args.preference_data, badness, args.seed)
    scores.update(learned_scores)

    ranking = archive[["solution_id", *CRITERIA]].copy()
    method_names = list(scores)
    for method, score in scores.items():
        ranking[method + "_score"] = score
        ranking[method + "_rank"] = pd.Series(score).rank(ascending=False, method="min").astype(int)
    classical_rank_columns = [method + "_rank" for method in CLASSICAL_METHODS]
    ranking["borda_rank_sum"] = ranking[classical_rank_columns].sum(axis=1)
    ranking["borda_score"] = -ranking["borda_rank_sum"]
    ranking["borda_rank"] = ranking["borda_rank_sum"].rank(method="min").astype(int)
    method_names.append("borda")

    selections = []
    data = routing.load_data()
    os.makedirs(ROUTE_DIR, exist_ok=True)
    for method in method_names:
        rank_column = method + "_rank"
        selected_index = ranking[rank_column].idxmin()
        selected = archive.loc[selected_index]
        method_name = materialize_solution(method, selected, data)
        selections.append({
            "decision_method": method, "output_method": method_name,
            "solution_id": selected["solution_id"],
            "cost_weight": weights[0], "duration_weight": weights[1],
            "imbalance_weight": weights[2],
            **{criterion: selected[criterion] for criterion in CRITERIA},
        })

    normalized_template = archive[["solution_id", *CRITERIA]].copy()
    normalized_template["cost_norm"] = badness[:, 0]
    normalized_template["duration_norm"] = badness[:, 1]
    normalized_template["imbalance_norm"] = badness[:, 2]
    normalized_template["preference_score"] = np.nan
    ranking.to_csv(RANKING_PATH, index=False, encoding="utf-8-sig")
    pd.DataFrame(selections).to_csv(SELECTION_PATH, index=False, encoding="utf-8-sig")
    rank_columns = [method + "_rank" for method in method_names]
    ranking[rank_columns].corr(method="spearman").to_csv(CORRELATION_PATH, encoding="utf-8-sig")
    normalized_template.to_csv(PREFERENCE_TEMPLATE_PATH, index=False, encoding="utf-8-sig")
    pd.DataFrame(learning_report).to_csv(LEARNING_REPORT_PATH, index=False, encoding="utf-8-sig")
    print("MODM/MCDM comparison completed.")
    print(pd.DataFrame(selections).to_string(index=False))
    if not args.preference_data:
        print("ML/DL selectors skipped: label preference_score in the generated template or provide cross-instance preference data.")
    print("Rankings: " + RANKING_PATH)


if __name__ == "__main__":
    main()
