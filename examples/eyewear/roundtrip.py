"""Render the model, trace the render back, and measure the two against each
other.

This is the measuring half of the pipeline, demonstrated without needing
anyone else's photograph: the "reference" is a render of the model itself,
seen from a viewpoint the fitter is not told about. If the chain works, the
fitter should recover that viewpoint and the outlines should land within a
fraction of a millimetre.

Against a real photograph the same code gave 0.32 mm on a traced front and
1.31 mm on a view nothing was traced from.

    python examples/eyewear/roundtrip.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from rgeo import (Camera, comparison_strip, fit_camera, fit_to_frame, mesh,
                  shade)
from front import build, parameters

OUT = Path(__file__).resolve().parent / "out"
SIZE = (820, 560)
TRUTH = Camera(yaw=-24.0, pitch=11.0, roll=2.0)     # what the fitter must find


def reference_image(v, t):
    """Stand in for a photograph: the model from an undisclosed viewpoint,
    rendered dark on light the way a product shot looks."""
    cam = fit_to_frame(v, TRUTH, SIZE, margin=0.10)
    img, mask = shade(v, t, cam, SIZE, background=250)
    photo = cv2.cvtColor(255 - (255 - img) // 2, cv2.COLOR_GRAY2BGR)
    return photo, mask, cam


def main() -> int:
    OUT.mkdir(exist_ok=True)
    solid = build(parameters())
    v, t = mesh(solid, 0.02, 0.15)

    photo, reference_mask, truth_cam = reference_image(v, t)
    cv2.imwrite(str(OUT / "roundtrip_reference.png"), photo)

    result = fit_camera(v, t, reference_mask, start=Camera(yaw=-35, pitch=20),
                        size=SIZE)
    img, _ = shade(v, t, result.camera, SIZE)
    cv2.imwrite(str(OUT / "roundtrip_compare.png"),
                comparison_strip(photo, img, result.model_mask, reference_mask,
                                 result, "rendered"))

    print("[camera]")
    print(f"  truth      yaw {truth_cam.yaw:7.2f}  pitch {truth_cam.pitch:6.2f}"
          f"  roll {truth_cam.roll:5.2f}  scale {truth_cam.scale:5.2f} px/mm")
    print(f"  recovered  yaw {result.camera.yaw:7.2f}  pitch {result.camera.pitch:6.2f}"
          f"  roll {result.camera.roll:5.2f}  scale {result.camera.scale:5.2f} px/mm")
    print(f"\n[match]\n  {result.summary()}")
    print(f"  wrote {OUT / 'roundtrip_compare.png'}")

    ok = result.mean_mm < 0.30 and abs(result.camera.yaw - truth_cam.yaw) < 3.0
    print(f"\n  {'ok' if ok else 'FAIL'}: the chain recovers the viewpoint and "
          "the outline to within a third of a millimetre")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
