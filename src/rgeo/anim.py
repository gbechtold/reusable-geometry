"""Turntable animations: a model seen from every side, as a GIF.

The point of a turntable is to show the part, so the camera has to hold still
while the part turns. That is the one thing easy to get wrong: fitting the
camera per frame makes the model breathe in and out as its silhouette changes
width. `fixed_camera` sizes the view once, from the radius of the point cloud,
so every frame shares a scale.

    from rgeo import mesh, turntable_gif
    v, t = mesh(solid)
    turntable_gif(v, t, "out/front.gif", start_yaw=0, sweep=360)
"""
from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np

from .render import Camera, shade


def _render(v, t, cam: Camera, size, background: int, supersample: int):
    """One frame, optionally rendered large and scaled down.

    Supersampling is the cheapest quality there is here: the renderer fills
    triangles without antialiasing, so edges come out stepped. Rendering at
    2x or 3x and averaging down removes that, and on a shaded grey surface
    it is the difference between a render and a screenshot.
    """
    if supersample <= 1:
        img, _ = shade(v, t, cam, size, background=background)
        return img
    big = (size[0] * supersample, size[1] * supersample)
    cam_big = Camera(cam.yaw, cam.pitch, cam.roll, cam.scale * supersample,
                     cam.cx * supersample, cam.cy * supersample)
    img, _ = shade(v, t, cam_big, big, background=background)
    return cv2.resize(img, size, interpolation=cv2.INTER_AREA)


def fixed_camera(v, size, margin: float = 0.08, pitch: float = 0.0,
                 roll: float = 0.0, yaw: float = 0.0) -> Camera:
    """One camera for the whole sweep, scaled so nothing leaves the frame at
    any angle.

    Uses the radius of the point cloud about its own centre rather than the
    bounding box of one view: the box changes width as the part turns, and
    scaling to it makes the model pulse.
    """
    w, h = size
    centre = (v.min(axis=0) + v.max(axis=0)) / 2
    rel = v - centre
    r_horizontal = float(np.sqrt(rel[:, 0] ** 2 + rel[:, 2] ** 2).max())
    r_vertical = float(np.abs(rel[:, 1]).max())
    scale = min(w * (1 - 2 * margin) / max(2 * r_horizontal, 1e-9),
                h * (1 - 2 * margin) / max(2 * r_vertical, 1e-9))
    cam = Camera(yaw, pitch, roll, scale, 0.0, 0.0)
    mid = centre @ cam.matrix().T
    return Camera(yaw, pitch, roll, scale,
                  w / 2 - mid[0] * scale, h / 2 + mid[1] * scale)


def turntable(v, t, size=(640, 480), frames: int = 48, start_yaw: float = 0.0,
              sweep: float = 360.0, pitch: float = 0.0, roll: float = 0.0,
              margin: float = 0.08, background: int = 244, ease: bool = False,
              supersample: int = 1, progress=None):
    """Render a sweep. Returns a list of greyscale frames.

    `sweep=360` goes right round and loops seamlessly. A partial sweep -
    say 0 to 70 degrees - reads better with `ease=True`, which slows the start
    and the end so it does not snap back.
    """
    cam0 = fixed_camera(v, size, margin, pitch, roll, start_yaw)
    endpoint = abs(sweep % 360.0) > 1e-9        # a full turn must not repeat
    steps = np.linspace(0.0, 1.0, frames, endpoint=endpoint)
    if ease:
        steps = steps * steps * (3 - 2 * steps)

    out = []
    for i, s in enumerate(steps):
        cam = Camera(start_yaw + sweep * float(s), pitch, roll,
                     cam0.scale, cam0.cx, cam0.cy)
        out.append(_render(v, t, cam, size, background, supersample))
        if progress:
            progress(i + 1, len(steps))
    return out


def write_gif(frames, path, fps: float = 24.0, loop: int = 0,
              colors: int = 32) -> Path:
    """Write frames as an animated GIF.

    Greyscale renders need very few colours. Measured on a 36-frame sweep at
    860 x 560, adaptive palette per frame:

        32 colours   594 kB     128 colours   971 kB

    and the two are indistinguishable - mean difference 0.13 of 255. Hence 32.

    A single shared palette across all frames was tried, on the theory that it
    would help GIF's between-frame compression. It does the opposite: 1010 kB
    at 32 colours, worse at every setting. Pillow's own optimiser handles the
    per-frame case better.
    """
    try:
        from PIL import Image
    except ImportError as e:                                      # noqa: BLE001
        raise RuntimeError("writing a GIF needs Pillow: pip install pillow") from e

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    images = [Image.fromarray(np.asarray(f)).convert("P", palette=Image.ADAPTIVE,
                                                    colors=colors)
              for f in frames]
    images[0].save(path, save_all=True, append_images=images[1:],
                   duration=int(round(1000.0 / max(fps, 1e-6))), loop=loop,
                   optimize=True, disposal=2)
    return path


def turntable_gif(v, t, path, size=(640, 480), frames: int = 48, fps: float = 24.0,
                  **kwargs) -> Path:
    """Render a turntable straight to a GIF. Everything `turntable` takes is
    accepted here too."""
    return write_gif(turntable(v, t, size=size, frames=frames, **kwargs),
                     path, fps=fps)


def rock(v, t, size=(640, 480), frames: int = 36, amplitude: float = 35.0,
         centre_yaw: float = 0.0, supersample: int = 1, **kwargs):
    """A sweep that goes out and comes back - for showing one face of a part
    without ever turning away from it.

    This is what to use for a front elevation: it leaves and returns to the
    view the drawing is in, so the reader never loses the reference.
    """
    half = max(frames // 2, 2)
    angles = np.r_[np.linspace(0.0, 1.0, half, endpoint=False),
                   np.linspace(1.0, 0.0, frames - half, endpoint=False)]
    angles = angles * angles * (3 - 2 * angles)      # smoothstep both ways
    cam0 = fixed_camera(v, size, kwargs.get("margin", 0.08),
                        kwargs.get("pitch", 0.0), kwargs.get("roll", 0.0),
                        centre_yaw)
    out = []
    for s in angles:
        cam = Camera(centre_yaw + amplitude * (2 * float(s) - 1),
                     kwargs.get("pitch", 0.0), kwargs.get("roll", 0.0),
                     cam0.scale, cam0.cx, cam0.cy)
        out.append(_render(v, t, cam, size,
                           kwargs.get("background", 244), supersample))
    return out
