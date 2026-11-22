import numpy as np
import pytest

from rgeo import (Camera, CheckList, Shell, Torus, WallProfile, fit_camera,
                  fit_to_frame, iou, mesh, mesh_report, outline_distance,
                  shade, silhouette, sweep, trace)


@pytest.fixture
def body(ring):
    outer, hole = ring
    return (Shell(Torus.from_radii(88.3, 220.0))
            .outer(outer, WallProfile(6.0).chamfer_both(1.0))
            .hole(hole, WallProfile(6.0, outward=True).chamfer_both(0.6))
            .build())


def test_iou_of_a_mask_with_itself():
    m = np.zeros((40, 40), np.uint8)
    m[10:30, 10:30] = 255
    assert iou(m, m) == pytest.approx(1.0)
    assert iou(m, np.zeros_like(m)) == 0.0


def test_outline_distance_measures_a_known_shift():
    a = np.zeros((200, 200), np.uint8); a[50:150, 50:150] = 255
    b = np.zeros((200, 200), np.uint8); b[50:150, 60:160] = 255
    mean_mm, _ = outline_distance(b, a, px_per_mm=10.0)
    assert 0.2 < mean_mm < 0.6          # a 10 px shift at 10 px/mm


def test_camera_fit_recovers_a_hidden_viewpoint(body):
    """The whole measuring chain in one test: render from a viewpoint the
    fitter is not told, then see whether it finds it again."""
    v, t = mesh(body, 0.05, 0.3)
    size = (400, 300)
    truth = fit_to_frame(v, Camera(yaw=-22.0, pitch=9.0, roll=1.5), size, 0.1)
    target = silhouette(v, t, truth, size)

    result = fit_camera(v, t, target, start=Camera(yaw=-32, pitch=18), size=size)
    assert result.iou > 0.97
    assert abs(result.camera.yaw - truth.yaw) < 3.0
    assert result.mean_mm < 0.5


def test_silhouette_keeps_holes_open(body):
    v, t = mesh(body, 0.05, 0.3)
    cam = fit_to_frame(v, Camera(), (300, 220))
    m = silhouette(v, t, cam, (300, 220))
    assert m[110, 150] == 0             # middle of the opening
    assert m.sum() > 0


def test_sweep_reports_a_flat_optimum(capsys):
    lines = []
    sweep(lambda k: k, {"k": [1.0, 1.001, 1.002]}, score=lambda k: 0.5 + k * 1e-5,
          log=lines.append)
    assert any("flat optimum" in line for line in lines)


def test_sweep_sorts_best_first():
    out = sweep(lambda k: k, {"k": [0.1, 0.9, 0.5]}, score=float, log=lambda *_: None)
    assert [r["k"] for r in out] == [0.9, 0.5, 0.1]


def test_trace_round_trips_through_an_image(body, tmp_path):
    """Render the body, trace the render, and check the outline comes back."""
    import cv2
    v, t = mesh(body, 0.05, 0.3)
    size = (600, 420)
    cam = fit_to_frame(v, Camera(), size, margin=0.12)
    img, _ = shade(v, t, cam, size, background=252)
    path = tmp_path / "render.png"
    cv2.imwrite(str(path), cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))

    traced = trace(str(path), threshold=235, hull_holes_above=0)
    assert len(traced.holes) == 1
    scaled = traced.scaled(1.0 / cam.scale,
                           origin=(cam.cx, cam.cy)).tidy(240, 160)
    width = scaled.outer[:, 0].max() - scaled.outer[:, 0].min()
    assert width == pytest.approx(80.0, abs=1.5)    # the 40 mm radius outline


def test_mirror_makes_a_mask_symmetric():
    from rgeo import mirror_mask
    m = np.zeros((60, 80), np.uint8)
    m[20:40, 30:70] = 255               # off-centre blob
    out, axis = mirror_mask(m)
    k = min(axis, out.shape[1] - axis)
    assert np.array_equal(out[:, axis:axis + k],
                          np.fliplr(out[:, axis - k:axis]))


def test_checklist_fails_loudly(body):
    cl = (CheckList().watertight("body", body)
          .at_least("wall", 1.0, 2.5))
    assert len(cl.failed) == 1
    assert cl.exit_code() == 1
    assert "FAIL" in cl.report()


def test_mesh_report_merges_vertices(body):
    r = mesh_report(body)
    assert r["watertight"]
    assert r["triangles"] > 100
