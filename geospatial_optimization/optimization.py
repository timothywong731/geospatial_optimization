from typing import List, Dict, Any, Tuple

import numpy as np
import pulp
from shapely.geometry import MultiPolygon
from shapely.ops import unary_union

from .utils import create_fan_polygon, get_grid_points_in_polygon_km

__all__ = ["optimize_sensor_placement", "calculate_placement_metrics"]


def optimize_sensor_placement(
    operational_area: MultiPolygon,
    configurations: List[Dict[str, Any]],
    resolution_km: float = 30,
    max_sensors: int = 99,
    coverage_requirement: float = 0.80,
    encourage_overlapping: float = 0.5,
) -> Tuple[List[Dict[str, Any]], str]:
    """Solve the sensor placement optimization problem.

    Parameters
    ----------
    operational_area:
        Multipolygon describing the boundary in which sensors may be placed.
    configurations:
        List of dictionaries, each defining ``range_km``, ``azimuth_degree`` and
        ``fan_degree`` for a sensor configuration.
    resolution_km:
        Granularity of the grid used when formulating the model.
    max_sensors:
        Maximum number of sensors that may be installed.
    coverage_requirement:
        Proportion of grid points that must be covered by at least one sensor.
    encourage_overlapping:
        Factor between 0 and 1 controlling the preference for overlapping
        coverage.

    Returns
    -------
    placed_sensors_info:
        List of dictionaries describing the chosen sensor locations and
        configurations.
    status:
        Optimization solver status string.
    """
    locations = get_grid_points_in_polygon_km(operational_area, resolution_km)
    num_locations = len(locations)
    num_configs = len(configurations)

    covers = np.zeros((num_locations, num_locations, num_configs))
    for l_idx, l_point in enumerate(locations):
        for j_idx, j_key in enumerate(configurations):
            fan_poly = create_fan_polygon(
                l_point.x,
                l_point.y,
                j_key["range_km"],
                j_key["azimuth_degree"],
                j_key["fan_degree"],
            )
            for i_idx, i_point in enumerate(locations):
                if fan_poly.contains(i_point):
                    covers[i_idx, l_idx, j_idx] = 1

    prob = pulp.LpProblem("Sensor_Placement", pulp.LpMinimize)
    x = pulp.LpVariable.dicts("Place", (range(num_locations), range(num_configs)), cat="Binary")
    y = pulp.LpVariable.dicts("IsCovered", range(num_locations), cat="Binary")
    y_prime = pulp.LpVariable.dicts("CoveredCount", range(num_locations), cat="Integer")

    prob += (
        pulp.lpSum(x[l][j] for l in range(num_locations) for j in range(num_configs))
        - encourage_overlapping * pulp.lpSum(y_prime[i] - 1 for i in range(num_locations)),
        "Objective_func",
    )

    prob += pulp.lpSum(y_prime[i] for i in range(num_locations)) >= encourage_overlapping * pulp.lpSum(
        y[i] for i in range(num_locations)
    )

    for i in range(num_locations):
        prob += y_prime[i] <= 2

    for i in range(num_locations):
        prob += pulp.lpSum(covers[i, l, j] * x[l][j] for l in range(num_locations) for j in range(num_configs)) >= encourage_overlapping * y_prime[i]

    prob += pulp.lpSum(x[l][j] for l in range(num_locations) for j in range(num_configs)) <= max_sensors

    prob += pulp.lpSum(y[i] for i in range(num_locations)) >= coverage_requirement * num_locations

    for i in range(num_locations):
        prob += pulp.lpSum(covers[i, l, j] * x[l][j] for l in range(num_locations) for j in range(num_configs)) >= y[i]

    for l in range(num_locations):
        prob += pulp.lpSum(x[l][j] for j in range(num_configs)) <= 1

    prob.solve()

    placed_sensors_info: List[Dict[str, Any]] = []
    for l in range(num_locations):
        for j in range(num_configs):
            if pulp.value(x[l][j]) == 1:
                loc = locations[l]
                placed_sensors_info.append({"location": loc, "config": configurations[j]})

    status = pulp.LpStatus[prob.status]
    return placed_sensors_info, status


def calculate_placement_metrics(
    operational_area: MultiPolygon,
    placed_sensors_info: List[Dict[str, Any]],
    resolution_km: float = 30,
) -> Tuple[List, Dict[str, float]]:
    """Calculate coverage metrics for a set of placed sensors.

    Parameters
    ----------
    operational_area:
        Multipolygon representing the entire area of interest.
    placed_sensors_info:
        Output from :func:`optimize_sensor_placement` describing sensor
        positions and configurations.
    resolution_km:
        Grid resolution used when estimating coverage percentage.

    Returns
    -------
    placed_sensors_polygons:
        List of polygons representing the coverage area of each sensor.
    metrics:
        Dictionary containing ``estimated_coverage`` and ``area_coverage``.
    """

    placed_sensors_polygons = []
    for sensor in placed_sensors_info:
        loc = sensor["location"]
        cfg = sensor["config"]
        fan = create_fan_polygon(
            loc.x,
            loc.y,
            cfg["range_km"],
            cfg["azimuth_degree"],
            cfg["fan_degree"],
        )
        placed_sensors_polygons.append(fan)

    grid = get_grid_points_in_polygon_km(operational_area, resolution_km)
    covered = 0
    for pt in grid:
        if any(fan.contains(pt) for fan in placed_sensors_polygons):
            covered += 1

    estimated_coverage_perc = (covered / len(grid)) if grid else 0.0

    total_coverage_geom = unary_union(placed_sensors_polygons)
    final_covered_area = operational_area.intersection(total_coverage_geom)
    area_coverage_percentage = final_covered_area.area / operational_area.area

    return placed_sensors_polygons, {
        "estimated_coverage": estimated_coverage_perc,
        "area_coverage": area_coverage_percentage,
    }

