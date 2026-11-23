import os
import pandas as pd

from routing_economics import build_order_revenue_lookup


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DRIVERS_PATH = os.path.join(BASE_DIR, "data", "drivers.csv")
ORDERS_PATH = os.path.join(BASE_DIR, "data", "orders.csv")
VEHICLE_PARAMS_PATH = os.path.join(BASE_DIR, "data", "vehicle_parameters.csv")
DISTANCE_MATRIX_PATH = os.path.join(BASE_DIR, "data", "distance_matrix.csv")

ROUTES_OUTPUT_PATH = os.path.join(BASE_DIR, "outputs", "routes", "baseline_routes.csv")
SUMMARY_OUTPUT_PATH = os.path.join(BASE_DIR, "outputs", "reports", "baseline_summary.csv")
STEPS_OUTPUT_PATH = os.path.join(BASE_DIR, "outputs", "routes", "baseline_route_steps.csv")


def normalize_vehicle_type(value: str) -> str:
    value = str(value).strip().lower()
    value = value.replace("-", "_").replace(" ", "_")
    return value


def load_data():
    drivers = pd.read_csv(DRIVERS_PATH)
    orders = pd.read_csv(ORDERS_PATH)
    vehicle_params = pd.read_csv(VEHICLE_PARAMS_PATH)
    distance_matrix = pd.read_csv(DISTANCE_MATRIX_PATH, index_col=0)

    drivers["vehicle_type"] = drivers["vehicle_type"].apply(normalize_vehicle_type)
    orders["required_vehicle"] = orders["required_vehicle"].apply(normalize_vehicle_type)
    vehicle_params["vehicle_type"] = vehicle_params["vehicle_type"].apply(normalize_vehicle_type)

    return drivers, orders, vehicle_params, distance_matrix


def get_distance(distance_matrix: pd.DataFrame, from_node: str, to_node: str) -> float:
    return float(distance_matrix.loc[from_node, to_node])


def build_baseline_solution(drivers, orders, vehicle_params, distance_matrix):
    vehicle_cost = dict(zip(vehicle_params["vehicle_type"], vehicle_params["cost_vnd_per_km"]))
    vehicle_capacity = dict(zip(vehicle_params["vehicle_type"], vehicle_params["capacity_kg"]))
    order_revenue_lookup = build_order_revenue_lookup(orders, vehicle_params, distance_matrix)

    # Current position of each driver
    driver_state = {}

    for _, driver in drivers.iterrows():
        driver_id = driver["driver_id"]
        vehicle_type = driver["vehicle_type"]

        driver_state[driver_id] = {
            "vehicle_type": vehicle_type,
            "current_node": f"{driver_id}_START",
            "capacity_kg": vehicle_capacity[vehicle_type],
            "cost_per_km": vehicle_cost[vehicle_type],
            "total_distance_km": 0.0,
            "total_cost_vnd": 0.0,
            "total_revenue_vnd": 0.0,
            "current_load_kg": 0.0,
            "step_number": 0,
            "assigned_orders": [],
            "route_nodes": [f"{driver_id}_START"],
        }

    route_records = []
    step_records = []

    # Greedy assignment: process orders one by one
    for _, order in orders.iterrows():
        order_id = order["order_id"]
        required_vehicle = order["required_vehicle"]
        demand_kg = float(order["demand_kg"])

        order_num = str(order_id).replace("O", "").zfill(2)
        pickup_node = f"P{order_num}"
        delivery_node = f"L{order_num}"

        candidate_drivers = [
            driver_id
            for driver_id, state in driver_state.items()
            if state["vehicle_type"] == required_vehicle
            and demand_kg <= state["capacity_kg"]
        ]

        if len(candidate_drivers) == 0:
            route_records.append({
                "order_id": order_id,
                "driver_id": None,
                "vehicle_type": required_vehicle,
                "pickup_node": pickup_node,
                "delivery_node": delivery_node,
                "pickup_step": None,
                "delivery_step": None,
                "distance_to_pickup_km": None,
                "pickup_to_delivery_km": None,
                "order_distance_km": None,
                "order_cost_vnd": None,
                "order_revenue_vnd": None,
                "order_profit_vnd": None,
                "status": "unassigned_no_feasible_vehicle",
            })
            continue

        # Select driver closest to pickup from current position
        best_driver = None
        best_distance_to_pickup = float("inf")

        for driver_id in candidate_drivers:
            current_node = driver_state[driver_id]["current_node"]
            distance_to_pickup = get_distance(distance_matrix, current_node, pickup_node)

            if distance_to_pickup < best_distance_to_pickup:
                best_distance_to_pickup = distance_to_pickup
                best_driver = driver_id

        state = driver_state[best_driver]

        pickup_to_delivery = get_distance(distance_matrix, pickup_node, delivery_node)
        order_distance = best_distance_to_pickup + pickup_to_delivery
        order_cost = order_distance * state["cost_per_km"]
        order_revenue = order_revenue_lookup[order_id]["revenue_vnd"]
        order_profit = order_revenue - order_cost

        pickup_load_before = state["current_load_kg"]
        pickup_load_after = pickup_load_before + demand_kg
        pickup_step = state["step_number"] + 1
        pickup_cost = best_distance_to_pickup * state["cost_per_km"]

        step_records.append({
            "driver_id": best_driver,
            "step": pickup_step,
            "from_node": state["current_node"],
            "to_node": pickup_node,
            "order_id": order_id,
            "action": "pickup",
            "distance_km": round(best_distance_to_pickup, 3),
            "cost_vnd": round(pickup_cost, 0),
            "load_before_kg": round(pickup_load_before, 3),
            "load_after_kg": round(pickup_load_after, 3),
            "capacity_kg": state["capacity_kg"],
        })

        delivery_load_before = pickup_load_after
        delivery_load_after = delivery_load_before - demand_kg
        delivery_step = pickup_step + 1
        delivery_cost = pickup_to_delivery * state["cost_per_km"]

        step_records.append({
            "driver_id": best_driver,
            "step": delivery_step,
            "from_node": pickup_node,
            "to_node": delivery_node,
            "order_id": order_id,
            "action": "delivery",
            "distance_km": round(pickup_to_delivery, 3),
            "cost_vnd": round(delivery_cost, 0),
            "load_before_kg": round(delivery_load_before, 3),
            "load_after_kg": round(delivery_load_after, 3),
            "capacity_kg": state["capacity_kg"],
        })

        # Update driver state
        state["current_node"] = delivery_node
        state["total_distance_km"] += order_distance
        state["total_cost_vnd"] += order_cost
        state["total_revenue_vnd"] += order_revenue
        state["current_load_kg"] = delivery_load_after
        state["step_number"] = delivery_step
        state["assigned_orders"].append(order_id)
        state["route_nodes"].extend([pickup_node, delivery_node])

        route_records.append({
            "order_id": order_id,
            "driver_id": best_driver,
            "vehicle_type": state["vehicle_type"],
            "pickup_node": pickup_node,
            "delivery_node": delivery_node,
            "pickup_step": pickup_step,
            "delivery_step": delivery_step,
            "distance_to_pickup_km": round(best_distance_to_pickup, 3),
            "pickup_to_delivery_km": round(pickup_to_delivery, 3),
            "order_distance_km": round(order_distance, 3),
            "order_cost_vnd": round(order_cost, 0),
            "order_revenue_vnd": round(order_revenue, 0),
            "order_profit_vnd": round(order_profit, 0),
            "status": "assigned",
        })

    # Build summary
    summary_records = []

    for driver_id, state in driver_state.items():
        summary_records.append({
            "driver_id": driver_id,
            "vehicle_type": state["vehicle_type"],
            "num_orders": len(state["assigned_orders"]),
            "assigned_orders": " -> ".join(state["assigned_orders"]),
            "route": " -> ".join(state["route_nodes"]),
            "total_distance_km": round(state["total_distance_km"], 3),
            "total_cost_vnd": round(state["total_cost_vnd"], 0),
            "total_revenue_vnd": round(state["total_revenue_vnd"], 0),
            "net_profit_vnd": round(state["total_revenue_vnd"] - state["total_cost_vnd"], 0),
        })

    routes_df = pd.DataFrame(route_records)
    summary_df = pd.DataFrame(summary_records)
    steps_df = pd.DataFrame(step_records)

    return routes_df, summary_df, steps_df


