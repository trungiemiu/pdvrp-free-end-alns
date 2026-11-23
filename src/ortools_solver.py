import os
import pandas as pd
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from routing_economics import build_order_revenue_lookup, sum_order_revenue


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DRIVERS_PATH = os.path.join(BASE_DIR, "data", "drivers.csv")
ORDERS_PATH = os.path.join(BASE_DIR, "data", "orders.csv")
VEHICLE_PARAMS_PATH = os.path.join(BASE_DIR, "data", "vehicle_parameters.csv")
NODES_PATH = os.path.join(BASE_DIR, "data", "nodes_geocoded.csv")
DISTANCE_MATRIX_PATH = os.path.join(BASE_DIR, "data", "distance_matrix.csv")

ROUTES_OUTPUT_PATH = os.path.join(BASE_DIR, "outputs", "routes", "ortools_routes.csv")
STEPS_OUTPUT_PATH = os.path.join(BASE_DIR, "outputs", "routes", "ortools_route_steps.csv")
SUMMARY_OUTPUT_PATH = os.path.join(BASE_DIR, "outputs", "reports", "ortools_summary.csv")


def normalize_vehicle_type(value: str) -> str:
    value = str(value).strip().lower()
    value = value.replace("-", "_").replace(" ", "_")
    return value


def load_data():
    drivers = pd.read_csv(DRIVERS_PATH)
    orders = pd.read_csv(ORDERS_PATH)
    vehicle_params = pd.read_csv(VEHICLE_PARAMS_PATH)
    nodes = pd.read_csv(NODES_PATH)
    distance_matrix = pd.read_csv(DISTANCE_MATRIX_PATH, index_col=0)

    drivers["vehicle_type"] = drivers["vehicle_type"].apply(normalize_vehicle_type)
    orders["required_vehicle"] = orders["required_vehicle"].apply(normalize_vehicle_type)
    vehicle_params["vehicle_type"] = vehicle_params["vehicle_type"].apply(normalize_vehicle_type)

    return drivers, orders, vehicle_params, nodes, distance_matrix


def build_node_index(nodes):
    node_ids = nodes["node_id"].tolist()
    node_to_index = {node_id: idx for idx, node_id in enumerate(node_ids)}
    index_to_node = {idx: node_id for node_id, idx in node_to_index.items()}
    return node_ids, node_to_index, index_to_node


def build_order_lookup(orders):
    order_lookup = {}

    for _, row in orders.iterrows():
        order_id = row["order_id"]
        order_num = str(order_id).replace("O", "").zfill(2)

        order_lookup[order_id] = {
            "order_id": order_id,
            "pickup_node": f"P{order_num}",
            "delivery_node": f"L{order_num}",
            "demand_kg": int(row["demand_kg"]),
            "required_vehicle": row["required_vehicle"],
        }

    return order_lookup


def build_vehicle_lookup(drivers, vehicle_params):
    cost_lookup = dict(zip(vehicle_params["vehicle_type"], vehicle_params["cost_vnd_per_km"]))
    capacity_lookup = dict(zip(vehicle_params["vehicle_type"], vehicle_params["capacity_kg"]))

    vehicle_lookup = {}

    for vehicle_id, row in drivers.reset_index(drop=True).iterrows():
        driver_id = row["driver_id"]
        vehicle_type = row["vehicle_type"]

        vehicle_lookup[vehicle_id] = {
            "vehicle_id": vehicle_id,
            "driver_id": driver_id,
            "vehicle_type": vehicle_type,
            "start_node": f"{driver_id}_START",
            "capacity_kg": int(capacity_lookup[vehicle_type]),
            "cost_per_km": float(cost_lookup[vehicle_type]),
        }

    return vehicle_lookup


def build_augmented_distance_matrix(node_ids, distance_matrix, num_vehicles):
    """
    OR-Tools needs an explicit end node for each vehicle if we want open routes.

    We create dummy end nodes:
        END_D01, END_D02, ...

    Distance from any real node to any dummy end node = 0.
    This allows a vehicle to finish at its last visited real node without paying
    return-to-depot cost.

    Dummy nodes are only used internally and are not written into final routes.
    """
    real_n = len(node_ids)
    total_n = real_n + num_vehicles

    augmented = [[0.0 for _ in range(total_n)] for _ in range(total_n)]

    # Real node to real node distances
    for i, from_node in enumerate(node_ids):
        for j, to_node in enumerate(node_ids):
            augmented[i][j] = float(distance_matrix.loc[from_node, to_node])

    # Real node to dummy end = 0
    # Dummy to any node = 0, not practically used because dummy is end.
    return augmented


