# AeroRoute — Autonomous Drone Delivery Mission Planner

A comprehensive, zero-dependency educational application demonstrating **Graph Algorithms, Dijkstra Shortest Paths, Priority-Aware Scheduling, and Battery-Constrained Tour Optimization** for autonomous drone delivery fleets.

Designed with the **ThoughtStream Design System** — featuring a minimalist, high-contrast visual hierarchy, sharp geometric typography, and an interactive schematic flight map.

---

## 🚀 Quickstart

You can run AeroRoute using either **Node.js** or pure **Python** (no external packages required for either).

### Option A: Using Node.js (Recommended for Web Devs)

```bash
# 1. Install dependencies (zero external packages required)
npm install

# 2. Start the application server
npm start
```
Open **[http://localhost:3000](http://localhost:3000)** in your browser:
- **`index.html`** — Project overview, architecture, and theoretical foundation.
- **`planner.html`** — Full interactive Mission Planner and flight simulator.

---

### Option B: Using Python (Zero Dependencies)

Requires Python 3.10 or later:

```bash
# Start the backend server (default: port 8000 or 8080)
python run.py --port 8080
```
*(On Windows, you can also use `py -3 run.py --port 8080`)*

Open **[http://127.0.0.1:8080](http://127.0.0.1:8080)** in your browser.

---

## 🧪 Running Automated Unit Tests

AeroRoute includes a comprehensive test suite (28 test cases) testing Dijkstra pathfinding, deterministic tie-breaking, battery reserve invariants, safety thresholds, and HTTP API endpoints.

Run tests using either command:

```bash
# Via npm
npm test

# Or directly via Python unittest
python -m unittest discover -s backend -v
```

All 28 tests run in `< 1.0s` with zero external dependencies.

---

## 📦 Project Architecture

```text
ADA/
├── index.html                 # Showcase landing page & algorithm walk-through
├── planner.html               # Interactive Mission Planner & real-time canvas UI
├── styles.css                 # ThoughtStream design system styles & CSS variables
├── app.js                     # Frontend API bridge & Tasklet client logic
├── map.js                     # SVG graph renderer & flight geometry module
├── server.js                  # Node.js static server & API proxy (Port 3000)
├── run.py                     # Python application server entry point (Port 8000/8080)
├── package.json               # Node.js project manifest & npm scripts
├── tasklet.config.json        # Tasklet instant application configuration
├── thoughtstream-DESIGN.md    # Design system specifications & palette tokens
├── .gitignore                 # Standard git ignores (caches, user-data, logs)
│
├── backend/
│   ├── planner.py             # Core routing engine: Dijkstra, Priority Queue, 2-Opt
│   ├── server.py              # Lightweight ThreadingHTTPServer & JSON REST API
│   ├── cli.py                 # CLI interface, atomic scenario persistence & encoding
│   ├── test_planner.py        # 17 Unit tests for graph algorithms & battery physics
│   ├── test_server.py         # 11 Unit tests for HTTP endpoints, validation & security
│   └── README.md              # Backend protocol, API contract & time complexity specs
│
└── releases/
    └── planner-*.pyz          # Standalone zipapp bundle for containerized runtimes
```

---

## 🧠 Algorithms & Mathematical Model

### 1. Weighted Undirected Graph & Dijkstra Shortest Path
- Vertices \(V\) represent delivery locations, waypoints, and the central distribution hub (Warehouse).
- Enabled edges \(E\) represent unobstructed airspace corridors with positive distances in kilometers.
- Dijkstra's algorithm uses a `heapq` binary min-priority queue with predecessor tracking to find optimal shortest paths between any two vertices in \(O((V + E) \log V)\) time.

### 2. Priority-Aware Scheduling & 2-Opt Tour Optimization
Deliveries are tiered by operational priority:
- **Priority 1 (High):** Time-sensitive emergency/medical orders (e.g., Hindu Rao Hospital, Rohini Residences). Always dispatched first.
- **Priority 2 (Normal):** Standard commercial deliveries.
- **Priority 3 (Low / Deferred):** Non-urgent parcels scheduled as energy permits.

To prevent wasteful deadhead backtracking, AeroRoute applies a **2-Opt local search heuristic** that untangles intersecting flight paths into an optimal perimeter circuit.

### 3. Battery Constraints & Reserve Protection
Before dispatching to candidate node \(u\), the planner calculates:
$$\text{Usable Energy (Wh)} = \max\left(0, \text{Capacity (Wh)} \times \frac{\text{Current Charge } \% - \text{Reserve } \%}{100}\right)$$
$$\text{Leg Energy (Wh)} = \text{Distance (km)} \times \text{Consumption Rate (Wh/km)}$$

A delivery stop is committed **only if**:
$$\text{Energy Used to Stop} + \text{Energy to Return to Hub from Stop} \le \text{Usable Energy}$$

If energy is insufficient, the stop is gracefully **deferred** with an explicit reason, preventing stranded drones while protecting the safety reserve.

---

## 🎨 Visual System & Palette Tokens

Built following the **ThoughtStream Design System**:
- **Background:** Warm Alabaster (`#FAF8F4`)
- **Primary / Brand Accent:** Deep Forest Green (`#1F5C4A`)
- **Route Line Gradient:** Sequential progression from light (`#9DB8D9`) to dark navy (`#1F3A5F`) with mid-leg directional arrowheads
- **Return Line:** Distinct dashed sage green (`#5C8A2E`)
- **Battery Health Scale:**
  - `> 50%`: Green (`#4C9A5B`)
  - `20% - 50%`: Amber (`#E0A030`)
  - `< 20%`: Warning Red (`#C8372D`)
- **Contrast & Accessibility:** Fully WCAG 4.5:1 compliant text contrast with sharp geometric (`0px` radius) borders and badges.

---

## 👥 Sharing with Friends / Evaluators

To share this project:
1. Zip the entire `ADA/` folder (or push to a Git repository).
2. Recipients can immediately run:
   - **`npm start`** and visit `http://localhost:3000`
   - or **`python run.py`** and visit `http://localhost:8080`
   - and run tests with **`npm test`** (28/28 passing).
