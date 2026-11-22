import numpy as np
import pytest

from rgeo import (attachments, ccw, mean_radial_gap, offset, radius_at,
                  resample, signed_area, subtract)


def test_ccw_normalises_direction(ring):
    outer, _ = ring
    assert signed_area(ccw(outer[::-1])) > 0


def test_offset_grows_and_shrinks(ring):
    outer, _ = ring
    assert signed_area(offset(outer, 2.0)) > signed_area(outer)
    assert signed_area(offset(outer, -2.0)) < signed_area(outer)


def test_offset_keeps_the_point_count(ring):
    outer, _ = ring
    assert len(offset(outer, 1.5)) == len(outer)


def test_offset_survives_a_concave_outline():
    """A per-vertex normal offset folds over here and silently self-intersects."""
    from shapely.geometry import Polygon
    pts = np.array([(0, 0), (40, 0), (40, 20), (22, 20), (22, 6),
                    (18, 6), (18, 20), (0, 20)], float)
    out = offset(resample(pts, 120), -1.5)
    assert Polygon(out).is_simple


def test_offset_that_collapses_raises(ring):
    _, hole = ring
    with pytest.raises(ValueError):
        offset(hole, -50.0)


def test_resample_spaces_points_evenly(ring):
    outer, _ = ring
    r = resample(outer, 200)
    d = np.linalg.norm(np.diff(np.r_[r, r[:1]], axis=0), axis=1)
    assert d.max() / d.min() < 1.1


def test_mean_radial_gap_measures_the_wall(ring):
    outer, hole = ring
    med, lo, hi = mean_radial_gap(hole, outer, n=180)
    assert 10.0 <= med <= 12.0


def test_attachments_finds_what_sticks_out():
    """Concentric circles, so the wall is the same all the way round and the
    only thing that stands out is the bump."""
    t = np.linspace(0, 2 * np.pi, 240, endpoint=False)
    inner = np.c_[np.cos(t) * 25, np.sin(t) * 25]
    outer = np.c_[np.cos(t) * 30, np.sin(t) * 30]
    ang = np.degrees(np.arctan2(outer[:, 1], outer[:, 0]))
    outer[np.abs(ang - 40) < 8] *= 1.3
    found = attachments(inner, outer, wall=5.0, tol=0.8)
    assert len(found) == 1
    assert 30 < found[0]["angle_mid"] < 50
    assert found[0]["max_excess"] > 5.0


def test_subtract_takes_a_bite_out_of_the_boundary(ring):
    outer, _ = ring
    bite = np.array([(30, -40), (60, -40), (60, 40), (30, 40)], float)
    out = subtract(outer, resample(bite, 80))
    assert signed_area(out) < signed_area(outer)
    assert out[:, 0].max() < 30.5


def test_subtract_ignores_an_interior_region(ring):
    """Documented limitation: only the outer boundary comes back."""
    outer, hole = ring
    assert signed_area(subtract(outer, hole * 0.4)) == pytest.approx(
        signed_area(outer))
