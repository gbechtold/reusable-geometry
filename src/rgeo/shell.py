"""Build a solid by describing its walls, not by cutting it out of a block.

    body = (Shell(Torus.from_radii(88.3, 220.0))
            .outer(front_outline, WallProfile(6.0).chamfer_both(1.0))
            .hole(lens_left,  lens_wall)
            .hole(lens_right, lens_wall)
            .hole(bridge_window, WallProfile(6.0, outward=True).chamfer_both(0.6))
            .build())

Why this exists instead of extrude-and-cut: booleans against a large curved
surface are unreliable in OpenCascade. Measured on a sphere of R = 88 mm, the
same cut returned 3920 mm3 at fuzzy tolerance 1e-4 and 2689 mm3 at 1e-3, an
exact boolean returned an empty solid with no error at all, and a union of two
lofted bodies came back at -2.4e6 mm3. Describing the walls removes the
question: there is nothing left to go wrong at boolean time.

What you give up: features that genuinely need a boolean (a slot across a
boss, a hole at an angle) have to be expressed as a wall profile, or cut
afterwards at your own risk. `rgeo.check` will tell you if that broke the mesh.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cadquery as cq
import numpy as np
from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing

from .outline import ccw, offset as offset_outline
from .profile import WallProfile
from .surface import GeometryError, Surface


@dataclass
class _Wall:
    pts: np.ndarray
    profile: WallProfile
    thickness: object = None       # None = the profile's own, or a per-point array


class Shell:
    """Collects walls, then sews them into one closed solid."""

    def __init__(self, surface: Surface, cap: str = "trimmed"):
        """cap="trimmed" cuts real faces out of the surface and takes any
        number of holes. cap="ruled" spans the front and back between the
        outer outline and a single hole - cruder, but it works on surfaces
        whose parametrisation has a pole in the way (a Sphere, typically)."""
        self.surface = surface
        self.cap = cap
        self._outer: _Wall | None = None
        self._holes: list[_Wall] = []

    def outer(self, pts, profile: WallProfile, thickness=None) -> "Shell":
        self._outer = _Wall(_prepare(pts, "outer wall"), profile, thickness)
        return self

    def hole(self, pts, profile: WallProfile, thickness=None) -> "Shell":
        self._holes.append(_Wall(_prepare(pts, "hole"), profile, thickness))
        return self

    # --- checks ---------------------------------------------------------
    def _check_clearances(self) -> None:
        """Catch outlines that collide once the wall profiles are applied.

        A chamfer widens a hole and narrows the outer wall, so two features
        that look 0.2 mm apart in the sketch can overlap in the built body.
        OpenCascade does not complain: it returns a face with a plausible area
        that simply has no triangles, and the mesh ends up full of holes.
        """
        from shapely.geometry import Polygon

        def widest(wall: _Wall) -> Polygon:
            offs = [o for _, o in wall.profile.steps(wall.thickness)]
            flat = [float(np.max(np.abs(o))) for o in offs]
            d = max(flat) if flat else 0.0
            pts = offset_outline(wall.pts, d if wall.profile.outward else -d) \
                if d else wall.pts
            poly = Polygon(pts)
            return poly if poly.is_valid else poly.buffer(0)

        outer = widest(self._outer)
        holes = [(i, widest(h)) for i, h in enumerate(self._holes)]
        for i, h in holes:
            if not outer.contains(h):
                raise GeometryError(
                    f"hole {i} reaches outside the outer wall once the wall "
                    "profiles are applied. Shrink the chamfer or move the hole.")
        for (i, a), (j, b) in ((holes[m], holes[n])
                               for m in range(len(holes))
                               for n in range(m + 1, len(holes))):
            if a.intersects(b):
                gap = a.distance(b)
                raise GeometryError(
                    f"holes {i} and {j} overlap once the wall profiles are "
                    f"applied (gap {gap:.2f} mm). They need at least the sum "
                    "of their chamfers between them.")

    # --- building -------------------------------------------------------
    def _wires(self, wall: _Wall) -> list[cq.Wire]:
        out = []
        for depth, off in wall.profile.steps(wall.thickness):
            pts = offset_outline(wall.pts, off) if np.any(np.abs(off) > 1e-12) \
                else wall.pts
            if hasattr(depth, "__len__") and len(depth) != len(pts):
                raise GeometryError(
                    f"thickness has {len(depth)} entries but the outline has "
                    f"{len(pts)} points - they have to line up")
            out.append(self.surface.edge(pts, depth))
        return out

    def build(self) -> cq.Workplane:
        if self._outer is None:
            raise GeometryError("a shell needs an outer wall")
        for w in [self._outer, *self._holes]:
            problems = w.profile.validate()
            if problems:
                raise GeometryError("wall profile: " + "; ".join(problems))
        self._check_clearances()

        ow = self._wires(self._outer)
        faces = _ruled(ow)
        hole_wires = []
        for h in self._holes:
            hw = self._wires(h)
            faces += _ruled(hw)
            hole_wires.append(hw)

        if self.cap == "trimmed":
            faces.append(self.surface.face(ow[0], [h[0] for h in hole_wires], 0.0))
            back = self._outer.profile.steps(self._outer.thickness)[-1][0]
            if hasattr(back, "__len__") and float(np.ptp(back)) > 1e-9:
                # A varying wall puts the back face on no single surface, so
                # it cannot be trimmed out of one. A ruled face spans it, and
                # that needs exactly one hole to span to.
                if len(hole_wires) != 1:
                    raise GeometryError(
                        "a wall of varying thickness can only be closed at the "
                        "back by a ruled face, which needs exactly one hole; "
                        f"this shell has {len(hole_wires)}. Keep the thickness "
                        "constant, or split the part.")
                faces.append(cq.Face.makeRuledSurface(ow[-1], hole_wires[0][-1]))
            else:
                faces.append(self.surface.face(
                    ow[-1], [h[-1] for h in hole_wires], _scalar_depth(back)))
        elif self.cap == "ruled":
            if len(hole_wires) != 1:
                raise GeometryError('cap="ruled" needs exactly one hole; '
                                    'use cap="trimmed" for anything else')
            faces += [cq.Face.makeRuledSurface(ow[0], hole_wires[0][0]),
                      cq.Face.makeRuledSurface(ow[-1], hole_wires[0][-1])]
        else:
            raise GeometryError(f"unknown cap mode {self.cap!r}")

        return cq.Workplane("XY").add(sew(faces))


def _prepare(pts, what: str) -> np.ndarray:
    """Normalise an incoming outline, and refuse the two shapes that produce
    a broken body without saying so.

    Direction: everything downstream assumes counter-clockwise. A clockwise
    outline (shapely hands them out that way) inverts the wall offsets, so a
    chamfer grows the part instead of cutting it.

    Spacing: points distributed by angle rather than by arc length leave
    millimetre-long segments next to micron-long ones. The spline fit then
    overshoots and the tessellation explodes - measured on one such outline:
    1.2 million triangles and 3521 non-manifold edges.
    """
    a = ccw(np.asarray(pts, float))
    if len(a) < 8:
        raise GeometryError(f"{what}: {len(a)} points is too few")
    d = np.linalg.norm(np.diff(np.r_[a, a[:1]], axis=0), axis=1)
    if d.min() <= 1e-9:
        raise GeometryError(f"{what}: outline repeats a point")
    if d.max() / d.min() > 25:
        raise GeometryError(
            f"{what}: segment lengths run {d.min():.3f}..{d.max():.3f} mm. "
            "Resample by arc length first - rgeo.resample(pts, n) - or the "
            "spline will overshoot.")
    return a


def _scalar_depth(depth) -> float:
    return float(np.max(depth)) if hasattr(depth, "__len__") else float(depth)


def _ruled(wires: list[cq.Wire]) -> list[cq.Face]:
    return [cq.Face.makeRuledSurface(a, b) for a, b in zip(wires, wires[1:])]


def sew(faces, tol: float = 1.0e-5) -> cq.Solid:
    """Sew faces into one shell and close it into a solid.

    Shell.makeShell on its own leaves every face with its own edges, so the
    shell stays open and the volume it reports is meaningless.
    """
    sewing = BRepBuilderAPI_Sewing(tol)
    for f in faces:
        sewing.Add(f.wrapped)
    sewing.Perform()
    shell = cq.Shape.cast(sewing.SewedShape())
    if shell.ShapeType() != "Shell" or sewing.NbFreeEdges():
        raise GeometryError(
            f"sewing produced a {shell.ShapeType()} with "
            f"{sewing.NbFreeEdges()} free edges - the walls do not meet")
    solid = cq.Solid.makeSolid(cq.Shell(shell.wrapped))
    if solid.Volume() < 0:
        solid = cq.Solid(solid.wrapped.Reversed())
    solid.wrapped.Closed(True)     # OCC does not set the flag itself
    return solid


def sweep_sections(path, sections, close_ends: bool = True, **kwargs):
    """Deprecated: use rgeo.sweep, which can also handle a closed path.

    Kept so existing code keeps working. The old implementation pinned the up
    direction to (0, 1, 0) and collapsed wherever a path ran vertically, which
    is exactly where a closed rim runs. `sweep` defaults to detecting that and
    switching frames.
    """
    from .path import sweep_path
    return sweep_path(path, sections, **kwargs)