def build_demand_vector(node_ids, orders):
    demand = {node_id: 0 for node_id in node_ids}

    for _, row in orders.iterrows():
        order_id = row["order_id"]
        order_num = str(order_id).replace("O", "").zfill(2)
        q = int(row["demand_kg"])

        pickup_node = f"P{order_num}"
        delivery_node = f"L{order_num}"

        demand[pickup_node] = q
        demand[delivery_node] = -q

    return [demand[node_id] for node_id in node_ids]


def create_routing_model(
    drivers,
    orders,
    vehicle_params,
    nodes,
    distance_matrix,
):
    node_ids, node_to_index, index_to_node = build_node_index(nodes)
    order_lookup = build_order_lookup(orders)
    vehicle_lookup = build_vehicle_lookup(drivers, vehicle_params)
    order_revenue_lookup = build_order_revenue_lookup(orders, vehicle_params, distance_matrix)

    num_vehicles = len(vehicle_lookup)
    real_node_count = len(node_ids)

    # Add one dummy end node per vehicle
    augmented_distance = build_augmented_distance_matrix(
        node_ids=node_ids,
        distance_matrix=distance_matrix,
        num_vehicles=num_vehicles,
    )

    starts = []
    ends = []

    for vehicle_id, vehicle in vehicle_lookup.items():
        starts.append(node_to_index[vehicle["start_node"]])
        ends.append(real_node_count + vehicle_id)

    manager = pywrapcp.RoutingIndexManager(
        real_node_count + num_vehicles,
        num_vehicles,
        starts,
        ends,
    )

    routing = pywrapcp.RoutingModel(manager)

    # -------------------------
    # Cost callbacks by vehicle
    # -------------------------
    transit_callback_indices = {}

    for vehicle_id, vehicle in vehicle_lookup.items():
        cost_per_km = vehicle["cost_per_km"]

        def cost_callback(from_index, to_index, cost_per_km=cost_per_km):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)

            distance_km = augmented_distance[from_node][to_node]
            cost_vnd = distance_km * cost_per_km

            return int(round(cost_vnd))

        callback_index = routing.RegisterTransitCallback(cost_callback)
        transit_callback_indices[vehicle_id] = callback_index
        routing.SetArcCostEvaluatorOfVehicle(callback_index, vehicle_id)

    # -------------------------
    # Distance dimension
    # Used for pickup-before-delivery precedence.
    # -------------------------
    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)

        distance_km = augmented_distance[from_node][to_node]
        distance_meters = int(round(distance_km * 1000))

        return distance_meters

    distance_callback_index = routing.RegisterTransitCallback(distance_callback)

    routing.AddDimension(
        distance_callback_index,
        0,
        1_000_000_000,
        True,
        "Distance",
    )

    distance_dimension = routing.GetDimensionOrDie("Distance")

    # -------------------------
    # Capacity dimension
    # -------------------------
    real_demands = build_demand_vector(node_ids, orders)

    # Dummy end nodes have zero demand.
    demands = real_demands + [0] * num_vehicles

    def demand_callback(from_index):
        from_node = manager.IndexToNode(from_index)
        return int(demands[from_node])

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)

    vehicle_capacities = [
        int(vehicle_lookup[v]["capacity_kg"])
        for v in range(num_vehicles)
    ]

    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,
        vehicle_capacities,
        True,
        "Capacity",
    )

    # -------------------------
    # Pickup and delivery constraints
    # -------------------------
    for order_id, order in order_lookup.items():
        pickup_node = order["pickup_node"]
        delivery_node = order["delivery_node"]

        pickup_index = manager.NodeToIndex(node_to_index[pickup_node])
        delivery_index = manager.NodeToIndex(node_to_index[delivery_node])

        routing.AddPickupAndDelivery(pickup_index, delivery_index)

        # Same vehicle
        routing.solver().Add(
            routing.VehicleVar(pickup_index) == routing.VehicleVar(delivery_index)
        )

        # Pickup before delivery
        routing.solver().Add(
            distance_dimension.CumulVar(pickup_index)
            <= distance_dimension.CumulVar(delivery_index)
        )

    # -------------------------
    # Vehicle compatibility
    # -------------------------
    for order_id, order in order_lookup.items():
        required_vehicle = order["required_vehicle"]
        pickup_node = order["pickup_node"]
        delivery_node = order["delivery_node"]

        allowed_vehicle_ids = [
            vehicle_id
            for vehicle_id, vehicle in vehicle_lookup.items()
            if vehicle["vehicle_type"] == required_vehicle
        ]

        pickup_index = manager.NodeToIndex(node_to_index[pickup_node])
        delivery_index = manager.NodeToIndex(node_to_index[delivery_node])

        routing.SetAllowedVehiclesForIndex(allowed_vehicle_ids, pickup_index)
        routing.SetAllowedVehiclesForIndex(allowed_vehicle_ids, delivery_index)

    return {
        "routing": routing,
        "manager": manager,
        "distance_dimension": distance_dimension,
        "vehicle_lookup": vehicle_lookup,
        "order_lookup": order_lookup,
        "order_revenue_lookup": order_revenue_lookup,
        "node_ids": node_ids,
        "node_to_index": node_to_index,
        "index_to_node": index_to_node,
        "augmented_distance": augmented_distance,
        "real_node_count": real_node_count,
    }


