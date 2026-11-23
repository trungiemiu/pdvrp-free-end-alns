import argparse
import json
import math
import os
import shutil
import time
import urllib.error
import urllib.request
from datetime import datetime

import pandas as pd

from distance_matrix import haversine_km, validate_coordinates


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_NODES_PATH = os.path.join(BASE_DIR, "data", "nodes_geocoded.csv")
DEFAULT_DISTANCE_OUTPUT_PATH = os.path.join(BASE_DIR, "data", "distance_matrix_osrm.csv")
DEFAULT_DURATION_OUTPUT_PATH = os.path.join(BASE_DIR, "data", "duration_matrix_osrm_seconds.csv")
DEFAULT_METADATA_OUTPUT_PATH = os.path.join(BASE_DIR, "data", "osrm_matrix_metadata.json")
DEFAULT_ACTIVE_DISTANCE_PATH = os.path.join(BASE_DIR, "data", "distance_matrix.csv")
DEFAULT_HAVERSINE_BACKUP_PATH = os.path.join(BASE_DIR, "data", "distance_matrix_haversine_backup.csv")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build road distance and travel-time matrices with OSRM Table API."
    )
    parser.add_argument(
        "--nodes-path",
        default=DEFAULT_NODES_PATH,
        help="Input nodes CSV with node_id, lat, lon columns.",
    )
    parser.add_argument(
        "--endpoint",
        default="https://router.project-osrm.org",
        help="OSRM endpoint. Use a self-hosted endpoint for reproducible or high-volume runs.",
    )
    parser.add_argument(
        "--profile",
        default="driving",
        help="OSRM profile, usually driving for the public demo server.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of source rows requested per OSRM call.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=1.1,
        help="Pause between calls. Keep >= 1.0 for the public OSRM demo server.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Retry count for transient HTTP failures.",
    )
    parser.add_argument(
        "--distance-output",
        default=DEFAULT_DISTANCE_OUTPUT_PATH,
        help="Output CSV for road distance matrix in kilometers.",
    )
    parser.add_argument(
        "--duration-output",
        default=DEFAULT_DURATION_OUTPUT_PATH,
        help="Output CSV for travel-time matrix in seconds.",
    )
    parser.add_argument(
        "--metadata-output",
        default=DEFAULT_METADATA_OUTPUT_PATH,
        help="Output JSON metadata file.",
    )
    parser.add_argument(
        "--replace-distance-matrix",
        action="store_true",
        help="Backup data/distance_matrix.csv and replace it with the OSRM distance matrix.",
    )
    parser.add_argument(
        "--fallback-haversine-speed-kmh",
        type=float,
        default=None,
        help=(
            "If OSRM returns an unroutable pair, fill it with Haversine distance "
            "and estimate duration with this speed. Omit to fail on unroutable pairs."
        ),
    )

    return parser.parse_args()


def build_coordinates(nodes):
    return ";".join(
        "{:.6f},{:.6f}".format(float(row["lon"]), float(row["lat"]))
        for _, row in nodes.iterrows()
    )


def build_table_url(endpoint, profile, coordinates, source_indexes):
    sources = ";".join(str(i) for i in source_indexes)
    endpoint = endpoint.rstrip("/")

    return (
        "{}/table/v1/{}/{}"
        "?sources={}&destinations=all&annotations=duration,distance"
    ).format(endpoint, profile, coordinates, sources)


def fetch_json(url, timeout, retries):
    headers = {
        "User-Agent": "pd-vrp-osrm-matrix/1.0",
    }

    last_error = None

    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read().decode("utf-8")
            return json.loads(payload)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt >= retries:
                break

            wait_seconds = 2 ** attempt
            print(f"Request failed ({exc}). Retrying in {wait_seconds}s...")
            time.sleep(wait_seconds)

    raise RuntimeError(f"OSRM request failed after {retries + 1} attempts: {last_error}")


def fill_missing_with_haversine(nodes, distance_matrix, duration_matrix, speed_kmh):
    if speed_kmh is None:
        return

    node_lookup = nodes.set_index("node_id")

    for from_node in distance_matrix.index:
        for to_node in distance_matrix.columns:
            if not pd.isna(distance_matrix.loc[from_node, to_node]):
                continue

            if from_node == to_node:
                distance_km = 0.0
            else:
                from_row = node_lookup.loc[from_node]
                to_row = node_lookup.loc[to_node]
                distance_km = haversine_km(
                    from_row["lat"],
                    from_row["lon"],
                    to_row["lat"],
                    to_row["lon"],
                )

            duration_seconds = 0.0
            if speed_kmh > 0:
                duration_seconds = distance_km / speed_kmh * 3600.0

            distance_matrix.loc[from_node, to_node] = round(distance_km, 3)
            duration_matrix.loc[from_node, to_node] = round(duration_seconds, 1)


def validate_complete_matrix(distance_matrix, duration_matrix):
    missing_distance = int(distance_matrix.isna().sum().sum())
    missing_duration = int(duration_matrix.isna().sum().sum())

    if missing_distance or missing_duration:
        raise ValueError(
            "OSRM returned missing values. "
            f"Missing distances={missing_distance}, missing durations={missing_duration}. "
            "Retry, use a self-hosted OSRM server, or pass --fallback-haversine-speed-kmh."
        )


