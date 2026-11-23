def normalize_vehicle_type(value):
    value = str(value).strip().lower()
    value = value.replace("-", "_").replace(" ", "_")
    return value


def build_vehicle_economics(vehicle_params):
    economics = {}

    for _, row in vehicle_params.iterrows():
        vehicle_type = normalize_vehicle_type(row["vehicle_type"])
        economics[vehicle_type] = {
            "revenue_under_30km_vnd": float(row.get("revenue_under_30km_vnd", 0.0)),
            "build_up_revenue_vnd_per_km": float(row.get("build_up_revenue_vnd_per_km", 0.0)),
            "cost_vnd_per_km": float(row.get("cost_vnd_per_km", 0.0)),
        }

    return economics


def calculate_order_revenue(distance_km, vehicle_type, vehicle_economics):
    vehicle_type = normalize_vehicle_type(vehicle_type)

    if vehicle_type not in vehicle_economics:
        return 0.0

    params = vehicle_economics[vehicle_type]
    base_revenue = params["revenue_under_30km_vnd"]
    build_up_rate = params["build_up_revenue_vnd_per_km"]
    extra_distance = max(0.0, float(distance_km) - 30.0)

    return base_revenue + extra_distance * build_up_rate


def order_nodes(order_id):
    order_num = str(order_id).replace("O", "").zfill(2)
    return f"P{order_num}", f"L{order_num}"


def build_order_revenue_lookup(orders, vehicle_params, distance_matrix):
    vehicle_economics = build_vehicle_economics(vehicle_params)
    lookup = {}

    for _, row in orders.iterrows():
        order_id = str(row["order_id"])
        vehicle_type = normalize_vehicle_type(row["required_vehicle"])
        pickup_node, delivery_node = order_nodes(order_id)
        direct_distance = float(distance_matrix.loc[pickup_node, delivery_node])
        revenue = calculate_order_revenue(
            distance_km=direct_distance,
            vehicle_type=vehicle_type,
            vehicle_economics=vehicle_economics,
        )

        lookup[order_id] = {
            "pickup_node": pickup_node,
            "delivery_node": delivery_node,
            "direct_distance_km": direct_distance,
            "revenue_vnd": revenue,
        }

    return lookup


def sum_order_revenue(order_ids, order_revenue_lookup):
    total = 0.0

    for order_id in order_ids:
        total += float(order_revenue_lookup.get(str(order_id), {}).get("revenue_vnd", 0.0))

    return total
