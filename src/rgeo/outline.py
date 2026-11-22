"""Closed 2D outlines: offset, resample, symmetry, set operations.

Offsetting goes through shapely's buffer rather than a per-vertex normal
offset. On concave runs a normal offset folds over itself, and the resulting
self-intersecting outline makes every surface built on it invalid two steps
later, where the cause is no longer visible.
"""
from __future__ import annotations

import math

import numpy as np
from shapely.geometry import Polygon


def signed_area(pts) -> float:
    pts = np.asarray(pts, float)
    return 0.5 * float(np.sum(pts[:, 0] * np.roll(pts[:, 1], -1)
                              - np.roll(pts[:, 0], -1) * pts[:, 1]))


def ccw(pts) -> np.ndarray:
    """Counter-clockwise, which is what everything downstream assumes."""
    pts = np.asarray(pts, float)
    return pts if signed_area(pts) > 0 else pts[::-1]


def resample(pts, n: int) -> np.ndarray:
    """n points spaced evenly along the outline."""
    pts = np.asarray(pts, float)
    ring = np.r_[pts, pts[:1]]
    d = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(ring, axis=0), axis=1))]
    s = np.linspace(0, d[-1], n, endpoint=False)
    return np.c_[np.interp(s, d, ring[:, 0]), np.interp(s, d, ring[:, 1])]


def smooth(pts, window: int) -> np.ndarray:
    """Moving average around the loop. Keep the window small: a wide one
    rounds real corners inward, which on a narrow rim shows up as a visible
    seam against the reference."""
    pts = np.asarray(pts, float)
    k = np.ones(window) / window
    ext = np.r_[pts[-window:], pts, pts[:window]]
    out = np.c_[np.convolve(ext[:, 0], k, "same"), np.convolve(ext[:, 1], k, "same")]
    return out[window:-window]


def offset(pts, d: float, keep_count: bool = True) -> np.ndarray:
    """Outward offset by `d` (negative = inward), self-intersections resolved."""
    pts = np.asarray(pts, float)
    if abs(d) < 1e-12:
        return pts
    poly = Polygon(pts)
    if not poly.is_valid:
        poly = poly.buffer(0)
    out = poly.buffer(d, join_style=1, quad_segs=16)
    if out.geom_type == "MultiPolygon":
        out = max(out.geoms, key=lambda g: g.area)
    if out.is_empty:
        raise ValueError(f"offset by {d} collapsed the outline")
    ring = ccw(np.array(out.exterior.coords)[:-1])
    if not keep_count:
        return ring
    ring = resample(ring, len(pts))
    k = int(np.argmin(np.linalg.norm(ring - pts[0], axis=1)))
    return np.roll(ring, -k, axis=0)


def clean(pts, corner_radius: float = 0.0) -> np.ndarray:
    """Make a traced region into a simple valid polygon, optionally rounding
    its corners."""
    poly = Polygon(np.asarray(pts, float))
    if not poly.is_valid:
        poly = poly.buffer(0)
    if corner_radius:
        poly = poly.buffer(corner_radius, join_style=1, quad_segs=16)
        poly = poly.buffer(-corner_radius, join_style=1, quad_segs=16)
    if poly.geom_type == "MultiPolygon":
        poly = max(poly.geoms, key=lambda g: g.area)
    return ccw(np.array(poly.exterior.coords)[:-1])


def subtract(pts, hole) -> np.ndarray:
    """Region minus region, as a single outline.

    Only the outer boundary comes back. Subtracting something that lies wholly
    inside leaves the boundary untouched - that case is a hole, and holes
    belong in Shell.hole(), not here.
    """
    a, b = Polygon(np.asarray(pts, float)), Polygon(np.asarray(hole, float))
    a = a if a.is_valid else a.buffer(0)
    b = b if b.is_valid else b.buffer(0)
    out = a.difference(b)
    if out.geom_type == "MultiPolygon":
        out = max(out.geoms, key=lambda g: g.area)
    if out.is_empty:
        raise ValueError("subtract removed everything")
    return ccw(np.array(out.exterior.coords)[:-1])


def cut_at_x(pts, x_cut: float, keep: str = "left") -> np.ndarray:
    """Trim at a vertical plane - a centre plane, a mirror line."""
    poly = Polygon(np.asarray(pts, float))
    poly = poly if poly.is_valid else poly.buffer(0)
    x0, y0, x1, y1 = poly.bounds
    box = Polygon([(x0 - 10, y0 - 10), (x_cut, y0 - 10), (x_cut, y1 + 10),
                   (x0 - 10, y1 + 10)]) if keep == "left" else \
        Polygon([(x_cut, y0 - 10), (x1 + 10, y0 - 10), (x1 + 10, y1 + 10),
                 (x_cut, y1 + 10)])
    out = poly.intersection(box)
    if out.geom_type == "MultiPolygon":
        out = max(out.geoms, key=lambda g: g.area)
    return ccw(np.array(out.exterior.coords)[:-1])


