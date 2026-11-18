"""Mean tree canopy cover per CONUS county for one year of NLCD TCC.

    python scripts/zonal_stats.py --year 2025 --zip /mnt/tcc/nlcd_tcc_conus_2025.zip

Writes data/zonal/tcc_<year>.csv with GEOID, mean canopy (%), the summed
pixel weights, and the number of valid pixels, so years can be compared and
results re-aggregated (e.g. to states) without re-reading the rasters.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from canopy.data import extract_rasters, load_counties  # noqa: E402
from canopy.zonal import zonal_means  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--zip", required=True, help="downloaded TCC zip")
    ap.add_argument("--workdir", default=None, help="where to extract (default: next to the zip)")
    ap.add_argument("--tile", type=int, default=8192)
    ap.add_argument("--keep-zip", action="store_true")
    args = ap.parse_args()

    zip_path = Path(args.zip)
    work = Path(args.workdir) if args.workdir else zip_path.parent / f"tcc_{args.year}"
    t0 = time.time()
    rasters = extract_rasters(zip_path, work)
    if not args.keep_zip:
        zip_path.unlink()
    print(f"extracted {len(rasters)} raster(s) in {time.time() - t0:.0f}s", flush=True)
    if not rasters:
        raise SystemExit("no raster found in the zip")

    counties = load_counties(ROOT / "data" / "raw")
    acc = zonal_means(rasters, counties, tile=args.tile)

    out = pd.DataFrame({
        "GEOID": counties["GEOID"],
        "year": args.year,
        "tcc_mean": acc.means(),
        "weight_sum": acc.weight_sum[1:],
        "valid_pixels": acc.pixels[1:],
    })
    dest = ROOT / "data" / "zonal" / f"tcc_{args.year}.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(dest, index=False, float_format="%.4f")
    print(f"wrote {dest} ({out['tcc_mean'].notna().sum()} counties with data) "
          f"in {(time.time() - t0) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
