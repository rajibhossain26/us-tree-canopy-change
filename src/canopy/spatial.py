"""Spatial weights and global / local Moran's I, in plain numpy.

Local Moran's I uses conditional randomisation with one shared set of random
draws for all locations (the approach used by PySAL's esda), which keeps the
run time low for ~3,100 counties.
"""

from __future__ import annotations

import numpy as np


def queen_neighbors(gdf) -> list[set[int]]:
    """Queen contiguity (polygons sharing any boundary point) from a
    GeoDataFrame, by positional index."""
    import geopandas as gpd

    g = gdf[["geometry"]].reset_index(drop=True)
    pairs = gpd.sjoin(g, g, how="inner", predicate="intersects")
    nbrs: list[set[int]] = [set() for _ in range(len(g))]
    for i, j in zip(pairs.index.to_numpy(), pairs["index_right"].to_numpy()):
        if i != j:
            nbrs[int(i)].add(int(j))
    return nbrs


def row_standardize(nbrs: list[set[int]]) -> np.ndarray:
    n = len(nbrs)
    w = np.zeros((n, n))
    for i, js in enumerate(nbrs):
        if js:
            w[i, list(js)] = 1.0 / len(js)
    return w


def morans_i(values, w: np.ndarray, permutations: int = 999, seed: int = 0):
    """Global Moran's I, its expectation under no autocorrelation, and a
    one-sided permutation pseudo p-value."""
    z = np.asarray(values, float)
    z = z - z.mean()
    n, s0 = len(z), w.sum()

    def stat(v):
        return (n / s0) * (v @ (w @ v)) / (v @ v)

    obs = stat(z)
    rng = np.random.default_rng(seed)
    sims = np.array([stat(rng.permutation(z)) for _ in range(permutations)])
    expected = -1.0 / (n - 1)
    extreme = np.sum(sims >= obs) if obs >= expected else np.sum(sims <= obs)
    return float(obs), expected, float((extreme + 1) / (permutations + 1))


def local_morans(values, w: np.ndarray, permutations: int = 999, seed: int = 0):
    """Local Moran's I (Anselin 1995) with conditional permutation inference.

    Returns ``I``, quadrant ``q`` (1 High-High, 2 Low-High, 3 Low-Low,
    4 High-Low) and folded one-sided pseudo p-values ``p``.
    """
    x = np.asarray(values, float)
    n = len(x)
    z = (x - x.mean()) / x.std()
    lag = w @ z
    I = z * lag
    q = np.where(z > 0, np.where(lag > 0, 1, 4), np.where(lag > 0, 2, 3))

    k_max = int((w > 0).sum(axis=1).max())
    rng = np.random.default_rng(seed)
    # One shared table of draws from the n - 1 "other" locations.
    rids = np.array([rng.permutation(n - 1)[:k_max] for _ in range(permutations)])

    p = np.ones(n)
    for i in range(n):
        js = np.nonzero(w[i])[0]
        k = len(js)
        if k == 0:
            continue
        others = np.delete(z, i)
        sims = z[i] * (others[rids[:, :k]] @ w[i, js])
        larger = np.sum(sims >= I[i])
        if permutations - larger < larger:
            larger = permutations - larger
        p[i] = (larger + 1) / (permutations + 1)
    return {"I": I, "q": q, "p": p, "z": z, "lag": lag}


QUADRANT_LABELS = {1: "High-High", 2: "Low-High", 3: "Low-Low", 4: "High-Low"}


def within_group_corr(x, y, groups) -> float:
    """Pearson correlation of x and y after removing each group's mean
    (equivalent to a fixed-effects slope's correlation). Used to ask whether
    a relationship holds *within* states, not just between regions."""
    import pandas as pd

    df = pd.DataFrame({"x": np.asarray(x, float), "y": np.asarray(y, float), "g": np.asarray(groups)}).dropna()
    if len(df) < 3:
        return float("nan")
    dx = df["x"] - df.groupby("g")["x"].transform("mean")
    dy = df["y"] - df.groupby("g")["y"].transform("mean")
    return float(np.corrcoef(dx, dy)[0, 1])
