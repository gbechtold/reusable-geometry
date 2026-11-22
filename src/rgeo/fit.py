"""Measure a model against a reference image, and search the parameters that
the reference does not pin down.

Two rules keep the number honest:

1. **Fit the camera, never the geometry.** The optimiser is allowed to move
   the viewpoint until it matches the photograph. It is not allowed to touch
   the part. What is left over is then a statement about shape.
2. **Report millimetres, not just overlap.** IoU is harsh on anything thin: a
   5 mm wide rim offset by half a millimetre loses ten points of overlap and
   reads like a much bigger error than it is. The distance between the two
   outlines says how far off the shape actually is.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np
from scipy.optimize import minimize

from .render import Camera, fit_to_frame, shade, silhouette


def iou(a, b) -> float:
    a, b = a > 0, b > 0
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 0.0


def outline_distance(model_mask, reference_mask, px_per_mm: float):
    """Mean and 95th percentile distance from the model's outline to the
    reference's, in millimetres."""
    ref_edge = cv2.Canny((reference_mask > 0).astype(np.uint8) * 255, 50, 150)
    mod_edge = cv2.Canny((model_mask > 0).astype(np.uint8) * 255, 50, 150)
    dist = cv2.distanceTransform(255 - ref_edge, cv2.DIST_L2, 5)
    d = dist[mod_edge > 0]
    if not len(d):
        return float("nan"), float("nan")
    return float(d.mean() / px_per_mm), float(np.percentile(d, 95) / px_per_mm)


@dataclass
class FitResult:
    camera: Camera
    iou: float
    mean_mm: float = float("nan")
    p95_mm: float = float("nan")
    model_mask: np.ndarray | None = field(default=None, repr=False)

    def summary(self) -> str:
        return (f"overlap {self.iou * 100:5.1f}%   outline off by "
                f"{self.mean_mm:.2f} mm mean, {self.p95_mm:.2f} mm p95   "
                f"(yaw {self.camera.yaw:6.1f}, {self.camera.scale:4.2f} px/mm)")


def fit_camera(v, t, reference_mask, start: Camera | None = None, size=None,
               rounds: int = 3, iters: int = 200) -> FitResult:
    """Move the viewpoint until the silhouettes line up as well as they can."""
    size = size or (reference_mask.shape[1], reference_mask.shape[0])
    start = start or Camera()
    cam0 = fit_to_frame(v, start, size, margin=0.04)
    x0 = np.array(cam0.as_list(), float)

    def loss(x):
        if x[3] <= 0:
            return 1.0
        return 1.0 - iou(silhouette(v, t, Camera.from_list(x), size), reference_mask)

    best, step = x0, np.array([7.0, 5.0, 3.0, x0[3] * 0.07, 16.0, 16.0])
    for _ in range(rounds):
        r = minimize(loss, best, method="Nelder-Mead",
                     options={"maxiter": iters, "xatol": 0.02, "fatol": 1e-4,
                              "initial_simplex": np.vstack([best, best + np.diag(step)])})
        best, step = r.x, step * 0.45

    cam = Camera.from_list(best)
    mask = silhouette(v, t, cam, size)
    mean_mm, p95 = outline_distance(mask, reference_mask, cam.scale)
    return FitResult(cam, 1.0 - loss(best), mean_mm, p95, mask)


def comparison_strip(photo_bgr, model_img, model_mask, reference_mask,
                     result: FitResult, title: str = "") -> np.ndarray:
    """Photo, model and overlay side by side - the picture that makes the
    number checkable."""
    h, w = reference_mask.shape[:2]
    photo = cv2.resize(photo_bgr, (w, h), interpolation=cv2.INTER_AREA)
    over = np.full((h, w, 3), 255, np.uint8)
    over[reference_mask > 0] = (210, 190, 120)     # BGR: reference, pale blue
    over[model_mask > 0] = (120, 170, 235)         # model, orange
    over[(reference_mask > 0) & (model_mask > 0)] = (90, 90, 90)
    out = np.hstack([photo, cv2.cvtColor(model_img, cv2.COLOR_GRAY2BGR), over])
    cv2.rectangle(out, (0, 0), (3 * w, 34), (245, 245, 245), -1)
    for i, txt in enumerate([f"{title} reference".strip(), "model",
                             "overlay: reference blue, model orange, grey = both"]):
        cv2.putText(out, txt, (i * w + 14, 24), 0, 0.6, (40, 40, 40), 1, cv2.LINE_AA)
    cv2.putText(out, result.summary(), (2 * w + 14, h - 14), 0, 0.55,
                (40, 40, 40), 1, cv2.LINE_AA)
    return out


def sweep(build, grid: dict, score, log=print):
    """Grid search over parameters the reference cannot pin down.

    `build(**combo)` returns whatever `score(built)` takes, and `score` returns
    a FitResult or a float. Results come back sorted, best first, with every
    combination kept - a flat optimum is information, and quietly reporting
    only the winner hides it.
    """
    import itertools
    keys = list(grid)
    results = []
    for combo in itertools.product(*(grid[k] for k in keys)):
        kw = dict(zip(keys, combo))
        try:
            s = score(build(**kw))
        except Exception as e:                                    # noqa: BLE001
            log(f"  {kw}  build failed: {str(e)[:60]}")
            continue
        value = s.iou if isinstance(s, FitResult) else float(s)
        row = {**kw, "score": value}
        if isinstance(s, FitResult):
            row["mean_mm"] = s.mean_mm
        results.append(row)
        extra = f"   outline {row['mean_mm']:5.2f} mm" if "mean_mm" in row else ""
        log(f"  {kw}   score {value * 100:5.1f}%{extra}")
    results.sort(key=lambda r: -r["score"])
    if results:
        spread = results[0]["score"] - results[-1]["score"]
        if spread < 0.02:
            log(f"  flat optimum: best and worst differ by {spread * 100:.1f} "
                "points, so this parameter is not constrained by the reference")
    return results