def radius_at(pts, deg: float) -> float:
    """Distance from the origin to the outline along a ray."""
    pts = np.asarray(pts, float)
    th = math.radians(deg)
    d = np.array([math.cos(th), math.sin(th)])
    a, b = pts, np.roll(pts, -1, axis=0)
    e = b - a
    den = e[:, 0] * d[1] - e[:, 1] * d[0]
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (a[:, 1] * d[0] - a[:, 0] * d[1]) / den
        s = np.where(abs(d[0]) > abs(d[1]),
                     (a[:, 0] + t * e[:, 0]) / d[0],
                     (a[:, 1] + t * e[:, 1]) / d[1])
    ok = (t >= -1e-9) & (t <= 1 + 1e-9) & (s > 0) & np.isfinite(s)
    if not ok.any():
        raise ValueError(f"no crossing at {deg} deg")
    return float(np.max(np.where(ok, s, -np.inf)))


def point_at_angle(pts, deg: float) -> np.ndarray:
    r = radius_at(pts, deg)
    th = math.radians(deg)
    return np.array([r * math.cos(th), r * math.sin(th)])


def align_by_angle(reference, pts) -> np.ndarray:
    """Resample `pts` so point i sits at the same polar angle as reference[i].

    Needed before spanning two outlines with a ruled face: a ruled surface
    matches its wires by parameter, not by position, so without this the face
    comes out twisted and the shell will not close.
    """
    ref = np.asarray(reference, float)
    ang = np.degrees(np.arctan2(ref[:, 1], ref[:, 0]))
    return np.array([point_at_angle(pts, a) for a in ang])


def mean_radial_gap(inner, outer, skip_sectors=(), n: int = 360):
    """Median, min and max wall width between two outlines - the rim width of
    a frame, the wall of a housing. `skip_sectors` are (lo, hi) angle ranges
    to ignore, e.g. where something sticks out."""
    gaps = []
    for a in np.linspace(-180, 180, n, endpoint=False):
        if any(lo - 4 <= a <= hi + 4 for lo, hi in skip_sectors):
            continue
        try:
            gaps.append(radius_at(outer, a) - radius_at(inner, a))
        except ValueError:
            pass
    g = np.array(gaps)
    return float(np.median(g)), float(g.min()), float(g.max())


def attachments(inner, outer, wall: float, tol: float = 0.8, min_run: int = 6):
    """Angular ranges where `outer` sticks out past `inner + wall`.

    Finds the bits that are not plain wall - a bridge, a hinge boss, a lug -
    by measurement rather than by hand-placed angles, so they move when the
    outline does.
    """
    rim = offset(inner, wall)
    outer = np.asarray(outer, float)
    ang = np.degrees(np.arctan2(outer[:, 1], outer[:, 0]))
    rad = np.linalg.norm(outer, axis=1)
    excess = rad - np.array([radius_at(rim, a) for a in ang])

    flags = excess > tol
    runs, run = [], []
    start = int(np.argmin(flags)) if flags.any() else 0
    for i in np.roll(np.arange(len(outer)), -start):
        if flags[i]:
            run.append(i)
        elif run:
            runs.append(run)
            run = []
    if run:
        runs.append(run)

    out = []
    for r in runs:
        if len(r) < min_run:
            continue
        a = ang[r]
        out.append({"index": r, "points": outer[r],
                    "angle_lo": float(a.min()), "angle_hi": float(a.max()),
                    "angle_mid": float(np.degrees(np.arctan2(
                        np.sin(np.radians(a)).mean(), np.cos(np.radians(a)).mean()))),
                    "max_excess": float(excess[r].max())})
    return out


def sector(pts, lo: float, hi: float, pad: float = 0.0, inner_radius: float = 0.0,
           reach: float = 500.0) -> np.ndarray:
    """The part of a region inside an angular wedge from the origin.

    `inner_radius` keeps the wedge off the origin. Worth setting on a curved
    surface: a vertex sitting exactly on the surface axis makes booleans
    against it return empty.
    """
    a0, a1 = math.radians(lo - pad), math.radians(hi + pad)
    n = 48
    arc = [(reach * math.cos(a0 + (a1 - a0) * i / n),
            reach * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]
    if inner_radius > 0:
        arc += [(inner_radius * math.cos(a1 - (a1 - a0) * i / n),
                 inner_radius * math.sin(a1 - (a1 - a0) * i / n))
                for i in range(n + 1)]
    else:
        arc.append((0.0, 0.0))
    poly = Polygon(np.asarray(pts, float))
    poly = poly if poly.is_valid else poly.buffer(0)
    out = poly.intersection(Polygon(arc))
    if out.geom_type == "MultiPolygon":
        out = max(out.geoms, key=lambda g: g.area)
    if out.is_empty:
        raise ValueError("sector is empty")
    return ccw(np.array(out.exterior.coords)[:-1])
