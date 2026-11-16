"""Validation and deterministic battery-constrained route planning for AeroRoute."""
from __future__ import annotations

import heapq
import math
from typing import Any, Mapping


KINDS = {"warehouse", "delivery", "waypoint"}
_EPS = 1e-9


def _fail(message: str) -> None:
    raise ValueError(message)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _finite_number(value: Any, label: str) -> float:
    if not _is_number(value):
        _fail(f"{label} must be a finite number")
    try:
        converted = float(value)
    except (OverflowError, ValueError):
        _fail(f"{label} must be a finite number")
    if not math.isfinite(converted):
        _fail(f"{label} must be a finite number")
    return converted


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    return value


def _required(obj: Mapping[str, Any], key: str, label: str) -> Any:
    if key not in obj:
        _fail(f"{label}.{key} is required")
    return obj[key]


def _string(value: Any, label: str, maximum: int) -> str:
    if not isinstance(value, str):
        _fail(f"{label} must be a string")
    if not value:
        _fail(f"{label} must not be empty")
    if len(value) > maximum:
        _fail(f"{label} exceeds {maximum} characters")
    return value


def _bounded(value: Any, label: str, low: float, high: float) -> float:
    number = _finite_number(value, label)
    if number < low or number > high:
        _fail(f"{label} must be between {low:g} and {high:g}")
    return number


def validate_scenario(scenario: Any) -> dict[str, Any]:
    """Validate a scenario and return it unchanged.

    Validation is intentionally strict so the planner can assume the contract
    after this function returns. Numeric booleans are rejected explicitly.
    """
    root = _object(scenario, "scenario")
    version = _required(root, "version", "scenario")
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        _fail("scenario.version must be 1")
    _string(_required(root, "name", "scenario"), "scenario.name", 80)

    nodes_value = _required(root, "nodes", "scenario")
    edges_value = _required(root, "edges", "scenario")
    settings_value = _required(root, "settings", "scenario")
    if not isinstance(nodes_value, list):
        _fail("scenario.nodes must be an array")
    if not isinstance(edges_value, list):
        _fail("scenario.edges must be an array")
    if len(nodes_value) > 80:
        _fail("scenario.nodes may contain at most 80 nodes")
    if len(edges_value) > 500:
        _fail("scenario.edges may contain at most 500 edges")

    ids: set[str] = set()
    warehouses = []
    for index, raw in enumerate(nodes_value):
        node = _object(raw, f"nodes[{index}]")
        node_id = _string(_required(node, "id", f"nodes[{index}]"), f"nodes[{index}].id", 40)
        if node_id in ids:
            _fail(f"duplicate node id: {node_id}")
        ids.add(node_id)
        _string(_required(node, "name", f"nodes[{index}]"), f"nodes[{index}].name", 80)
        x = _finite_number(_required(node, "x", f"nodes[{index}]"), f"nodes[{index}].x")
        y = _finite_number(_required(node, "y", f"nodes[{index}]"), f"nodes[{index}].y")
        if not 0 <= x <= 10:
            _fail(f"nodes[{index}].x must be between 0 and 10")
        if not 0 <= y <= 7:
            _fail(f"nodes[{index}].y must be between 0 and 7")
        kind = _required(node, "kind", f"nodes[{index}]")
        if not isinstance(kind, str) or kind not in KINDS:
            _fail(f"nodes[{index}].kind must be warehouse, delivery, or waypoint")
        priority = _required(node, "priority", f"nodes[{index}]")
        if isinstance(priority, bool) or not isinstance(priority, int) or priority not in (1, 2, 3):
            _fail(f"nodes[{index}].priority must be 1, 2, or 3")
        if kind == "warehouse":
            warehouses.append(node_id)
    if len(warehouses) != 1:
        _fail("scenario must contain exactly one warehouse")

    edge_ids: set[str] = set()
    pairs: set[frozenset[str]] = set()
    for index, raw in enumerate(edges_value):
        edge = _object(raw, f"edges[{index}]")
        edge_id = _string(_required(edge, "id", f"edges[{index}]"), f"edges[{index}].id", 40)
        if edge_id in edge_ids:
            _fail(f"duplicate edge id: {edge_id}")
        edge_ids.add(edge_id)
        source = _required(edge, "from", f"edges[{index}]")
        target = _required(edge, "to", f"edges[{index}]")
        if not isinstance(source, str) or source not in ids:
            _fail(f"edges[{index}].from must reference a node")
        if not isinstance(target, str) or target not in ids:
            _fail(f"edges[{index}].to must reference a node")
        if source == target:
            _fail(f"edges[{index}] must not be a self edge")
        pair = frozenset((source, target))
        if pair in pairs:
            _fail("duplicate undirected edge pair")
        pairs.add(pair)
        distance = _finite_number(_required(edge, "distance", f"edges[{index}]"), f"edges[{index}].distance")
        if distance <= 0 or distance > 1000:
            _fail(f"edges[{index}].distance must be positive and at most 1000 km")
        enabled = _required(edge, "enabled", f"edges[{index}]")
        if not isinstance(enabled, bool):
            _fail(f"edges[{index}].enabled must be boolean")

    settings = _object(settings_value, "scenario.settings")
    _bounded(_required(settings, "batteryWh", "settings"), "settings.batteryWh", 1, 10000)
    _bounded(_required(settings, "chargePct", "settings"), "settings.chargePct", 0, 100)
    _bounded(_required(settings, "reservePct", "settings"), "settings.reservePct", 0, 100)
    _bounded(_required(settings, "consumptionWhKm", "settings"), "settings.consumptionWhKm", 0.1, 1000)
    _bounded(_required(settings, "speedKmh", "settings"), "settings.speedKmh", 1, 200)
    _bounded(_required(settings, "serviceMinutes", "settings"), "settings.serviceMinutes", 0, 60)
    priority_mode = _required(settings, "priorityMode", "settings")
    if not isinstance(priority_mode, bool):
        _fail("settings.priorityMode must be boolean")
    return root


