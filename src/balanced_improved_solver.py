import os
import pandas as pd

from routing_economics import build_order_revenue_lookup, sum_order_revenue


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DRIVERS_PATH = os.path.join(BASE_DIR, "data", "drivers.csv")
ORDERS_PATH = os.path.join(BASE_DIR, "data", "orders.csv")
VEHICLE_PARAMS_PATH = os.path.join(BASE_DIR, "data", "vehicle_parameters.csv")
DISTANCE_MATRIX_PATH = os.path.join(BASE_DIR, "data", "distance_matrix.csv")

ROUTES_OUTPUT_PATH = os.path.join(BASE_DIR, "outputs", "routes", "balanced_improved_routes.csv")
SUMMARY_OUTPUT_PATH = os.path.join(BASE_DIR, "outputs", "reports", "balanced_improved_summary.csv")
STEPS_OUTPUT_PATH = os.path.join(BASE_DIR, "outputs", "routes", "balanced_improved_route_steps.csv")

# Higher value = stronger workload balancing
BALANCE_PENALTY = 5.0


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


def create_driver_state(drivers, vehicle_params):
    vehicle_cost = dict(zip(vehicle_params["vehicle_type"], vehicle_params["cost_vnd_per_km"]))
    vehicle_capacity = dict(zip(vehicle_params["vehicle_type"], vehicle_params["capacity_kg"]))

    driver_state = {}

    for _, driver in drivers.iterrows():
        driver_id = driver["driver_id"]
        vehicle_type = driver["vehicle_type"]

        driver_state[driver_id] = {
            "driver_id": driver_id,
            "vehicle_type": vehicle_type,
            "start_node": f"{driver_id}_START",
            "current_node": f"{driver_id}_START",
            "capacity_kg": float(vehicle_capacity[vehicle_type]),
            "cost_per_km": float(vehicle_cost[vehicle_type]),
            "assigned_orders": [],
        }

    return driver_state


def assign_orders_to_drivers_balanced(drivers, orders, vehicle_params, distance_matrix):
    """
    Balanced assignment rule:

    score = distance_to_pickup + BALANCE_PENALTY * num_assigned_orders

    This prevents the solver from assigning too many orders to a single driver.
    """
    driver_state = create_driver_state(drivers, vehicle_params)

    assignment_records = []

    for _, order in orders.iterrows():
        order_id = order["order_id"]
        required_vehicle = order["required_vehicle"]
        demand_kg = float(order["demand_kg"])

        order_num = str(order_id).replace("O", "").zfill(2)
        pickup_node = f"P{order_num}"

        candidate_drivers = []

        for driver_id, state in driver_state.items():
            if state["vehicle_type"] != required_vehicle:
                continue

            if demand_kg > state["capacity_kg"]:
                continue

            distance_to_pickup = get_distance(
                distance_matrix,
                state["current_node"],
                pickup_node
            )

            num_assigned = len(state["assigned_orders"])
            balance_cost = BALANCE_PENALTY * num_assigned
            score = distance_to_pickup + balance_cost

            candidate_drivers.append({
                "driver_id": driver_id,
                "distance_to_pickup": distance_to_pickup,
                "num_assigned_orders": num_assigned,
                "balance_cost": balance_cost,
                "score": score,
            })

        if len(candidate_drivers) == 0:
            assignment_records.append({
                "order_id": order_id,
                "driver_id": None,
                "status": "unassigned_no_feasible_vehicle",
                "assignment_score": None,
                "distance_to_pickup": None,
                "balance_cost": None,
                "num_assigned_before": None,
            })
            continue

        candidate_drivers = sorted(candidate_drivers, key=lambda x: x["score"])
        selected = candidate_drivers[0]
        selected_driver = selected["driver_id"]

        driver_state[selected_driver]["current_node"] = pickup_node
        driver_state[selected_driver]["assigned_orders"].append(order_id)

        assignment_records.append({
            "order_id": order_id,
            "driver_id": selected_driver,
            "status": "assigned",
            "assignment_score": round(selected["score"], 3),
            "distance_to_pickup": round(selected["distance_to_pickup"], 3),
            "balance_cost": round(selected["balance_cost"], 3),
            "num_assigned_before": selected["num_assigned_orders"],
        })

    assignment_df = pd.DataFrame(assignment_records)

    return assignment_df


