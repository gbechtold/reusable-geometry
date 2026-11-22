"""Wall profiles: what the material does between the front face and the back.

This is where features live that would otherwise be booleans. An edge break,
a groove, a step - each is a lateral offset applied at some depth, and the
shell builder turns the stack into faces. Nothing is cut afterwards, so
nothing can fail afterwards.

    >>> rim = WallProfile(6.0).chamfer_front(1.1).chamfer_back(0.7)
    >>> lens = (WallProfile(6.0, outward=True)
    ...         .chamfer_front(0.6).chamfer_back(0.6)
    ...         .groove(at=2.6, width=0.9, depth=0.7))

`outward=True` is for the wall around a hole: positive offsets widen the
opening. For an outer wall the offsets pull material in.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


def _sub(thickness, d):
    """thickness - d, working for both a number and a per-point array."""
    return thickness - d if not hasattr(thickness, "__len__") else np.asarray(thickness) - d


@dataclass
class WallProfile:
    """A stack of (depth, lateral offset) samples down one wall."""

    thickness: float
    outward: bool = False
    steps_: list[tuple[float, float, str]] = field(default_factory=list)
    arc_segments: int = 5

    # --- ends -----------------------------------------------------------
    def chamfer_front(self, c: float) -> "WallProfile":
        """Flat bevel at the front face. Reads as a facet."""
        if c > 0:
            self._add(0.0, c, "front")
            self._add(c, 0.0, "front")
        return self

    def chamfer_back(self, c: float) -> "WallProfile":
        if c > 0:
            self._add(c, 0.0, "back")
            self._add(0.0, c, "back")
        return self

    def round_front(self, r: float, n: int | None = None) -> "WallProfile":
        """Quarter-round at the front face, tangent to it.

        This is the replacement for fillet(): OpenCascade's fillet on spline
        edges lying on a curved face does not complete (measured: over nine
        minutes on four edges, no result). Built into the profile it is exact
        and costs nothing.
        """
        n = n or self.arc_segments
        for i in range(n + 1):
            a = math.pi / 2 * i / n
            self._add(r * (1 - math.cos(a)), r * (1 - math.sin(a)), "front")
        return self

    def round_back(self, r: float, n: int | None = None) -> "WallProfile":
        n = n or self.arc_segments
        for i in range(n + 1):
            a = math.pi / 2 * i / n
            self._add(r - r * math.sin(a), r * (1 - math.cos(a)), "back")
        return self

    def round_both(self, r: float, n: int | None = None) -> "WallProfile":
        return self.round_front(r, n).round_back(r, n)

    def chamfer_both(self, c: float) -> "WallProfile":
        return self.chamfer_front(c).chamfer_back(c)

    # --- features -------------------------------------------------------
    def groove(self, at: float, width: float, depth: float) -> "WallProfile":
        """V groove centred at `at`, measured from the FRONT face.

        Front-referenced on purpose: a lens sits a fixed distance behind the
        front whatever the frame does further back.
        """
        self._add(at - width / 2, 0.0, "front")
        self._add(at, depth, "front")
        self._add(at + width / 2, 0.0, "front")
        return self

    def step(self, at: float, offset: float, run: float = 0.0) -> "WallProfile":
        """A shoulder: the wall jumps sideways by `offset` at depth `at`,
        over `run` of depth (0 = a hard step)."""
        self._add(at, 0.0, "front")
        self._add(at + run, offset, "front")
        self._add(0.0, offset, "back")
        return self

    # --- output ---------------------------------------------------------
    def _add(self, depth: float, offset: float, anchor: str) -> None:
        self.steps_.append((float(depth), float(offset), anchor))

    def steps(self, thickness=None):
        """Samples from front to back, including the plain ends.

        `thickness` may be a single number or an array with one entry per
        outline point - that is how a wall gets thicker in one region without
        a boolean. Steps anchored to the back move with it; steps anchored to
        the front (a groove, an edge break) stay where they are.

        Offsets are signed for the caller: negative pulls an outer wall in,
        positive widens a hole.
        """
        t = self.thickness if thickness is None else thickness
        sign = 1.0 if self.outward else -1.0

        front = sorted([(d, o) for d, o, a in self.steps_ if a == "front"],
                       key=lambda p: p[0])
        back = sorted([(d, o) for d, o, a in self.steps_ if a == "back"],
                      key=lambda p: -p[0])

        # plain ends, but only where the profile does not already start there
        if not front or front[0][0] > 1e-9:
            front.insert(0, (0.0, 0.0))
        if not back or back[-1][0] > 1e-9:
            back.append((0.0, 0.0))

        out = [(d, sign * o) for d, o in front]
        out += [(_sub(t, d), sign * o) for d, o in back]
        return out

    def validate(self) -> list[str]:
        """Complaints a caller should hear before building."""
        bad = []
        s = self.steps()
        for d, o in s:
            if abs(o) > self.thickness:
                bad.append(f"offset {o:.2f} mm exceeds the wall thickness")
        depths = [float(d) for d, _ in s]
        if depths != sorted(depths):
            bad.append("depths are not monotonic")
        front = [o for d, o in s if float(d) < self.thickness / 2]
        if self.outward and any(o < 0 for o in front):
            bad.append("an outward wall should not have negative offsets")
        return bad
