import numpy as np
import pytest

from rgeo import Cylinder, GeometryError, Plane, Sphere, Torus


def outline(rx=30, ry=20, n=80, dx=0.0):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.c_[np.cos(t) * rx + dx, np.sin(t) * ry]


@pytest.mark.parametrize("surface", [Plane(), Cylinder(200.0),
                                     Torus.from_radii(88.3, 220.0)])
def test_trimmed_face_with_a_hole(surface):
    f = surface.face(surface.edge(outline()), [surface.edge(outline(12, 8))])
    assert f.Area() > 0 and f.isValid()


def test_torus_takes_three_holes():
    s = Torus.from_radii(88.3, 220.0)
    holes = [s.edge(outline(12, 8, dx=-28)), s.edge(outline(12, 8, dx=28)),
             s.edge(outline(5, 3))]
    f = s.face(s.edge(outline(60, 26)), holes)
    assert f.Area() > 0 and f.isValid()
    assert len(f.Wires()) == 4


def test_plane_has_no_sag():
    assert Plane().sag(30, 20) == pytest.approx(0.0)


def test_cylinder_sags_across_but_not_along():
    c = Cylinder(200.0)
    assert c.sag(40, 0) < -3.0
    assert c.sag(0, 40) == pytest.approx(0.0)


def test_torus_carries_both_curvatures():
    t = Torus.from_radii(vertical=88.3, horizontal=220.0)
    assert t.sag(0, 25) < -3.0          # base curve, vertically
    assert t.sag(60, 0) < -8.0          # wrap, horizontally
    assert t.sag(60, 0) < t.sag(0, 25)  # the wrap dominates at the edge


def test_base_curve_converts_to_a_radius():
    assert Sphere.from_base_curve(6.0).radius == pytest.approx(88.333, abs=1e-2)


def test_sphere_says_so_instead_of_returning_an_empty_face():
    """The outline encloses the pole, where the parametrisation is singular."""
    s = Sphere.from_base_curve(6.0)
    with pytest.raises(GeometryError, match="pole"):
        s.face(s.edge(outline()))


def test_depth_offsets_towards_the_back():
    for s in (Cylinder(200.0), Torus.from_radii(88.3, 220.0)):
        assert s.z(10, 5, 0.0) - s.z(10, 5, 4.0) == pytest.approx(4.0, abs=0.25)
