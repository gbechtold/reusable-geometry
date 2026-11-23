"""Sweeping a section along a path, including paths that close on themselves.

The hard part of a sweep is not the section, it is deciding which way is "up"
at every point. Two frames are useful and they fail in different places:

**Fixed up.** `across = up x tangent` with `up` pinned, usually to (0, 1, 0).
Right for anything that has a real up - a temple, a handle, a rail - because
the section then never rolls. Degenerate wherever the path runs parallel to
`up`: the cross product goes to zero and the section collapses to nothing.

**Parallel transport.** Each frame is the previous one rotated by the smallest
rotation that takes the previous tangent onto the current one. No preferred
direction, therefore no singularity anywhere, and the section does not spin
about the path the way a recomputed-from-scratch frame does. The cost is that
"up" drifts, so a part that needs a consistent up does not want this.

A closed rim needs the second: it runs vertically at its left and right
extremes, which is exactly where a fixed-up frame dies. That failure is what
this module was written for.
"""
from __future__ import annotations

import cadquery as cq
import numpy as np

from .surface import GeometryError


def resample_path(pts, n: int, closed: bool = False) -> np.ndarray:
    """n points spaced evenly along a 3D path."""
    p = np.asarray(pts, float)
    ring = np.r_[p, p[:1]] if closed else p
    d = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(ring, axis=0), axis=1))]
    if d[-1] <= 0:
        raise GeometryError("the path has zero length")
    s = np.linspace(0, d[-1], n, endpoint=not closed)
    return np.c_[tuple(np.interp(s, d, ring[:, k]) for k in range(3))]


def transported_frames(path, closed: bool = False):
    """(tangent, normal, binormal) at each point, parallel-transported."""
    p = np.asarray(path, float)
    tan = (np.roll(p, -1, axis=0) - np.roll(p, 1, axis=0)) if closed \
        else np.gradient(p, axis=0)
    lens = np.linalg.norm(tan, axis=1, keepdims=True)
    if (lens < 1e-12).any():
        raise GeometryError("the path repeats a point; resample it first")
    tan = tan / lens

    seed = np.array([0.0, 0.0, 1.0])
    if abs(float(np.dot(seed, tan[0]))) > 0.9:
        seed = np.array([0.0, 1.0, 0.0])
    nor = np.empty_like(tan)
    nor[0] = seed - np.dot(seed, tan[0]) * tan[0]
    nor[0] /= np.linalg.norm(nor[0])

    for i in range(1, len(p)):
        a, b = tan[i - 1], tan[i]
        axis = np.cross(a, b)
        s = float(np.linalg.norm(axis))
        if s < 1e-9:                      # straight run: nothing to rotate
            v = nor[i - 1]
        else:                             # Rodrigues about the turn axis
            k = axis / s
            ang = float(np.arccos(np.clip(np.dot(a, b), -1.0, 1.0)))
            v0 = nor[i - 1]
            v = (v0 * np.cos(ang) + np.cross(k, v0) * np.sin(ang)
                 + k * float(np.dot(k, v0)) * (1 - np.cos(ang)))
        v = v - np.dot(v, tan[i]) * tan[i]
        nor[i] = v / np.linalg.norm(v)
    return tan, nor, np.cross(tan, nor)


def fixed_frames(path, up=(0.0, 1.0, 0.0), closed: bool = False):
    """(tangent, across, up) with `up` pinned. Raises where it degenerates."""
    p = np.asarray(path, float)
    tan = (np.roll(p, -1, axis=0) - np.roll(p, 1, axis=0)) if closed \
        else np.gradient(p, axis=0)
    lens = np.linalg.norm(tan, axis=1, keepdims=True)
    if (lens < 1e-12).any():
        raise GeometryError("the path repeats a point; resample it first")
    tan = tan / lens

    u = np.asarray(up, float)
    u = u / np.linalg.norm(u)
    across = np.cross(np.broadcast_to(u, tan.shape), tan)
    mag = np.linalg.norm(across, axis=1)
    if mag.min() < 0.05:
        worst = int(np.argmin(mag))
        raise GeometryError(
            f"the path runs parallel to up={tuple(round(float(x), 3) for x in u)} at point "
            f"{worst} of {len(p)}, where a fixed frame collapses. Use "
            'frame="transport" - a closed rim always needs it.')
    across = across / mag[:, None]
    return tan, across, np.cross(tan, across)


def sweep_path(path, sections, frame: str = "auto", up=(0.0, 1.0, 0.0),
          closed: bool = False, ruled: bool = True) -> cq.Workplane:
    """Sweep per-point 2D sections along a 3D path.

    `sections` is one (m, 2) outline per path point, in the local frame.

    frame="up"        pin the up direction. No roll; dies on vertical runs.
    frame="transport" parallel transport. Works anywhere; up drifts.
    frame="auto"      try "up", fall back to "transport" where it would die.
    """
    p = np.asarray(path, float)
    if len(p) != len(sections):
        raise GeometryError("one section per path point, please")
    if closed:
        frame = "transport" if frame == "auto" else frame

    if frame == "auto":
        try:
            tan, a, b = fixed_frames(p, up, closed)
        except GeometryError:
            tan, a, b = transported_frames(p, closed)
    elif frame == "up":
        tan, a, b = fixed_frames(p, up, closed)
    elif frame == "transport":
        tan, a, b = transported_frames(p, closed)
    else:
        raise GeometryError(f"unknown frame {frame!r}")

    wires = []
    for i, sec in enumerate(sections):
        pts = [cq.Vector(*(p[i] + a[i] * u_ + b[i] * v_))
               for u_, v_ in np.asarray(sec, float)]
        wires.append(cq.Workplane("XY").polyline(pts).close().wire().val())
    if closed:
        wires.append(wires[0])

    solid = cq.Solid.makeLoft(wires, ruled=ruled)
    if solid.Volume() < 0:
        solid = cq.Solid(solid.wrapped.Reversed())
    return cq.Workplane("XY").add(solid)


def circle_section(radius: float, n: int = 12) -> np.ndarray:
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.c_[np.cos(a) * radius, np.sin(a) * radius]


def tube(path, radius, sides: int = 12, closed: bool = False,
         resample: int | None = None) -> cq.Workplane:
    """Round wire along a path - a rim, a bar, a bridge, a pad arm.

    `radius` may be a single value or one per point, for wire that tapers.
    """
    p = np.asarray(path, float)
    if resample:
        p = resample_path(p, resample, closed)
    r = np.full(len(p), float(radius)) if np.isscalar(radius) \
        else np.asarray(radius, float)
    if len(r) != len(p):
        raise GeometryError("one radius per point, or a single number")
    return sweep_path(p, [circle_section(float(rr), sides) for rr in r],
                      frame="transport" if closed else "auto", closed=closed)
