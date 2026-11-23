"""Create a dependency-free HTML visualization of the three-objective Pareto set."""

import html
import os

import pandas as pd


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_DIR = os.path.join(BASE_DIR, "outputs", "reports")
OUTPUT_PATH = os.path.join(BASE_DIR, "outputs", "figures", "moalns_pareto_front.html")
ARCHIVE_PATH = os.path.join(REPORT_DIR, "moalns_pareto_archive.csv")
SELECTION_PATH = os.path.join(REPORT_DIR, "modm_selections.csv")


def scale(values, low, high, invert=False):
    minimum, maximum = min(values), max(values)
    if maximum == minimum:
        points = [(low + high) / 2] * len(values)
    else:
        points = [low + (value - minimum) / (maximum - minimum) * (high - low) for value in values]
    return [low + high - value for value in points] if invert else points


def scatter(frame, x_column, y_column, title, selected):
    width, height, margin = 520, 360, 58
    xs = scale(frame[x_column].tolist(), margin, width - margin)
    ys = scale(frame[y_column].tolist(), margin, height - margin, invert=True)
    elements = [
        f'<svg viewBox="0 0 {width} {height}" class="chart">',
        f'<text x="{width / 2}" y="24" text-anchor="middle" class="title">{html.escape(title)}</text>',
        f'<line x1="{margin}" y1="{height-margin}" x2="{width-margin}" y2="{height-margin}" class="axis"/>',
        f'<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{height-margin}" class="axis"/>',
        f'<text x="{width/2}" y="{height-10}" text-anchor="middle">{html.escape(x_column)}</text>',
        f'<text transform="translate(16 {height/2}) rotate(-90)" text-anchor="middle">{html.escape(y_column)}</text>',
    ]
    for (_, row), x, y in zip(frame.iterrows(), xs, ys):
        solution_id = str(row["solution_id"])
        chosen = solution_id in selected
        color = "#d62728" if chosen else "#2878b5"
        radius = 7 if chosen else 5
        tooltip = (f"{solution_id}: {x_column}={row[x_column]:.3f}, "
                   f"{y_column}={row[y_column]:.3f}")
        elements.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius}" fill="{color}"><title>{html.escape(tooltip)}</title></circle>')
        elements.append(f'<text x="{x+7:.2f}" y="{y-7:.2f}" class="label">{html.escape(solution_id)}</text>')
    elements.append("</svg>")
    return "".join(elements)


def main():
    archive = pd.read_csv(ARCHIVE_PATH)
    selections = pd.read_csv(SELECTION_PATH) if os.path.exists(SELECTION_PATH) else pd.DataFrame()
    selected = set(selections["solution_id"].astype(str)) if not selections.empty else set()
    charts = [
        scatter(archive, "total_cost_vnd", "max_route_duration_minutes", "Cost vs maximum route duration", selected),
        scatter(archive, "total_cost_vnd", "workload_imbalance", "Cost vs workload imbalance", selected),
        scatter(archive, "max_route_duration_minutes", "workload_imbalance", "Duration vs workload imbalance", selected),
    ]
    selection_table = selections.drop(columns=["output_method"], errors="ignore").to_html(index=False, float_format=lambda x: f"{x:.3f}")
    document = f"""<!doctype html><html><head><meta charset="utf-8"><title>MOALNS Pareto front</title>
    <style>body{{font-family:Segoe UI,Arial;margin:30px;color:#222}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(480px,1fr));gap:16px}}.chart{{border:1px solid #ccc;background:#fff}}.axis{{stroke:#333;stroke-width:1.5}}.title{{font-size:17px;font-weight:600}}.label{{font-size:10px}}table{{border-collapse:collapse}}th,td{{border:1px solid #ccc;padding:6px 9px}}</style>
    </head><body><h1>MOALNS three-objective Pareto front</h1>
    <p>Blue: non-dominated alternative. Red: selected by at least one decision method. All criteria are minimized.</p>
    <div class="grid">{''.join(charts)}</div><h2>MODM/MCDM selections</h2>{selection_table}</body></html>"""
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as file:
        file.write(document)
    print("Pareto visualization saved to: " + OUTPUT_PATH)


if __name__ == "__main__":
    main()