def solve_model(model_data, time_limit_seconds=60):
    routing = model_data["routing"]

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()

    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    )

    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )

    search_parameters.time_limit.seconds = time_limit_seconds

    search_parameters.log_search = False

    solution = routing.SolveWithParameters(search_parameters)

    return solution


def extract_solution(model_data, solution):
    routing = model_data["routing"]
    manager = model_data["manager"]
    vehicle_lookup = model_data["vehicle_lookup"]
    order_lookup = model_data["order_lookup"]
    order_revenue_lookup = model_data["order_revenue_lookup"]
    node_ids = model_data["node_ids"]
    augmented_distance = model_data["augmented_distance"]
    real_node_count = model_data["real_node_count"]

    capacity_dimension = routing.GetDimensionOrDie("Capacity")

    summary_records = []
    step_records = []

    # Build reverse order lookup by pickup/delivery node
    node_to_order_action = {}

    for order_id, order in order_lookup.items():
        node_to_order_action[order["pickup_node"]] = (order_id, "pickup")
        node_to_order_action[order["delivery_node"]] = (order_id, "delivery")

    for vehicle_id, vehicle in vehicle_lookup.items():
        driver_id = vehicle["driver_id"]
        vehicle_type = vehicle["vehicle_type"]
        cost_per_km = vehicle["cost_per_km"]

        index = routing.Start(vehicle_id)

        route_nodes = []
        assigned_orders = set()

        total_distance = 0.0
        total_cost = 0.0

        step = 0

        previous_node_id = None

        while not routing.IsEnd(index):
            node_index = manager.IndexToNode(index)

            if node_index < real_node_count:
                node_id = node_ids[node_index]
                route_nodes.append(node_id)
            else:
                node_id = f"END_{driver_id}"

            next_index = solution.Value(routing.NextVar(index))
            next_node_index = manager.IndexToNode(next_index)

            # If next node is dummy end, the route terminates.
            if next_node_index >= real_node_count:
                break

            next_node_id = node_ids[next_node_index]

            distance_km = augmented_distance[node_index][next_node_index]
            cost_vnd = distance_km * cost_per_km

            load_before = solution.Value(capacity_dimension.CumulVar(index))
            load_after = solution.Value(capacity_dimension.CumulVar(next_index))

            order_id = None
            action = None

            if next_node_id in node_to_order_action:
                order_id, action = node_to_order_action[next_node_id]
                assigned_orders.add(order_id)

            step += 1

            step_records.append({
                "driver_id": driver_id,
                "step": step,
                "from_node": node_id,
                "to_node": next_node_id,
                "order_id": order_id,
                "action": action,
                "distance_km": round(distance_km, 3),
                "cost_vnd": round(cost_vnd, 0),
                "load_before_kg": load_before,
                "load_after_kg": load_after,
                "capacity_kg": vehicle["capacity_kg"],
            })

            total_distance += distance_km
            total_cost += cost_vnd

            index = next_index

        # Remove duplicate order count issue because each order appears twice.
        completed_order_ids = set()

        for node_id in route_nodes:
            if node_id in node_to_order_action:
                order_id, _ = node_to_order_action[node_id]
                completed_order_ids.add(order_id)

        summary_records.append({
            "driver_id": driver_id,
            "vehicle_type": vehicle_type,
            "num_orders": len(completed_order_ids),
            "assigned_orders": " -> ".join(sorted(completed_order_ids)),
            "route": " -> ".join(route_nodes),
            "total_distance_km": round(total_distance, 3),
            "total_cost_vnd": round(total_cost, 0),
            "total_revenue_vnd": round(sum_order_revenue(completed_order_ids, order_revenue_lookup), 0),
            "net_profit_vnd": round(sum_order_revenue(completed_order_ids, order_revenue_lookup) - total_cost, 0),
        })

    summary_df = pd.DataFrame(summary_records)
    steps_df = pd.DataFrame(step_records)

    route_records = []

    for order_id, order in order_lookup.items():
        pickup_node = order["pickup_node"]
        delivery_node = order["delivery_node"]

        pickup_rows = steps_df[
            (steps_df["to_node"] == pickup_node)
            & (steps_df["action"] == "pickup")
        ]

        delivery_rows = steps_df[
            (steps_df["to_node"] == delivery_node)
            & (steps_df["action"] == "delivery")
        ]

        if len(pickup_rows) == 0 or len(delivery_rows) == 0:
            route_records.append({
                "order_id": order_id,
                "driver_id": None,
                "vehicle_type": None,
                "pickup_node": pickup_node,
                "delivery_node": delivery_node,
                "pickup_step": None,
                "delivery_step": None,
                "order_revenue_vnd": None,
                "status": "unassigned_or_incomplete",
            })
            continue

        pickup_row = pickup_rows.iloc[0]
        delivery_row = delivery_rows.iloc[0]

        driver_id = pickup_row["driver_id"]

        vehicle_type = summary_df[summary_df["driver_id"] == driver_id].iloc[0]["vehicle_type"]

        route_records.append({
            "order_id": order_id,
            "driver_id": driver_id,
            "vehicle_type": vehicle_type,
            "pickup_node": pickup_node,
            "delivery_node": delivery_node,
            "pickup_step": int(pickup_row["step"]),
            "delivery_step": int(delivery_row["step"]),
            "order_revenue_vnd": round(order_revenue_lookup[order_id]["revenue_vnd"], 0),
            "status": "assigned",
        })

    routes_df = pd.DataFrame(route_records)

    return routes_df, steps_df, summary_df