def dijkstra(adjacency: Mapping[str, Any], start: str) -> tuple[dict[str, float], dict[str, str | None]]:
    """Return shortest distances and predecessor map for an adjacency mapping.

    Adjacency values may be iterables of ``(neighbor, distance)`` pairs. The
    heap's node-ID tie breaker makes equal-distance results deterministic.
    """
    if start not in adjacency:
        return {}, {}
    distances: dict[str, float] = {node: math.inf for node in adjacency}
    previous: dict[str, str | None] = {node: None for node in adjacency}
    distances[start] = 0.0
    queue: list[tuple[float, str]] = [(0.0, start)]
    while queue:
        distance, node = heapq.heappop(queue)
        if distance > distances[node]:
            continue
        neighbors = adjacency.get(node, ())
        for item in neighbors:
            try:
                neighbor, weight = item
            except (TypeError, ValueError):
                _fail("invalid adjacency entry")
            if neighbor not in distances:
                distances[neighbor] = math.inf
                previous[neighbor] = None
            candidate = distance + float(weight)
            old = distances[neighbor]
            # Strict improvement avoids predecessor cycles when a very small
            # positive weight rounds away next to a much larger distance.
            # Sorted adjacency and heap node IDs already make ties deterministic.
            if candidate < old:
                distances[neighbor] = candidate
                previous[neighbor] = node
                heapq.heappush(queue, (candidate, neighbor))
    return distances, previous


def _path(previous: Mapping[str, str | None], start: str, target: str) -> list[str] | None:
    if target == start:
        return [start]
    if target not in previous or previous[target] is None:
        return None
    result: list[str] = []
    current: str | None = target
    while current is not None:
        result.append(current)
        if current == start:
            result.reverse()
            return result
        current = previous.get(current)
    return None


def _graph(scenario: Mapping[str, Any]) -> dict[str, list[tuple[str, float]]]:
    graph = {node["id"]: [] for node in scenario["nodes"]}
    for edge in scenario["edges"]:
        if edge["enabled"]:
            source, target, distance = edge["from"], edge["to"], float(edge["distance"])
            graph[source].append((target, distance))
            graph[target].append((source, distance))
    for neighbors in graph.values():
        neighbors.sort(key=lambda pair: pair[0])
    return graph


