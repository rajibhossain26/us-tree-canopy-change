"""Download helpers for the public inputs (all free, no API key needed)."""

from __future__ import annotations

import json
import time
import urllib.request
import zipfile
from pathlib import Path

TCC_BASE = "https://data.fs.usda.gov/geodata/rastergateway/treecanopycover/docs/v2025-6/"
COUNTIES_URL = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip"
ACS_URL = ("https://api.census.gov/data/2023/acs/acs5"
           "?get=NAME,B01003_001E,B19013_001E&for=county:*")

# Not in the conterminous US: AK, HI, and the territories.
NON_CONUS = {"02", "15", "60", "66", "69", "72", "78"}


def tcc_url(year: int, product: str = "nlcd") -> str:
    return f"{TCC_BASE}{product}_tcc_conus_{year}_v2025-6_wgs84.zip"


def _get(url: str, tries: int = 4) -> bytes:
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
        shp_zip.write_bytes(_get(COUNTIES_URL))
    g = gpd.read_file(f"zip://{shp_zip}")
    g = g[~g["STATEFP"].isin(NON_CONUS)].copy()
    g = g.sort_values("GEOID").reset_index(drop=True)
    return g[["GEOID", "STATEFP", "NAME", "STUSPS", "STATE_NAME", "ALAND", "AWATER", "geometry"]]


def load_acs(cache_dir: str | Path = "data/raw"):
    """ACS 2019-2023 5-year county population and median household income."""
    import pandas as pd

    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / "acs2023_county.json"
    if not path.exists():
        path.write_bytes(_get(ACS_URL))
    rows = json.loads(path.read_text())
    df = pd.DataFrame(rows[1:], columns=rows[0])
    df["GEOID"] = df["state"] + df["county"]
    df["population"] = pd.to_numeric(df["B01003_001E"], errors="coerce")
    inc = pd.to_numeric(df["B19013_001E"], errors="coerce")
    df["median_income"] = inc.where(inc > 0)  # negative values are Census missing codes
    return df[["GEOID", "population", "median_income"]]


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