def main():
    print("Loading data...")
    drivers, orders, vehicle_params, nodes, distance_matrix = load_data()

    print(f"Drivers: {len(drivers)}")
    print(f"Orders: {len(orders)}")
    print(f"Nodes: {len(nodes)}")
    print(f"Distance matrix shape: {distance_matrix.shape}")

    print("\nCreating OR-Tools routing model...")
    model_data = create_routing_model(
        drivers=drivers,
        orders=orders,
        vehicle_params=vehicle_params,
        nodes=nodes,
        distance_matrix=distance_matrix,
    )

    print("Solving OR-Tools model...")
    solution = solve_model(model_data, time_limit_seconds=60)

    if solution is None:
        print("\nNo solution found by OR-Tools.")
        return

    print("\nSolution found. Extracting results...")

    routes_df, steps_df, summary_df = extract_solution(model_data, solution)

    os.makedirs(os.path.dirname(ROUTES_OUTPUT_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(STEPS_OUTPUT_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(SUMMARY_OUTPUT_PATH), exist_ok=True)

    routes_df.to_csv(ROUTES_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    steps_df.to_csv(STEPS_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    summary_df.to_csv(SUMMARY_OUTPUT_PATH, index=False, encoding="utf-8-sig")

    total_distance = summary_df["total_distance_km"].sum()
    total_cost = summary_df["total_cost_vnd"].sum()
    total_revenue = summary_df["total_revenue_vnd"].sum()
    net_profit = summary_df["net_profit_vnd"].sum()
    assigned_orders = routes_df[routes_df["status"] == "assigned"].shape[0]
    unassigned_orders = routes_df[routes_df["status"] != "assigned"].shape[0]
    used_drivers = summary_df[summary_df["num_orders"] > 0].shape[0]

    print("\nOR-Tools completed.")
    print(f"Assigned orders: {assigned_orders}")
    print(f"Unassigned orders: {unassigned_orders}")
    print(f"Used drivers: {used_drivers}")
    print(f"Total distance: {total_distance:.3f} km")
    print(f"Total cost: {total_cost:,.0f} VND")
    print(f"Total revenue: {total_revenue:,.0f} VND")
    print(f"Net profit: {net_profit:,.0f} VND")

    print(f"\nRoutes saved to: {ROUTES_OUTPUT_PATH}")
    print(f"Route steps saved to: {STEPS_OUTPUT_PATH}")
    print(f"Summary saved to: {SUMMARY_OUTPUT_PATH}")

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