def backup_and_replace_distance_matrix(distance_output_path):
    if os.path.exists(DEFAULT_ACTIVE_DISTANCE_PATH):
        backup_path = DEFAULT_HAVERSINE_BACKUP_PATH

        if os.path.exists(backup_path):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(
                BASE_DIR,
                "data",
                f"distance_matrix_haversine_backup_{timestamp}.csv",
            )

        shutil.copy2(DEFAULT_ACTIVE_DISTANCE_PATH, backup_path)
        print(f"Existing distance matrix backed up to: {backup_path}")

    shutil.copy2(distance_output_path, DEFAULT_ACTIVE_DISTANCE_PATH)
    print(f"Active distance matrix replaced: {DEFAULT_ACTIVE_DISTANCE_PATH}")


def build_osrm_matrices(args):
    nodes = pd.read_csv(args.nodes_path)
    nodes = validate_coordinates(nodes)
    node_ids = nodes["node_id"].astype(str).tolist()

    if args.batch_size <= 0:
        raise ValueError("--batch-size must be positive.")

    coordinates = build_coordinates(nodes)
    distance_matrix = pd.DataFrame(index=node_ids, columns=node_ids, dtype=float)
    duration_matrix = pd.DataFrame(index=node_ids, columns=node_ids, dtype=float)

    total_nodes = len(node_ids)

    print(f"Nodes: {total_nodes}")
    print(f"OSRM endpoint: {args.endpoint}")
    print(f"Profile: {args.profile}")
    print(f"Batch size: {args.batch_size}")

    for start in range(0, total_nodes, args.batch_size):
        end = min(start + args.batch_size, total_nodes)
        source_indexes = list(range(start, end))
        url = build_table_url(args.endpoint, args.profile, coordinates, source_indexes)

        print(f"Fetching OSRM rows {start + 1}-{end} / {total_nodes}...")
        data = fetch_json(url, timeout=args.timeout, retries=args.retries)

        if data.get("code") != "Ok":
            raise RuntimeError(f"OSRM returned code={data.get('code')}: {data}")

        distances = data.get("distances")
        durations = data.get("durations")

        if distances is None or durations is None:
            raise RuntimeError("OSRM response does not contain distances and durations.")

        if len(distances) != len(source_indexes) or len(durations) != len(source_indexes):
            raise RuntimeError("OSRM response row count does not match requested sources.")

        for local_row, source_index in enumerate(source_indexes):
            from_node = node_ids[source_index]

            if len(distances[local_row]) != total_nodes or len(durations[local_row]) != total_nodes:
                raise RuntimeError("OSRM response column count does not match node count.")

            for destination_index, to_node in enumerate(node_ids):
                distance_m = distances[local_row][destination_index]
                duration_s = durations[local_row][destination_index]

                if distance_m is not None and not math.isnan(float(distance_m)):
                    distance_matrix.loc[from_node, to_node] = round(float(distance_m) / 1000.0, 3)

                if duration_s is not None and not math.isnan(float(duration_s)):
                    duration_matrix.loc[from_node, to_node] = round(float(duration_s), 1)

        if end < total_nodes and args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)

    fill_missing_with_haversine(
        nodes,
        distance_matrix,
        duration_matrix,
        speed_kmh=args.fallback_haversine_speed_kmh,
    )
    validate_complete_matrix(distance_matrix, duration_matrix)

    os.makedirs(os.path.dirname(args.distance_output), exist_ok=True)
    os.makedirs(os.path.dirname(args.duration_output), exist_ok=True)
    os.makedirs(os.path.dirname(args.metadata_output), exist_ok=True)

    distance_matrix.to_csv(args.distance_output, encoding="utf-8-sig")
    duration_matrix.to_csv(args.duration_output, encoding="utf-8-sig")

    metadata = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "OSRM Table API",
        "endpoint": args.endpoint,
        "profile": args.profile,
        "nodes_path": os.path.abspath(args.nodes_path),
        "node_count": total_nodes,
        "distance_output": os.path.abspath(args.distance_output),
        "duration_output": os.path.abspath(args.duration_output),
        "distance_unit": "km",
        "duration_unit": "seconds",
        "fallback_haversine_speed_kmh": args.fallback_haversine_speed_kmh,
        "notes": [
            "Distances and durations are road-network estimates from OpenStreetMap via OSRM.",
            "The public OSRM demo server is for fair-use testing; use self-hosted OSRM for reproducible production runs.",
        ],
    }

    with open(args.metadata_output, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    if args.replace_distance_matrix:
        backup_and_replace_distance_matrix(args.distance_output)

    return distance_matrix, duration_matrix


def main():
    args = parse_args()
    distance_matrix, duration_matrix = build_osrm_matrices(args)

    print("\nOSRM matrices created successfully.")
    print(f"Distance matrix: {args.distance_output}")
    print(f"Duration matrix: {args.duration_output}")
    print(f"Metadata: {args.metadata_output}")
    print(f"Matrix shape: {distance_matrix.shape}")

    print("\nDistance preview (km):")
    print(distance_matrix.iloc[:5, :5])

    print("\nDuration preview (seconds):")
    print(duration_matrix.iloc[:5, :5])


if __name__ == "__main__":
    main()
