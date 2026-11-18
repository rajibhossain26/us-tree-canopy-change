"""Map furniture: north arrow and scale bar for maps in a metre-based CRS
(EPSG:5070, CONUS Albers Equal Area, is used throughout)."""

from __future__ import annotations

from matplotlib.patches import Rectangle

CRS = "EPSG:5070"


def add_north_arrow(ax, x=0.95, y=0.95, length=0.08):
    """North arrow in axes-fraction coordinates. In Albers, grid north
    departs from true north away from the central meridian (-96°), by up to
    ~15° at the map's east and west edges; the arrow marks the centre."""
    ax.annotate("", xy=(x, y), xytext=(x, y - length), xycoords="axes fraction",
                arrowprops=dict(facecolor="black", edgecolor="black", width=3, headwidth=10, headlength=10))
    ax.text(x, y + 0.012, "N", transform=ax.transAxes, ha="center", va="bottom", fontsize=12, fontweight="bold")


def add_scale_bar(ax, length_km=500, segments=2, x_frac=0.03, y_frac=0.05):
    """Alternating black/white scale bar; the axes are in metres. Albers
    preserves area, not distance, so the bar is exact only along the
    standard parallels (29.5°N, 45.5°N) and within ~1% across most of CONUS."""
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    length = length_km * 1000.0
    height = (y1 - y0) * 0.012
    x = x0 + (x1 - x0) * x_frac
    y = y0 + (y1 - y0) * y_frac
    step = length / segments
    for i in range(segments):
        ax.add_patch(Rectangle((x + i * step, y), step, height, facecolor="black" if i % 2 == 0 else "white",
                               edgecolor="black", linewidth=0.8, zorder=5))
    for i in range(segments + 1):
        km = i * length_km / segments
        label = f"{km:g}" + (" km" if i == segments else "")
        ax.text(x + i * step, y + height * 1.8, label, ha="center", va="bottom", fontsize=8, zorder=5)
