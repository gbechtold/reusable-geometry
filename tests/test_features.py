import numpy as np
import pytest

from rgeo import (Boss, BodyFeature, CableTemple, ClipHinge, EdgeBreak, Feature,
                  GeometryError, Groove, LibraryTemple, MechanicalFeature,
                  ProfileFeature, Shell, SkullTemple, Temple, Torus,
                  WallProfile, distance, mesh_report)


# --- the hierarchy itself ------------------------------------------------
def test_the_hierarchy_says_what_can_go_wrong():
    assert issubclass(ClipHinge, MechanicalFeature)
    assert issubclass(MechanicalFeature, BodyFeature)
    assert issubclass(SkullTemple, Temple) and issubclass(Temple, BodyFeature)
    assert issubclass(Groove, ProfileFeature)
    for cls in (BodyFeature, ProfileFeature):
        assert issubclass(cls, Feature)


def test_a_feature_cannot_be_built_without_checks():
    with pytest.raises(TypeError):
        Feature(name="nameless")        # abstract


def test_profile_features_compose_onto_a_wall():
    p = WallProfile(6.0, outward=True)
    p = EdgeBreak(size=0.6).apply_to(p)
    p = Groove(at=2.6, width=0.9, depth=0.7).apply_to(p)
    deepest = max(p.steps(), key=lambda s: s[1])
    assert float(deepest[0]) == pytest.approx(2.6)
    assert deepest[1] == pytest.approx(0.7)


def test_edge_break_can_round_instead_of_chamfer():
    chamfered = EdgeBreak(size=0.5, style="chamfer").apply_to(WallProfile(4.0))
    rounded = EdgeBreak(size=0.5, style="round").apply_to(WallProfile(4.0))
    assert len(rounded.steps()) > len(chamfered.steps())
    with pytest.raises(GeometryError):
        EdgeBreak(style="bevelish").apply_to(WallProfile(4.0))


def test_boss_returns_a_thickness_per_point(ring):
    outer, _ = ring
    boss = Boss(angle_centre=90.0, angle_width=40.0, thickness=9.0)
    t = boss.thickness_for(outer, 6.0)
    assert len(t) == len(outer)
    assert t.max() == pytest.approx(9.0, abs=0.01)
    assert t.min() == pytest.approx(6.0, abs=0.01)


def test_boss_actually_adds_material(ring):
    outer, hole = ring
    rim = WallProfile(6.0).chamfer_both(1.0)
    opening = WallProfile(6.0, outward=True).chamfer_both(0.6)
    boss = Boss(angle_centre=90.0, angle_width=40.0, thickness=10.0)
    plain = (Shell(Torus.from_radii(88.3, 220.0))
             .outer(outer, rim).hole(hole, opening).build())
    raised = (Shell(Torus.from_radii(88.3, 220.0))
              .outer(outer, rim, thickness=boss.thickness_for(outer, 6.0))
              .hole(hole, opening).build())
    assert (mesh_report(raised)["volume_mm3"]
            > mesh_report(plain)["volume_mm3"] * 1.02)


# --- the clip hinge ------------------------------------------------------
def test_hinge_halves_are_sound_and_clear_each_other():
    h = ClipHinge()
    assert mesh_report(h.female(), 0.05)["watertight"]
    assert mesh_report(h.male(), 0.05)["watertight"]
    assert h.measured_gap() > 0


def test_hinge_gap_is_measured_not_claimed():
    """Change the clearance and the measured gap has to follow."""
    tight, loose = ClipHinge(clearance=0.10), ClipHinge(clearance=0.30)
    assert loose.measured_gap() > tight.measured_gap() + 0.12
    assert tight.measured_gap() == pytest.approx(0.10, abs=0.06)
    assert loose.measured_gap() == pytest.approx(0.30, abs=0.06)


def test_hinge_actually_snaps():
    """The pin has to be wider than the narrow point, or it just falls out."""
    h = ClipHinge()
    assert h.snap_interference() > 0
    assert h.narrow < 2 * h.pin_radius
    assert h.mouth > 2 * h.pin_radius      # but it still starts easily


def test_a_hinge_that_cannot_snap_fails_its_checks():
    loose = ClipHinge(snap_angle=89.0)     # narrow point as wide as the socket
    failed = [c.name for c in loose.checks().failed]
    assert any("snap interference" in n for n in failed)


def test_a_hinge_with_paper_thin_jaws_fails_its_checks():
    thin = ClipHinge(height=3.4)
    assert any("jaw thickness" in c.name for c in thin.checks().failed)


def test_hinge_can_be_placed():
    here, there = ClipHinge(), ClipHinge(origin=(30.0, 2.0, -5.0))
    a = here.female().val().BoundingBox()
    b = there.female().val().BoundingBox()
    assert b.xmin == pytest.approx(a.xmin + 30.0, abs=1e-6)
    assert there.measured_gap() == pytest.approx(here.measured_gap(), abs=1e-6)


def test_distance_between_separate_shapes():
    import cadquery as cq
    a = cq.Workplane("XY").box(2, 2, 2)
    b = cq.Workplane("XY").box(2, 2, 2).translate((5, 0, 0))
    assert distance(a, b) == pytest.approx(3.0, abs=1e-6)


# --- temples -------------------------------------------------------------
@pytest.mark.parametrize("cls", [Temple, SkullTemple, LibraryTemple, CableTemple])
def test_every_temple_builds_and_passes(cls):
    t = cls()
    assert mesh_report(t.solids()["arm"], 0.05)["watertight"]
    assert not t.checks().failed, [c.name for c in t.checks().failed]


def test_subclasses_differ_only_in_the_drop():
    f = np.linspace(0, 1, 50)
    assert np.allclose(Temple().drop(f), 0.0)
    assert np.allclose(LibraryTemple().drop(f), 0.0)
    assert SkullTemple().drop(f)[-1] < -10.0
    assert CableTemple().drop(f)[-1] < -15.0


def test_a_temple_tapers_towards_the_tip():
    t = SkullTemple()
    front, back = t.section(0.0), t.section(1.0)
    assert back[:, 1].max() < front[:, 1].max()


def test_a_temple_that_is_too_short_fails_its_checks():
    assert any("length" in c.name for c in SkullTemple(length=80.0).checks().failed)


def test_a_temple_with_a_hinge_brings_the_pin_along():
    t = SkullTemple(hinge=ClipHinge())
    assert set(t.solids()) == {"arm", "pin"}


def test_an_integrated_hinge_merges_into_one_body():
    t = SkullTemple(hinge=ClipHinge(), integrated_hinge=True)
    parts = t.solids()
    assert set(parts) == {"arm"}
    assert mesh_report(parts["arm"], 0.05)["watertight"]


def test_a_section_too_small_to_chamfer_is_refused():
    with pytest.raises(GeometryError, match="chamfer"):
        SkullTemple(thickness=1.0, thickness_back=1.0, chamfer=2.0).arm()
