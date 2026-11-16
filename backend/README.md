# AeroRoute backend

A dependency-free Python 3 backend for the AeroRoute schematic drone planner.

## Run

From the app root:

```sh
python3 backend/cli.py load
python3 backend/cli.py plan BASE64_UTF8_JSON
python3 backend/cli.py save BASE64_UTF8_JSON
python3 backend/server.py --host 127.0.0.1 --port 8000
```

The server exposes `GET /api/health`, `GET /api/scenario`, `POST /api/plan`,
`POST /api/scenario`, and only the app's `index.html`, `styles.css`, `app.js`,
and `map.js` static files. POST requests require `Content-Type: application/json`
and are limited to 1 MiB. Saved data is written atomically to
`user-data/scenario.json` (that file is runtime data and is not source code).

Run tests from this directory:

```sh
python3 -m unittest -v test_planner.py
```

## Input

A scenario is an object with `version: 1`, a string `name`, `nodes`, `edges`,
and `settings`. Nodes have unique IDs, names, schematic `x`/`y` coordinates,
a `kind` (`warehouse`, `delivery`, or `waypoint`), and priority 1 (High), 2
(Normal), or 3 (Low). There must be exactly one warehouse. Edges are unique
undirected pairs with positive distances; disabled edges are unavailable.
Settings are `batteryWh`, `chargePct`, `reservePct`, `consumptionWhKm`,
`speedKmh`, `serviceMinutes`, and boolean `priorityMode`. The validator
rejects non-finite values, booleans in numeric fields, missing references,
invalid ranges, duplicate IDs/pairs, and oversized node/edge collections.

## Algorithm and output

Enabled edges form an undirected graph. Dijkstra's algorithm (`heapq`) finds
shortest paths and complete node-by-node path expansions. The planner starts at
the warehouse and repeatedly chooses among candidates that can reach the
candidate and then return to the warehouse within usable energy. With
`priorityMode`, candidates are selected by `(priority, shortest next-leg
distance, ID)`; otherwise by `(0, distance, ID)`. Infeasible candidates are
skipped so a lower-priority feasible delivery can still be served. A selected
delivery is explicit: merely passing through a delivery node does not deliver
it. The route always includes a return leg when at least one delivery is made.

`usableEnergyWh = max(0, initial charge Wh - reserve Wh)`, with reserve based on
full battery capacity. Service time contributes to duration but intentionally
uses no energy. The baseline is the shortest-path route in original input
ordering, restricted to deliveries actually served by the heuristic; it is a
comparison only and not a globally optimal TSP solution.

Dijkstra from one source costs `O((V+E) log V)`. At most one source is needed
per current/candidate node, so a complete planning run is bounded by
`O(V (V+E) log V)` and uses `O(V²+E)` graph/cache storage (up to V cached shortest-path maps). This is a heuristic,
not a global route optimizer. Coordinates are schematic and do not determine
edge lengths.
