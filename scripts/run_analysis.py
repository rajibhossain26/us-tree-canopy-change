"""County-level analysis of four decades of US tree canopy change.

Reads the per-year zonal tables in data/zonal/ (made by zonal_stats.py),
joins Census boundaries and ACS population / income, and writes:

  results/county_canopy.csv   one row per CONUS county
  results/state_canopy.csv    one row per state (+ DC)
  results/national_trend.csv  CONUS area-weighted mean by year
  results/RESULTS.md          the numbers quoted in the README
  docs/*.png                  maps (with north arrow and scale bar) and charts
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import TwoSlopeNorm  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from canopy import mapping, spatial  # noqa: E402
from canopy.acs import load_acs  # noqa: E402
from canopy.data import load_counties  # noqa: E402

DOCS, RESULTS = ROOT / "docs", ROOT / "results"
INK, MUTED, GRID = "#1f2328", "#59636e", "#d0d7de"
BAR = "#2f6f4f"


def load_zonal() -> pd.DataFrame:
    files = sorted((ROOT / "data" / "zonal").glob("tcc_*.csv"))
    if len(files) < 2:
        raise SystemExit("need at least two years in data/zonal/ - run zonal_stats.py first")
    z = pd.concat([pd.read_csv(f, dtype={"GEOID": str}) for f in files], ignore_index=True)
    return z


def coverage_screen(z: pd.DataFrame, county_min: float = 0.99, year_max_share: float = 0.01):
    """Drop incomplete data.

    A county's valid-pixel count should be the same every year, so coverage
    is each county-year's count relative to that county's maximum. A year in
    which more than ``year_max_share`` of counties fall below ``county_min``
    has scene gaps and is dropped whole; remaining county-years below
    ``county_min`` are set to missing. Returns (screened table, notes).
    """
    z = z.copy()
    z["coverage"] = z["weight_sum"] / z.groupby("GEOID")["weight_sum"].transform("max")
    share_low = z.groupby("year")["coverage"].apply(lambda c: float((c < county_min).mean()))
    dropped = [int(y) for y, f in share_low.items() if f > year_max_share]
    notes = [f"{y}: {share_low[y]:.1%} of counties have under {county_min:.0%} of their usual valid pixels "
             f"(gaps in that year's raster), so {y} is left out." for y in dropped]
    z = z[~z["year"].isin(dropped)].copy()
    low = z["coverage"] < county_min
    if low.any():
        notes.append(f"{int(low.sum())} further county-year values with under {county_min:.0%} coverage set to missing.")
    z.loc[low, "tcc_mean"] = np.nan
    return z, notes


def weighted_mean(df, value, weight):
    d = df[[value, weight]].dropna()
    return float((d[value] * d[weight]).sum() / d[weight].sum())


def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def base_map(gdf, states, column, cmap, norm, title, label):
    fig, ax = plt.subplots(figsize=(12, 7.4))
    gdf.plot(column=column, cmap=cmap, norm=norm, ax=ax, linewidth=0, missing_kwds={"color": "#eeeeee"})
    states.boundary.plot(ax=ax, color="white", linewidth=0.6)
    ax.set_axis_off()
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    cb = fig.colorbar(sm, ax=ax, orientation="horizontal", fraction=0.035, pad=0.01, shrink=0.5)
    cb.set_label(label, color=INK)
    cb.outline.set_visible(False)
    ax.set_title(title, loc="left", fontsize=14, color=INK)
    mapping.add_north_arrow(ax)
    mapping.add_scale_bar(ax, length_km=500)
    return fig, ax


def main() -> None:
    DOCS.mkdir(exist_ok=True)
    RESULTS.mkdir(exist_ok=True)

    counties = load_counties(ROOT / "data" / "raw")
    z, coverage_notes = coverage_screen(load_zonal())
    years = sorted(z["year"].unique())
    y0, y1 = years[0], years[-1]

    wide = z.pivot(index="GEOID", columns="year", values="tcc_mean")
    wide.columns = [f"tcc_{y}" for y in wide.columns]
    weights = z[z["year"] == y1].set_index("GEOID")["weight_sum"].rename("weight")

    try:
        acs = load_acs(ROOT / "data" / "raw")
    except Exception as e:  # noqa: BLE001
        print("ACS download failed, continuing without it:", e)
        acs = pd.DataFrame(columns=["GEOID", "population", "median_income"])

    gdf = counties.merge(wide, left_on="GEOID", right_index=True, how="left")
    gdf = gdf.merge(weights, left_on="GEOID", right_index=True, how="left")
    gdf = gdf.merge(acs, on="GEOID", how="left")
    gdf["change_pp"] = gdf[f"tcc_{y1}"] - gdf[f"tcc_{y0}"]
    gdf["land_km2"] = gdf["ALAND"] / 1e6
    gdf["pop_density"] = gdf["population"] / gdf["land_km2"]
    gdf = gdf.to_crs(mapping.CRS)

    # ---- national and state summaries ---------------------------------
    # Trends use a balanced panel: counties with a value in every year.
    panel = gdf.dropna(subset=[f"tcc_{y}" for y in years])
    trend = pd.DataFrame({
        "year": years,
        "conus_mean_tcc": [weighted_mean(panel, f"tcc_{y}", "weight") for y in years],
    })
    trend.to_csv(RESULTS / "national_trend.csv", index=False, float_format="%.3f")

    st_rows = []
    for (fp, abbr, name), d in panel.groupby(["STATEFP", "STUSPS", "STATE_NAME"]):
        row = {"STATEFP": fp, "state": abbr, "name": name}
        for y in years:
            row[f"tcc_{y}"] = weighted_mean(d, f"tcc_{y}", "weight")
        st_rows.append(row)
    states_tbl = pd.DataFrame(st_rows)
    states_tbl["change_pp"] = states_tbl[f"tcc_{y1}"] - states_tbl[f"tcc_{y0}"]
    states_tbl = states_tbl.sort_values("change_pp").reset_index(drop=True)
    states_tbl.to_csv(RESULTS / "state_canopy.csv", index=False, float_format="%.3f")

    # ---- spatial clustering of change ---------------------------------
    an = gdf.dropna(subset=["change_pp"]).reset_index(drop=True)
    nbrs = spatial.queen_neighbors(an)
    w = spatial.row_standardize(nbrs)
    I, EI, p_global = spatial.morans_i(an["change_pp"].to_numpy(), w)
    lm = spatial.local_morans(an["change_pp"].to_numpy(), w)
    sig = lm["p"] < 0.05
    an["lisa"] = np.where(sig, pd.Series(lm["q"]).map(spatial.QUADRANT_LABELS), "Not significant")
    gdf = gdf.merge(an[["GEOID", "lisa"]], on="GEOID", how="left")

    # ---- relationships with population density and income -------------
    rel = gdf.dropna(subset=["change_pp", "pop_density", f"tcc_{y1}"]).copy()
    rel["log_density"] = np.log10(rel["pop_density"].clip(lower=0.1))
    rho = {}
    for xcol in ("log_density", "median_income"):
        for ycol in (f"tcc_{y1}", "change_pp"):
            d = rel.dropna(subset=[xcol, ycol])
            rho[(xcol, ycol)] = (
                float(spearmanr(d[xcol], d[ycol]).statistic),
                spatial.within_group_corr(d[xcol], d[ycol], d["STATEFP"]),
                len(d),
            )
    rel["density_quintile"] = pd.qcut(rel["pop_density"], 5, labels=["Q1 (most rural)", "Q2", "Q3", "Q4", "Q5 (most urban)"])
    quint = rel.groupby("density_quintile", observed=True).agg(
        counties=("GEOID", "size"),
        median_density=("pop_density", "median"),
        mean_tcc_last=(f"tcc_{y1}", "mean"),
        mean_change_pp=("change_pp", "mean"),
        share_losing=("change_pp", lambda s: (s < 0).mean()),
    )

    # ---- county table --------------------------------------------------
    cols = ["GEOID", "NAME", "STUSPS", *[f"tcc_{y}" for y in years], "change_pp",
            "population", "median_income", "pop_density", "lisa"]
    gdf[cols].sort_values("GEOID").to_csv(RESULTS / "county_canopy.csv", index=False, float_format="%.3f")

    # ---- figures -------------------------------------------------------
    states = gdf.dissolve(by="STATEFP")[["geometry"]]

    fig, _ = base_map(gdf, states, f"tcc_{y1}", plt.get_cmap("Greens"),
                      plt.Normalize(0, 80), f"Tree canopy cover by county, {y1}",
                      "Mean tree canopy cover (%)")
    fig.savefig(DOCS / f"canopy_{y1}_map.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    lim = float(np.nanpercentile(np.abs(gdf["change_pp"]), 98))
    fig, _ = base_map(gdf, states, "change_pp", plt.get_cmap("BrBG"),
                      TwoSlopeNorm(0, -lim, lim), f"Change in tree canopy cover, {y0}–{y1}",
                      "Change (percentage points); brown = loss, teal = gain")
    fig.savefig(DOCS / "canopy_change_map.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    lisa_colors = {"High-High": "#1b7f6b", "Low-Low": "#a6611a", "High-Low": "#80cdc1",
                   "Low-High": "#dfc27d", "Not significant": "#eeeeee"}
    fig, ax = plt.subplots(figsize=(12, 7.4))
    gdf.plot(color=gdf["lisa"].map(lisa_colors).fillna("#eeeeee"), ax=ax, linewidth=0)
    states.boundary.plot(ax=ax, color="white", linewidth=0.6)
    ax.set_axis_off()
    legend = [Patch(facecolor=lisa_colors[k], label=lab) for k, lab in [
        ("High-High", "Gain cluster (High-High)"), ("Low-Low", "Loss cluster (Low-Low)"),
        ("High-Low", "Gain amid losses (High-Low)"), ("Low-High", "Loss amid gains (Low-High)"),
        ("Not significant", "Not significant")]]
    ax.legend(handles=legend, loc="lower right", frameon=False, fontsize=9)
    ax.set_title(f"Clusters of canopy change, {y0}–{y1} (local Moran's I, p < 0.05)", loc="left", fontsize=14, color=INK)
    mapping.add_north_arrow(ax)
    mapping.add_scale_bar(ax, length_km=500)
    fig.savefig(DOCS / "change_clusters_map.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    st = states_tbl.sort_values("change_pp")
    fig, ax = plt.subplots(figsize=(7, 11))
    ax.barh(st["state"], st["change_pp"], color=np.where(st["change_pp"] < 0, "#a6611a", "#1b7f6b"), height=0.7)
    ax.axvline(0, color=INK, linewidth=0.8)
    ax.set_xlabel(f"Change in mean canopy cover, {y0}–{y1} (percentage points)", color=INK)
    ax.set_title(f"Canopy change by state, {y0}–{y1}", loc="left", fontsize=13, color=INK)
    ax.tick_params(axis="y", labelsize=8)
    style(ax)
    fig.savefig(DOCS / "state_change.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.plot(trend["year"], trend["conus_mean_tcc"], color=BAR, linewidth=2, marker="o", markersize=8)
    for _, r in trend.iterrows():
        ax.annotate(f"{r['conus_mean_tcc']:.1f}%", (r["year"], r["conus_mean_tcc"]), textcoords="offset points",
                    xytext=(0, 10), ha="center", fontsize=9, color=INK)
    ax.set_ylabel("Mean canopy cover (%)", color=INK)
    ax.set_title("Conterminous US mean tree canopy cover", loc="left", fontsize=13, color=INK)
    ax.set_xticks(years)
    lo, hi = trend["conus_mean_tcc"].min(), trend["conus_mean_tcc"].max()
    pad = max(0.5, (hi - lo) * 0.6)
    ax.set_ylim(lo - pad, hi + pad)
    style(ax)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.grid(axis="x", visible=False)
    fig.savefig(DOCS / "national_trend.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
    labels = [str(i) for i in quint.index]
    axes[0].bar(labels, quint["mean_tcc_last"], color=BAR, width=0.6)
    axes[0].set_title(f"Mean canopy cover, {y1} (%)", loc="left", fontsize=11, color=INK)
    axes[1].bar(labels, quint["mean_change_pp"], color=np.where(quint["mean_change_pp"] < 0, "#a6611a", "#1b7f6b"), width=0.6)
    axes[1].axhline(0, color=INK, linewidth=0.8)
    axes[1].set_title(f"Mean change, {y0}–{y1} (percentage points)", loc="left", fontsize=11, color=INK)
    for a in axes:
        style(a)
        a.grid(axis="x", visible=False)
        a.grid(axis="y", color=GRID, linewidth=0.6)
        a.tick_params(axis="x", labelsize=8)
    fig.suptitle("Counties grouped by population density (quintiles)", x=0.01, ha="left", fontsize=13, color=INK)
    fig.tight_layout()
    fig.savefig(DOCS / "density_quintiles.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    # ---- results markdown ---------------------------------------------
    valid = gdf.dropna(subset=["change_pp"])
    big = valid[valid["land_km2"] >= 250]  # skip tiny independent cities for the rankings
    losers = big.nsmallest(10, "change_pp")
    gainers = big.nlargest(10, "change_pp")
    popw = gdf.dropna(subset=["population", f"tcc_{y1}"])
    popw_tcc = float((popw[f"tcc_{y1}"] * popw["population"]).sum() / popw["population"].sum())
    lisa_counts = gdf["lisa"].value_counts()

    def tbl(df, cols, names):
        return df[cols].rename(columns=dict(zip(cols, names))).to_markdown(index=False, floatfmt=".1f")

    t0, t1 = trend["conus_mean_tcc"].iloc[0], trend["conus_mean_tcc"].iloc[-1]
    lines = [
        "# Results",
        "",
        f"_Generated by `scripts/run_analysis.py` from NLCD Tree Canopy Cover v2025.6, years {', '.join(map(str, years))}._",
        "",
        "## Headline numbers",
        "",
        f"- Counties analysed: **{valid.shape[0]:,}** of {len(gdf):,} in the conterminous US "
        f"({len(panel):,} with a value in every year, used for the national and state trends).",
        f"- CONUS area-weighted mean canopy cover: **{t0:.2f}%** in {y0} and **{t1:.2f}%** in {y1} "
        f"({t1 - t0:+.2f} percentage points).",
        f"- Counties with lower canopy in {y1} than {y0}: **{(valid['change_pp'] < 0).sum():,}** "
        f"({(valid['change_pp'] < 0).mean():.0%}); higher: **{(valid['change_pp'] > 0).sum():,}**.",
        f"- Median county change: **{valid['change_pp'].median():+.2f}** percentage points.",
        f"- Population-weighted mean canopy in {y1} (the canopy of the county the average resident lives in): **{popw_tcc:.1f}%**.",
        f"- Valid-pixel area as a share of Census land + water area (median county): "
        f"**{(valid['weight'] * 900 / (valid['ALAND'] + valid['AWATER'])).median():.3f}**; "
        f"as a share of land area only: **{(valid['weight'] * 900 / valid['ALAND']).median():.3f}**.",
        f"- Global Moran's I of county change (queen contiguity): **{I:.3f}** (expected {EI:.4f}, permutation p = {p_global:.3f}).",
        "- Local clusters (p < 0.05, no multiple-testing correction): "
        + ", ".join(f"{k}: {int(lisa_counts.get(k, 0))}" for k in ["High-High", "Low-Low", "High-Low", "Low-High"]) + ".",
        "",
        "## Data screening",
        "",
        *([f"- {n}" for n in coverage_notes] or ["- All years and counties passed the coverage check."]),
        "",
        "## National trend",
        "",
        trend.assign(year=trend["year"].astype(str)).rename(columns={"year": "Year", "conus_mean_tcc": "Mean canopy (%)"}).to_markdown(index=False, floatfmt=".2f"),
        "",
        "## States with the largest losses and gains",
        "",
        tbl(states_tbl.head(8), ["name", f"tcc_{y0}", f"tcc_{y1}", "change_pp"], ["State", f"{y0} (%)", f"{y1} (%)", "Change (pp)"]),
        "",
        tbl(states_tbl.tail(8).iloc[::-1], ["name", f"tcc_{y0}", f"tcc_{y1}", "change_pp"], ["State", f"{y0} (%)", f"{y1} (%)", "Change (pp)"]),
        "",
        "## Counties with the largest losses (land area ≥ 250 km²)",
        "",
        tbl(losers, ["NAME", "STUSPS", f"tcc_{y0}", f"tcc_{y1}", "change_pp"], ["County", "State", f"{y0} (%)", f"{y1} (%)", "Change (pp)"]),
        "",
        "## Counties with the largest gains (land area ≥ 250 km²)",
        "",
        tbl(gainers, ["NAME", "STUSPS", f"tcc_{y0}", f"tcc_{y1}", "change_pp"], ["County", "State", f"{y0} (%)", f"{y1} (%)", "Change (pp)"]),
        "",
        "## Canopy, density and income",
        "",
        "Spearman's ρ across all counties, and the Pearson correlation after removing each state's mean "
        "(\"within state\"), which strips out the big regional climate gradient.",
        "",
        "| Variable | Outcome | ρ (all counties) | r (within state) | n |",
        "|---|---|---|---|---|",
    ]
    names = {"log_density": "Population density (log)", "median_income": "Median household income",
             f"tcc_{y1}": f"Canopy {y1}", "change_pp": f"Change {y0}–{y1}"}
    for (xc, yc), (r_all, r_within, n) in rho.items():
        lines.append(f"| {names[xc]} | {names[yc]} | {r_all:+.2f} | {r_within:+.2f} | {n:,} |")
    lines += [
        "",
        "### By population-density quintile",
        "",
        quint.reset_index().rename(columns={
            "density_quintile": "Quintile", "counties": "Counties", "median_density": "Median people / km²",
            "mean_tcc_last": f"Mean canopy {y1} (%)", "mean_change_pp": "Mean change (pp)",
            "share_losing": "Share losing canopy"}).to_markdown(index=False, floatfmt=".2f"),
        "",
    ]
    (RESULTS / "RESULTS.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
