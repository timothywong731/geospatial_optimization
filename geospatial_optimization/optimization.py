from typing import List, Dict, Tuple
import numpy as np
from shapely.geometry import MultiPolygon
from shapely.ops import unary_union
import pulp

from .helpers import create_fan_polygon, get_grid_points_in_polygon_km


def optimize_sensor_placement(
    operational_area: MultiPolygon,
    configurations: List[Dict],
    resolution_km: float = 30,
    max_sensors: int = 99,
    coverage_requirement: float = 0.8,
    encourage_overlapping: float = 0.0,
) -> Tuple[str, List[Dict]]:
    """Place a subset of sensors optimally.

    Parameters
    ----------
    operational_area : MultiPolygon
        Area of interest in which coverage is required.
    configurations : list[dict]
        Candidate sensor configurations with orientation and range settings.
    resolution_km : float, optional
        Spacing used to sample the operational area.
    max_sensors : int, optional
        Maximum number of sensors that may be placed.
    coverage_requirement : float, optional
        Fraction of sampled points that must be covered. Default value is 0.8 (80%).
    encourage_overlapping : float, optional
        Weight applied to overlapping coverage in the objective. This is a numeric value between 0.0-1.0. 
        A value of 0.0 means no encouragement. For overlapping coverage, and 1.0 means strong encouragement. 

    Returns
    -------
    tuple[str, list[dict]]
        Solver status string and details of placed sensors.
    """
    # Initialize the solver
    # Tolerate a fractional gap of 1% for faster convergence
    # This can be adjusted based on problem size and complexity
    # Allow a maximum of 2 minutes for the solver to run
    solver = pulp.PULP_CBC_CMD(
        gapRel=0.01, 
        timeLimit=120,  # 2 minutes
    )

    locations = get_grid_points_in_polygon_km(operational_area, resolution_km)
    num_locations = len(locations)
    num_configs = len(configurations)

    covers = np.zeros((num_locations, num_locations, num_configs))
    for l_idx, l_point in enumerate(locations):
        for j_idx, config in enumerate(configurations):
            fan_poly = create_fan_polygon(
                l_point.x,
                l_point.y,
                config["range_km"],
                config["azimuth_degree"],
                config["fan_degree"],
            )
            for i_idx, i_point in enumerate(locations):
                if fan_poly.contains(i_point):
                    covers[i_idx, l_idx, j_idx] = 1
                    
    prob = pulp.LpProblem("Sensor_Placement", pulp.LpMinimize)
    x = pulp.LpVariable.dicts("Place", (range(num_locations), range(num_configs)), cat="Binary")
    y = pulp.LpVariable.dicts("IsCovered", range(num_locations), cat="Binary")
    y_prime = pulp.LpVariable.dicts("CoveredCount", range(num_locations), cat="Integer")

    # Objective: Minimize number of sensors placed, encourage overlapping coverage if specified
    prob += pulp.lpSum(x[l][j] for l in range(num_locations) for j in range(num_configs)) \
        - encourage_overlapping * pulp.lpSum(y_prime[i] - 1 for i in range(num_locations))

    # Constraint: Relate overlapping coverage to covered points
    prob += pulp.lpSum(y_prime[i] for i in range(num_locations)) >= encourage_overlapping * pulp.lpSum(
        y[i] for i in range(num_locations)
    )

    # Constraint: Limit overlapping count per location (example: at most 2)
    for i in range(num_locations):
        prob += y_prime[i] <= 2

    # Constraint: y_prime counts how many times location i is covered, scaled by encourage_overlapping
    for i in range(num_locations):
        prob += pulp.lpSum(covers[i, l, j] * x[l][j] for l in range(num_locations) for j in range(num_configs)) >= encourage_overlapping * y_prime[i]

    # Constraint: Do not exceed max_sensors
    prob += pulp.lpSum(x[l][j] for l in range(num_locations) for j in range(num_configs)) <= max_sensors

    # Constraint: Meet minimum coverage requirement
    prob += pulp.lpSum(y[i] for i in range(num_locations)) >= coverage_requirement * num_locations

    # Constraint: y[i] is 1 if location i is covered by any sensor
    for i in range(num_locations):
        prob += pulp.lpSum(covers[i, l, j] * x[l][j] for l in range(num_locations) for j in range(num_configs)) >= y[i]

    # Constraint: At most one sensor per location
    for l in range(num_locations):
        prob += pulp.lpSum(x[l][j] for j in range(num_configs)) <= 1

    prob.solve(solver)

    placed_sensors_info: List[Dict] = []
    for l in range(num_locations):
        for j in range(num_configs):
            if pulp.value(x[l][j]) == 1:
                loc = locations[l]
                placed_sensors_info.append({"location": loc, "config": configurations[j]})

    status = pulp.LpStatus[prob.status]
    return status, placed_sensors_info


def calculate_coverage_info(
    operational_area: MultiPolygon,
    placed_sensors: List[Dict],
    resolution_km: float = 30,
) -> Dict[str, float]:
    """Summarise the quality of a placement.

    Parameters
    ----------
    operational_area : MultiPolygon
        Target region for coverage calculation.
    placed_sensors : list[dict]
        Output from :func:`optimize_sensor_placement`.
    resolution_km : float, optional
        Sampling grid resolution used for estimation.

    Returns
    -------
    dict
        Dictionary containing number of sensors and coverage percentages.
    """
    locations = get_grid_points_in_polygon_km(operational_area, resolution_km)
    placed_polygons = [
        create_fan_polygon(
            s["location"].x,
            s["location"].y,
            s["config"]["range_km"],
            s["config"]["azimuth_degree"],
            s["config"]["fan_degree"],
        )
        for s in placed_sensors
    ]
    covered_count = 0
    for pt in locations:
        if any(poly.contains(pt) for poly in placed_polygons):
            covered_count += 1
    estimated = covered_count / len(locations) if locations else 0.0
    total_coverage_geom = unary_union(placed_polygons) if placed_polygons else None
    area_percent = 0.0
    if total_coverage_geom:
        final_covered_area = operational_area.intersection(total_coverage_geom)
        area_percent = final_covered_area.area / operational_area.area
    return {
        "num_sensors": len(placed_sensors),
        "estimated_coverage_percent": estimated,
        "actual_coverage_percent": area_percent,
    }
