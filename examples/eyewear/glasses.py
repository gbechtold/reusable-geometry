"""A complete pair: front, two clip hinges, two temples.

Shows the feature hierarchy doing real work:

  * `Boss` thickens the front locally so the hinge has something to sit on.
    A boss is a change of wall thickness, not a lump glued on, so there is no
    union anywhere in the front.
  * `ClipHinge` is a `MechanicalFeature`: it builds both halves and then
    MEASURES the gap between them instead of trusting the parameter.
  * `SkullTemple` is a `Temple` that overrides exactly one method.

    python examples/eyewear/glasses.py
    python examples/eyewear/glasses.py --temple cable
"""
from __future__ import annotations

import sys
from pathlib import Path

import cadquery as cq
import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from rgeo import (CableTemple, CheckList, ClipHinge, LibraryTemple,
                  STANDARD_VIEWS, Shell, SkullTemple, Torus, WallProfile, grid,
                  label, mass, merge, mesh, mesh_report, views)
from front import outlines, parameters

OUT = Path(__file__).resolve().parent / "out"
TEMPLES = {"skull": SkullTemple, "library": LibraryTemple, "cable": CableTemple}


def hinge_seat(outer, p, surface, side: int):
    """Where the hinge sits: outer end of the end piece, on the back face."""
    xs = outer[:, 0] * side
    end = outer[xs > xs.max() - 3.0]
    x = float(end[:, 0].mean())
    y = float((end[:, 1].min() + end[:, 1].max()) / 2)
    return np.array([x, y, float(surface.z(x, y, p.thickness))])


def build_front(p):
    """The same front as front.py.

    No boss here, and the reason is worth knowing: a wall of varying thickness
    puts the back face on no single surface, so it cannot be trimmed out of
    one, and a ruled back face needs exactly one hole to span to. This front
    has three. rgeo refuses rather than building something odd - see
    `test_variable_thickness_adds_material` for a part where a boss does work.

    So the hinge carries a flange instead, which is what the real part does:
    the steel fork seats against the frame rather than sitting in a moulded
    lump.
    """
    outer, lens_l, lens_r, window = outlines(p)
    surface = Torus.from_radii(530.0 / p.base_curve, p.front_radius)

    rim = WallProfile(p.thickness).chamfer_front(p.chamfer_front) \
                                  .chamfer_back(p.chamfer_back)
    lens_wall = (WallProfile(p.thickness, outward=True)
                 .chamfer_both(p.chamfer_lens)
                 .groove(at=p.groove_from_front, width=p.groove_width,
                         depth=p.groove_depth))
    plain = WallProfile(p.thickness, outward=True).chamfer_both(p.chamfer_lens)

    body = (Shell(surface)
            .outer(outer, rim)
            .hole(lens_l, lens_wall)
            .hole(lens_r, lens_wall)
            .hole(window, plain)
            .build())
    return body, surface, outer


def main(temple_kind: str = "skull") -> int:
    OUT.mkdir(exist_ok=True)
    p = parameters()
    print("[front]")
    front, surface, outer = build_front(p)
    print(f"  {len(front.val().Faces())} faces, "
          f"{mesh_report(front)['volume_mm3']:.0f} mm3, wall {float(p.thickness):.1f} mm")

    print("\n[hinges and temples]")
    parts = {"front": front}
    checks = CheckList().watertight("front", front)

    cls = TEMPLES[temple_kind]
    for side, tag in ((1, "right"), (-1, "left")):
        seat = hinge_seat(outer, p, surface, side)
        yaw = 0.0 if side > 0 else 180.0
        hinge = ClipHinge(origin=tuple(seat), yaw=yaw, name=f"hinge {tag}")
        temple = cls(origin=tuple(seat + np.array([0, 0, -hinge.socket_back])),
                     side=side, hinge=hinge, name=f"{tag} temple")

        parts[f"hinge_{tag}"] = hinge.female()
        parts[f"temple_{tag}"] = temple.solids()["arm"]
        parts[f"pin_{tag}"] = temple.solids()["pin"]
        gap = hinge.measured_gap()
        print(f"  {tag:5s}: hinge gap {gap:.3f} mm, temple reach "
              f"{temple.reach():.0f} mm, {mass(parts[f'temple_{tag}']):.1f} g")
        for item in hinge.checks().items + temple.checks().items:
            checks.items.append(item)

    print("\n[export]")
    asm = cq.Assembly()
    for name, solid in parts.items():
        cq.exporters.export(solid, str(OUT / f"glasses_{name}.stl"))
        asm.add(solid, name=name)
    asm.save(str(OUT / "glasses.step"))
    print(f"  {len(parts)} parts, {sum(mass(s) for s in parts.values()):.1f} g total")
    print(f"  wrote {OUT / 'glasses.step'}")

    v, t = merge([mesh(s, 0.025, 0.2) for s in parts.values()])
    rendered = views(v, t, STANDARD_VIEWS, size=(680, 480))
    name = OUT / f"glasses_{temple_kind}.png"
    cv2.imwrite(str(name),
                grid([label(img, lbl) for lbl, (img, _, _) in rendered.items()]))
    print(f"  wrote {name}")

    print("\n[checks]")
    print(checks.report())
    return checks.exit_code()


if __name__ == "__main__":
    kind = "skull"
    if "--temple" in sys.argv:
        kind = sys.argv[sys.argv.index("--temple") + 1]
    sys.exit(main(kind))
