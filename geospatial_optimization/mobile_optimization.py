from __future__ import annotations

"""Utilities for planning routes for mobile sensors."""

from typing import List, Dict

import numpy as np
from shapely.geometry import MultiPolygon, Point

from .helpers import create_fan_polygon, get_grid_points_in_polygon_km



def select_scan_positions(
    operational_area: MultiPolygon,
    sensor_config: Dict,
    resolution_km: float = 20,
    coverage_requirement: float = 0.8,
) -> List[Dict]:
    """Select scan positions that cover the required area.

    This uses a greedy set cover approach over a grid of candidate points.
    Each returned dictionary contains the ``location`` as a :class:`~shapely.geometry.Point`
    and the ``config`` used to create the fan polygon.
    """
    locations = get_grid_points_in_polygon_km(operational_area, resolution_km)
    coverage_points = locations

    candidate_polys = []
    for loc in locations:
        fan_poly = create_fan_polygon(
            loc.x,
            loc.y,
            sensor_config["range_km"],
            sensor_config["azimuth_degree"],
            sensor_config["fan_degree"],
        )
        candidate_polys.append(fan_poly)

    uncovered = set(range(len(coverage_points)))
    selected: List[Dict] = []

    while uncovered and len(uncovered) / len(coverage_points) > 1 - coverage_requirement:
        best_idx = None
        best_cover = set()
        for idx, poly in enumerate(candidate_polys):
            cover_set = {i for i in uncovered if poly.contains(coverage_points[i])}
            if len(cover_set) > len(best_cover):
                best_cover = cover_set
                best_idx = idx
        if not best_cover:
            break
        uncovered -= best_cover
        selected.append({"location": locations[best_idx], "config": sensor_config})
    return selected


def _haversine_dist(pt1: Point, pt2: Point) -> float:
    """Return distance in kilometres between two geographic points."""
    r = 6371  # Earth radius km
    lat1 = np.radians(pt1.y)
    lat2 = np.radians(pt2.y)
    d_lat = lat2 - lat1
    d_lon = np.radians(pt2.x - pt1.x)
    a = np.sin(d_lat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(d_lon / 2) ** 2
    c = 2 * np.arcsin(np.sqrt(a))
    return r * c


def plan_sensor_routes(
    scan_points: List[Dict],
    depot: Point,
    num_sensors: int,
) -> List[List[Point]]:
    """Plan routes for ``num_sensors`` starting and ending at ``depot``.

    The input ``scan_points`` list comes from :func:`select_scan_positions`.
    A mixed integer program is solved with :mod:`pulp` to minimise total travel
    distance while visiting each scan point exactly once.

    Objective
    ---------
    Minimise the sum of travelled distances between consecutive waypoints.

    Constraints
    -----------
    - Each scan point has exactly one incoming and one outgoing arc.
    - Exactly ``num_sensors`` tours leave and return to the depot.
    - Miller--Tucker--Zemlin constraints remove sub-tours.
    """

    import pulp

    points = [depot] + [s["location"] for s in scan_points]
    n = len(points)

    # Pre-compute distances in kilometres
    dist = [[_haversine_dist(points[i], points[j]) for j in range(n)] for i in range(n)]

    prob = pulp.LpProblem("MTSP", pulp.LpMinimize)
    x = pulp.LpVariable.dicts("x", (range(n), range(n)), cat="Binary")
    u = pulp.LpVariable.dicts("u", range(1, n), lowBound=1, upBound=n - 1, cat="Integer")

    # Objective function: sum over arcs of distance * decision
    prob += pulp.lpSum(dist[i][j] * x[i][j] for i in range(n) for j in range(n))

    # Each non-depot node has exactly one incoming and one outgoing arc
    for k in range(1, n):
        prob += pulp.lpSum(x[i][k] for i in range(n)) == 1
        prob += pulp.lpSum(x[k][j] for j in range(n)) == 1

    # Depot has num_sensors outgoing and incoming arcs
    prob += pulp.lpSum(x[0][j] for j in range(1, n)) == num_sensors
    prob += pulp.lpSum(x[i][0] for i in range(1, n)) == num_sensors

    # Prevent self-loops
    for i in range(n):
        prob += x[i][i] == 0

    # MTZ sub-tour elimination
    for i in range(1, n):
        for j in range(1, n):
            if i != j:
                prob += u[i] - u[j] + (n - 1) * x[i][j] <= n - 2

    solver = pulp.PULP_CBC_CMD(gapRel=0.01, timeLimit=60)
    result_status = prob.solve(solver)
    if pulp.LpStatus[result_status] != "Optimal":
        raise RuntimeError("Route optimisation did not converge")

    # Extract tours
    routes: List[List[Point]] = []
    successors = {i: j for i in range(n) for j in range(n) if pulp.value(x[i][j]) == 1}

    for _ in range(num_sensors):
        current = 0
        tour = [depot]
        while True:
            nxt = successors[current]
            if nxt == 0:
                tour.append(depot)
                break
            tour.append(points[nxt])
            current = nxt
        routes.append(tour)

    return routes
