"""Temples: the arms of a pair of glasses, and a worked example of where
inheritance belongs.

Every temple is the same construction - a centre line, a section swept along
it, a rounded tip - and they differ in exactly one thing: what the centre line
does towards the ear. So that is the only method a subclass overrides.

    Temple                  centre line, sections, sweep, checks
    |
    +-- SkullTemple         bends down behind the ear. The usual one.
    +-- LibraryTemple       stays straight: for glasses that go on and off
    +-- CableTemple         curls right round the ear, for sport and vintage

Add a shape by writing one method. If you find yourself overriding more than
`drop()`, the base class is wrong and should be fixed instead.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import cadquery as cq
import numpy as np

from .check import CheckList
from .features import BodyFeature, ClipHinge
from .shell import sweep_sections
from .surface import GeometryError


@dataclass
class Temple(BodyFeature):
    """Base temple: straight run, tapering section, rounded tip."""

    length: float = 140.0           # along the temple, hinge to tip [mm]
    height: float = 11.0            # at the hinge, vertical [mm]
    height_back: float = 7.5
    thickness: float = 3.6          # across the head [mm]
    thickness_back: float = 3.0
    rise: float = 0.0               # how far the tip rises, over the length
    wrap: float = 6.0               # inward curve towards the head [mm]
    chamfer: float = 0.8
    tip_round: float = 7.0
    sections: int = 90
    hinge: ClipHinge | None = None
    integrated_hinge: bool = False  # True merges the pin carrier into the arm
    origin: tuple = (0.0, 0.0, 0.0)
    side: int = 1                   # +1 right, -1 left
    name: str = "temple"

    # --- the one thing subclasses change --------------------------------
    def drop(self, s_norm: np.ndarray) -> np.ndarray:
        """Vertical offset of the centre line, as a fraction of the length.

        `s_norm` runs 0 at the hinge to 1 at the tip. Return millimetres,
        negative is downward. The base temple is straight.
        """
        return np.zeros_like(s_norm)

    # --- shared construction --------------------------------------------
    def centreline(self) -> tuple[np.ndarray, np.ndarray]:
        s = np.linspace(0.0, self.length, self.sections)
        f = s / self.length
        z = -s
        y = self.rise * f + self.drop(f)
        x = -self.side * self.wrap * f ** 2
        return np.c_[x, y, z], f

    def section(self, frac: float, taper: float = 1.0) -> np.ndarray:
        """Chamfered rectangle in the local frame (across, up)."""
        w = (self.thickness + (self.thickness_back - self.thickness) * frac) * taper
        h = (self.height + (self.height_back - self.height) * frac) * taper
        c = min(self.chamfer * taper, w / 2 - 0.12, h / 2 - 0.12)
        if c <= 0:
            raise GeometryError(f"{self.name}: section too small to chamfer")
        a, b = w / 2, h / 2
        return np.array([(a, b - c), (a - c, b), (-a + c, b), (-a, b - c),
                         (-a, -b + c), (-a + c, -b), (a - c, -b), (a, -b + c)])

    def _taper(self, frac: np.ndarray) -> np.ndarray:
        """Shrink the last few sections so the tip reads as rounded."""
        back = (1.0 - frac) * self.length
        r = max(self.tip_round, 1e-6)
        inside = np.clip(1 - ((r - back) / r) ** 2, 0.0, 1.0)
        return np.where(back >= r, 1.0, np.maximum(np.sqrt(inside), 0.22))

    def arm(self) -> cq.Workplane:
        path, frac = self.centreline()
        taper = self._taper(frac)
        body = sweep_sections(path, [self.section(f, t) for f, t in zip(frac, taper)])
        return self._place(body)

    def _place(self, wp: cq.Workplane) -> cq.Workplane:
        if any(self.origin):
            wp = wp.translate(cq.Vector(*self.origin))
        return wp

    # --- bodies and checks ----------------------------------------------
    def solids(self) -> dict[str, cq.Workplane]:
        out = {"arm": self.arm()}
        if self.hinge is not None:
            pin = self.hinge.male()
            if self.integrated_hinge:
                merged = out["arm"].union(pin)
                from .check import mesh_report
                if not mesh_report(merged, 0.05)["watertight"]:
                    raise GeometryError(
                        f"{self.name}: merging the pin carrier into the arm "
                        "left a broken mesh - keep them as separate parts")
                out["arm"] = merged
            else:
                out["pin"] = pin
        return out

    def reach(self) -> float:
        """Straight-line distance from hinge to tip - what has to clear the
        head, as opposed to the length along the arm."""
        path, _ = self.centreline()
        return float(np.linalg.norm(path[-1] - path[0]))

    def checks(self) -> CheckList:
        cl = super().checks()
        extra = (CheckList()
                 .between(f"{self.name} length", self.length, 110, 160)
                 .at_least(f"{self.name} section at the tip",
                           min(self.thickness_back, self.height_back), 2.0)
                 .at_least(f"{self.name} reach", self.reach(), 100.0)
                 .add(f"{self.name} taper goes the right way",
                      self.height_back <= self.height,
                      f"{self.height_back} mm", f"<= {self.height} mm at the hinge"))
        cl.items.extend(extra.items)
        return cl


@dataclass
class SkullTemple(Temple):
    """The usual shape: straight, then down behind the ear."""

    drop_start: float = 0.70        # fraction of the length where it bends
    drop_depth: float = 14.0        # how far the tip ends up below [mm]
    name: str = "skull temple"

    def drop(self, f: np.ndarray) -> np.ndarray:
        t = np.clip((f - self.drop_start) / max(1 - self.drop_start, 1e-6), 0, 1)
        return -self.drop_depth * (t * t * (3 - 2 * t))      # smoothstep


@dataclass
class LibraryTemple(Temple):
    """No bend at all - for glasses meant to be taken on and off one-handed."""

    name: str = "library temple"
    height_back: float = 9.0

    def drop(self, f: np.ndarray) -> np.ndarray:
        return np.zeros_like(f)


@dataclass
class CableTemple(Temple):
    """Curls round the ear. Longer, thinner at the back, and the curl is a
    full half turn rather than a bend."""

    curl_start: float = 0.62
    curl_radius: float = 11.0
    length: float = 155.0
    height_back: float = 4.0
    thickness_back: float = 2.6
    tip_round: float = 4.0
    name: str = "cable temple"

    def drop(self, f: np.ndarray) -> np.ndarray:
        t = np.clip((f - self.curl_start) / max(1 - self.curl_start, 1e-6), 0, 1)
        return -self.curl_radius * (1 - np.cos(t * math.pi))
