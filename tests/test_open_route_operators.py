import random
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import alns_pdvrp_solver as alns


class OpenRouteOperatorTests(unittest.TestCase):
    def setUp(self):
        self.orders = {
            "O01": {"pickup_node": "P01", "delivery_node": "L01", "demand_kg": 2.0,
                    "required_vehicle": "bike"},
            "O02": {"pickup_node": "P02", "delivery_node": "L02", "demand_kg": 2.0,
                    "required_vehicle": "bike"},
        }
        self.drivers = {
            "D1": {"driver_id": "D1", "start_node": "D1_START", "vehicle_type": "bike",
                   "capacity_kg": 10.0, "cost_per_km": 1.0},
            "D2": {"driver_id": "D2", "start_node": "D2_START", "vehicle_type": "bike",
                   "capacity_kg": 10.0, "cost_per_km": 1.0},
        }
        nodes = ["D1_START", "D2_START", "P01", "L01", "P02", "L02"]
        self.distance = pd.DataFrame(1.0, index=nodes, columns=nodes)
        for node in nodes:
            self.distance.loc[node, node] = 0.0

    def test_zero_load_suffix_selects_last_complete_request(self):
        routes = {
            "D1": [("O01", "pickup"), ("O01", "delivery"),
                   ("O02", "pickup"), ("O02", "delivery")],
            "D2": [],
        }
        removed = alns.destroy_tail(
            routes, 2, random.Random(42), order_lookup=self.orders
        )
        self.assertEqual(removed, ["O02"])

    def test_interleaved_route_uses_late_delivery_fallback(self):
        routes = {
            "D1": [("O01", "pickup"), ("O02", "pickup"),
                   ("O01", "delivery"), ("O02", "delivery")],
            "D2": [],
        }
        removed = alns.destroy_tail(
            routes, 1, random.Random(42), order_lookup=self.orders
        )
        self.assertEqual(removed, ["O02"])

    def test_tail_repair_only_appends_pair(self):
        base = [("O01", "pickup"), ("O01", "delivery")]
        routes = {"D1": list(base), "D2": []}
        options = alns.best_insertions_for_order(
            "O02", routes, self.drivers, self.orders, self.distance,
            noise=0.0, rng=random.Random(42), tail_only=True,
        )
        self.assertTrue(options)
        for option in options:
            original = base if option["driver_id"] == "D1" else []
            self.assertEqual(option["sequence"][:len(original)], original)
            self.assertEqual(option["sequence"][-2:], [("O02", "pickup"), ("O02", "delivery")])


if __name__ == "__main__":
    unittest.main()
