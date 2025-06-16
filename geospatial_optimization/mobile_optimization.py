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
    """Select scan positions that satisfy a coverage threshold.

    A grid of candidate locations is generated over ``operational_area`` and a
    greedy set cover routine chooses a subset whose fan-shaped detection areas
    sweep across at least ``coverage_requirement`` of the region.  The returned
    dictionaries contain the ``location`` as a :class:`~shapely.geometry.Point`
    and the ``config`` describing the sensor orientation and range.
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
    depots: List[Point],
    operational_area: MultiPolygon,
) -> List[List[Point]]:
    """Plan a route for each depot.

    Scan points are first assigned to the nearest depot. A travelling salesman
    problem is then solved with :mod:`pulp` for each depot individually while
    restricting travel to remain inside ``operational_area``.

    Objective
    ---------
    Minimise the total travel distance for each sensor.

    Constraints
    -----------
    - Every assigned scan point has exactly one incoming and one outgoing arc.
    - Routes start and end at the same depot.
    - All path segments lie completely inside ``operational_area``.
    - Miller--Tucker--Zemlin constraints remove sub-tours for each route.
    """

    import pulp
    from shapely.geometry import LineString

    # Assign scan points to the closest depot
    clusters: List[List[Dict]] = [[] for _ in depots]
    for sp in scan_points:
        distances = [_haversine_dist(sp["location"], d) for d in depots]
        clusters[int(np.argmin(distances))].append(sp)

    routes: List[List[Point]] = []

    for depot, assigned in zip(depots, clusters):
        pts = [depot] + [s["location"] for s in assigned]
        n = len(pts)
        if n == 1:
            routes.append([depot, depot])
            continue

        # Pre-compute distances and allowed arcs (within operational area)
        arcs = []
        dist = {}
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                segment = LineString([pts[i], pts[j]])
                if operational_area.contains(segment):
                    arcs.append((i, j))
                    dist[(i, j)] = _haversine_dist(pts[i], pts[j])

        prob = pulp.LpProblem("TSP", pulp.LpMinimize)
        x = pulp.LpVariable.dicts("x", arcs, cat="Binary")
        u = pulp.LpVariable.dicts("u", range(1, n), lowBound=1, upBound=n - 1, cat="Integer")

        # Objective
        prob += pulp.lpSum(dist[i, j] * x[i, j] for i, j in arcs)

        # Degree constraints
        for k in range(1, n):
            prob += pulp.lpSum(x[i, j] for (i, j) in arcs if j == k) == 1
            prob += pulp.lpSum(x[i, j] for (i, j) in arcs if i == k) == 1
        prob += pulp.lpSum(x[0, j] for i, j in arcs if i == 0) == 1
        prob += pulp.lpSum(x[i, 0] for i, j in arcs if j == 0) == 1

        # MTZ sub-tour elimination
        for i in range(1, n):
            for j in range(1, n):
                if i != j and (i, j) in arcs:
                    prob += u[i] - u[j] + (n - 1) * x[i, j] <= n - 2

        solver = pulp.PULP_CBC_CMD(gapRel=0.01, timeLimit=60)
        result_status = prob.solve(solver)
        if pulp.LpStatus[result_status] != "Optimal":
            raise RuntimeError("Route optimisation did not converge")

        # Extract route starting at depot index 0
        succ = {i: j for i, j in arcs if pulp.value(x[i, j]) == 1}
        current = 0
        tour = [depot]
        while True:
            nxt = succ[current]
            if nxt == 0:
                tour.append(depot)
                break
            tour.append(pts[nxt])
            current = nxt
        routes.append(tour)

    return routes