def plan(scenario: Any) -> dict[str, Any]:
    """Create a deterministic nearest-neighbor mission satisfying battery limits."""
    scenario = validate_scenario(scenario)
    nodes = scenario["nodes"]
    by_id = {node["id"]: node for node in nodes}
    warehouse = next(node["id"] for node in nodes if node["kind"] == "warehouse")
    deliveries = [node for node in nodes if node["kind"] == "delivery"]
    settings = scenario["settings"]
    battery_wh = float(settings["batteryWh"])
    initial_wh = battery_wh * float(settings["chargePct"]) / 100.0
    reserve_wh = battery_wh * float(settings["reservePct"]) / 100.0
    usable_wh = max(0.0, initial_wh - reserve_wh)
    consumption = float(settings["consumptionWhKm"])
    usable_distance = usable_wh / consumption
    graph = _graph(scenario)

    # Cache shortest paths from each node as they are needed. This remains
    # standard Dijkstra and avoids recomputing a source during a mission.
    cache: dict[str, tuple[dict[str, float], dict[str, str | None]]] = {}

    def shortest(source: str, target: str) -> tuple[float, list[str] | None]:
        if source not in cache:
            cache[source] = dijkstra(graph, source)
        distances, previous = cache[source]
        distance = distances.get(target, math.inf)
        return distance, _path(previous, source, target) if math.isfinite(distance) else None

    current = warehouse
    cumulative = 0.0
    selected: list[str] = []
    route_path = [warehouse]
    legs: list[dict[str, Any]] = []
    pending = {node["id"] for node in deliveries}
    while pending:
        feasible: list[tuple[int, float, str, list[str]]] = []
        for node_id in pending:
            outward, route = shortest(current, node_id)
            back, _ = shortest(node_id, warehouse)
            if route is None or not math.isfinite(back):
                continue
            if (cumulative + outward + back) * consumption <= usable_wh + _EPS:
                key_priority = int(by_id[node_id]["priority"]) if settings["priorityMode"] else 0
                feasible.append((key_priority, outward, node_id, route))
        if not feasible:
            break
        # Python's heap ordering exactly implements (priority, distance, id).
        heapq.heapify(feasible)
        _priority, outward, target, route = heapq.heappop(feasible)
        pending.remove(target)
        cumulative += outward
        route_path.extend(route[1:])
        remaining_pct = (initial_wh - cumulative * consumption) / battery_wh * 100.0
        legs.append({
            "from": current,
            "to": target,
            "path": route,
            "distanceKm": outward,
            "cumulativeDistanceKm": cumulative,
            "batteryRemainingPct": remaining_pct,
            "kind": "delivery",
        })
        selected.append(target)
        current = target

    if selected:
        return_distance, return_path = shortest(current, warehouse)
        # A selected candidate was checked with a return path. This guard keeps
        # output valid if the graph helper is ever changed independently.
        if return_path is not None and math.isfinite(return_distance):
            cumulative += return_distance
            route_path.extend(return_path[1:])
            remaining_pct = (initial_wh - cumulative * consumption) / battery_wh * 100.0
            legs.append({
                "from": current,
                "to": warehouse,
                "path": return_path,
                "distanceKm": return_distance,
                "cumulativeDistanceKm": cumulative,
                "batteryRemainingPct": remaining_pct,
                "kind": "return",
            })

    delivered_ids = list(selected)
    deferred = []
    for node in deliveries:
        node_id = node["id"]
        if node_id in selected:
            continue
        distance, _ = shortest(warehouse, node_id)
        reason = "Unreachable from warehouse" if not math.isfinite(distance) else "Insufficient battery for delivery and return"
        deferred.append({"id": node_id, "reason": reason})

    if not deliveries:
        status = "empty"
    elif not deferred:
        status = "complete"
    elif selected:
        status = "partial"
    else:
        status = "infeasible"

    # Baseline is the original input-node ordering restricted to deliveries
    # actually served by the heuristic, plus the required return leg.
    baseline_distance: float | None = 0.0
    baseline_current = warehouse
    for node in nodes:
        node_id = node["id"]
        if node_id not in selected:
            continue
        distance, _ = shortest(baseline_current, node_id)
        if not math.isfinite(distance):
            baseline_distance = None
            break
        baseline_distance += distance
        baseline_current = node_id
    if baseline_distance is not None and selected:
        distance, _ = shortest(baseline_current, warehouse)
        baseline_distance = baseline_distance + distance if math.isfinite(distance) else None

    energy = cumulative * consumption
    remaining_pct = (initial_wh - energy) / battery_wh * 100.0
    result = {
        "status": status,
        "order": [warehouse, *selected, warehouse] if selected else [warehouse],
        "path": route_path,
        "legs": legs,
        "distanceKm": cumulative,
        "durationMinutes": cumulative / float(settings["speedKmh"]) * 60.0 + len(selected) * float(settings["serviceMinutes"]),
        "energyWh": energy,
        "remainingBatteryPct": remaining_pct,
        "usableEnergyWh": usable_wh,
        "batterySafe": initial_wh - energy >= reserve_wh - _EPS,
        "deliveredIds": delivered_ids,
        "deferred": deferred,
        "baselineDistanceKm": baseline_distance,
        "algorithm": "Dijkstra shortest paths with priority-aware nearest-neighbor selection",
    }
    return result
