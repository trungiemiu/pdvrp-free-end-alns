import os
import pandas as pd


# Project root: MDVRP/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Input files
DRIVERS_PATH = os.path.join(BASE_DIR, "data", "drivers.csv")
ORDERS_PATH = os.path.join(BASE_DIR, "data", "orders.csv")

# Output file
OUTPUT_PATH = os.path.join(BASE_DIR, "data", "nodes.csv")


def build_nodes(drivers: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    nodes = []

    # 1. Driver starting locations
    for _, row in drivers.iterrows():
        nodes.append({
            "node_id": f"{row['driver_id']}_START",
            "node_type": "driver_start",
            "related_id": row["driver_id"],
            "address": f"Start location of {row['driver_id']}",
            "lat": row["start_lat"],
            "lon": row["start_lon"],
        })

    # 2. Pickup and delivery locations
    for _, row in orders.iterrows():
        order_num = str(row["order_id"]).replace("O", "").zfill(2)

        nodes.append({
            "node_id": f"P{order_num}",
            "node_type": "pickup",
            "related_id": row["order_id"],
            "address": row["pickup_address"],
            "lat": "",
            "lon": "",
        })

        nodes.append({
            "node_id": f"L{order_num}",
            "node_type": "delivery",
            "related_id": row["order_id"],
            "address": row["delivery_address"],
            "lat": "",
            "lon": "",
        })

    return pd.DataFrame(nodes)


def main():
    print("Reading input files...")
    print(f"Drivers path: {DRIVERS_PATH}")
    print(f"Orders path: {ORDERS_PATH}")

    drivers = pd.read_csv(DRIVERS_PATH)
    orders = pd.read_csv(ORDERS_PATH)

    nodes = build_nodes(drivers, orders)

    nodes.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    print("\n nodes.csv created successfully.")
    print(f"Number of drivers: {len(drivers)}")
    print(f"Number of orders: {len(orders)}")
    print(f"Number of nodes: {len(nodes)}")

    print("\nPreview:")
    print(nodes.head(15))


if __name__ == "__main__":
    main()