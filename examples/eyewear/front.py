"""A spectacle front, built with rgeo from parameters alone.

Deliberately not traced from a product photo: the outlines here are generated,
so the example ships without anyone else's imagery. The tracing half of the
pipeline is shown in `roundtrip.py`, which renders this model, traces the
render back and measures the two against each other.

Run it:

    python examples/eyewear/front.py

Writes out/front.stl, out/front.step, out/front_views.png and prints the
parameter table and the checks.
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
                  mesh, mesh_report, offset, resample, views)
from rgeo import ccw

OUT = Path(__file__).resolve().parent / "out"


def parameters() -> ParamSet:
    """Every number, with where it came from.

    The values and their sources are the ones from the project this package
    came out of - a navigator front measured off product photography.
    """
    return ParamSet(
        lens_width=Assumed(56.0, "typical aviator boxing",
                           "nothing in a photo fixes absolute scale"),
        lens_height=Measured(44.8, "front photo", "bounding box of the opening"),
        dbl=Measured(17.6, "front photo", "gap between the openings"),
        rim_top=Measured(3.7, "front photo", "brow bar above the lens"),
        rim_side=Measured(5.7, "front photo", "median radial gap"),
        corner=Assumed(0.22, "navigator shape", "0 = rectangle, 1 = ellipse",
                       unit=""),
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
        bridge_window=Measured(13.0, "front photo", "width of the opening"),
        bridge_window_h=Measured(7.0, "front photo", "height of the opening"),
        bridge_window_top=Assumed(
            3.5, "material left above the window, below the brow bar top"),
    )


def superellipse(width, height, corner, n=200, centre=(0.0, 0.0)):
    """A rounded rectangle that reads as a navigator shape.

    `corner` runs 0 (rectangle) to 1 (ellipse). Real lens shapes come from a
    DXF or a trace; this is here so the example needs no outside data.
    """
    e = 2.0 / max(corner, 1e-3)
    t = np.linspace(0, 2 * np.pi, n * 8, endpoint=False)
    c, s = np.cos(t), np.sin(t)
    x = np.sign(c) * np.abs(c) ** (2.0 / e) * width / 2
    y = np.sign(s) * np.abs(s) ** (2.0 / e) * height / 2
    # by arc length, not by angle: a square-ish superellipse sampled by angle
    # puts most of its points on the flats and almost none on the corners
    return resample(np.c_[x + centre[0], y + centre[1]], n)


def outlines(p: ParamSet):
    """Lens openings, bridge window and the front silhouette around them."""
    half = p.dbl / 2 + p.lens_width / 2
    lens_r = superellipse(p.lens_width, p.lens_height, p.corner, centre=(half, 0))
    lens_l = lens_r * np.array([-1.0, 1.0])
    lens_l = lens_l[::-1]                       # keep both counter-clockwise
    top = p.lens_height / 2 + p.rim_top

    # The window sits in the bridge, between the lens openings: it has to be
    # narrower than the DBL and leave material above it.
    window = superellipse(p.bridge_window, p.bridge_window_h, 0.5, n=120,
                          centre=(0.0, top - p.bridge_window_top
                                  - p.bridge_window_h / 2))

    # The silhouette is the two openings grown by the rim width, plus the
    # bridge block that joins them. Without the block the two halves never
    # meet: the rim is 5.7 mm and the gap between the lenses is 17.6 mm.
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    block_x = p.dbl / 2 + p.lens_width * 0.18
    block_bottom = float(window[:, 1].min()) - p.rim_side * 0.8
    block = Polygon([(-block_x, block_bottom), (block_x, block_bottom),
                     (block_x, top), (-block_x, top)])

    grown = unary_union([Polygon(offset(lens_l, p.rim_side, keep_count=False)),
                         Polygon(offset(lens_r, p.rim_side, keep_count=False)),
                         block])
    if grown.geom_type == "MultiPolygon":
        raise ValueError("the front fell apart - rim_side too small for this dbl")
    grown = grown.buffer(2.0, join_style=1).buffer(-2.0, join_style=1)
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

    v, t = mesh(solid, 0.02, 0.15)
    rendered = views(v, t, STANDARD_VIEWS, size=(680, 480))
    cv2.imwrite(str(OUT / "front_views.png"),
                grid([label(img, name) for name, (img, _, _) in rendered.items()]))
    print(f"  wrote {OUT / 'front_views.png'}")

    print("\n[checks]")
    checks = check(p, solid)
    print(checks.report())
    return checks.exit_code()


if __name__ == "__main__":
    sys.exit(main())