def main():
    print("Loading data...")
    drivers, orders, vehicle_params, distance_matrix = load_data()

    print(f"Drivers: {len(drivers)}")
    print(f"Orders: {len(orders)}")
    print(f"Distance matrix shape: {distance_matrix.shape}")

    print("\nBuilding baseline solution...")
    routes_df, summary_df, steps_df = build_baseline_solution(
        drivers,
        orders,
        vehicle_params,
        distance_matrix
    )

    os.makedirs(os.path.dirname(ROUTES_OUTPUT_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(SUMMARY_OUTPUT_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(STEPS_OUTPUT_PATH), exist_ok=True)

    routes_df.to_csv(ROUTES_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    summary_df.to_csv(SUMMARY_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    steps_df.to_csv(STEPS_OUTPUT_PATH, index=False, encoding="utf-8-sig")

    total_distance = summary_df["total_distance_km"].sum()
    total_cost = summary_df["total_cost_vnd"].sum()
    total_revenue = summary_df["total_revenue_vnd"].sum()
    net_profit = summary_df["net_profit_vnd"].sum()
    assigned_orders = routes_df[routes_df["status"] == "assigned"].shape[0]
    unassigned_orders = routes_df[routes_df["status"] != "assigned"].shape[0]

    print("\nBaseline completed.")
    print(f"Assigned orders: {assigned_orders}")
    print(f"Unassigned orders: {unassigned_orders}")
    print(f"Total distance: {total_distance:.3f} km")
    print(f"Total cost: {total_cost:,.0f} VND")
    print(f"Total revenue: {total_revenue:,.0f} VND")
    print(f"Net profit: {net_profit:,.0f} VND")

    print(f"\nRoutes saved to: {ROUTES_OUTPUT_PATH}")
    print(f"Summary saved to: {SUMMARY_OUTPUT_PATH}")
    print(f"Route steps saved to: {STEPS_OUTPUT_PATH}")

    print("\nDriver summary:")
    print(summary_df[[
        "driver_id",
        "vehicle_type",
        "num_orders",
        "total_distance_km",
        "total_cost_vnd",
        "total_revenue_vnd",
        "net_profit_vnd",
    ]])


if __name__ == "__main__":
    main()
