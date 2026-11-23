import os
import time
import pandas as pd
from tqdm import tqdm
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NODES_PATH = os.path.join(BASE_DIR, "data", "nodes.csv")
OUTPUT_PATH = os.path.join(BASE_DIR, "data", "nodes_geocoded.csv")


def is_missing(value):
    return pd.isna(value) or str(value).strip() == "" or str(value).strip().lower() == "nan"


def simplify_address(address: str) -> str:
    """
    Clean and simplify Vietnamese addresses for OpenStreetMap/Nominatim.
    """
    address = str(address)

    replacements = [
        ("Thành phố Hồ Chí Minh", "Ho Chi Minh City"),
        ("thành phố Hồ Chí Minh", "Ho Chi Minh City"),
        ("TP.HCM", "Ho Chi Minh City"),
        ("Tp. Hồ Chí Minh", "Ho Chi Minh City"),
        ("Việt Nam", "Vietnam"),
        ("Quận", "District"),
        ("quận", "District"),
        ("Phường", "Ward"),
        ("phường", "Ward"),
        ("Đ.", "Đường"),
        ("P.", "Ward "),
    ]

    for old, new in replacements:
        address = address.replace(old, new)

    return address


def try_geocode(geocode, address):
    """
    Try multiple address versions to improve success rate.
    """
    candidates = []

    full_address = simplify_address(address)
    candidates.append(full_address)

    # Remove Vietnam
    candidates.append(full_address.replace(", Vietnam", "").replace(", Việt Nam", ""))

    # Keep only first part + city
    parts = full_address.split(",")
    if len(parts) >= 2:
        candidates.append(parts[0].strip() + ", Ho Chi Minh City, Vietnam")

    # Keep street-level simplified version
    if len(parts) >= 3:
        candidates.append(parts[0].strip() + ", " + parts[-2].strip() + ", Ho Chi Minh City, Vietnam")

    for candidate in candidates:
        candidate = candidate.strip()
        if candidate == "":
            continue

        location = geocode(candidate)

        if location is not None:
            return location, candidate

    return None, None


def main():
    print("Reading nodes.csv...")
    print(f"Input path: {NODES_PATH}")

    nodes = pd.read_csv(NODES_PATH)

    geolocator = Nominatim(user_agent="xedu_vrp_project")
    geocode = RateLimiter(
        geolocator.geocode,
        min_delay_seconds=1,
        max_retries=2,
        error_wait_seconds=3,
        swallow_exceptions=True,
    )

    for idx, row in tqdm(nodes.iterrows(), total=len(nodes)):
        # Skip nodes that already have coordinates
        if not is_missing(row["lat"]) and not is_missing(row["lon"]):
            continue

        address = row["address"]
        location, used_query = try_geocode(geocode, address)

        if location is not None:
            nodes.at[idx, "lat"] = location.latitude
            nodes.at[idx, "lon"] = location.longitude
            print(f"FOUND {row['node_id']}: {location.latitude}, {location.longitude}")
            print(f"  Query: {used_query}")
        else:
            print(f"NOT FOUND {row['node_id']}: {address}")

        time.sleep(0.2)

    nodes.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    missing = nodes[
        nodes["lat"].apply(is_missing)
        | nodes["lon"].apply(is_missing)
    ]

    print("\nGeocoding completed.")
    print(f"Total nodes: {len(nodes)}")
    print(f"Missing coordinates: {len(missing)}")
    print(f"Output saved to: {OUTPUT_PATH}")

    if len(missing) > 0:
        missing_path = os.path.join(BASE_DIR, "data", "missing_geocoding.csv")
        missing.to_csv(missing_path, index=False, encoding="utf-8-sig")

        print(f"\nMissing nodes saved to: {missing_path}")
        print(missing[["node_id", "node_type", "related_id", "address"]])


if __name__ == "__main__":
    main()