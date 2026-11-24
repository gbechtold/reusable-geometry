"""A spectacle front, built with rgeo from parameters alone.

Deliberately not traced from a product photo: the outlines here are generated,
so the example ships without anyone else's imagery. The tracing half of the
pipeline is shown in `roundtrip.py`, which renders this model, traces the
render back and measures the two against each other.

Run it:

    python examples/eyewear/front.py

Writes out/front.stl, out/front.step, out/front_views.png,
out/front_turntable.gif, and prints the parameter table and the checks.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cadquery as cq
import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from rgeo import (Assumed, CheckList, Fitted, Measured, ParamSet, STANDARD_VIEWS,
                  Shell, Torus, WallProfile, grid, label, mass, mean_radial_gap,
                  mesh, mesh_report, offset, resample, turntable, views,
                  write_gif)
from rgeo import ccw

OUT = Path(__file__).resolve().parent / "out"


def parameters() -> ParamSet:
    """Every number, with where it came from.

    The values and their sources are the ones from the project this package
    came out of - a navigator front measured off product photography.
    """
    return ParamSet(
        lens_width=Assumed(52.0, "typical boxing for this frame size",
                           "nothing in a photo fixes absolute scale"),
        lens_height=Assumed(41.0, "a frame is wider than it is tall",
                            "w:h about 1.27, the usual band"),
        dbl=Assumed(18.0, "bridge width", "the usual 16 to 20"),
        rim_top=Assumed(5.6, "brow bar above the lens",
                        "the heavy top edge this family is recognised by"),
        rim_side=Assumed(4.2, "rim beside the lens",
                         "lighter than the brow, which is the point"),
        corner_top=Assumed(0.52, "flat under the brow",
                           "0 = rectangle, 1 = ellipse", unit=""),
        corner_bottom=Assumed(0.78, "rounder underneath",
                              "0 = rectangle, 1 = ellipse", unit=""),
        lens_rise=Assumed(0.07, "lift at the outer top corner",
                          "fraction of the lens height", unit=""),
        base_curve=Assumed(6.0, "most common lens base curve", unit=""),
        front_radius=Fitted(220.0, "three-quarter view",
                            "flat optimum, 68-69% across 220..320"),
        thickness=Assumed(6.0, "typical SLS front"),
        chamfer_front=Assumed(1.1, "bright bevel in the photos"),
        chamfer_back=Assumed(0.7, "narrower than the front bevel"),
        chamfer_lens=Assumed(0.6, "edge break at the opening"),
        groove_depth=Assumed(0.7, "standard lens bevel"),
        groove_width=Assumed(0.9, "standard lens bevel"),
        groove_from_front=Assumed(2.6, "lens sits this far behind the front"),
        bridge_window=Assumed(11.0, "width of the opening in the bridge"),
        bridge_window_h=Assumed(5.0, "height of that opening"),
        bridge_window_top=Assumed(
            3.0, "material left above the window, below the brow bar top"),
    )


def lens_shape(width, height, corner_top=0.40, corner_bottom=0.62,
               rise=0.05, n=220, centre=(0.0, 0.0)):
    """A spectacle lens outline: flatter along the top, rounder underneath.

    A single superellipse is symmetric top to bottom, which is why it reads as
    a box rather than a frame. Real lens shapes are not: the top edge runs
    almost straight under the brow and the bottom is noticeably rounder. Two
    exponents, blended across the curve, is the smallest change that fixes it.

    `corner` runs 0 (rectangle) to 1 (ellipse). `rise` lifts the outer top
    corner, which is what gives a frame its lift instead of a deadpan
    horizontal.
    """
    t = np.linspace(0, 2 * np.pi, n * 8, endpoint=False)
    c, s_ = np.cos(t), np.sin(t)
    # blend the exponent between the top half and the bottom half
    upper = (s_ + 1) / 2
    corner = corner_bottom + (corner_top - corner_bottom) * upper
    e = 2.0 / np.clip(corner, 1e-3, None)
    x = np.sign(c) * np.abs(c) ** (2.0 / e) * width / 2
    y = np.sign(s_) * np.abs(s_) ** (2.0 / e) * height / 2
    y = y + rise * height * np.clip(c, 0, None) * np.clip(s_, 0, None)
    return resample(np.c_[x + centre[0], y + centre[1]], n)


def outlines(p: ParamSet):
    """Lens openings, bridge window and the front silhouette around them."""
    half = p.dbl / 2 + p.lens_width / 2
    lens_r = lens_shape(p.lens_width, p.lens_height, p.corner_top,
                        p.corner_bottom, p.lens_rise, centre=(half, 0))
    lens_l = lens_r * np.array([-1.0, 1.0])
    lens_l = lens_l[::-1]                       # keep both counter-clockwise
    top = p.lens_height / 2 + p.rim_top

    # The silhouette is the two openings grown by the rim width, joined by a
    # brow bar that runs the full width. A block only in the middle leaves a
    # step sticking up over the bridge; a continuous bar is both what the
    # frame family actually looks like and the simpler shape.
    from shapely.affinity import translate
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    # The brow bar is the grown lens shape again, shifted up. A rectangular
    # bar laid over the top leaves a step at the outer corner where it ends
    # and the lens is already narrower; shifting the same curve means the top
    # edge IS the lens shape, which is what a frame actually looks like.
    lift = max(p.rim_top - p.rim_side, 0.0)
    brows = []
    for lens in (lens_l, lens_r):
        g = Polygon(offset(lens, p.rim_side, keep_count=False))
        brows += [g, translate(g, 0.0, lift)]

    # The saddle bridge. Without it there is no material below the brow
    # between the lenses, and the window in it has nothing to sit in.
    #
    # Its top is taken from the brow it joins rather than from `top`: running
    # it to the full height leaves a rectangular step standing over the
    # bridge, because the brow follows the lens and has already fallen away
    # by the time it reaches the middle.
    brow = unary_union(brows)
    bridge_x = p.dbl / 2 + p.lens_width * 0.07
    strip = Polygon([(-bridge_x, -top), (bridge_x, -top),
                     (bridge_x, top * 2), (-bridge_x, top * 2)])
    shared = brow.intersection(strip)
    bridge_top = (shared.bounds[3] if not shared.is_empty
                  else p.lens_height / 2 + p.rim_side)
    # The window sits in the bridge, so it is placed from the bridge the way
    # it was actually built - not from a height worked out separately, which
    # goes wrong the moment any brow parameter changes.
    window = lens_shape(p.bridge_window, p.bridge_window_h, 0.62, 0.62,
                        rise=0.0, n=120,
                        centre=(0.0, bridge_top - p.bridge_window_top
                                - p.bridge_window_h / 2))
    bridge_bottom = float(window[:, 1].min()) - p.rim_side * 0.9
    saddle = Polygon([(-bridge_x, bridge_bottom), (bridge_x, bridge_bottom),
                      (bridge_x, bridge_top), (-bridge_x, bridge_top)])

    grown = unary_union(brows + [saddle])
    grown = grown.buffer(2.6, join_style=1).buffer(-2.6, join_style=1)
    # resample: the union leaves well over a thousand points, and both the
    # spline fit and the ruled faces cost time per point
    outer = resample(ccw(np.array(grown.exterior.coords)[:-1]), 320)
    return outer, lens_l, lens_r, window


def build(p: ParamSet) -> cq.Workplane:
    outer, lens_l, lens_r, window = outlines(p)
    surface = Torus.from_radii(530.0 / p.base_curve, p.front_radius)

    rim = (WallProfile(p.thickness)
           .chamfer_front(p.chamfer_front)
           .chamfer_back(p.chamfer_back))
    lens_wall = (WallProfile(p.thickness, outward=True)
                 .chamfer_both(p.chamfer_lens)
                 .groove(at=p.groove_from_front, width=p.groove_width,
                         depth=p.groove_depth))
    plain = WallProfile(p.thickness, outward=True).chamfer_both(p.chamfer_lens)

    return (Shell(surface)
            .outer(outer, rim)
            .hole(lens_l, lens_wall)
            .hole(lens_r, lens_wall)
            .hole(window, plain)
            .build())


def check(p: ParamSet, solid) -> CheckList:
    outer, lens_l, lens_r, _ = outlines(p)
    rim_med, rim_min, _ = mean_radial_gap(lens_r, outer, skip_sectors=[(150, 210)])
    width = outer[:, 0].max() - outer[:, 0].min()
    return (CheckList()
            .watertight("front", solid)
            .between("front width", width, 125, 155)
            .at_least("rim width", rim_med, 2.5)
            .at_least("groove lip front",
                      p.groove_from_front - p.groove_width / 2, 1.5)
            .at_least("groove lip back",
                      p.thickness - p.groove_from_front - p.groove_width / 2, 1.5)
            .add("chamfers fit the wall",
                 p.chamfer_front + p.chamfer_back < p.thickness * 0.6,
                 f"{p.chamfer_front + p.chamfer_back:.2f} mm",
                 f"< {p.thickness * 0.6:.2f} mm")
            .add("groove shallower than the rim", p.groove_depth < rim_med * 0.4,
                 f"{float(p.groove_depth):.2f} mm", f"< {rim_med * 0.4:.2f} mm"))


def main() -> int:
    OUT.mkdir(exist_ok=True)
    p = parameters()
    print("[parameters]")
    print(p.table())
    print(f"\n  {len(p.assumptions())} of {len(p.values)} values are assumptions: "
          f"{', '.join(p.assumptions())}\n")

    print("[build]")
    solid = build(p)
    r = mesh_report(solid)
    print(f"  {len(solid.val().Faces())} faces, watertight {r['watertight']}, "
          f"{r['volume_mm3']:.0f} mm3, {mass(solid):.1f} g in PA12")

    cq.exporters.export(solid, str(OUT / "front.stl"))
    cq.exporters.export(solid, str(OUT / "front.step"))
    json.dump(p.to_dict(), open(OUT / "front_params.json", "w"), indent=1)

    v, t = mesh(solid, 0.015, 0.12)
    rendered = views(v, t, STANDARD_VIEWS, size=(680, 480))
    cv2.imwrite(str(OUT / "front_views.png"),
                grid([label(img, name) for name, (img, _, _) in rendered.items()]))
    print(f"  wrote {OUT / 'front_views.png'}")

    gif = write_gif(turntable(v, t, size=(560, 400), frames=42, sweep=360.0,
                              pitch=10.0, background=246, supersample=3),
                    OUT / "front_turntable.gif", fps=24)
    print(f"  wrote {gif.name}, {gif.stat().st_size / 1024:.0f} kB")

    print("\n[checks]")
    checks = check(p, solid)
    print(checks.report())
    return checks.exit_code()


if __name__ == "__main__":
    sys.exit(main())
