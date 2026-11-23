import numpy as np
import pytest

from rgeo import (Camera, Shell, Torus, WallProfile, fixed_camera, load_stl,
                  mesh, rock, silhouette, turntable, turntable_gif, write_gif)


@pytest.fixture
def body(ring):
    outer, hole = ring
    return (Shell(Torus.from_radii(88.3, 220.0))
            .outer(outer, WallProfile(6.0).chamfer_both(1.0))
            .hole(hole, WallProfile(6.0, outward=True).chamfer_both(0.6))
            .build())


def test_turntable_renders_the_frames_asked_for(body):
    v, t = mesh(body, 0.08, 0.4)
    frames = turntable(v, t, size=(160, 120), frames=8)
    assert len(frames) == 8
    assert all(f.shape == (120, 160) for f in frames)


def test_a_full_turn_does_not_repeat_the_first_frame(body):
    """360 degrees has to loop seamlessly, so the last frame must not be the
    first one again."""
    v, t = mesh(body, 0.08, 0.4)
    frames = turntable(v, t, size=(120, 90), frames=6, sweep=360.0)
    assert not np.array_equal(frames[0], frames[-1])


def test_a_partial_sweep_includes_both_ends(body):
    v, t = mesh(body, 0.08, 0.4)
    a = turntable(v, t, size=(120, 90), frames=2, sweep=90.0)
    assert not np.array_equal(a[0], a[1])


def test_the_camera_holds_still_while_the_part_turns(body):
    """Fitting per frame would make the model breathe as its silhouette
    changes width. The scale has to be the same at every angle."""
    v, t = mesh(body, 0.08, 0.4)
    cams = [fixed_camera(v, (200, 150), yaw=a) for a in (0, 45, 90, 180)]
    assert len({round(c.scale, 9) for c in cams}) == 1


def test_nothing_leaves_the_frame_at_any_angle(body):
    v, t = mesh(body, 0.08, 0.4)
    size = (200, 150)
    for yaw in (0, 37, 90, 143, 214, 300):
        cam = fixed_camera(v, size, yaw=yaw)
        m = silhouette(v, t, cam, size)
        assert m[0, :].sum() == 0 and m[-1, :].sum() == 0
        assert m[:, 0].sum() == 0 and m[:, -1].sum() == 0


def test_rock_returns_to_where_it_started(body):
    v, t = mesh(body, 0.08, 0.4)
    frames = rock(v, t, size=(140, 100), frames=8, amplitude=30.0)
    assert len(frames) == 8
    assert np.abs(frames[0].astype(int) - frames[-1].astype(int)).mean() < 12


def test_write_gif_produces_an_animation(body, tmp_path):
    v, t = mesh(body, 0.08, 0.4)
    path = write_gif(turntable(v, t, size=(120, 90), frames=5),
                     tmp_path / "turn.gif", fps=12)
    from PIL import Image
    with Image.open(path) as im:
        assert im.n_frames == 5
        assert im.size == (120, 90)
    assert path.stat().st_size > 0


def test_turntable_gif_in_one_call(body, tmp_path):
    v, t = mesh(body, 0.08, 0.4)
    path = turntable_gif(v, t, tmp_path / "one.gif", size=(100, 80), frames=4)
    assert path.exists()


def test_stl_round_trip(body, tmp_path):
    """Export, read back, and the mesh has to be the same size."""
    import cadquery as cq
    path = tmp_path / "body.stl"
    cq.exporters.export(body, str(path))
    v, t = load_stl(path)
    bb = body.val().BoundingBox()
    span = v.max(axis=0) - v.min(axis=0)
    assert span[0] == pytest.approx(bb.xlen, abs=0.3)
    assert span[1] == pytest.approx(bb.ylen, abs=0.3)
    assert len(t) > 100


def test_stl_loader_merges_shared_vertices(tmp_path):
    """A triangle soup has three vertices per face; merging has to collapse
    the ones that coincide."""
    import cadquery as cq
    path = tmp_path / "cube.stl"
    cq.exporters.export(cq.Workplane("XY").box(10, 10, 10), str(path))
    merged, t = load_stl(path, merge_vertices=True)
    soup, _ = load_stl(path, merge_vertices=False)
    assert len(merged) == 8          # a cube has eight corners
    assert len(soup) == len(t) * 3


def test_stl_loader_reads_ascii(tmp_path):
    path = tmp_path / "tri.stl"
    path.write_text(
        "solid t\nfacet normal 0 0 1\nouter loop\n"
        "vertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\n"
        "endloop\nendfacet\nendsolid t\n")
    v, t = load_stl(path)
    assert len(t) == 1 and len(v) == 3


def test_a_truncated_stl_says_so(tmp_path):
    path = tmp_path / "bad.stl"
    path.write_bytes(b"\0" * 80 + (999).to_bytes(4, "little") + b"\0" * 50)
    with pytest.raises(ValueError, match="truncated"):
        load_stl(path)
