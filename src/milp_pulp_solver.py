import os
import argparse
import pandas as pd
import pulp

from routing_economics import build_order_revenue_lookup, sum_order_revenue


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DRIVERS_PATH = os.path.join(BASE_DIR, "data", "drivers.csv")
ORDERS_PATH = os.path.join(BASE_DIR, "data", "orders.csv")
VEHICLE_PARAMS_PATH = os.path.join(BASE_DIR, "data", "vehicle_parameters.csv")
DISTANCE_MATRIX_PATH = os.path.join(BASE_DIR, "data", "distance_matrix.csv")

ROUTES_OUTPUT_PATH = os.path.join(BASE_DIR, "outputs", "routes", "milp_pulp_routes.csv")
STEPS_OUTPUT_PATH = os.path.join(BASE_DIR, "outputs", "routes", "milp_pulp_route_steps.csv")
SUMMARY_OUTPUT_PATH = os.path.join(BASE_DIR, "outputs", "reports", "milp_pulp_summary.csv")
SOLVER_REPORT_PATH = os.path.join(BASE_DIR, "outputs", "reports", "milp_pulp_solver_report.csv")


def parse_args():
    parser = argparse.ArgumentParser(
        description="MILP/PuLP solver for the full pickup-delivery routing instance."
    )

    parser.add_argument(
        "--time-limit",
        type=int,
        default=None,
        help="Solver time limit in seconds. If omitted, no time limit is imposed."
    )

    parser.add_argument(
        "--solution-limit",
        type=int,
        default=None,
        help=(
            "Optional number of feasible solutions after which CBC should stop. "
            "If omitted, no solution limit is imposed."
        )
    )

    return parser.parse_args()


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

    if len(drivers) == 0:
        raise ValueError("drivers.csv is empty.")

    if len(orders) == 0:
        raise ValueError("orders.csv is empty.")

    print("\nInput data loaded:")
    print(f"Drivers: {len(drivers)}")
    print(f"Orders: {len(orders)}")
    print(f"Vehicle types: {drivers['vehicle_type'].unique().tolist()}")
    print(f"Distance matrix shape: {distance_matrix.shape}")

    return drivers, orders, vehicle_params, distance_matrix


def build_vehicle_info(drivers, vehicle_params):
    cost_lookup = dict(zip(vehicle_params["vehicle_type"], vehicle_params["cost_vnd_per_km"]))
    capacity_lookup = dict(zip(vehicle_params["vehicle_type"], vehicle_params["capacity_kg"]))

    vehicle_info = {}

    for _, row in drivers.iterrows():
        driver_id = row["driver_id"]
        vehicle_type = row["vehicle_type"]

        if vehicle_type not in cost_lookup:
            raise ValueError(f"Missing cost for vehicle type: {vehicle_type}")

        if vehicle_type not in capacity_lookup:
            raise ValueError(f"Missing capacity for vehicle type: {vehicle_type}")

        vehicle_info[driver_id] = {
            "driver_id": driver_id,
            "vehicle_type": vehicle_type,
            "start_node": f"{driver_id}_START",
            "end_node": f"END_{driver_id}",
            "capacity_kg": float(capacity_lookup[vehicle_type]),
            "cost_per_km": float(cost_lookup[vehicle_type]),
        }

    return vehicle_info


def build_order_info(orders):
    order_info = {}

    for _, row in orders.iterrows():
        order_id = row["order_id"]
        order_num = str(order_id).replace("O", "").zfill(2)

        order_info[order_id] = {
            "order_id": order_id,
            "pickup_node": f"P{order_num}",
            "delivery_node": f"L{order_num}",
            "demand_kg": float(row["demand_kg"]),
            "required_vehicle": row["required_vehicle"],
        }

    return order_info


def get_distance(distance_matrix, i, j):
    """
    Open route setting:
    - Traveling to END_driver has zero distance.
    - END_driver is only an artificial terminal node.
    """
    if str(j).startswith("END_"):
        return 0.0

    if str(i).startswith("END_"):
        return 0.0

    return float(distance_matrix.loc[i, j])