def build_order_lookup(orders):
    order_lookup = {}

    for _, order in orders.iterrows():
        order_id = order["order_id"]
        order_num = str(order_id).replace("O", "").zfill(2)

        order_lookup[order_id] = {
            "order_id": order_id,
            "pickup_node": f"P{order_num}",
            "delivery_node": f"L{order_num}",
            "demand_kg": float(order["demand_kg"]),
            "required_vehicle": order["required_vehicle"],
        }

    return order_lookup


def get_feasible_next_nodes(order_status, order_lookup, current_load, capacity):
    feasible_nodes = []

    for order_id, status in order_status.items():
        order = order_lookup[order_id]

        if not status["picked"]:
            if current_load + order["demand_kg"] <= capacity:
                feasible_nodes.append({
                    "node_id": order["pickup_node"],
                    "order_id": order_id,
                    "node_type": "pickup",
                    "demand_change": order["demand_kg"],
                })

        elif status["picked"] and not status["delivered"]:
            feasible_nodes.append({
                "node_id": order["delivery_node"],
                "order_id": order_id,
                "node_type": "delivery",
                "demand_change": -order["demand_kg"],
            })

    return feasible_nodes


def optimize_route_for_driver(
    driver_id,
    driver_info,
    assigned_orders,
    order_lookup,
    order_revenue_lookup,
    distance_matrix,
):
    current_node = driver_info["start_node"]
    capacity = driver_info["capacity_kg"]
    cost_per_km = driver_info["cost_per_km"]

    current_load = 0.0
    total_distance = 0.0
    total_cost = 0.0

    route_nodes = [current_node]
    route_steps = []

    order_status = {
        order_id: {
            "picked": False,
            "delivered": False,
        }
        for order_id in assigned_orders
    }

    step_number = 0

    while True:
        all_delivered = all(status["delivered"] for status in order_status.values())

        if all_delivered:
            break

        feasible_nodes = get_feasible_next_nodes(
            order_status=order_status,
            order_lookup=order_lookup,
            current_load=current_load,
            capacity=capacity,
        )

        if len(feasible_nodes) == 0:
            raise RuntimeError(
                f"No feasible next node for {driver_id}. "
                f"Current load={current_load}, capacity={capacity}, "
                f"remaining status={order_status}"
            )

        best_candidate = None
        best_distance = float("inf")

        for candidate in feasible_nodes:
            next_node = candidate["node_id"]
            distance = get_distance(distance_matrix, current_node, next_node)

            if distance < best_distance:
                best_distance = distance
                best_candidate = candidate

        next_node = best_candidate["node_id"]
        order_id = best_candidate["order_id"]
        node_type = best_candidate["node_type"]
        demand_change = best_candidate["demand_change"]

        previous_load = current_load
        current_load += demand_change

        if node_type == "pickup":
            order_status[order_id]["picked"] = True
        elif node_type == "delivery":
            order_status[order_id]["delivered"] = True

        travel_cost = best_distance * cost_per_km
        total_distance += best_distance
        total_cost += travel_cost

        step_number += 1

        route_steps.append({
            "driver_id": driver_id,
            "step": step_number,
            "from_node": current_node,
            "to_node": next_node,
            "order_id": order_id,
            "action": node_type,
            "distance_km": round(best_distance, 3),
            "cost_vnd": round(travel_cost, 0),
            "load_before_kg": round(previous_load, 3),
            "load_after_kg": round(current_load, 3),
            "capacity_kg": capacity,
        })

        route_nodes.append(next_node)
        current_node = next_node

    return {
        "driver_id": driver_id,
        "vehicle_type": driver_info["vehicle_type"],
        "num_orders": len(assigned_orders),
        "assigned_orders": " -> ".join(assigned_orders),
        "route": " -> ".join(route_nodes),
        "total_distance_km": round(total_distance, 3),
        "total_cost_vnd": round(total_cost, 0),
        "total_revenue_vnd": round(sum_order_revenue(assigned_orders, order_revenue_lookup), 0),
        "net_profit_vnd": round(sum_order_revenue(assigned_orders, order_revenue_lookup) - total_cost, 0),
    }, route_steps


