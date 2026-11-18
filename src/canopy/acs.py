"""ACS 2019-2023 5-year county estimates from the Census Bureau's
table-based summary files (plain pipe-delimited text, no API key needed)."""

from __future__ import annotations

from pathlib import Path

from canopy.data import get

SF_BASE = "https://www2.census.gov/programs-surveys/acs/summary_file/2023/table-based-SF/data/5YRData/"
TABLES = {"B01003": ("B01003_E001", "population"), "B19013": ("B19013_E001", "median_income")}


def parse_table(text: str, column: str, name: str):
    """County rows (GEO_ID 0500000USssccc) of one summary-file table.
    Negative values are Census annotation codes (e.g. -666666666) -> NaN."""
    import pandas as pd
    from io import StringIO

    df = pd.read_csv(StringIO(text), sep="|", dtype={"GEO_ID": str})
    df = df[df["GEO_ID"].str.startswith("0500000US")].copy()
    df["GEOID"] = df["GEO_ID"].str[-5:]
    vals = pd.to_numeric(df[column], errors="coerce")
    df[name] = vals.where(vals >= 0)
    return df[["GEOID", name]]


def load_acs(cache_dir: str | Path = "data/raw"):
    """County population (B01003) and median household income (B19013)."""
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    out = None
    for table, (column, name) in TABLES.items():
        path = cache / f"acsdt5y2023-{table.lower()}.dat"
        if not path.exists():
            path.write_bytes(get(f"{SF_BASE}{path.name}"))
        part = parse_table(path.read_text(), column, name)
        out = part if out is None else out.merge(part, on="GEOID", how="outer")
    return out