def create_solver(time_limit=None, solution_limit=None, log_path=None):
    """
    Build CBC solver command.

    Notes:
    - time_limit=None means no explicit time limit.
    - solution_limit is passed to CBC through the maxSolutions option.
    """
    options = []

    if solution_limit is not None:
        if solution_limit <= 0:
            raise ValueError("--solution-limit must be a positive integer.")

        # CBC option. If your local CBC version does not support it,
        # remove this option or tell me the error log.
        options.append(f"maxSolutions {solution_limit}")

    solver = pulp.PULP_CBC_CMD(
        msg=True,
        timeLimit=time_limit,
        options=options if options else None,
        logPath=log_path,
    )

    return solver


def solve_milp(
    drivers, orders, vehicle_params, distance_matrix,
    time_limit=None, solution_limit=None, log_path=None,
):
    vehicle_info = build_vehicle_info(drivers, vehicle_params)
    order_info = build_order_info(orders)
    order_revenue_lookup = build_order_revenue_lookup(orders, vehicle_params, distance_matrix)

    K = list(vehicle_info.keys())
    O = list(order_info.keys())

    task_nodes = []
    demand = {}

    for o in O:
        p = order_info[o]["pickup_node"]
        d = order_info[o]["delivery_node"]
        q = order_info[o]["demand_kg"]

        task_nodes.extend([p, d])
        demand[p] = q
        demand[d] = -q

    for k in K:
        demand[vehicle_info[k]["start_node"]] = 0
        demand[vehicle_info[k]["end_node"]] = 0

    model = pulp.LpProblem(
        "Full_Heterogeneous_Pickup_Delivery_VRP",
        pulp.LpMinimize
    )

    nodes_by_vehicle = {}
    arcs = []

    for k in K:
        s = vehicle_info[k]["start_node"]
        e = vehicle_info[k]["end_node"]

        nodes_k = [s] + task_nodes + [e]
        nodes_by_vehicle[k] = nodes_k

        for i in nodes_k:
            for j in nodes_k:
                if i == j:
                    continue

                # No outgoing arc from artificial end.
                if i == e:
                    continue

                # No incoming arc to vehicle start.
                if j == s:
                    continue

                arcs.append((k, i, j))

    print("\nMILP size estimate:")
    print(f"Vehicles: {len(K)}")
    print(f"Orders: {len(O)}")
    print(f"Task nodes: {len(task_nodes)}")
    print(f"Vehicle-specific arcs: {len(arcs)}")

    x = pulp.LpVariable.dicts(
        "x",
        arcs,
        lowBound=0,
        upBound=1,
        cat=pulp.LpBinary
    )

    z = pulp.LpVariable.dicts(
        "z",
        [(o, k) for o in O for k in K],
        lowBound=0,
        upBound=1,
        cat=pulp.LpBinary
    )

    M = len(task_nodes) + 2

    u = pulp.LpVariable.dicts(
        "u",
        [(k, n) for k in K for n in nodes_by_vehicle[k]],
        lowBound=0,
        upBound=M,
        cat=pulp.LpContinuous
    )

    load = pulp.LpVariable.dicts(
        "load",
        [(k, n) for k in K for n in nodes_by_vehicle[k]],
        lowBound=0,
        cat=pulp.LpContinuous
    )

    used = pulp.LpVariable.dicts(
        "used",
        K,
        lowBound=0,
        upBound=1,
        cat=pulp.LpBinary
    )

    # Objective: total vehicle-specific travel cost.
    model += pulp.lpSum(
        get_distance(distance_matrix, i, j)
        * vehicle_info[k]["cost_per_km"]
        * x[(k, i, j)]
        for (k, i, j) in arcs
    )

    # 1. Each order is assigned exactly once.
    for o in O:
        model += (
            pulp.lpSum(z[(o, k)] for k in K) == 1
        ), f"assign_once_{o}"

    # 2. Vehicle compatibility.
    for o in O:
        required_vehicle = order_info[o]["required_vehicle"]

        for k in K:
            if vehicle_info[k]["vehicle_type"] != required_vehicle:
                model += (
                    z[(o, k)] == 0
                ), f"vehicle_compat_{o}_{k}"

    # 3. Vehicle start/end constraints.
    for k in K:
        s = vehicle_info[k]["start_node"]
        e = vehicle_info[k]["end_node"]

        model += (
            pulp.lpSum(
                x[(k, s, j)]
                for j in nodes_by_vehicle[k]
                if (k, s, j) in x
            ) == used[k]
        ), f"start_leave_{k}"

        model += (
            pulp.lpSum(
                x[(k, i, e)]
                for i in nodes_by_vehicle[k]
                if (k, i, e) in x
            ) == used[k]
        ), f"end_enter_{k}"

        model += u[(k, s)] == 0, f"start_sequence_{k}"
        model += load[(k, s)] == 0, f"start_load_{k}"
        model += load[(k, e)] == 0, f"end_load_{k}"

    # 4. Pickup and delivery visits if order is assigned to vehicle k.
    for o in O:
        p = order_info[o]["pickup_node"]
        d = order_info[o]["delivery_node"]

        for k in K:
            model += (
                pulp.lpSum(
                    x[(k, p, j)]
                    for j in nodes_by_vehicle[k]
                    if (k, p, j) in x
                ) == z[(o, k)]
            ), f"pickup_out_{o}_{k}"

            model += (
                pulp.lpSum(
                    x[(k, i, p)]
                    for i in nodes_by_vehicle[k]
                    if (k, i, p) in x
                ) == z[(o, k)]
            ), f"pickup_in_{o}_{k}"

            model += (
                pulp.lpSum(
                    x[(k, d, j)]
                    for j in nodes_by_vehicle[k]
                    if (k, d, j) in x
                ) == z[(o, k)]
            ), f"delivery_out_{o}_{k}"

            model += (
                pulp.lpSum(
                    x[(k, i, d)]
                    for i in nodes_by_vehicle[k]
                    if (k, i, d) in x
                ) == z[(o, k)]
            ), f"delivery_in_{o}_{k}"

            model += (
                u[(k, p)] + 1 <= u[(k, d)] + M * (1 - z[(o, k)])
            ), f"pickup_before_delivery_{o}_{k}"

    # 5. Flow conservation for task nodes.
    for k in K:
        for n in task_nodes:
            model += (
                pulp.lpSum(
                    x[(k, i, n)]
                    for i in nodes_by_vehicle[k]
                    if (k, i, n) in x
                )
                ==
                pulp.lpSum(
                    x[(k, n, j)]
                    for j in nodes_by_vehicle[k]
                    if (k, n, j) in x
                )
            ), f"flow_{k}_{n}"

    # 6. Sequencing and load propagation.
    for (k, i, j) in arcs:
        if str(j).startswith("END_"):
            continue

        model += (
            u[(k, j)] >= u[(k, i)] + 1 - M * (1 - x[(k, i, j)])
        ), f"seq_{k}_{i}_{j}"

        qj = demand.get(j, 0)
        Qk = vehicle_info[k]["capacity_kg"]

        model += (
            load[(k, j)] >= load[(k, i)] + qj - Qk * 2 * (1 - x[(k, i, j)])
        ), f"load_lower_{k}_{i}_{j}"

        model += (
            load[(k, j)] <= load[(k, i)] + qj + Qk * 2 * (1 - x[(k, i, j)])
        ), f"load_upper_{k}_{i}_{j}"

    # 7. Capacity bounds.
    for k in K:
        Qk = vehicle_info[k]["capacity_kg"]

        for n in nodes_by_vehicle[k]:
            model += (
                load[(k, n)] <= Qk
            ), f"capacity_{k}_{n}"

    # 8. Link vehicle use to assigned orders.
    for k in K:
        model += (
            pulp.lpSum(z[(o, k)] for o in O) <= len(O) * used[k]
        ), f"used_link_{k}"

    solver = create_solver(
        time_limit=time_limit,
        solution_limit=solution_limit,
        log_path=log_path,
    )

    print("\nSolving MILP with PuLP/CBC...")
    if time_limit is None:
        print("Time limit: None")
    else:
        print(f"Time limit: {time_limit} seconds")

    if solution_limit is None:
        print("Solution limit: None")
    else:
        print(f"Solution limit: {solution_limit}")

    status_code = model.solve(solver)

    status = pulp.LpStatus[status_code]
    objective = pulp.value(model.objective)

    return {
        "model": model,
        "x": x,
        "z": z,
        "u": u,
        "load": load,
        "used": used,
        "vehicle_info": vehicle_info,
        "order_info": order_info,
        "order_revenue_lookup": order_revenue_lookup,
        "task_nodes": task_nodes,
        "nodes_by_vehicle": nodes_by_vehicle,
        "status": status,
        "objective": objective,
        "time_limit": time_limit,
        "solution_limit": solution_limit,
    }


