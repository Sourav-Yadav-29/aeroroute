"""Standard-library tests for the AeroRoute planner and validation contract."""
from __future__ import annotations

import copy
import json
import math
import random
import subprocess
import sys
import unittest
from pathlib import Path

from planner import dijkstra, plan, validate_scenario


ROOT = Path(__file__).resolve().parent


def scenario(nodes, edges, **settings):
    defaults = {
        "batteryWh": 100,
        "chargePct": 100,
        "reservePct": 0,
        "consumptionWhKm": 1,
        "speedKmh": 60,
        "serviceMinutes": 10,
        "priorityMode": True,
    }
    defaults.update(settings)
    return {"version": 1, "name": "Test mission", "nodes": nodes, "edges": edges, "settings": defaults}


def node(node_id, kind="delivery", x=1, y=1, priority=2):
    return {"id": node_id, "name": node_id.upper(), "x": x, "y": y, "kind": kind, "priority": priority}


def edge(edge_id, source, target, distance, enabled=True):
    return {"id": edge_id, "from": source, "to": target, "distance": distance, "enabled": enabled}


class PlannerTests(unittest.TestCase):
    def test_dijkstra_prefers_short_graph_path_over_direct(self):
        graph = {"w": [("a", 2), ("b", 10)], "a": [("w", 2), ("b", 2)], "b": [("w", 10), ("a", 2)]}
        distances, previous = dijkstra(graph, "w")
        self.assertEqual(distances["b"], 4)
        self.assertEqual(previous["b"], "a")

    def test_priority_ordering_and_shortest_paths(self):
        s = scenario(
            [node("w", "warehouse", 0, 0), node("low", priority=3), node("high", priority=1, x=2)],
            [edge("wa", "w", "low", 1), edge("wh", "w", "high", 2)],
        )
        self.assertEqual(plan(s)["deliveredIds"], ["high", "low"])
        s["settings"]["priorityMode"] = False
        self.assertEqual(plan(s)["deliveredIds"], ["low", "high"])

    def test_infeasible_high_priority_does_not_block_lower(self):
        s = scenario(
            [node("w", "warehouse", 0, 0), node("high", priority=1), node("low", priority=3, x=0.5)],
            [edge("wh", "w", "high", 60), edge("wl", "w", "low", 1)],
            batteryWh=10,
        )
        result = plan(s)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["deliveredIds"], ["low"])
        self.assertEqual(result["deferred"], [{"id": "high", "reason": "Insufficient battery for delivery and return"}])

    def test_unreachable_is_deferred(self):
        s = scenario([node("w", "warehouse", 0, 0), node("d")], [])
        result = plan(s)
        self.assertEqual(result["status"], "infeasible")
        self.assertEqual(result["deferred"][0]["reason"], "Unreachable from warehouse")
        self.assertEqual(result["baselineDistanceKm"], 0)

    def test_exact_capacity_includes_return(self):
        s = scenario([node("w", "warehouse", 0, 0), node("d")], [edge("e", "w", "d", 5)], batteryWh=10)
        result = plan(s)
        self.assertEqual(result["status"], "complete")
        self.assertAlmostEqual(result["distanceKm"], 10)
        self.assertAlmostEqual(result["remainingBatteryPct"], 0)

    def test_charge_and_reserve_use_full_capacity_reserve(self):
        s = scenario(
            [node("w", "warehouse", 0, 0), node("d")],
            [edge("e", "w", "d", 3)],
            batteryWh=10,
            chargePct=80,
            reservePct=20,
        )
        result = plan(s)
        self.assertEqual(result["status"], "complete")
        self.assertAlmostEqual(result["usableEnergyWh"], 6)
        self.assertAlmostEqual(result["remainingBatteryPct"], 20)
        self.assertTrue(result["batterySafe"])

    def test_charge_below_reserve_has_no_flights_and_is_unsafe(self):
        s = scenario([node("w", "warehouse", 0, 0), node("d")], [edge("e", "w", "d", 1)], chargePct=10, reservePct=20)
        result = plan(s)
        self.assertEqual(result["status"], "infeasible")
        self.assertEqual(result["order"], ["w"])
        self.assertFalse(result["batterySafe"])

    def test_empty_mission(self):
        result = plan(scenario([node("w", "warehouse", 0, 0)], []))
        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["order"], ["w"])
        self.assertEqual(result["path"], ["w"])
        self.assertEqual(result["legs"], [])
        self.assertEqual(result["distanceKm"], 0)
        self.assertEqual(result["baselineDistanceKm"], 0)

    def test_waypoint_is_not_implicitly_delivered(self):
        s = scenario(
            [node("w", "warehouse", 0, 0), node("p", "waypoint"), node("d")],
            [edge("wp", "w", "p", 1), edge("pd", "p", "d", 1)],
        )
        result = plan(s)
        self.assertEqual(result["deliveredIds"], ["d"])
        self.assertEqual(result["path"], ["w", "p", "d", "p", "w"])

    def test_baseline_uses_original_input_order_of_delivered_subset(self):
        s = scenario(
            [node("w", "warehouse", 0, 0), node("b", x=2), node("a", x=1)],
            [edge("wa", "w", "a", 1), edge("ab", "a", "b", 1)],
        )
        result = plan(s)
        self.assertEqual(result["deliveredIds"], ["a", "b"])
        self.assertAlmostEqual(result["baselineDistanceKm"], 4)

    def test_deterministic_id_tie_break(self):
        s = scenario(
            [node("w", "warehouse", 0, 0), node("z", x=1), node("a", x=1)],
            [edge("wz", "w", "z", 1), edge("wa", "w", "a", 1)],
            priorityMode=False,
        )
        self.assertEqual(plan(s)["deliveredIds"], ["a", "z"])

    def test_disabled_edges_unavailable(self):
        s = scenario([node("w", "warehouse", 0, 0), node("d")], [edge("e", "w", "d", 1, False)])
        self.assertEqual(plan(s)["status"], "infeasible")

    def test_validation_rejects_bad_values(self):
        base = scenario([node("w", "warehouse", 0, 0), node("d")], [edge("e", "w", "d", 1)])
        cases = []
        for mutate in (
            lambda x: x["nodes"].append(node("w")),
            lambda x: x["edges"].append(edge("e2", "w", "d", 1)),
            lambda x: x["edges"].__getitem__(0).__setitem__("distance", -1),
            lambda x: x["settings"].__setitem__("batteryWh", True),
            lambda x: x["settings"].__setitem__("speedKmh", 0),
            lambda x: x["nodes"].__getitem__(1).__setitem__("x", float("nan")),
            lambda x: x.__setitem__("name", 12),
        ):
            value = copy.deepcopy(base)
            mutate(value)
            cases.append(value)
        for value in cases:
            with self.assertRaises(ValueError):
                validate_scenario(value)

    def test_validation_rejects_missing_or_wrong_types(self):
        base = scenario([node("w", "warehouse", 0, 0), node("d")], [edge("e", "w", "d", 1)])
        for key in ("version", "name", "nodes", "edges", "settings"):
            value = copy.deepcopy(base)
            del value[key]
            with self.assertRaises(ValueError):
                validate_scenario(value)
        value = copy.deepcopy(base)
        value["settings"]["priorityMode"] = 1
        with self.assertRaises(ValueError):
            validate_scenario(value)

    def test_all_numeric_ranges(self):
        base = scenario([node("w", "warehouse", 0, 0), node("d")], [edge("e", "w", "d", 1)])
        for key, bad in (("batteryWh", 0), ("chargePct", 101), ("reservePct", -1), ("consumptionWhKm", 0), ("speedKmh", 201), ("serviceMinutes", 61)):
            value = copy.deepcopy(base)
            value["settings"][key] = bad
            with self.assertRaises(ValueError):
                validate_scenario(value)

    def test_seeded_random_route_invariants(self):
        rng = random.Random(20260909)
        for trial in range(20):
            nodes = [node("w", "warehouse", 0, 0)]
            for index in range(1, 6):
                nodes.append(node(f"d{index}", x=round(rng.uniform(0, 10), 3), y=round(rng.uniform(0, 7), 3), priority=rng.randint(1, 3)))
            edges = [edge(f"e{i}", nodes[i]["id"], nodes[i + 1]["id"], round(rng.uniform(0.1, 5), 3)) for i in range(5)]
            result = plan(scenario(nodes, edges, batteryWh=10000, priorityMode=bool(trial % 2)))
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["path"][0], "w")
            self.assertEqual(result["path"][-1], "w")
            self.assertEqual(len(result["deliveredIds"]), 5)
            self.assertEqual(len(result["legs"]), 6)
            for leg in result["legs"]:
                self.assertEqual(leg["path"][0], leg["from"])
                self.assertEqual(leg["path"][-1], leg["to"])
                self.assertGreater(leg["distanceKm"], 0)

    def test_cli_plan_and_save_load(self):
        value = scenario([node("w", "warehouse", 0, 0)], [])
        encoded = __import__("base64").b64encode(json.dumps(value).encode()).decode()
        result = subprocess.run([sys.executable, str(ROOT / "cli.py"), "plan", encoded], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "empty")


if __name__ == "__main__":
    unittest.main()
