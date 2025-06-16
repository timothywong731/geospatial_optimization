from __future__ import annotations

"""Utilities for planning routes for mobile sensors."""

from typing import List, Dict, Tuple

import numpy as np
from shapely.geometry import MultiPolygon, Point
from shapely.ops import unary_union

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
    Routes are solved using the OR-Tools vehicle routing solver.
    The returned structure is a list of point sequences for each sensor.
    """
    try:
        from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    except Exception as exc:  # pragma: no cover - import failure
        raise RuntimeError("OR-Tools is required for route planning") from exc

    all_points = [depot] + [s["location"] for s in scan_points]
    size = len(all_points)
    dist_matrix = np.zeros((size, size))
    for i in range(size):
        for j in range(size):
            if i == j:
                dist = 0
            else:
                dist = _haversine_dist(all_points[i], all_points[j])
            dist_matrix[i, j] = int(dist * 1000)  # metres as integer

    manager = pywrapcp.RoutingIndexManager(size, num_sensors, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index: int, to_index: int) -> int:
        return int(dist_matrix[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)])

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    for node in range(1, size):
        routing.AddDisjunction([manager.NodeToIndex(node)], 100000)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_parameters.time_limit.seconds = 10

    solution = routing.SolveWithParameters(search_parameters)
    if solution is None:
        raise RuntimeError("No route found")

    routes: List[List[Point]] = []
    for v in range(num_sensors):
        index = routing.Start(v)
        tour: List[Point] = []
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            tour.append(all_points[node])
            index = solution.Value(routing.NextVar(index))
        tour.append(depot)
        routes.append(tour)
    return routes
