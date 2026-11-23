import argparse
import os
import re

import folium
import pandas as pd
from folium.plugins import PolyLineTextPath


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODES_PATH = os.path.join(BASE_DIR, "data", "nodes_geocoded.csv")
DRIVER_COLORS = {
    "D01": "#E6194B", "D02": "#3CB44B", "D03": "#4363D8",
    "D04": "#F58231", "D05": "#911EB4", "D06": "#46F0F0",
    "D07": "#F032E6", "D08": "#BCF60C", "D09": "#000075",
}
TITLES = {
    "baseline": "Baseline Route Map",
    "improved_baseline": "Improved Baseline Route Map",
    "balanced_improved": "Balanced Improved Route Map",
    "ortools": "OR-Tools Route Map",
    "milp_pulp": "MILP/PuLP Route Map",
    "alns_pdvrp": "Proposed ALNS-PDVRP Route Map",
    "moalns_borda": "MOALNS + Borda Consensus Route Map",
}


def parse_args():
    parser = argparse.ArgumentParser(description="Visualize a routing solution.")
    parser.add_argument("--method", default="alns_pdvrp")
    return parser.parse_args()


def route_nodes(text):
    if pd.isna(text) or not str(text).strip():
        return []
    return [value.strip() for value in str(text).split("->")]


def main():
    method = parse_args().method
    if not re.fullmatch(r"[A-Za-z0-9_]+", method):
        raise ValueError("Method name may contain only letters, numbers, and underscores.")

    summary_path = os.path.join(BASE_DIR, "outputs", "reports", f"{method}_summary.csv")
    output_path = os.path.join(BASE_DIR, "outputs", "figures", f"{method}_route_map.html")
    if not os.path.exists(summary_path):
        raise FileNotFoundError(summary_path)

    nodes = pd.read_csv(NODES_PATH)
    summary = pd.read_csv(summary_path)
    lookup = nodes.set_index("node_id").to_dict(orient="index")
    route_map = folium.Map(
        location=[nodes["lat"].astype(float).mean(), nodes["lon"].astype(float).mean()],
        zoom_start=12,
        tiles="OpenStreetMap",
    )

    for _, node in nodes.iterrows():
        node_type = str(node["node_type"])
        color, icon = {
            "driver_start": ("black", "home"),
            "pickup": ("green", "plus"),
            "delivery": ("red", "flag"),
        }.get(node_type, ("gray", "info-sign"))
        folium.Marker(
            [float(node["lat"]), float(node["lon"])],
            tooltip=f"{node['node_id']} ({node_type})",
            popup=f"<b>{node['node_id']}</b><br>{node.get('address', '')}",
            icon=folium.Icon(color=color, icon=icon, prefix="fa"),
        ).add_to(route_map)

    active_drivers = []
    for _, row in summary.iterrows():
        if int(row.get("num_orders", 0)) <= 0:
            continue
        driver = str(row["driver_id"])
        sequence = route_nodes(row["route"])
        coordinates = [
            [float(lookup[node]["lat"]), float(lookup[node]["lon"])]
            for node in sequence if node in lookup
        ]
        if len(coordinates) < 2:
            continue
        color = DRIVER_COLORS.get(driver, "#555555")
        line = folium.PolyLine(
            coordinates,
            color=color,
            weight=5,
            opacity=0.9,
            tooltip=f"{driver}: {int(row['num_orders'])} orders, {float(row['total_distance_km']):.2f} km",
        ).add_to(route_map)
        PolyLineTextPath(line, "➜", repeat=False, center=True, offset=8,
                         attributes={"fill": color, "font-size": "24"}).add_to(route_map)
        active_drivers.append((driver, color, int(row["num_orders"])))

    title = TITLES.get(method, f"{method.replace('_', ' ').title()} Route Map")
    driver_lines = "".join(
        f'<span style="color:{color}">■</span> {driver}: {count} orders<br>'
        for driver, color, count in active_drivers
    )
    legend = f"""
    <div style="position:fixed;bottom:35px;left:35px;background:white;border:2px solid #777;
                z-index:9999;padding:12px;border-radius:8px;font-size:14px">
      <b>{title}</b><br><br>{driver_lines}
      <span style="color:green">●</span> pickup &nbsp;
      <span style="color:red">●</span> delivery
    </div>"""
    route_map.get_root().html.add_child(folium.Element(legend))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    route_map.save(output_path)
    print(f"Map saved to: {output_path}")


if __name__ == "__main__":
    main()
