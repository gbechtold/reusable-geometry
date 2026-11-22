"""The checks that have to pass after every change.

A model that passes these is at least manufacturable and dimensionally what
the parameters claim. Add to them whenever reality teaches you something: a
print that came out wrong, a wall that was too thin. A lesson that becomes a
check cannot come back.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .render import mesh


@dataclass
class Check:
    name: str
    ok: bool
    got: object
    want: str

    def line(self, width: int = 28) -> str:
        return (f"{'ok ' if self.ok else 'FAIL'}  {self.name:<{width}}  "
                f"{str(self.got):>14}   want {self.want}")


class CheckList:
    def __init__(self):
        self.items: list[Check] = []

    def add(self, name, ok, got, want) -> "CheckList":
        self.items.append(Check(name, bool(ok), got, want))
        return self

    def between(self, name, value, lo, hi, unit="mm") -> "CheckList":
        return self.add(name, lo <= value <= hi, f"{value:.2f} {unit}",
                        f"{lo}..{hi} {unit}")

    def at_least(self, name, value, lo, unit="mm") -> "CheckList":
        return self.add(name, value >= lo, f"{value:.2f} {unit}", f">= {lo} {unit}")

    def watertight(self, name, solid, tol: float = 0.03) -> "CheckList":
        r = mesh_report(solid, tol)
        self.add(f"{name} watertight", r["watertight"], r["non_manifold_edges"],
                 "0 non-manifold edges")
        return self

    @property
    def failed(self):
        return [c for c in self.items if not c.ok]

    def report(self) -> str:
        w = max((len(c.name) for c in self.items), default=10)
        return "\n".join("  " + c.line(w) for c in self.items)

    def to_dict(self):
        return [{"check": c.name, "ok": c.ok, "got": c.got, "want": c.want}
                for c in self.items]

    def exit_code(self) -> int:
        return 1 if self.failed else 0


def mesh_report(solid, tol: float = 0.03) -> dict:
    """Watertightness measured on the MESH, not the B-rep.

    OpenCascade will flag a perfectly printable solid as invalid, and will
    also call a broken one valid. The mesh is what gets printed, so the mesh
    is what decides. Vertices are merged by position first: OCC meshes each
    face separately, so without merging every shared edge looks non-manifold.
    """
    v, t = mesh(solid, tol, 0.2)
    key = np.round(v / 1e-5).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    v, t = v[first], inv[t]
    t = t[(t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 0] != t[:, 2])]

    edges = {}
    for tri in t:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            k = (min(a, b), max(a, b))
            edges[k] = edges.get(k, 0) + 1
    bad = sum(1 for c in edges.values() if c != 2)
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    vol = float(abs(np.sum(np.einsum("ij,ij->i", a, np.cross(b, c))) / 6))
    return {"triangles": int(len(t)), "non_manifold_edges": int(bad),
            "watertight": bad == 0, "volume_mm3": round(vol, 1)}


def mass(solid, density_g_cm3: float = 1.01, tol: float = 0.03) -> float:
    """Grams. Default density is PA12, the usual SLS nylon."""
    return mesh_report(solid, tol)["volume_mm3"] * density_g_cm3 / 1000.0
