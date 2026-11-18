import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from canopy.spatial import local_morans, morans_i, row_standardize, within_group_corr  # noqa: E402
from canopy.zonal import ZoneAccumulator, row_area_weights, tile_windows  # noqa: E402


def test_accumulator_means_skip_nodata_and_outside():
    zone = np.array([[1, 1, 2], [2, 0, 2]])
    vals = np.array([[10, 30, 50], [255, 99, 70]], dtype=np.uint8)
    acc = ZoneAccumulator(2)
    acc.add(zone, vals)
    # zone 1: (10+30)/2 ; zone 2: 50 and 70 (255 is no-data); zone 0 ignored
    assert acc.means() == pytest.approx([20.0, 60.0])
    assert acc.pixels[1:].tolist() == [2, 2]


def test_accumulator_is_additive_across_tiles():
    acc = ZoneAccumulator(1)
    acc.add(np.array([[1, 1]]), np.array([[0, 100]]))
    acc.add(np.array([[1]]), np.array([[50]]))
    assert acc.means()[0] == pytest.approx(50.0)


def test_weighted_accumulator():
    acc = ZoneAccumulator(1)
    acc.add(np.array([[1], [1]]), np.array([[0], [90]]), weights=np.array([[2.0], [1.0]]))
    assert acc.means()[0] == pytest.approx(30.0)


def test_empty_zone_is_nan():
    acc = ZoneAccumulator(2)
    acc.add(np.array([[1]]), np.array([[5]]))
    assert np.isnan(acc.means()[1])


def test_tile_windows_cover_raster_exactly():
    cover = np.zeros((10, 7), int)
    for r, c, h, w in tile_windows(10, 7, 4):
        cover[r:r + h, c:c + w] += 1
    assert (cover == 1).all()


def test_row_area_weights_follow_cos_latitude():
    class T:  # minimal affine stand-in: top edge at 60N, 1-degree rows
        f, e = 60.5, -1.0
    w = row_area_weights(T, 0, 2)
    assert w == pytest.approx(np.cos(np.radians([60.0, 59.0])))


def _line_neighbors(n):
    return [{j for j in (i - 1, i + 1) if 0 <= j < n} for i in range(n)]


def test_morans_i_detects_smooth_gradient():
    w = row_standardize(_line_neighbors(30))
    I, EI, p = morans_i(np.arange(30.0), w, permutations=199)
    assert I > 0.8 and p < 0.01 and EI == pytest.approx(-1 / 29)


def test_morans_i_negative_for_checkerboard():
    w = row_standardize(_line_neighbors(30))
    I, _, p = morans_i(np.tile([0.0, 1.0], 15), w, permutations=199)
    assert I < -0.9 and p < 0.01


def test_local_morans_flags_cluster_ends():
    x = np.r_[np.full(8, 10.0), np.zeros(52)]
    res = local_morans(x, row_standardize(_line_neighbors(60)), permutations=999)
    assert res["q"][0] == 1 and res["q"][-1] == 3  # High-High, Low-Low
    assert res["p"][3] < 0.05 and res["p"][30] > 0.05


def test_within_group_corr_removes_group_offsets():
    # Between groups x and y move together, within groups they move opposite.
    x = np.array([0, 1, 10, 11], float)
    y = np.array([1, 0, 11, 10], float)
    g = ["a", "a", "b", "b"]
    assert np.corrcoef(x, y)[0, 1] > 0.9
    assert within_group_corr(x, y, g) == pytest.approx(-1.0)
