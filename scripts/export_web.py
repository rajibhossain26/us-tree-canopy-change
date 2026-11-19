"""Export the county results for the interactive map in docs/index.html.

Writes docs/data/counties.geojson (simplified county outlines with canopy
values for every year) and docs/data/states.geojson (state outlines).

Outlines are simplified with ``shapely.coverage_simplify``, which simplifies
shared borders once for both neighbours, so no gaps or slivers open between
counties. Coordinates are rounded to 0.001 degrees (about 100 m), far finer
than a county map needs, to keep the download small.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import shapely

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from canopy.data import load_counties  # noqa: E402

OUT = ROOT / "docs" / "data"
TOLERANCE = 0.01  # degrees, about 1 km


def rounded(obj, nd=3):
    if isinstance(obj, (list, tuple)):
        return [rounded(o, nd) for o in obj]
    if isinstance(obj, float):
        return round(obj, nd)
    return obj


def feature(geom, props):
    gj = json.loads(shapely.to_geojson(geom))
    gj["coordinates"] = rounded(gj["coordinates"])
    return {"type": "Feature", "properties": props, "geometry": gj}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    counties = load_counties(ROOT / "data" / "raw").to_crs("EPSG:4326")
    table = pd.read_csv(ROOT / "results" / "county_canopy.csv", dtype={"GEOID": str})
    years = sorted(int(c.split("_")[1]) for c in table.columns if c.startswith("tcc_"))
    simple = shapely.coverage_simplify(counties.geometry.to_numpy(), tolerance=TOLERANCE)
    # d3-geo expects exterior rings clockwise (the reverse of RFC 7946); otherwise a
    # polygon is read as "the whole globe except this county".
    simple = shapely.orient_polygons(simple, exterior_cw=True)
    counties = counties.assign(geometry=simple)
    merged = counties.merge(table, on="GEOID", how="left", suffixes=("", "_t"))

    feats = []
    for _, r in merged.iterrows():
        vals = [None if pd.isna(r[f"tcc_{y}"]) else round(float(r[f"tcc_{y}"]), 1) for y in years]
        feats.append(feature(r.geometry, {"id": r["GEOID"], "n": r["NAME"], "s": r["STUSPS"], "v": vals}))

    # Headline numbers come from run_analysis.py at full precision, so the map and
    # results/RESULTS.md always agree.
    meta = json.loads((ROOT / "results" / "summary.json").read_text())
    assert meta["years"] == years, (meta["years"], years)
    meta["source"] = "USDA Forest Service / NLCD Tree Canopy Cover v2025.6"
    fc = {"type": "FeatureCollection", "meta": meta, "features": feats}
    path = OUT / "counties.geojson"
    path.write_text(json.dumps(fc, separators=(",", ":")))

    states = counties.dissolve(by="STUSPS")[["geometry"]].reset_index()
    states_geom = shapely.orient_polygons(states.geometry.to_numpy(), exterior_cw=True)
    sfeats = [feature(g, {"s": s}) for s, g in zip(states["STUSPS"], states_geom)]
    (OUT / "states.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": sfeats},
                                                    separators=(",", ":")))

    size = path.stat().st_size / 1e6
    print(f"wrote {path} ({len(feats)} counties, {size:.2f} MB), years {years}")
    print("meta:", meta)
    if size > 6:
        raise SystemExit("counties.geojson is unexpectedly large; check the simplification")
    missing = sum(1 for f in feats if all(v is None for v in f["properties"]["v"]))
    print(f"counties with no canopy values: {missing}")
    assert np.isfinite(meta["national"]).all()


if __name__ == "__main__":
    main()
