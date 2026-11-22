"""The surfaces a shell is built on, and trimmed faces on them.

A part like a spectacle front, a visor, a shell or a panel is a flat outline
wrapped onto a curved surface. This module provides that surface in four
flavours and, crucially, the ability to cut a face out of it with any number
of holes - built from 2D curves in the surface's own parameter space, which is
the only way that works reliably in OpenCascade.

All four keep the same contract: a 2D outline in the XY plane keeps its (x, y)
and is given a z. `depth` offsets inward from the front face, so a wall of
thickness t runs from depth 0 to depth t.

Choosing one:

    Plane      flat parts. Always works.
    Cylinder   single curvature, e.g. a wrapped panel.
    Sphere     a lens or a dome. Watch the pole, see below.
    Torus      two curvatures at once - a spectacle front carries the lens
               base curve vertically and a flatter face-form wrap horizontally.

**The pole matters.** A sphere's parametrisation is singular at its pole, and
an outline that encloses or approaches it cannot be expressed as a closed 2D
curve. For a part centred on the axis - which is the usual case - `face()` on
a Sphere will fail. Cylinder and Torus have no pole near the part, which is
why a full eyewear front is modelled on a torus even though each lens is
spherical.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import cadquery as cq
import numpy as np
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
from OCP.BRepLib import BRepLib
from OCP.Geom import (Geom_CylindricalSurface, Geom_Plane, Geom_SphericalSurface,
                      Geom_Surface, Geom_ToroidalSurface)
from OCP.Geom2dAPI import Geom2dAPI_PointsToBSpline
from OCP.gp import gp_Ax3, gp_Dir, gp_Pnt, gp_Pnt2d
from OCP.ShapeFix import ShapeFix_Face
from OCP.TColgp import TColgp_Array1OfPnt2d


class Surface:
    """Base class. Subclasses provide `z`, `uv` and `occ`."""

    def z(self, x, y, depth: float = 0.0):
        raise NotImplementedError

    def uv(self, x, y, depth: float = 0.0):
        raise NotImplementedError

    def occ(self, depth: float = 0.0) -> Geom_Surface:
        raise NotImplementedError

    # --- shared ---------------------------------------------------------
    def point(self, x, y, depth: float = 0.0) -> cq.Vector:
        return cq.Vector(float(x), float(y), float(self.z(x, y, depth)))

    def points(self, pts2d, depth: float = 0.0) -> list[cq.Vector]:
        a = np.asarray(pts2d, float)
        z = self.z(a[:, 0], a[:, 1], depth)
        return [cq.Vector(float(x), float(y), float(zz))
                for (x, y), zz in zip(a, np.atleast_1d(z))]

    def sag(self, x, y) -> float:
        """How far the front face drops at (x, y) relative to the origin."""
        return float(self.z(x, y, 0.0)) - float(self.z(0.0, 0.0, 0.0))

    def edge(self, pts2d, depth=0.0, degree: int = 3,
             tol: float = 1.0e-4) -> cq.Wire:
        """Closed wire ON the surface, carrying its pcurve from birth.

        Built from a periodic 2D B-spline in parameter space rather than from
        3D points. Trimming a face with a wire that has no pcurve returns a
        face of area 0 - no exception, just nothing.

        `depth` may be an array with one entry per point, for a wall whose
        thickness varies. Such a wire does NOT lie on any single surface, so
        it gets built in 3D instead: usable for ruled faces, not as the
        boundary of a trimmed one.
        """
        if hasattr(depth, "__len__"):
            return self.edge_3d(pts2d, depth, degree)
        u, v = self.uv(np.asarray(pts2d, float)[:, 0],
                       np.asarray(pts2d, float)[:, 1], depth)
        u, v = np.atleast_1d(u), np.atleast_1d(v)
        arr = TColgp_Array1OfPnt2d(1, len(u))
        for i in range(len(u)):
            arr.SetValue(i + 1, gp_Pnt2d(float(u[i]), float(v[i])))
        curve = Geom2dAPI_PointsToBSpline(arr, degree, 8, tol).Curve()
        curve.SetPeriodic()
        e = BRepBuilderAPI_MakeEdge(curve, self.occ(depth)).Edge()
        BRepLib.BuildCurves3d_s(e)
        return cq.Wire(BRepBuilderAPI_MakeWire(e).Wire())

    def edge_3d(self, pts2d, depths, degree: int = 3) -> cq.Wire:
        """Closed 3D wire whose depth varies point by point."""
        a = np.asarray(pts2d, float)
        d = np.broadcast_to(np.asarray(depths, float), (len(a),))
        pts = [cq.Vector(float(x), float(y), float(self.z(x, y, dd)))
               for (x, y), dd in zip(a, d)]
        return cq.Workplane("XY").spline(pts, periodic=True).wire().val()

    def face(self, outer: cq.Wire, holes=(), depth: float = 0.0,
             tol: float = 1.0e-6) -> cq.Face:
        """Patch of the surface bounded by `outer`, with any number of holes.

        Goes through ShapeFix_Face rather than MakeFace().Add() for two
        measured reasons: adding a hole to an already trimmed face silently
        yields area 0, and an outline that runs counter-clockwise in (x, y)
        can run the other way in (u, v), which trims the complement. ShapeFix
        takes all wires at once and sorts out orientation itself.
        """
        sf = ShapeFix_Face()
        sf.Init(self.occ(depth), tol, True)
        sf.Add(outer.wrapped)
        for h in holes:
            sf.Add(h.wrapped)
        sf.Perform()
        sf.FixOrientation()
        f = cq.Face(sf.Face())
        if f.Area() <= 0:
            raise GeometryError(
                f"{type(self).__name__}.face() came out empty. If this is a "
                "Sphere, the outline probably encloses the pole - use Torus or "
                "Cylinder instead.")
        return f


class GeometryError(RuntimeError):
    """Raised where OpenCascade would otherwise return something empty."""


@dataclass
class Plane(Surface):
    """Flat. z = -depth everywhere."""

    def z(self, x, y, depth: float = 0.0):
        return np.full_like(np.asarray(x, float), -depth) if np.ndim(x) else -depth

    def uv(self, x, y, depth: float = 0.0):
        return np.asarray(x, float), np.asarray(y, float)

    def occ(self, depth: float = 0.0) -> Geom_Surface:
        return Geom_Plane(gp_Ax3(gp_Pnt(0, 0, -depth), gp_Dir(0, 0, 1),
                                 gp_Dir(1, 0, 0)))


@dataclass
class Cylinder(Surface):
    """Curved about the vertical (Y) axis. Front face touches the origin."""

    radius: float

    def _rho(self, depth):
        return self.radius - depth

    def z(self, x, y, depth: float = 0.0):
        rho = self._rho(depth)
        x = np.asarray(x, float)
        return -self.radius + np.sqrt(np.maximum(rho * rho - x * x, 1e-12))

    def uv(self, x, y, depth: float = 0.0):
        rho = self._rho(depth)
        u = np.arcsin(np.clip(np.asarray(x, float) / rho, -1.0, 1.0))
        return u, np.asarray(y, float)

    def occ(self, depth: float = 0.0) -> Geom_Surface:
        ax = gp_Ax3(gp_Pnt(0, 0, -self.radius), gp_Dir(0, 1, 0), gp_Dir(0, 0, 1))
        return Geom_CylindricalSurface(ax, self._rho(depth))


@dataclass
class Sphere(Surface):
    """Centred on the Z axis, front face touching the origin.

    `face()` fails for outlines around the axis - that is the pole. Use it for
    walls and ruled caps, not for trimmed faces with holes.
    """

    radius: float

    @classmethod
    def from_base_curve(cls, base_curve: float) -> "Sphere":
        """Optical base curve to radius: R = 530 / BC."""
        return cls(530.0 / base_curve)

    def z(self, x, y, depth: float = 0.0):
        rho = self.radius - depth
        x, y = np.asarray(x, float), np.asarray(y, float)
        return -self.radius + np.sqrt(np.maximum(rho * rho - x * x - y * y, 1e-12))

    def uv(self, x, y, depth: float = 0.0):
        rho = self.radius - depth
        x, y = np.asarray(x, float), np.asarray(y, float)
        u = np.arctan2(y, x)
        v = np.arcsin(np.clip(np.sqrt(np.maximum(x * x + y * y, 0.0)) / rho,
                              -1.0, 1.0))
        return u, np.pi / 2 - v

    def occ(self, depth: float = 0.0) -> Geom_Surface:
        ax = gp_Ax3(gp_Pnt(0, 0, -self.radius), gp_Dir(0, 0, 1), gp_Dir(1, 0, 0))
        return Geom_SphericalSurface(ax, self.radius - depth)


@dataclass
class Torus(Surface):
    """Two curvatures: `minor` vertically, `major + minor` horizontally.

    The vertical radius is the part's own curvature (for eyewear: the lens
    base curve); the horizontal one is the flatter wrap across the whole part.
    No pole near the part, so `face()` works with any number of holes.
    """

    minor: float
    major: float

    @classmethod
    def from_radii(cls, vertical: float, horizontal: float) -> "Torus":
        if horizontal <= vertical:
            raise ValueError("horizontal radius must exceed the vertical one")
        return cls(minor=vertical, major=horizontal - vertical)

    @property
    def z0(self) -> float:
        return -(self.major + self.minor)

    def _frame(self, x, y, depth):
        rho = self.minor - depth
        v = np.arcsin(np.clip(np.asarray(y, float) / rho, -1.0, 1.0))
        h = self.major + rho * np.cos(v)
        u = np.arcsin(np.clip(np.asarray(x, float) / h, -1.0, 1.0))
        return u, v, h

    def z(self, x, y, depth: float = 0.0):
        u, _, h = self._frame(x, y, depth)
        return self.z0 + h * np.cos(u)

    def uv(self, x, y, depth: float = 0.0):
        u, v, _ = self._frame(x, y, depth)
        return u, v

    def occ(self, depth: float = 0.0) -> Geom_Surface:
        ax = gp_Ax3(gp_Pnt(0, 0, self.z0), gp_Dir(0, 1, 0), gp_Dir(0, 0, 1))
        return Geom_ToroidalSurface(ax, self.major, self.minor - depth)
