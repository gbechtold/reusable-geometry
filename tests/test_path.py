import numpy as np
import pytest

from rgeo import (GeometryError, circle_section, fixed_frames, resample_path,
                  sweep_path, transported_frames, tube)


def ellipse(rx=25.0, ry=20.0, n=120):
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.c_[np.cos(a) * rx, np.sin(a) * ry, np.zeros(n)]


def line(n=40):
    return np.c_[np.zeros(n), np.linspace(0, 3, n), np.linspace(0, -120, n)]


def test_a_closed_rim_sweeps():
    """The case a fixed-up frame cannot do: vertical at 3 and 9 o'clock."""
    t = tube(ellipse(), 0.6, closed=True)
    assert t.val().isValid()
    assert t.val().Volume() > 0


def test_closed_rim_volume_is_about_right():
    rim = ellipse(25.0, 20.0, 240)
    r = 0.6
    body = tube(rim, r, sides=16, closed=True)
    length = np.linalg.norm(np.diff(np.r_[rim, rim[:1]], axis=0), axis=1).sum()
    assert body.val().Volume() == pytest.approx(length * np.pi * r * r, rel=0.1)


def test_a_fixed_frame_says_where_it_dies():
    rim = ellipse()
    with pytest.raises(GeometryError, match="parallel to up"):
        sweep_path(rim, [circle_section(0.6) for _ in rim], frame="up", closed=True)


def test_auto_falls_back_to_transport():
    rim = ellipse()
    body = sweep_path(rim, [circle_section(0.6) for _ in rim], frame="auto",
                 closed=True)
    assert body.val().Volume() > 0


def test_a_fixed_frame_is_used_where_it_works():
    """A temple has a real up, and the section must not roll along it."""
    p = line()
    tan, across, up = fixed_frames(p)
    assert np.allclose(np.abs(up[:, 1]), np.abs(up[0, 1]), atol=1e-6)


def test_transport_keeps_the_frame_orthonormal():
    tan, nor, binor = transported_frames(ellipse(), closed=True)
    assert np.allclose(np.einsum("ij,ij->i", tan, nor), 0.0, atol=1e-9)
    assert np.allclose(np.linalg.norm(nor, axis=1), 1.0, atol=1e-9)
    assert np.allclose(np.linalg.norm(binor, axis=1), 1.0, atol=1e-9)


def test_transport_does_not_spin_the_section():
    """Along a straight run the frame must not rotate at all."""
    _, nor, _ = transported_frames(line())
    assert np.allclose(nor, nor[0], atol=1e-9)


def test_a_repeated_point_is_refused():
    p = np.array([[0, 0, 0], [0, 0, 0], [1, 0, 0]], float)
    with pytest.raises(GeometryError, match="repeats a point"):
        transported_frames(p)


def test_resample_spaces_a_path_evenly():
    p = resample_path(ellipse(), 300, closed=True)
    d = np.linalg.norm(np.diff(np.r_[p, p[:1]], axis=0), axis=1)
    assert d.max() / d.min() < 1.05


def test_tube_takes_a_radius_per_point():
    p = line()
    r = np.linspace(1.2, 0.6, len(p))
    assert tube(p, r).val().Volume() > 0
    with pytest.raises(GeometryError, match="one radius per point"):
        tube(p, np.array([1.0, 2.0]))


def test_sweep_sections_still_works():
    """The old name is kept so existing code keeps running."""
    from rgeo import sweep_sections
    p = line()
    sec = np.array([(-2, -5), (2, -5), (2, 5), (-2, 5)], float)
    assert sweep_sections(p, [sec] * len(p)).val().Volume() > 0