def extract_solution(result, distance_matrix):
    x = result["x"]
    load = result["load"]
    vehicle_info = result["vehicle_info"]
    order_info = result["order_info"]
    order_revenue_lookup = result["order_revenue_lookup"]

    K = list(vehicle_info.keys())
    O = list(order_info.keys())

    node_to_order_action = {}

    for o in O:
        node_to_order_action[order_info[o]["pickup_node"]] = (o, "pickup")
        node_to_order_action[order_info[o]["delivery_node"]] = (o, "delivery")

    summary_records = []
    step_records = []

    for k in K:
        s = vehicle_info[k]["start_node"]
        e = vehicle_info[k]["end_node"]

        current = s
        route_nodes = [s]
        total_distance = 0.0
        total_cost = 0.0
        step = 0

        visited_arcs = set()

        while current != e:
            found_next = None

            for key, var in x.items():
                kk, i, j = key

                if kk != k:
                    continue

                if i != current:
                    continue

                var_value = pulp.value(var)

                if var_value is not None and var_value > 0.5:
                    if (kk, i, j) in visited_arcs:
                        continue

                    found_next = j
                    visited_arcs.add((kk, i, j))
                    break

            if found_next is None:
                break

            if found_next == e:
                break

            distance_km = get_distance(distance_matrix, current, found_next)
            cost_vnd = distance_km * vehicle_info[k]["cost_per_km"]

            step += 1

            order_id = None
            action = None

            if found_next in node_to_order_action:
                order_id, action = node_to_order_action[found_next]

            load_before = pulp.value(load[(k, current)]) if (k, current) in load else 0
            load_after = pulp.value(load[(k, found_next)]) if (k, found_next) in load else 0

            if load_before is None:
                load_before = 0

            if load_after is None:
                load_after = 0

            step_records.append({
                "driver_id": k,
                "step": step,
                "from_node": current,
                "to_node": found_next,
                "order_id": order_id,
                "action": action,
                "distance_km": round(distance_km, 3),
                "cost_vnd": round(cost_vnd, 0),
                "load_before_kg": round(load_before, 3),
                "load_after_kg": round(load_after, 3),
                "capacity_kg": vehicle_info[k]["capacity_kg"],
            })

            route_nodes.append(found_next)
            total_distance += distance_km
            total_cost += cost_vnd
            current = found_next

        completed_orders = set()

        for n in route_nodes:
            if n in node_to_order_action:
                order_id, _ = node_to_order_action[n]
                completed_orders.add(order_id)

        summary_records.append({
            "driver_id": k,
            "vehicle_type": vehicle_info[k]["vehicle_type"],
            "num_orders": len(completed_orders),
            "assigned_orders": " -> ".join(sorted(completed_orders)),
            "route": " -> ".join(route_nodes),
            "total_distance_km": round(total_distance, 3),
            "total_cost_vnd": round(total_cost, 0),
            "total_revenue_vnd": round(sum_order_revenue(completed_orders, order_revenue_lookup), 0),
            "net_profit_vnd": round(sum_order_revenue(completed_orders, order_revenue_lookup) - total_cost, 0),
        })

    steps_df = pd.DataFrame(step_records)
    summary_df = pd.DataFrame(summary_records)

    route_records = []

    for o in O:
        pickup_node = order_info[o]["pickup_node"]
        delivery_node = order_info[o]["delivery_node"]

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
                "order_id": o,
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
        vehicle_type = vehicle_info[driver_id]["vehicle_type"]

        route_records.append({
            "order_id": o,
            "driver_id": driver_id,
            "vehicle_type": vehicle_type,
            "pickup_node": pickup_node,
            "delivery_node": delivery_node,
            "pickup_step": int(pickup_row["step"]),
            "delivery_step": int(delivery_row["step"]),
            "order_revenue_vnd": round(order_revenue_lookup[o]["revenue_vnd"], 0),
            "status": "assigned",
        })

    routes_df = pd.DataFrame(route_records)

    return routes_df, steps_df, summary_df


