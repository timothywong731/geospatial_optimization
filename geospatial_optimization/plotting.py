from typing import List, Dict
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from shapely.geometry import MultiPolygon
from mpl_toolkits.basemap import Basemap
from mpl_toolkits.basemap import cm
from netCDF4 import Dataset
from shapely.geometry import Polygon
from .helpers import create_fan_polygon


def plot_sensor_map(
    operational_area: MultiPolygon,
    placed_sensors: List[Dict],
    fan_opacity: float = 0.5,
    ax: plt.Axes | None = None,
) -> plt.Axes:
    """Visualise the optimisation outcome on a geographical map.

    Parameters
    ----------
    operational_area : MultiPolygon
        Operational boundary to plot.
    placed_sensors : list[dict]
        Sensors returned by the optimisation routine.
    fan_opacity : float, optional
        Transparency applied to each sensor's coverage wedge.
    ax : matplotlib.axes.Axes, optional
        Existing axes to draw on.  If ``None`` a new figure is created.

    Returns
    -------
    matplotlib.axes.Axes
        Axes containing the completed plot.
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=(10, 7))
    # Determine plot bounds
    min_px = min(min(poly.exterior.xy[0]) for poly in operational_area.geoms)
    min_py = min(min(poly.exterior.xy[1]) for poly in operational_area.geoms)
    max_px = max(max(poly.exterior.xy[0]) for poly in operational_area.geoms)
    max_py = max(max(poly.exterior.xy[1]) for poly in operational_area.geoms)

    plot_margin = 3

    m = Basemap(
        projection="merc",
        llcrnrlon=min_px - plot_margin,
        urcrnrlon=max_px + plot_margin,
        llcrnrlat=min_py - plot_margin,
        urcrnrlat=max_py + plot_margin,
        resolution="i",
        ax=ax,
    )

    # Get topography for nice background
    url = "http://ferret.pmel.noaa.gov/thredds/dodsC/data/PMEL/etopo5.nc"
    etopodata = Dataset(url)
    topoin = etopodata.variables["ROSE"][:]
    lons = etopodata.variables["ETOPO05_X"][:]
    lats = etopodata.variables["ETOPO05_Y"][:]
    topoin, lons = Basemap.shiftgrid(180.0, topoin, lons, start=False)
    nx = int((m.xmax - m.xmin) / 10000.0) + 1
    ny = int((m.ymax - m.ymin) / 10000.0) + 1
    topodat = m.transform_scalar(topoin, lons, lats, nx, ny)
    m.imshow(topodat, cm.GMT_haxby)

    m.drawcoastlines()
    m.drawcountries()
    m.drawmapboundary()

    # Plot operational area polygons
    for poly in operational_area.geoms:
        px, py = poly.exterior.xy
        mx, my = m(px, py)
        xy = list(zip(mx, my))
        p = plt.Polygon(xy, facecolor="none", edgecolor="blue", linewidth=2)
        ax.add_patch(p)

    placed_polygons = []
    for sensor in placed_sensors:
        loc = sensor["location"]
        fan_poly = create_fan_polygon(
            loc.x,
            loc.y,
            sensor["config"]["range_km"],
            sensor["config"]["azimuth_degree"],
            sensor["config"]["fan_degree"],
        )
        placed_polygons.append(fan_poly)
        fan_x, fan_y = fan_poly.exterior.xy
        mx, my = m(fan_x, fan_y)
        xy = list(zip(mx, my))
        p = plt.Polygon(xy, alpha=fan_opacity, facecolor="red", edgecolor="darkred", linewidth=1)
        ax.add_patch(p)

    sensor_x = [s["location"].x for s in placed_sensors]
    sensor_y = [s["location"].y for s in placed_sensors]
    msx, msy = m(sensor_x, sensor_y)
    for x_pt, y_pt in zip(msx, msy):
        ax.plot(x_pt, y_pt, marker="^", markersize=12, color="black", markeredgecolor="white", linestyle="None", zorder=6)

    legend_elements = [
        plt.Line2D([0], [0], color="b", lw=2, label="Operational Area"),
        Patch(facecolor="red", alpha=fan_opacity, edgecolor="darkred", label="Individual Sensor Coverage"),
        plt.Line2D([0], [0], marker="^", color="black", label="Placed Sensor", markersize=12, markerfacecolor="black", markeredgecolor="white", linestyle="None"),
    ]
    ax.legend(handles=legend_elements, loc="upper right")
    ax.set_title("Optimal Sensor Placement")
    return ax
