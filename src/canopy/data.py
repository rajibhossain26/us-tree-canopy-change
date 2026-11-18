"""Download helpers for the public inputs (all free, no API key needed)."""

from __future__ import annotations

import time
import urllib.request
import zipfile
from pathlib import Path

TCC_BASE = "https://data.fs.usda.gov/geodata/rastergateway/treecanopycover/docs/v2025-6/"
COUNTIES_URL = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip"

# Not in the conterminous US: AK, HI, and the territories.
NON_CONUS = {"02", "15", "60", "66", "69", "72", "78"}


def tcc_url(year: int, product: str = "nlcd") -> str:
    return f"{TCC_BASE}{product}_tcc_conus_{year}_v2025-6_wgs84.zip"


def get(url: str, tries: int = 4) -> bytes:
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "us-tree-canopy-change"})
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.read()
        except Exception:  # noqa: BLE001 - retried, then re-raised
            if attempt == tries - 1:
                raise
            time.sleep(10 * (attempt + 1))
    raise RuntimeError("unreachable")


def load_counties(cache_dir: str | Path = "data/raw"):
    """Census 2023 cartographic-boundary counties (1:500k), CONUS only."""
    import geopandas as gpd

    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    shp_zip = cache / "cb_2023_us_county_500k.zip"
    if not shp_zip.exists():
        shp_zip.write_bytes(get(COUNTIES_URL))
    g = gpd.read_file(f"zip://{shp_zip}")
    g = g[~g["STATEFP"].isin(NON_CONUS)].copy()
    g = g.sort_values("GEOID").reset_index(drop=True)
    return g[["GEOID", "STATEFP", "NAME", "STUSPS", "STATE_NAME", "ALAND", "AWATER", "geometry"]]


def extract_rasters(zip_path: str | Path, out_dir: str | Path) -> list[Path]:
    """Extract every GeoTIFF/IMG in a TCC zip; return their paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            print("  zip member:", name, flush=True)
            if name.lower().endswith((".tif", ".tiff", ".img", ".ige", ".ovr", ".aux.xml", ".tfw", ".xml")):
                zf.extract(name, out)
                if name.lower().endswith((".tif", ".tiff", ".img")):
                    paths.append(out / name)
    return paths
