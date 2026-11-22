import numpy as np
import pytest

from rgeo import (GeometryError, Shell, Torus, WallProfile, mass, mesh_report,
                  resample, sweep_sections)


def rim(t=6.0):
    return WallProfile(t).chamfer_both(1.0)


def opening(t=6.0):
    return WallProfile(t, outward=True).chamfer_both(0.6)


def test_a_shell_closes(ring):
    outer, hole = ring
    s = Shell(Torus.from_radii(88.3, 220.0)).outer(outer, rim()).hole(hole, opening())
    body = s.build()
    report = mesh_report(body)
    assert report["watertight"]
    assert body.val().Closed()
    assert report["volume_mm3"] > 0


def test_two_holes_and_a_groove(two_holes):
    outer, a, b = two_holes
    grooved = (WallProfile(6.0, outward=True).chamfer_both(0.6)
               .groove(at=2.6, width=0.9, depth=0.7))
    body = (Shell(Torus.from_radii(88.3, 220.0))
            .outer(outer, rim()).hole(a, grooved).hole(b, grooved).build())
    assert mesh_report(body)["watertight"]


def test_clockwise_input_is_corrected(ring):
    outer, hole = ring
    body = (Shell(Torus.from_radii(88.3, 220.0))
            .outer(outer[::-1], rim()).hole(hole[::-1], opening()).build())
    assert mesh_report(body)["watertight"]


def test_uneven_point_spacing_is_refused(ring):
    """Points placed by angle rather than arc length blow up the spline."""
    outer, hole = ring
    bad = outer.copy()
    bad[:10] = bad[0] + (bad[:10] - bad[0]) * 0.001
    with pytest.raises(GeometryError, match="Resample"):
        Shell(Torus.from_radii(88.3, 220.0)).outer(bad, rim())


def test_colliding_holes_are_caught_before_building():
    t = np.linspace(0, 2 * np.pi, 120, endpoint=False)
    outer = np.c_[np.cos(t) * 40, np.sin(t) * 25]
    a = np.c_[np.cos(t) * 15 - 15.2, np.sin(t) * 12]
    b = np.c_[np.cos(t) * 15 + 15.2, np.sin(t) * 12]
    wide = WallProfile(6.0, outward=True).chamfer_both(1.0)
    with pytest.raises(GeometryError, match="overlap"):
        Shell(Torus.from_radii(88.3, 220.0)).outer(outer, rim()) \
            .hole(a, wide).hole(b, wide).build()


def test_a_hole_outside_the_wall_is_caught(ring):
    outer, _ = ring
    far = outer * 0.99
    with pytest.raises(GeometryError, match="outside"):
        Shell(Torus.from_radii(88.3, 220.0)).outer(outer, rim()) \
            .hole(far, opening()).build()


def test_variable_thickness_adds_material(ring):
    """A boss raised out of the back face, without a boolean."""
    outer, hole = ring
    flat = (Shell(Torus.from_radii(88.3, 220.0))
            .outer(outer, rim()).hole(hole, opening()).build())
    ang = np.degrees(np.arctan2(outer[:, 1], outer[:, 0]))
    thick = np.where(np.abs(ang - 90) < 30, 10.0, 6.0)
    bossed = (Shell(Torus.from_radii(88.3, 220.0))
              .outer(outer, rim(), thickness=thick)
              .hole(hole, opening()).build())
    assert mesh_report(bossed)["volume_mm3"] > mesh_report(flat)["volume_mm3"] * 1.02


def test_variable_thickness_with_several_holes_is_refused(two_holes):
    outer, a, b = two_holes
    ang = np.degrees(np.arctan2(outer[:, 1], outer[:, 0]))
    thick = np.where(np.abs(ang - 90) < 30, 10.0, 6.0)
    with pytest.raises(GeometryError, match="varying thickness"):
        Shell(Torus.from_radii(88.3, 220.0)).outer(outer, rim(), thickness=thick) \
            .hole(a, opening()).hole(b, opening()).build()


def test_thickness_array_must_match_the_outline(ring):
    outer, hole = ring
    with pytest.raises(GeometryError, match="line up"):
        Shell(Torus.from_radii(88.3, 220.0)) \
            .outer(outer, rim(), thickness=np.full(7, 6.0)) \
            .hole(hole, opening()).build()


def test_ruled_caps_need_exactly_one_hole(two_holes):
    outer, a, b = two_holes
    with pytest.raises(GeometryError, match="exactly one hole"):
        Shell(Torus.from_radii(88.3, 220.0), cap="ruled") \
            .outer(outer, rim()).hole(a, opening()).hole(b, opening()).build()


def test_sweep_sections_builds_a_bar():
    path = np.c_[np.zeros(40), np.linspace(0, 4, 40), np.linspace(0, -120, 40)]
    sec = np.array([(-2, -5), (2, -5), (2, 5), (-2, 5)], float)
    body = sweep_sections(path, [sec] * 40)
    assert body.val().Volume() > 0
    assert mass(body) > 0


def test_mass_uses_the_mesh(ring):
    outer, hole = ring
    body = (Shell(Torus.from_radii(88.3, 220.0))
            .outer(outer, rim()).hole(hole, opening()).build())
    assert 1.0 < mass(body) < 100.0
