from typing import List, Dict, Any
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.patches import Polygon as mpl_polygon
from mpl_toolkits.basemap import Basemap, shiftgrid, cm
from netCDF4 import Dataset

from .utils import create_fan_polygon

__all__ = ["plot_sensor_map"]


def plot_sensor_map(
    operational_area,
    placed_sensors_polygons: List,
    placed_sensors_info: List[Dict[str, Any]],
    fan_opacity: float = 0.5,
):
    """Visualise sensor placements on a Basemap figure.

    Parameters
    ----------
    operational_area:
        Multipolygon describing the operational boundary.
    placed_sensors_polygons:
        Coverage polygons computed for each placed sensor.
    placed_sensors_info:
        Information about each sensor returned by
        :func:`optimize_sensor_placement`.
    fan_opacity:
        Transparency for the coverage polygons.
    """
    url = "http://ferret.pmel.noaa.gov/thredds/dodsC/data/PMEL/etopo5.nc"
    etopodata = Dataset(url)
    topoin = etopodata.variables["ROSE"][:]
    lons = etopodata.variables["ETOPO05_X"][:]
    lats = etopodata.variables["ETOPO05_Y"][:]
    topoin, lons = shiftgrid(180.0, topoin, lons, start=False)

    fig, ax = plt.subplots(figsize=(10, 7))
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
    nx = int((m.xmax - m.xmin) / 10000.0) + 1
    ny = int((m.ymax - m.ymin) / 10000.0) + 1
    topodat = m.transform_scalar(topoin, lons, lats, nx, ny)
    m.imshow(topodat, cm.GMT_haxby)
    m.drawcoastlines()
    m.drawcountries()
    m.drawmapboundary()

    for poly in operational_area.geoms:
        px, py = poly.exterior.xy
        mx, my = m(px, py)
        xy = list(zip(mx, my))
        p = mpl_polygon(xy, facecolor="none", edgecolor="blue", linewidth=2)
        ax.add_patch(p)

    for fan_poly in placed_sensors_polygons:
        fan_x, fan_y = fan_poly.exterior.xy
        mx, my = m(fan_x, fan_y)
        xy = list(zip(mx, my))
        p = mpl_polygon(xy, alpha=fan_opacity, facecolor="red", edgecolor="darkred", linewidth=1)
        ax.add_patch(p)

    sensor_x = [s["location"].x for s in placed_sensors_info]
    sensor_y = [s["location"].y for s in placed_sensors_info]
    msx, msy = m(sensor_x, sensor_y)
    for x_pt, y_pt in zip(msx, msy):
        ax.plot(
            x_pt,
            y_pt,
            marker="^",
            markersize=12,
            color="black",
            markeredgecolor="white",
            linestyle="None",
            zorder=6,
            label="Placed Sensor",
        )

    handles, labels = ax.get_legend_handles_labels()
    unique = dict(zip(labels, handles))
    ax.legend(unique.values(), unique.keys(), loc="upper right")

    legend_elements = [
        plt.Line2D([0], [0], color="b", lw=2, label="Operational Area"),
        Patch(facecolor="red", alpha=fan_opacity, edgecolor="darkred", label="Individual Sensor Coverage"),
        plt.Line2D(
            [0],
            [0],
            marker="^",
            color="black",
            label="Placed Sensor",
            markersize=12,
            markerfacecolor="black",
            markeredgecolor="white",
            linestyle="None",
        ),
    ]
    ax.legend(handles=legend_elements, loc="upper right")
    ax.set_title("Optimal Sensor Placement")
    plt.show()