def build_balanced_solution(drivers, orders, vehicle_params, distance_matrix):
    driver_state = create_driver_state(drivers, vehicle_params)
    order_lookup = build_order_lookup(orders)
    order_revenue_lookup = build_order_revenue_lookup(orders, vehicle_params, distance_matrix)

    assignment_df = assign_orders_to_drivers_balanced(
        drivers=drivers,
        orders=orders,
        vehicle_params=vehicle_params,
        distance_matrix=distance_matrix,
    )

    assigned = assignment_df[assignment_df["status"] == "assigned"]

    orders_by_driver = {
        driver_id: []
        for driver_id in driver_state.keys()
    }

    for _, row in assigned.iterrows():
        orders_by_driver[row["driver_id"]].append(row["order_id"])

    summary_records = []
    all_step_records = []

    for driver_id, driver_info in driver_state.items():
        assigned_orders = orders_by_driver[driver_id]

        if len(assigned_orders) == 0:
            summary_records.append({
                "driver_id": driver_id,
                "vehicle_type": driver_info["vehicle_type"],
                "num_orders": 0,
                "assigned_orders": "",
                "route": driver_info["start_node"],
                "total_distance_km": 0.0,
                "total_cost_vnd": 0.0,
                "total_revenue_vnd": 0.0,
                "net_profit_vnd": 0.0,
            })
            continue

        summary_record, route_steps = optimize_route_for_driver(
            driver_id=driver_id,
            driver_info=driver_info,
            assigned_orders=assigned_orders,
            order_lookup=order_lookup,
            order_revenue_lookup=order_revenue_lookup,
            distance_matrix=distance_matrix,
        )

        summary_records.append(summary_record)
        all_step_records.extend(route_steps)

    summary_df = pd.DataFrame(summary_records)
    steps_df = pd.DataFrame(all_step_records)

    route_records = []

    for _, row in assignment_df.iterrows():
        order_id = row["order_id"]
        driver_id = row["driver_id"]
        status = row["status"]

        if status != "assigned":
            route_records.append({
                "order_id": order_id,
                "driver_id": None,
                "vehicle_type": None,
                "pickup_node": None,
                "delivery_node": None,
                "pickup_step": None,
                "delivery_step": None,
                "assignment_score": row.get("assignment_score", None),
                "distance_to_pickup": row.get("distance_to_pickup", None),
                "balance_cost": row.get("balance_cost", None),
                "order_revenue_vnd": None,
                "status": status,
            })
            continue

        order = order_lookup[order_id]
        driver_vehicle = driver_state[driver_id]["vehicle_type"]

        pickup_step_df = steps_df[
            (steps_df["driver_id"] == driver_id)
            & (steps_df["order_id"] == order_id)
            & (steps_df["action"] == "pickup")
        ]

        delivery_step_df = steps_df[
            (steps_df["driver_id"] == driver_id)
            & (steps_df["order_id"] == order_id)
            & (steps_df["action"] == "delivery")
        ]

        pickup_step = int(pickup_step_df.iloc[0]["step"]) if len(pickup_step_df) > 0 else None
        delivery_step = int(delivery_step_df.iloc[0]["step"]) if len(delivery_step_df) > 0 else None

        route_records.append({
            "order_id": order_id,
            "driver_id": driver_id,
            "vehicle_type": driver_vehicle,
            "pickup_node": order["pickup_node"],
            "delivery_node": order["delivery_node"],
            "pickup_step": pickup_step,
            "delivery_step": delivery_step,
            "assignment_score": row.get("assignment_score", None),
            "distance_to_pickup": row.get("distance_to_pickup", None),
            "balance_cost": row.get("balance_cost", None),
            "order_revenue_vnd": round(order_revenue_lookup[order_id]["revenue_vnd"], 0),
            "status": status,
        })

    routes_df = pd.DataFrame(route_records)

    return routes_df, summary_df, steps_df


def main():
    print("Loading data...")
    drivers, orders, vehicle_params, distance_matrix = load_data()

    print(f"Drivers: {len(drivers)}")
    print(f"Orders: {len(orders)}")
    print(f"Distance matrix shape: {distance_matrix.shape}")
    print(f"Balance penalty: {BALANCE_PENALTY}")

    print("\nBuilding balanced improved solution...")
    routes_df, summary_df, steps_df = build_balanced_solution(
        drivers=drivers,
        orders=orders,
        vehicle_params=vehicle_params,
        distance_matrix=distance_matrix,
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
    used_drivers = summary_df[summary_df["num_orders"] > 0].shape[0]

    print("\nBalanced improved baseline completed.")
    print(f"Assigned orders: {assigned_orders}")
    print(f"Unassigned orders: {unassigned_orders}")
    print(f"Used drivers: {used_drivers}")
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
