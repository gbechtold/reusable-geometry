import numpy as np
import pytest

from rgeo import WallProfile


def test_chamfer_runs_front_to_back():
    s = WallProfile(6.0).chamfer_front(1.0).chamfer_back(0.5).steps()
    depths = [float(d) for d, _ in s]
    assert depths == sorted(depths)
    assert depths[0] == 0.0 and depths[-1] == 6.0
    assert s[0][1] == pytest.approx(-1.0)
    assert s[-1][1] == pytest.approx(-0.5)


def test_outward_profiles_push_the_other_way():
    s = WallProfile(6.0, outward=True).chamfer_both(0.6).steps()
    assert s[0][1] > 0 and s[-1][1] > 0


def test_groove_sits_where_it_is_asked_to():
    s = WallProfile(6.0, outward=True).groove(at=2.6, width=0.9, depth=0.7).steps()
    deepest = max(s, key=lambda p: p[1])
    assert float(deepest[0]) == pytest.approx(2.6)
    assert deepest[1] == pytest.approx(0.7)


def test_variable_thickness_moves_only_the_back():
    t = np.array([6.0, 6.0, 9.0, 9.0])
    s = WallProfile(6.0).chamfer_front(1.0).chamfer_back(0.5).steps(t)
    assert float(np.max(s[0][0])) == 0.0                 # front stays put
    assert np.allclose(np.atleast_1d(s[-1][0]), t)       # back follows


def test_round_front_is_tangent_to_the_face():
    s = WallProfile(4.6).round_front(0.5, n=8).steps()
    assert s[0][1] == pytest.approx(-0.5)
    assert float(s[0][0]) == pytest.approx(0.0)


def test_validate_catches_an_oversized_offset():
    p = WallProfile(2.0).chamfer_front(3.0)
    assert p.validate()