def save_solver_report(result, routes_df, summary_df):
    total_distance = summary_df["total_distance_km"].sum()
    total_cost = summary_df["total_cost_vnd"].sum()
    total_revenue = summary_df["total_revenue_vnd"].sum()
    net_profit = summary_df["net_profit_vnd"].sum()
    assigned_orders = routes_df[routes_df["status"] == "assigned"].shape[0]
    unassigned_orders = routes_df[routes_df["status"] != "assigned"].shape[0]
    used_drivers = summary_df[summary_df["num_orders"] > 0].shape[0]

    report = pd.DataFrame([{
        "method": "milp_pulp",
        "solver": "PuLP_CBC",
        "status": result["status"],
        "objective_value": result["objective"],
        "time_limit": result["time_limit"],
        "solution_limit": result["solution_limit"],
        "assigned_orders": assigned_orders,
        "unassigned_orders": unassigned_orders,
        "used_drivers": used_drivers,
        "total_distance_km": round(total_distance, 3),
        "total_cost_vnd": round(total_cost, 0),
        "total_revenue_vnd": round(total_revenue, 0),
        "net_profit_vnd": round(net_profit, 0),
    }])

    os.makedirs(os.path.dirname(SOLVER_REPORT_PATH), exist_ok=True)
    report.to_csv(SOLVER_REPORT_PATH, index=False, encoding="utf-8-sig")

    return report


