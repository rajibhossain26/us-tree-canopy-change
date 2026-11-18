"""County zonal statistics for the USFS / NLCD Tree Canopy Cover (TCC) rasters.

The CONUS rasters are ~15 billion 30 m pixels, so they are read tile by tile.
For each tile the counties that touch it are burned into a zone raster at the
tile's own grid, and per-county sums are gathered with ``np.bincount``. Only
the accumulator below needs numpy; the raster driver needs rasterio and
geopandas and is imported lazily so the core stays easy to test.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# NLCD TCC stores percent canopy as 0-100. Values above 100 are background /
# no-data codes (254 and 255 in the published files) and are skipped.
VALID_MAX = 100


@dataclass
class ZoneAccumulator:
    """Running per-zone sums. Zone 0 means "outside every county"."""

    n_zones: int
    value_sum: np.ndarray = field(init=False)
    weight_sum: np.ndarray = field(init=False)
    pixels: np.ndarray = field(init=False)

    def __post_init__(self):
        self.value_sum = np.zeros(self.n_zones + 1)
        self.weight_sum = np.zeros(self.n_zones + 1)
        self.pixels = np.zeros(self.n_zones + 1, dtype=np.int64)

    def add(self, zone: np.ndarray, values: np.ndarray, weights: np.ndarray | None = None,
            valid_max: int = VALID_MAX) -> None:
        """Add one tile. ``weights`` (same shape, optional) are pixel areas;
        pass them when the raster is in geographic coordinates."""
        ok = (zone > 0) & (values <= valid_max)
        z = zone[ok].astype(np.int64)
        v = values[ok].astype(np.float64)
        w = np.ones_like(v) if weights is None else np.asarray(weights)[ok].astype(np.float64)
        m = self.n_zones + 1
        self.value_sum += np.bincount(z, weights=v * w, minlength=m)
        self.weight_sum += np.bincount(z, weights=w, minlength=m)
        self.pixels += np.bincount(z, minlength=m)

    def means(self) -> np.ndarray:
        """Area-weighted mean value for zones 1..n (NaN where no valid pixel)."""
        with np.errstate(invalid="ignore", divide="ignore"):
            out = self.value_sum / self.weight_sum
        out[self.weight_sum == 0] = np.nan
        return out[1:]


def tile_windows(height: int, width: int, tile: int):
    """Yield (row_off, col_off, rows, cols) covering a raster in square tiles."""
    for r in range(0, height, tile):
        for c in range(0, width, tile):
            yield r, c, min(tile, height - r), min(tile, width - c)


def row_area_weights(transform, row_off: int, rows: int) -> np.ndarray:
    """Relative pixel area (cos latitude) for each row of a geographic grid."""
    lat = transform.f + transform.e * (row_off + np.arange(rows) + 0.5)
    return np.cos(np.radians(lat))


def zonal_means(raster_paths, counties, tile: int = 8192, log_every: int = 25):
    """Mean canopy per county across one or more raster files.

    ``counties`` is a GeoDataFrame; its row order defines the zone ids
    (row i -> zone i + 1). Returns a ZoneAccumulator.
    """
    import rasterio
    from rasterio.features import rasterize
    from rasterio.windows import Window, bounds as win_bounds
    from shapely.geometry import box

    acc = ZoneAccumulator(len(counties))
    for path in raster_paths:
        with rasterio.open(path) as src:
            g = counties.to_crs(src.crs)
            geoms = list(g.geometry)
            sindex = g.sindex
            geographic = bool(src.crs and src.crs.is_geographic)
            tiles = list(tile_windows(src.height, src.width, tile))
            print(f"{path}: {src.width} x {src.height} px, crs={src.crs}, {len(tiles)} tiles", flush=True)
            for k, (r, c, h, w) in enumerate(tiles, 1):
                win = Window(c, r, w, h)
                hits = sindex.query(box(*win_bounds(win, src.transform)))
                if len(hits) == 0:
                    continue
                arr = src.read(1, window=win)
                if not (arr <= VALID_MAX).any():
                    continue
                zone = rasterize(((geoms[i], int(i) + 1) for i in hits), out_shape=arr.shape,
                                 transform=src.window_transform(win), fill=0, dtype="int32")
                weights = None
                if geographic:
                    weights = np.broadcast_to(row_area_weights(src.transform, r, h)[:, None], arr.shape)
                acc.add(zone, arr, weights)
                if k % log_every == 0:
                    print(f"  tile {k}/{len(tiles)}", flush=True)
    return acc
