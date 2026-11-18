# Four decades of US tree canopy change, county by county

[![tests](https://github.com/rajibhossain26/us-tree-canopy-change/actions/workflows/tests.yml/badge.svg)](https://github.com/rajibhossain26/us-tree-canopy-change/actions/workflows/tests.yml)
[![zonal statistics](https://github.com/rajibhossain26/us-tree-canopy-change/actions/workflows/zonal.yml/badge.svg)](https://github.com/rajibhossain26/us-tree-canopy-change/actions/workflows/zonal.yml)

How much tree canopy does each county in the conterminous US have, how has
that changed since 1985, and where are the losses and gains clustered? This
project answers that from the **USDA Forest Service / NLCD Tree Canopy Cover
(TCC) v2025.6** rasters — 30 m, wall-to-wall, about 15 billion pixels per year —
and links the results to population density and household income.

Everything is rebuilt by GitHub Actions from public data: the pipeline downloads
each year's raster (~3.6 GB), computes county means at full resolution, and
commits the tables and maps you see here.

**Results:** _the first pipeline run is in progress; numbers and maps appear here when it finishes._

## Data

| Input | Source | Notes |
|---|---|---|
| Tree canopy cover, 1985, 1995, 2005, 2015, 2025 | [USDA Forest Service TCC v2025.6](https://data.fs.usda.gov/geodata/rastergateway/treecanopycover/) (NLCD product) | Percent canopy (0–100) per 30 m pixel, Albers Equal Area. The NLCD version masks water and non-tree agriculture and smooths year-to-year noise, which suits trend work. Codes 254/255 (background/no data) are skipped. |
| County boundaries | [Census 2023 cartographic boundary file, 1:500k](https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html) | 3,100+ CONUS counties and equivalents (Connecticut planning regions). |
| Population, median household income | [ACS 2019–2023 5-year](https://www.census.gov/data/developers/data-sets/acs-5year.html), tables B01003 and B19013 | Public API, no key needed. |

## Methods

1. **Zonal statistics at 30 m.** Each raster is read in 8,192 × 8,192 pixel
   tiles. For every tile the counties that overlap it are rasterized onto the
   tile's own grid (pixel-centre rule) and per-county sums are gathered with
   `np.bincount` (`src/canopy/zonal.py`). Because the raster is equal-area,
   the pixel mean is the area-weighted mean canopy for the county.
2. **Change** is the 2025 mean minus the 1985 mean, in percentage points (pp).
   National and state means are weighted by each county's valid pixel count.
3. **Spatial clustering.** Global Moran's I on county change with queen
   contiguity and 999 permutations, then local Moran's I (Anselin 1995) with
   conditional permutation to map clusters of loss and gain
   (`src/canopy/spatial.py`, plain numpy, unit-tested).
4. **Density and income.** Spearman correlations across counties, plus the
   correlation *within states* (each state's mean removed) to separate a real
   relationship from the East–West climate gradient that dominates canopy.

Maps use EPSG:5070 (CONUS Albers) with a north arrow and scale bar.

## Repository layout

```
src/canopy/zonal.py      tiled zonal statistics (bincount accumulator)
src/canopy/spatial.py    queen weights, global and local Moran's I
src/canopy/mapping.py    north arrow and scale bar
src/canopy/data.py       downloads: TCC, Census boundaries, ACS
scripts/zonal_stats.py   one year of TCC -> data/zonal/tcc_<year>.csv
scripts/run_analysis.py  tables, maps and results/RESULTS.md
.github/workflows/       tests, the full raster pipeline, and a quick re-run of the analysis
```

## Run it yourself

```bash
pip install -r requirements.txt
curl -fLo tcc_2025.zip https://data.fs.usda.gov/geodata/rastergateway/treecanopycover/docs/v2025-6/nlcd_tcc_conus_2025_v2025-6_wgs84.zip
python scripts/zonal_stats.py --year 2025 --zip tcc_2025.zip
# ...repeat for at least one more year, then:
python scripts/run_analysis.py
pytest -q
```

Each year needs ~8 GB of free disk (zip plus extracted GeoTIFF) and runs in
well under an hour on a laptop.

## Caveats

- TCC is a **model** (random forests on Landsat and Sentinel-2 imagery); its
  per-pixel error is substantial, though county averages over millions of
  pixels are far more stable. Small changes (under ~1 pp) should be read as
  "no clear change".
- Canopy here includes forests, orchards and street trees alike; a county can
  gain canopy from plantation forestry while losing urban trees.
- County means hide big within-county differences; this is a screening-level
  national picture, not a neighbourhood equity analysis.
- The correlations are descriptive, not causal.

## Citation

USDA Forest Service. 2026. *Tree Canopy Cover, v2025.6*. Salt Lake City, UT.
https://data.fs.usda.gov/geodata/rastergateway/treecanopycover/

---
Author: [Rajib Hossain](https://rajibhossain26.github.io) · MIT License
