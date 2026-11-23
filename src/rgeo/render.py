"""A small offscreen renderer that also hands back the silhouette as data.

Not a viewer. It exists so a model can be compared with a photograph by
measurement: fixed named cameras, a mask you can do arithmetic on, and the
same output on every machine.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Camera:
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    scale: float = 1.0     # pixels per mm
    cx: float = 0.0
    cy: float = 0.0

    def matrix(self) -> np.ndarray:
        cy_, sy = math.cos(math.radians(self.yaw)), math.sin(math.radians(self.yaw))
        cp, sp = math.cos(math.radians(self.pitch)), math.sin(math.radians(self.pitch))
        cr, sr = math.cos(math.radians(self.roll)), math.sin(math.radians(self.roll))
        Ry = np.array([[cy_, 0, sy], [0, 1, 0], [-sy, 0, cy_]])
        Rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
        Rz = np.array([[cr, -sr, 0], [sr, cr, 0], [0, 0, 1]])
        return Rz @ Rx @ Ry

    def as_list(self):
        return [self.yaw, self.pitch, self.roll, self.scale, self.cx, self.cy]

    @classmethod
    def from_list(cls, x):
        return cls(*[float(v) for v in x])


def mesh(shape, tol: float = 0.02, angular: float = 0.15):
    """Tessellate a CadQuery shape into vertices and triangles."""
    verts, tris = (shape.val() if hasattr(shape, "val") else shape).tessellate(
        tol, angular)
    return np.array([[p.x, p.y, p.z] for p in verts], float), np.array(tris, int)


def load_stl(path, merge_vertices: bool = True):
    """Read a mesh straight from an STL file, binary or ASCII.

    So a model that was built earlier - or by something else entirely - can be
    rendered, animated or compared without rebuilding it.
    """
    import struct
    from pathlib import Path

    raw = Path(path).read_bytes()
    if raw[:5] == b"solid" and b"facet" in raw[:2048]:
        verts = []
        for line in raw.decode("ascii", "replace").splitlines():
            parts = line.split()
            if parts[:1] == ["vertex"]:
                verts.append([float(x) for x in parts[1:4]])
        v = np.array(verts, float)
        if len(v) % 3:
            raise ValueError(f"{path}: vertex count is not a multiple of three")
        t = np.arange(len(v)).reshape(-1, 3)
    else:
        n = struct.unpack("<I", raw[80:84])[0]
        if len(raw) < 84 + n * 50:
            raise ValueError(f"{path}: truncated, expected {n} triangles")
        block = np.frombuffer(raw[84:84 + n * 50], dtype=np.uint8).reshape(n, 50)
        v = block[:, 12:48].copy().view("<f4").reshape(n * 3, 3).astype(float)
        t = np.arange(n * 3).reshape(-1, 3)

    if merge_vertices:
        key = np.round(v / 1e-5).astype(np.int64)
        _, first, inv = np.unique(key, axis=0, return_index=True,
                                  return_inverse=True)
        v, t = v[first], inv[t]
    return v, t


def merge(meshes):
    """One mesh from several, so parts share a camera."""
    vs, ts, off = [], [], 0
    for v, t in meshes:
        vs.append(v); ts.append(t + off); off += len(v)
    return np.vstack(vs), np.vstack(ts)


def fit_to_frame(v, cam: Camera, size, margin: float = 0.06) -> Camera:
    """Centre and scale so the model fills the frame."""
    w, h = size
    p = v @ cam.matrix().T
    lo, hi = p[:, :2].min(axis=0), p[:, :2].max(axis=0)
    span = np.maximum(hi - lo, 1e-9)
    s = min(w * (1 - 2 * margin) / span[0], h * (1 - 2 * margin) / span[1])
    mid = (lo + hi) / 2
    return Camera(cam.yaw, cam.pitch, cam.roll, s,
                  w / 2 - mid[0] * s, h / 2 + mid[1] * s)


def silhouette(v, t, cam: Camera, size) -> np.ndarray:
    """Filled mask of what the camera sees. Holes stay holes."""
    w, h = size
    p = v @ cam.matrix().T
    uv = np.c_[p[:, 0] * cam.scale + cam.cx, -p[:, 1] * cam.scale + cam.cy]
    tri = uv[t]
    e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    front = (e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) < 0
    m = np.zeros((h, w), np.uint8)
    cv2.fillPoly(m, list(np.round(tri[front]).astype(np.int32)), 255)
    return m


def vertex_normals(v, t):
    """Area-weighted normal at every vertex.

    Averaging the faces that meet at a vertex is what removes the facets from
    a shaded render. Without it a tessellated surface shows every triangle,
    and a curved part looks like a low-poly model of itself however fine the
    mesh is.
    """
    face = np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]])
    out = np.zeros_like(v)
    for k in range(3):
        np.add.at(out, t[:, k], face)        # area-weighted: not normalised yet
    ln = np.linalg.norm(out, axis=1)[:, None]
    return np.divide(out, ln, out=np.zeros_like(out), where=ln > 1e-12)


def shade(v, t, cam: Camera, size, light=(-0.35, 0.45, 1.0), background: int = 238,
          smooth: bool = True):
    """Lambert plus a little specular, painter's algorithm. Returns the image
    and the silhouette.

    `smooth` shades each triangle by the average of its vertex normals rather
    than by its own, which hides the tessellation. Set it False to see the
    mesh as it is - useful when judging whether a tolerance is fine enough.
    """
    w, h = size
    R = cam.matrix()
    p = v @ R.T
    uv = np.c_[p[:, 0] * cam.scale + cam.cx, -p[:, 1] * cam.scale + cam.cy]
    tri, depth = uv[t], p[:, 2][t].mean(axis=1)
    e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    front = (e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) < 0
    tri, depth, idx = tri[front], depth[front], t[front]

    if smooth:
        vn = vertex_normals(v, t) @ R.T
        n = vn[idx].mean(axis=1)
    else:
        f = p[idx]
        n = np.cross(f[:, 1] - f[:, 0], f[:, 2] - f[:, 0])
    ln = np.linalg.norm(n, axis=1)[:, None]
    n = np.divide(n, ln, out=np.zeros_like(n), where=ln > 1e-12)
    L = np.array(light, float); L /= np.linalg.norm(L)
    lam = np.clip(n @ L, 0, 1)
    tone = np.clip(42 + 150 * lam + 70 * lam ** 24, 0, 255)

    img = np.full((h, w), float(background))
    zbuf = np.full((h, w), -1e9)
    pts = np.round(tri).astype(np.int32)
    mask = np.zeros((h, w), np.uint8)
    cv2.fillPoly(mask, list(pts), 255)

    # Work inside each triangle's bounding box. Rasterising every triangle
    # over the whole frame is the same picture and minutes slower: a model
    # with 100k triangles takes hours that way.
    for i in np.argsort(depth):
        poly = pts[i]
        x0, y0 = poly.min(axis=0)
        x1, y1 = poly.max(axis=0)
        x0, y0 = max(int(x0), 0), max(int(y0), 0)
        x1, y1 = min(int(x1) + 1, w), min(int(y1) + 1, h)
        if x1 <= x0 or y1 <= y0:
            continue
        sub = np.zeros((y1 - y0, x1 - x0), np.uint8)
        cv2.fillConvexPoly(sub, poly - [x0, y0], 1)
        win = zbuf[y0:y1, x0:x1]
        upd = sub.astype(bool) & (depth[i] > win)
        img[y0:y1, x0:x1][upd] = tone[i]
        win[upd] = depth[i]
    return img.astype(np.uint8), mask


def grid(tiles, columns: int = 2) -> np.ndarray:
    """Stack labelled tiles into one sheet."""
    rows = [np.hstack(tiles[i:i + columns]) for i in range(0, len(tiles), columns)]
    width = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 0), (0, width - r.shape[1]), (0, 0)),
                   constant_values=238) for r in rows]
    return np.vstack(rows)


def label(img, text: str) -> np.ndarray:
    out = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if img.ndim == 2 else img.copy()
    cv2.putText(out, text, (16, 32), 0, 0.7, (90, 90, 90), 2, cv2.LINE_AA)
    return out


def views(v, t, cameras: dict, size=(760, 560), margin: float = 0.06):
    """Render a named set of views with one call. Same cameras every run, so
    two versions can be compared by eye without re-aiming anything."""
    out = {}
    for name, angles in cameras.items():
        yaw, pitch, roll = angles
        cam = fit_to_frame(v, Camera(yaw, pitch, roll), size, margin)
        img, mask = shade(v, t, cam, size)
        out[name] = (img, mask, cam)
    return out


STANDARD_VIEWS = {"front": (0, 0, 0), "three-quarter": (-32, 16, 0),
                  "side": (-90, 0, 0), "top": (0, 90, 0)}