def main():
    args = parse_args()

    print("MILP/PuLP full input-data solver")
    print("--------------------------------")
    if args.time_limit is None:
        print("Input time limit: None")
    else:
        print(f"Input time limit: {args.time_limit} seconds")

    if args.solution_limit is None:
        print("Input solution limit: None")
    else:
        print(f"Input solution limit: {args.solution_limit}")

    drivers, orders, vehicle_params, distance_matrix = load_data()

    result = solve_milp(
        drivers=drivers,
        orders=orders,
        vehicle_params=vehicle_params,
        distance_matrix=distance_matrix,
        time_limit=args.time_limit,
        solution_limit=args.solution_limit,
    )

    print("\nMILP completed.")
    print(f"Solver status: {result['status']}")
    print(f"Objective value: {result['objective']}")

    if result["status"] not in ["Optimal", "Feasible"]:
        print("No feasible solution extracted.")
        solver_report = pd.DataFrame([{
            "method": "milp_pulp",
            "solver": "PuLP_CBC",
            "status": result["status"],
            "objective_value": result["objective"],
            "time_limit": result["time_limit"],
            "solution_limit": result["solution_limit"],
            "assigned_orders": None,
            "unassigned_orders": None,
            "used_drivers": None,
            "total_distance_km": None,
            "total_cost_vnd": None,
            "total_revenue_vnd": None,
            "net_profit_vnd": None,
        }])

        os.makedirs(os.path.dirname(SOLVER_REPORT_PATH), exist_ok=True)
        solver_report.to_csv(SOLVER_REPORT_PATH, index=False, encoding="utf-8-sig")
        print(f"Solver report saved to: {SOLVER_REPORT_PATH}")
        return

    routes_df, steps_df, summary_df = extract_solution(
        result=result,
        distance_matrix=distance_matrix
    )

    os.makedirs(os.path.dirname(ROUTES_OUTPUT_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(STEPS_OUTPUT_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(SUMMARY_OUTPUT_PATH), exist_ok=True)

    routes_df.to_csv(ROUTES_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    steps_df.to_csv(STEPS_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    summary_df.to_csv(SUMMARY_OUTPUT_PATH, index=False, encoding="utf-8-sig")

    solver_report = save_solver_report(result, routes_df, summary_df)

    total_distance = summary_df["total_distance_km"].sum()
    total_cost = summary_df["total_cost_vnd"].sum()
    total_revenue = summary_df["total_revenue_vnd"].sum()
    net_profit = summary_df["net_profit_vnd"].sum()
    assigned_orders = routes_df[routes_df["status"] == "assigned"].shape[0]
    unassigned_orders = routes_df[routes_df["status"] != "assigned"].shape[0]
    used_drivers = summary_df[summary_df["num_orders"] > 0].shape[0]

    print("\nMILP/PuLP solution summary:")
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
    print(f"Solver report saved to: {SOLVER_REPORT_PATH}")

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

    print("\nSolver report:")
    print(solver_report.T)


if __name__ == "__main__":
    main()
