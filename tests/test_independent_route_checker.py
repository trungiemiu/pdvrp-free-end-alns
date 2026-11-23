import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from independent_route_checker import Instance, check_solution


class IndependentCheckerTests(unittest.TestCase):
    def setUp(self):
        nodes = ["D1_START", "D2_START", "P01", "L01", "P02", "L02"]
        matrix = pd.DataFrame(0.0, index=nodes, columns=nodes)
        for i, origin in enumerate(nodes):
            for j, destination in enumerate(nodes):
                matrix.loc[origin, destination] = 0.0 if origin == destination else abs(i - j) + 1.0
        self.instance = Instance(
            orders={
                "O01": {"pickup_node": "P01", "delivery_node": "L01", "demand": 4.0,
                         "required_vehicle": "bike"},
                "O02": {"pickup_node": "P02", "delivery_node": "L02", "demand": 7.0,
                         "required_vehicle": "bike"},
            },
            drivers={
                "D1": {"start_node": "D1_START", "vehicle_type": "bike", "capacity": 10.0,
                       "cost_per_km": 2.0},
                "D2": {"start_node": "D2_START", "vehicle_type": "truck", "capacity": 20.0,
                       "cost_per_km": 3.0},
            },
            distance=matrix,
            duration=matrix * 60.0,
        )
        self.valid = {
            "D1": [("O01", "pickup"), ("O01", "delivery"),
                   ("O02", "pickup"), ("O02", "delivery")],
            "D2": [],
        }

    def assertViolation(self, routes, prefix):
        result = check_solution(self.instance, routes)
        self.assertIn(prefix, result["violations"])
        self.assertFalse(result["all_checks_pass"])

    def test_valid_open_route_has_no_return_arc(self):
        result = check_solution(self.instance, self.valid)
        self.assertTrue(result["all_checks_pass"], result["violations"])
        # D1_START->P01->L01->P02->L02; no L02->D1_START term.
        expected_distance = 3.0 + 2.0 + 2.0 + 2.0
        self.assertAlmostEqual(result["recomputed_total_distance_km"], expected_distance)
        self.assertAlmostEqual(result["recomputed_total_cost_vnd"], 2.0 * expected_distance)

    def test_missing_delivery(self):
        routes = {"D1": [("O01", "pickup"), ("O02", "pickup"), ("O02", "delivery")], "D2": []}
        self.assertViolation(routes, "delivery_count:O01:0")

    def test_delivery_before_pickup(self):
        routes = {"D1": [("O01", "delivery"), ("O01", "pickup"),
                         ("O02", "pickup"), ("O02", "delivery")], "D2": []}
        self.assertViolation(routes, "delivery_before_pickup:O01:D1")

    def test_split_request(self):
        routes = {"D1": [("O01", "pickup"), ("O02", "pickup"), ("O02", "delivery")],
                  "D2": [("O01", "delivery")]}
        self.assertViolation(routes, "different_drivers:O01:D1:D2")

    def test_capacity_violation(self):
        routes = {"D1": [("O01", "pickup"), ("O02", "pickup"),
                         ("O01", "delivery"), ("O02", "delivery")], "D2": []}
        self.assertViolation(routes, "capacity:D1:2")

    def test_vehicle_incompatibility(self):
        routes = {"D1": [("O02", "pickup"), ("O02", "delivery")],
                  "D2": [("O01", "pickup"), ("O01", "delivery")]}
        self.assertViolation(routes, "vehicle_incompatible:O01:D2:truck")

    def test_duplicate_pickup(self):
        routes = {"D1": [("O01", "pickup"), ("O01", "pickup"), ("O01", "delivery"),
                         ("O02", "pickup"), ("O02", "delivery")], "D2": []}
        self.assertViolation(routes, "duplicate_pickup:O01:D1")

    def test_false_reported_objective(self):
        result = check_solution(self.instance, self.valid, {"total_cost_vnd": 999.0})
        self.assertTrue(result["feasible"])
        self.assertFalse(result["objectives_match"])
        self.assertIn("objective_mismatch:total_cost_vnd", result["violations"])


if __name__ == "__main__":
    unittest.main()
