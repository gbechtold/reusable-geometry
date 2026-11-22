"""Photograph to outlines.

Measuring a reference instead of eyeballing it is the single change that moves
a model most: on the first part this package was built from, tracing the
outline rather than estimating it took silhouette overlap from 69.6 % to
92.0 %.

    outlines = trace("front.png", threshold=165, mirror=True)
    outlines.outer        # (n, 2) in pixels
    outlines.holes        # list of (n, 2)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from .outline import ccw, resample, smooth


@dataclass
class Traced:
    outer: np.ndarray
    holes: list[np.ndarray] = field(default_factory=list)
    mask: np.ndarray | None = None
    axis_x: float | None = None

    def scaled(self, mm_per_px: float, origin=(0.0, 0.0), flip_y: bool = True):
        """Pixels to millimetres, y pointing up, origin where you say."""
        def conv(c):
            out = np.asarray(c, float).copy()
            out[:, 0] = (out[:, 0] - origin[0]) * mm_per_px
            out[:, 1] = ((origin[1] - out[:, 1]) if flip_y
                         else (out[:, 1] - origin[1])) * mm_per_px
            return ccw(out)
        return Traced(conv(self.outer), [conv(h) for h in self.holes])

    def tidy(self, n_outer: int = 300, n_hole: int = 180, window: int = 7):
        """Resample and lightly smooth. Keep the window small - a wide one
        rounds real corners inward."""
        def fix(c, n):
            return resample(smooth(resample(c, max(n * 4, 600)), window), n)
        return Traced(fix(self.outer, n_outer), [fix(h, n_hole) for h in self.holes])


def frame_mask(img, threshold: int = 165, open_px: int = 11, close_px: int = 5,
               hull_holes_above: float = 0.05) -> np.ndarray:
    """Filled silhouette of a dark part on a light ground.

    `open_px` removes the drop shadow, which otherwise survives the threshold
    as thin tails along the bottom edge. `hull_holes_above` replaces large
    holes with their convex hull - for a transparent window with something
    visible behind it, which would otherwise bite notches out of the opening.
    Set it to 0 to keep holes exactly as traced.
    """
    g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (3, 3), 0)
    bw = (g < threshold).astype(np.uint8) * 255
    if open_px:
        bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((open_px, open_px), np.uint8))
    if close_px:
        bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((close_px, close_px), np.uint8))

    cnts, hier = cv2.findContours(bw, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    hier = hier[0]
    areas = [cv2.contourArea(c) for c in cnts]
    outer = max((i for i in range(len(cnts)) if hier[i][3] < 0), key=lambda i: areas[i])

    m = np.zeros(bw.shape, np.uint8)
    cv2.fillPoly(m, [cnts[outer]], 255)
    for i in range(len(cnts)):
        if hier[i][3] == outer and areas[i] > areas[outer] * 0.004:
            c = cv2.convexHull(cnts[i]) if (hull_holes_above and
                                            areas[i] > areas[outer] * hull_holes_above) \
                else cnts[i]
            cv2.fillPoly(m, [c], 0)
    return m


def mirror_mask(mask: np.ndarray, axis_x: int | None = None):
    """Mirror one half onto the other.

    Done on the MASK, before any contour is taken: a part that should be
    symmetric then is, exactly, and both sides carry identical outlines.
    Tracing two halves separately leaves them a pixel or two apart.
    """
    xs = np.where(mask.any(axis=0))[0]
    x0 = int(round((xs.min() + xs.max()) / 2)) if axis_x is None else int(axis_x)
    right = mask[:, x0:]
    left = np.fliplr(right)
    out = np.zeros_like(mask)
    w = min(left.shape[1], x0)
    out[:, x0 - w:x0] = left[:, left.shape[1] - w:]
    out[:, x0:x0 + right.shape[1]] = right
    return out, x0


def trace(path_or_image, threshold: int = 165, mirror: bool = False,
          min_hole_fraction: float = 0.004, **mask_kw) -> Traced:
    img = cv2.imread(str(path_or_image)) if isinstance(path_or_image, (str, bytes)) \
        else path_or_image
    if img is None:
        raise FileNotFoundError(path_or_image)
    mask = frame_mask(img, threshold, **mask_kw)
    axis = None
    if mirror:
        mask, axis = mirror_mask(mask)

    cnts, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    hier = hier[0]
    areas = [cv2.contourArea(c) for c in cnts]
    oi = max((i for i in range(len(cnts)) if hier[i][3] < 0), key=lambda i: areas[i])
    holes = sorted((i for i in range(len(cnts))
                    if hier[i][3] == oi and areas[i] > areas[oi] * min_hole_fraction),
                   key=lambda i: areas[i], reverse=True)
    return Traced(cnts[oi].reshape(-1, 2).astype(float),
                  [cnts[i].reshape(-1, 2).astype(float) for i in holes],
                  mask=mask, axis_x=axis)


def overlay(img, traced: Traced, thickness: int = 3) -> np.ndarray:
    """Draw what was found, for a look before trusting it."""
    vis = img.copy()
    cv2.drawContours(vis, [traced.outer.astype(np.int32)], -1, (0, 150, 255), thickness)
    cols = [(0, 220, 60), (230, 80, 230), (60, 60, 255), (255, 200, 0)]
    for n, h in enumerate(traced.holes):
        cv2.drawContours(vis, [h.astype(np.int32)], -1, cols[n % len(cols)], thickness)
    return vis
