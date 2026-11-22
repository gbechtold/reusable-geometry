"""Features: named, reusable pieces of geometry that know how to check
themselves.

The hierarchy exists to keep a promise. Every feature says how it is made, and
that decides what can go wrong with it:

    Feature                  a named thing with its own checks
    |
    +-- ProfileFeature       changes a wall profile. No body of its own, no
    |                        boolean, so nothing can fail at build time.
    |
    +-- BodyFeature          brings solids with it
            |
            +-- MechanicalFeature   two parts that have to fit each other.
                                    Carries the clearance between them and
                                    MEASURES it rather than claiming it.

`MechanicalFeature` is where the hierarchy earns its keep. A fit is not a
shape, it is a relationship between two shapes, and the thing that goes wrong
with it is always the same: the gap is not what the drawing says. So the base
class owns `clearance`, `male()`, `female()` and `check_fit()`, and a subclass
only supplies the two shapes.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import cadquery as cq
import numpy as np
from OCP.BRepExtrema import BRepExtrema_DistShapeShape

from .check import CheckList, mesh_report
from .profile import WallProfile
from .surface import GeometryError


# --------------------------------------------------------------------- base --
@dataclass
class Feature(ABC):
    """A named piece of geometry that can be asked whether it is sound."""

    name: str = "feature"

    @abstractmethod
    def checks(self) -> CheckList:
        """What has to be true for this feature to be worth building."""

    def describe(self) -> str:
        return f"{type(self).__name__} '{self.name}'"


@dataclass
class ProfileFeature(Feature):
    """Changes a wall profile. The safest kind of feature there is: it never
    creates a body, so it cannot fail a boolean or leave a hole in a mesh."""

    @abstractmethod
    def apply_to(self, profile: WallProfile) -> WallProfile:
        """Return the profile with this feature added."""


@dataclass
class BodyFeature(Feature):
    """Brings one or more solids with it."""

    @abstractmethod
    def solids(self) -> dict[str, cq.Workplane]:
        """Named bodies, ready to export or add to an assembly."""

    def checks(self) -> CheckList:
        cl = CheckList()
        for name, solid in self.solids().items():
            cl.watertight(f"{self.name}.{name}", solid)
        return cl


@dataclass
class MechanicalFeature(BodyFeature):
    """Two parts designed to fit together, with the gap between them measured.

    Subclasses provide `male()` and `female()` in the SAME coordinate frame,
    positioned as assembled. The base class then measures what is actually
    between them, which is the only honest way to report a fit: a clearance
    written in a parameter is a claim, the distance between two solids is a
    measurement.
    """

    clearance: float = 0.15
    min_wall: float = 0.8

    @abstractmethod
    def male(self) -> cq.Workplane:
        """The part that goes in."""

    @abstractmethod
    def female(self) -> cq.Workplane:
        """The part it goes into."""

    def solids(self) -> dict[str, cq.Workplane]:
        return {"male": self.male(), "female": self.female()}

    def measured_gap(self) -> float:
        """Smallest distance between the two parts as assembled. 0 means they
        interfere."""
        return distance(self.male(), self.female())

    def check_fit(self, tolerance: float = 0.06) -> CheckList:
        gap = self.measured_gap()
        cl = CheckList()
        cl.add(f"{self.name} parts clear each other", gap > 1e-6,
               f"{gap:.3f} mm", "> 0 mm (no interference)")
        cl.add(f"{self.name} gap matches the clearance",
               abs(gap - self.clearance) <= tolerance,
               f"{gap:.3f} mm", f"{self.clearance:.2f} +/- {tolerance:.2f} mm")
        return cl

    def checks(self) -> CheckList:
        cl = super().checks()
        for item in self.check_fit().items:
            cl.items.append(item)
        return cl


def _dedupe(pts: np.ndarray, tol: float = 1e-9) -> np.ndarray:
    """Drop repeated points. A zero-length segment makes polyline() fail with
    'BRep_API: command not done', which says nothing about the cause."""
    out = [pts[0]]
    for p in pts[1:]:
        if np.linalg.norm(p - out[-1]) > tol:
            out.append(p)
    if np.linalg.norm(out[-1] - out[0]) <= tol:
        out.pop()
    return np.array(out, float)


def distance(a, b) -> float:
    """Minimum distance between two shapes, in millimetres."""
    sa = a.val().wrapped if hasattr(a, "val") else a.wrapped
    sb = b.val().wrapped if hasattr(b, "val") else b.wrapped
    d = BRepExtrema_DistShapeShape(sa, sb)
    if not d.IsDone():
        raise GeometryError("could not measure the distance between the parts")
    return float(d.Value())


# ----------------------------------------------------------- profile features --
@dataclass
class Groove(ProfileFeature):
    """A V groove at a given depth - a lens bevel, a seal seat, an O-ring."""

    at: float = 2.6
    width: float = 0.9
    depth: float = 0.7
    name: str = "groove"

    def apply_to(self, profile: WallProfile) -> WallProfile:
        return profile.groove(self.at, self.width, self.depth)

    def checks(self) -> CheckList:
        return (CheckList()
                .at_least(f"{self.name} width", self.width, 0.4)
                .at_least(f"{self.name} depth", self.depth, 0.2))


@dataclass
class EdgeBreak(ProfileFeature):
    """Chamfer or round on both ends of a wall.

    `style="round"` builds the quarter circle into the profile instead of
    calling fillet(), which does not complete on spline edges lying on a
    curved face.
    """

    size: float = 0.6
    style: str = "chamfer"          # "chamfer" | "round"
    name: str = "edge break"

    def apply_to(self, profile: WallProfile) -> WallProfile:
        if self.style == "chamfer":
            return profile.chamfer_both(self.size)
        if self.style == "round":
            return profile.round_both(self.size)
        raise GeometryError(f"unknown edge style {self.style!r}")

    def checks(self) -> CheckList:
        return CheckList().at_least(f"{self.name} size", self.size, 0.1)


@dataclass
class Boss(ProfileFeature):
    """A local thickening, for a hinge seat or a screw column.

    Returns a thickness array rather than touching the profile: a boss is a
    change of wall thickness, and Shell takes that per point. This is how a
    raised pad gets made without a union - the operation that returned
    -2.4e6 mm3 when it was tried.
    """

    angle_centre: float = 170.0
    angle_width: float = 30.0
    thickness: float = 9.0
    blend: float = 7.0
    name: str = "boss"

    def apply_to(self, profile: WallProfile) -> WallProfile:
        return profile            # a boss changes thickness, not the profile

    def thickness_for(self, outline, base_thickness: float) -> np.ndarray:
        """Per-point wall thickness, blending smoothly into the boss."""
        pts = np.asarray(outline, float)
        ang = np.degrees(np.arctan2(pts[:, 1], pts[:, 0]))
        delta = (ang - self.angle_centre + 180) % 360 - 180
        inside = self.angle_width / 2 - np.abs(delta)
        s = np.clip(inside / max(self.blend, 1e-6), 0.0, 1.0)
        s = s * s * (3 - 2 * s)                       # smoothstep
        return base_thickness + (self.thickness - base_thickness) * s

    def checks(self) -> CheckList:
        return (CheckList()
                .at_least(f"{self.name} thickness", self.thickness, 1.0)
                .at_least(f"{self.name} blend", self.blend, 0.0, unit="deg"))


# --------------------------------------------------------------- clip hinge --
@dataclass
class ClipHinge(MechanicalFeature):
    """A hinge the temple clips into: a slotted fork on the front, a cross pin
    on the temple.

    Taken from a printed eyewear frame, where the hinge is a bought steel part
    rather than a moulded one - two jaws with a slot between them, a pin that
    is pushed past a narrow point and snaps into a round socket behind it.

    Both halves are plain extrusions of a 2D outline: the snap - lead-in,
    narrow point, socket - is the SHAPE of the slot, not something cut into it
    afterwards. That is the whole trick, and it is why this builds in
    milliseconds and cannot fail a boolean.

                        z = 0 (face of the frame)
         +-------------------------------+   ^
         |          ___                  |   |  height
         |      ---(   )---------------  |   |     <- slot, open at the back
         |          ---                  |   |
         +-------------------------------+   v
                 socket  narrow   lead-in
         <------------ length ------------>
    """

    pin_radius: float = 1.1
    height: float = 7.0             # of the fork block
    width: float = 4.2              # across, i.e. the pin's length
    length: float = 7.5             # how far the fork reaches back
    slot_lead: float = 1.6          # straight run at the mouth
    ramp: float = 1.0               # over which the slot narrows
    snap_angle: float = 50.0        # where the slot meets the socket [deg]
    socket_back: float = 2.6        # socket centre, measured from the face
    temple_block: float = 5.0       # length of the pin carrier on the temple
    flange: float = 1.2             # seat that lies against the frame [mm]
    flange_height: float = 2.0      # how far it stands proud, top and bottom
    origin: tuple = (0.0, 0.0, 0.0)
    yaw: float = 0.0                # rotation about Y when placed [deg]
    name: str = "clip hinge"

    # --- derived --------------------------------------------------------
    @property
    def socket_radius(self) -> float:
        return self.pin_radius + self.clearance

    @property
    def narrow(self) -> float:
        """Slot height at the narrow point. Set by where the slot meets the
        socket, so the two are tangent instead of merely near each other."""
        return 2 * self.socket_radius * math.sin(math.radians(self.snap_angle))

    @property
    def mouth(self) -> float:
        """Slot height at the mouth - wide enough to start the pin in."""
        return 2 * self.socket_radius + 2 * self.clearance

    def snap_interference(self) -> float:
        """How far the pin has to deflect the jaws to pass the narrow point.
        This is what makes it click; zero would mean it falls in."""
        return 2 * self.pin_radius - self.narrow

    # --- outlines -------------------------------------------------------
    def fork_outline(self, n_arc: int = 24) -> np.ndarray:
        """Side view of the fork, in (z, y). z runs back from the face."""
        r = self.socket_radius
        zc = -self.socket_back
        g = math.radians(self.snap_angle)
        z_narrow = zc - r * math.cos(g)          # narrow point, behind the socket
        z_ramp = z_narrow - self.ramp
        z_back = -self.length
        half_m = self.mouth / 2

        # the socket bulges FORWARD, towards the face: the pin sits at zc and
        # the arc has to wrap its front half, so sweep from -(180-snap) past 0
        # to +(180-snap). Getting this sign wrong puts solid material where
        # the pin goes, and the parts then measure zero clearance.
        wrap = math.radians(180.0 - self.snap_angle)
        arc = [(zc + r * math.cos(a), r * math.sin(a))
               for a in np.linspace(-wrap, wrap, n_arc)]
        # Walk the outside of the block, then into the slot and back out.
        # The arc already begins and ends exactly at the narrow point, so that
        # point is not listed again.
        h, fh = self.height / 2, self.height / 2 + self.flange_height
        pts = [(0.0, -fh), (-self.flange, -fh), (-self.flange, -h),
               (z_back, -h), (z_back, -half_m), (z_ramp, -half_m)]
        pts += [(z, y) for z, y in arc]
        pts += [(z_ramp, half_m), (z_back, half_m), (z_back, h),
                (-self.flange, h), (-self.flange, fh), (0.0, fh)]
        return _dedupe(np.array(pts, float))

    def carrier_outline(self) -> np.ndarray:
        """Side view of the pin carrier on the temple, in (z, y)."""
        r = self.socket_radius
        zc = -self.socket_back
        back = zc - self.temple_block - r
        h = self.narrow / 2 - self.clearance      # slides through the narrow point
        return np.array([(zc, -h), (back, -h), (back, h), (zc, h)], float)

    # --- bodies ---------------------------------------------------------
    def _extrude(self, outline_zy: np.ndarray, width: float) -> cq.Workplane:
        """Extrude a (z, y) outline across X."""
        pts = [(float(z), float(y)) for z, y in _dedupe(outline_zy)]
        wp = (cq.Workplane("YZ")
              .polyline([(y, z) for z, y in pts]).close()
              .extrude(width / 2, both=True))
        return wp

    def female(self) -> cq.Workplane:
        return self._place(self._extrude(self.fork_outline(), self.width))

    def male(self) -> cq.Workplane:
        w = self.width - 2 * self.clearance
        carrier = self._extrude(self.carrier_outline(), w)
        pin = (cq.Workplane("YZ")
               .workplane(offset=-w / 2)
               .center(0.0, -self.socket_back)
               .circle(self.pin_radius)
               .extrude(w))
        body = carrier.union(pin)
        if not mesh_report(body, 0.05)["watertight"]:
            raise GeometryError(
                "the pin and its carrier did not merge into a sound body - "
                "check pin_radius against the carrier height")
        return self._place(body)

    def _place(self, wp: cq.Workplane) -> cq.Workplane:
        if self.yaw:
            wp = wp.rotate((0, 0, 0), (0, 1, 0), self.yaw)
        if any(self.origin):
            wp = wp.translate(cq.Vector(*self.origin))
        return wp

    # --- checks ---------------------------------------------------------
    def checks(self) -> CheckList:
        cl = super().checks()
        jaw = (self.height - self.mouth) / 2
        extra = (CheckList()
                 .at_least(f"{self.name} jaw thickness", jaw, self.min_wall)
                 .at_least(f"{self.name} snap interference",
                           self.snap_interference(), 0.05)
                 .add(f"{self.name} snap is not excessive",
                      self.snap_interference() < self.pin_radius * 0.8,
                      f"{self.snap_interference():.2f} mm",
                      f"< {self.pin_radius * 0.8:.2f} mm (it has to go back in)")
                 .at_least(f"{self.name} socket depth",
                           self.socket_back - self.socket_radius, 0.5)
                 .at_least(f"{self.name} flange", self.flange, 0.4)
                 .add(f"{self.name} socket fits the block",
                      self.socket_back + self.socket_radius < self.length,
                      f"{self.socket_back + self.socket_radius:.2f} mm",
                      f"< {self.length} mm"))
        cl.items.extend(extra.items)
        return cl
