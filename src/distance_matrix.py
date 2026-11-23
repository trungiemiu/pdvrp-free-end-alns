import os
import math
import pandas as pd


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NODES_PATH = os.path.join(BASE_DIR, "data", "nodes_geocoded.csv")
OUTPUT_PATH = os.path.join(BASE_DIR, "data", "distance_matrix.csv")


def haversine_km(lat1, lon1, lat2, lon2):
    """
    Calculate distance between two latitude/longitude points using the Haversine formula.
    Output: distance in kilometers.
    """
    radius_earth_km = 6371.0

    lat1_rad = math.radians(float(lat1))
    lon1_rad = math.radians(float(lon1))
    lat2_rad = math.radians(float(lat2))
    lon2_rad = math.radians(float(lon2))

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return radius_earth_km * c


def validate_coordinates(nodes: pd.DataFrame):
    """
    Check whether all nodes have valid latitude and longitude.
    """
    required_cols = ["node_id", "lat", "lon"]

    for col in required_cols:
        if col not in nodes.columns:
            raise ValueError(f"Missing required column in nodes.csv: {col}")

    nodes["lat"] = nodes["lat"].astype(str).str.strip()
    nodes["lon"] = nodes["lon"].astype(str).str.strip()

    missing = nodes[
        (nodes["lat"] == "")
        | (nodes["lon"] == "")
        | (nodes["lat"].str.lower() == "nan")
        | (nodes["lon"].str.lower() == "nan")
    ]

    if len(missing) > 0:
        print("\nSome nodes are missing coordinates.")
        print("Please fill lat/lon before generating distance_matrix.csv.\n")
        print(missing[["node_id", "node_type", "related_id", "address", "lat", "lon"]])

        raise ValueError(
            f"Cannot create distance matrix because {len(missing)} nodes are missing coordinates."
        )

    # Check numeric conversion
    try:
        nodes["lat"] = nodes["lat"].astype(float)
        nodes["lon"] = nodes["lon"].astype(float)
    except ValueError as e:
        raise ValueError("Some lat/lon values are not numeric. Please check nodes.csv.") from e

    return nodes


def build_distance_matrix(nodes: pd.DataFrame) -> pd.DataFrame:
    """
    Build a square distance matrix where rows and columns are node_id.
    """
    node_ids = nodes["node_id"].tolist()

    matrix = pd.DataFrame(index=node_ids, columns=node_ids, dtype=float)

    node_lookup = nodes.set_index("node_id")

    for from_node in node_ids:
        lat1 = node_lookup.loc[from_node, "lat"]
        lon1 = node_lookup.loc[from_node, "lon"]

        for to_node in node_ids:
            lat2 = node_lookup.loc[to_node, "lat"]
            lon2 = node_lookup.loc[to_node, "lon"]

            if from_node == to_node:
                distance = 0.0
            else:
                distance = haversine_km(lat1, lon1, lat2, lon2)

            matrix.loc[from_node, to_node] = round(distance, 3)

    return matrix


def main():
    print("Reading nodes.csv...")
    print(f"Nodes path: {NODES_PATH}")

    nodes = pd.read_csv(NODES_PATH)

    print(f"Number of nodes: {len(nodes)}")

    nodes = validate_coordinates(nodes)

    print("Building distance matrix...")
    distance_matrix = build_distance_matrix(nodes)

    distance_matrix.to_csv(OUTPUT_PATH, encoding="utf-8-sig")

    print("\ndistance_matrix.csv created successfully.")
    print(f"Output path: {OUTPUT_PATH}")
    print(f"Matrix shape: {distance_matrix.shape}")

    print("\nPreview:")
    print(distance_matrix.iloc[:5, :5])


if __name__ == "__main__":
    main()