from typing import List, Dict, Any
import json
import numpy as np
from shapely.geometry import Polygon, Point, mapping


def create_fan_polygon(center_lon: float, center_lat: float, range_km: float,
                        orientation_deg: float, fan_angle_deg: float) -> Polygon:
    """Return a fan-shaped coverage polygon.

    Parameters
    ----------
    center_lon, center_lat : float
        Sensor location in decimal degrees.
    range_km : float
        Sensor range measured in kilometres.
    orientation_deg : float
        Centre bearing of the fan in degrees clockwise from north.
    fan_angle_deg : float
        Total angle of the fan in degrees.

    Returns
    -------
    Polygon
        ``shapely`` polygon describing the coverage wedge.
    """
    EARTH_RADIUS_KM = 6371
    range_deg = (range_km / EARTH_RADIUS_KM) * (180 / np.pi)
    angles = np.linspace(
        orientation_deg - fan_angle_deg / 2,
        orientation_deg + fan_angle_deg / 2,
        20,
    )
    arc_points = []
    for angle in angles:
        d_lat = range_deg * np.cos(np.radians(angle))
        d_lon = range_deg * np.sin(np.radians(angle)) / np.cos(np.radians(center_lat))
        arc_points.append((center_lon + d_lon, center_lat + d_lat))
    fan_points = [(center_lon, center_lat)] + arc_points
    return Polygon(fan_points)


def get_grid_points_in_polygon_km(polygon: Polygon, resolution_km: float = 10) -> List[Point]:
    """Generate grid points within a polygon.

    Parameters
    ----------
    polygon : Polygon
        Boundary in which to generate candidate points.
    resolution_km : float, optional
        Approximate spacing between grid points.

    Returns
    -------
    list[Point]
        Points evenly spaced across ``polygon`` in geographic coordinates.
    """
    EARTH_RADIUS_KM = 6371
    min_lon, min_lat, max_lon, max_lat = polygon.bounds
    grid_points: List[Point] = []
    lat_step = (resolution_km / EARTH_RADIUS_KM) * (180 / np.pi)
    current_lat = min_lat
    while current_lat <= max_lat:
        deg_lon_dist_km = (np.pi / 180) * EARTH_RADIUS_KM * np.cos(np.radians(current_lat))
        lon_step = resolution_km / deg_lon_dist_km if deg_lon_dist_km > 0 else max_lon - min_lon + 1
        current_lon = min_lon
        while current_lon <= max_lon:
            point = Point(current_lon, current_lat)
            if polygon.contains(point):
                grid_points.append(point)
            current_lon += lon_step
        current_lat += lat_step
    return grid_points


def export_to_geojson(filename: str, op_area: Polygon, placed_sensors: List[Dict[str, Any]]) -> None:
    """Write placement results as a GeoJSON file.

    Parameters
    ----------
    filename : str
        Output file path.
    op_area : Polygon
        Overall operational area.
    placed_sensors : list[dict]
        Sensor placements returned by :func:`optimize_sensor_placement`.
    """
    features = []
    features.append({
        "type": "Feature",
        "geometry": mapping(op_area),
        "properties": {"name": "Operational Area", "type": "boundary"},
    })
    for i, sensor in enumerate(placed_sensors):
        loc = sensor["location"]
        fan_poly = create_fan_polygon(
            center_lon=loc.x,
            center_lat=loc.y,
            range_km=sensor["config"]["range_km"],
            orientation_deg=sensor["config"]["azimuth_degree"],
            fan_angle_deg=sensor["config"]["fan_degree"],
        )
        features.append({
            "type": "Feature",
            "geometry": mapping(loc),
            "properties": {"type": "Sensor Placement", "id": i, "marker-symbol": "circle"},
        })
        features.append({
            "type": "Feature",
            "geometry": mapping(fan_poly),
            "properties": {
                "type": "Coverage Area",
                "sensor_id": i,
                "range_km": sensor["config"]["range_km"],
                "orientation_deg": sensor["config"]["azimuth_degree"],
                "fan_angle_deg": sensor["config"]["fan_degree"],
                "fill": "#FF0000",
                "fill-opacity": 0.5,
            },
        })
    geojson_output = {"type": "FeatureCollection", "features": features}
    with open(filename, "w") as f:
        json.dump(geojson_output, f)
