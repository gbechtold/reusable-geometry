# rgeo - idea to reusable geometry

Build parametric CAD in code when your reference is a photograph rather than a
drawing, and prove afterwards how close you got.

![a parametric eyewear front built with rgeo](docs/img/example-front.png)

```python
from rgeo import Shell, Torus, WallProfile, mesh_report

body = (Shell(Torus.from_radii(vertical=88.3, horizontal=220.0))
        .outer(front_outline, WallProfile(6.0).chamfer_front(1.1).chamfer_back(0.7))
        .hole(lens_left,  lens_wall)
        .hole(lens_right, lens_wall)
        .hole(bridge_window, WallProfile(6.0, outward=True).chamfer_both(0.6))
        .build())

mesh_report(body)     # {'watertight': True, 'volume_mm3': 14613.0, ...}
```

That builds in a tenth of a second and comes out watertight, with chamfers, a
lens groove and three openings - and not one boolean operation.

## Why

Code-defined CAD is attractive: dimensions become variables, the model is
diffable, and a language model can write it. Two things get in the way in
practice.

**The kernel fights you.** On a curved surface of any size, OpenCascade's
booleans and fillets fail - and mostly fail *silently*. Measured on a sphere
of R = 88 mm: the same cut returned 3920 mm³ at fuzzy tolerance 1e-4 and 2689
mm³ at 1e-3; an exact boolean returned an empty solid with no error; a union
of two lofted bodies came back at -2.4e6 mm³; `fillet()` on four spline edges
ran for over nine minutes without completing. Full list with reproductions in
[docs/WHY.md](docs/WHY.md).

**Numbers lose their pedigree.** Six months on, nobody remembers which
dimension was measured off the part, which was fitted, and which was a guess
that has been quietly load-bearing ever since.

rgeo answers both: describe walls instead of cutting them, and make every
number carry where it came from.

## Install

```bash
pip install -e ".[dev]"        # Python 3.10-3.12; cadquery has no 3.13+ wheels yet
pytest
```

## The pipeline

```
reference ──trace──> outlines ──┐
                                ├──> Shell ──> solid ──> check ──> compare
            parameters ─────────┘                                     │
                                                                      └──> mm
```

Each stage stands on its own. Use the whole chain, or just the shell builder.

### 1. Measure the reference, do not estimate it

```python
from rgeo import trace
traced = trace("product-photo.png", threshold=165, mirror=True)
outlines = traced.scaled(mm_per_px=0.09, origin=(cx, cy)).tidy()
```

`mirror=True` mirrors one half onto the other **on the mask, before any
contour is taken**, so a part that should be symmetric is - exactly.

On the project this came out of, tracing the outline rather than estimating it
moved silhouette overlap from 69.6 % to 92.0 %. It is the single change that
mattered most.

### 2. Say where every number came from

```python
from rgeo import ParamSet, Measured, Fitted, Assumed

p = ParamSet(
    lens_height = Measured(44.8, "front photo", "bounding box of the opening"),
    front_radius= Fitted(220.0, "three-quarter view", "flat optimum 220..320"),
    lens_width  = Assumed(56.0, "typical aviator boxing",
                          "nothing in a photo fixes absolute scale"),
)
p.lens_width + 1.0          # 57.0 - it is a float everywhere
print(p.table())            # markdown, grouped by provenance
p.assumptions()             # the ones a reader has to be warned about
```

### 3. Describe the walls

A feature that would normally be a cut is an offset in a wall profile:

```python
from rgeo import WallProfile

rim  = WallProfile(6.0).chamfer_front(1.1).chamfer_back(0.7)
lens = (WallProfile(6.0, outward=True)
        .chamfer_both(0.6)
        .groove(at=2.6, width=0.9, depth=0.7))     # lens bevel groove
boss = WallProfile(6.0).round_both(0.5).step(at=4.0, offset=0.8)
```

Thickness may vary across the part, which is how a boss stands proud of the
back face without a boolean:

```python
thick = np.where(np.abs(angle - 90) < 30, 10.0, 6.0)   # one entry per point
shell.outer(outline, rim, thickness=thick)
```

### 4. Pick the surface the part lies on

| | use for | trimmed faces with holes |
|---|---|---|
| `Plane()` | flat parts | yes |
| `Cylinder(r)` | single curvature | yes |
| `Sphere(r)` / `from_base_curve(6)` | lenses, domes | **no** - see below |
| `Torus.from_radii(vertical, horizontal)` | two curvatures at once | yes |

A sphere's parametrisation is singular at its pole, so an outline around the
axis cannot be expressed there. rgeo says so instead of handing back an empty
face:

```
GeometryError: Sphere.face() came out empty. If this is a Sphere, the outline
probably encloses the pole - use Torus or Cylinder instead.
```

This is not academic. A spectacle front is spherical per lens, but a 145 mm
wide front on a base-curve-6 sphere would sag 35 mm. Real fronts carry the
base curve vertically and a flatter wrap horizontally - a torus, which also
happens to be the shape whose parameter space has no pole in the way.

### 5. Check, every time

```python
from rgeo import CheckList

checks = (CheckList()
          .watertight("front", body)
          .at_least("rim width", rim_mm, 2.5)
          .between("front width", width_mm, 125, 155))
print(checks.report())
raise SystemExit(checks.exit_code())     # non-zero if anything failed
```

Watertightness is measured on the **mesh**, not the B-rep: OpenCascade will
flag a perfectly printable solid as invalid and will also call a broken one
valid. The mesh is what gets printed.

### 6. Compare against the reference, in millimetres

```python
from rgeo import fit_camera, comparison_strip

result = fit_camera(vertices, triangles, photo_mask)
print(result.summary())
# overlap  85.0%   outline off by 0.32 mm mean, 0.76 mm p95  (yaw 0.9, 4.18 px/mm)
```

![render, trace, fit](docs/img/roundtrip.png)

Two rules keep that number honest:

- **The camera is fitted, never the geometry.** What is left over is then a
  statement about shape, not about viewpoint.
- **Millimetres, not just overlap.** IoU is brutal on anything thin: a 5 mm
  wide rim offset by half a millimetre loses ten points of overlap and reads
  like a far bigger error than it is.

And when a parameter is not constrained by the reference, `sweep` says so
rather than reporting a winner:

```
flat optimum: best and worst differ by 1.4 points, so this parameter is not
constrained by the reference
```

## Features, and why they form a hierarchy

A feature is a named piece of geometry that knows how to check itself. The
hierarchy is not decoration: each level says how the feature is made, and that
decides what can go wrong with it.

```
Feature                      a named thing with its own checks
├── ProfileFeature           changes a wall. No body, no boolean, so nothing
│                            can fail at build time.
└── BodyFeature              brings solids with it
        └── MechanicalFeature    two parts that have to fit, gap MEASURED
```

`MechanicalFeature` is where it earns its keep. A fit is not a shape, it is a
relationship between two shapes, and the thing that goes wrong is always the
same: the gap is not what the drawing says. So the base class owns the
clearance and measures it; a subclass only supplies the two bodies.

```python
from rgeo import ClipHinge

hinge = ClipHinge(pin_radius=1.1, clearance=0.15)
hinge.measured_gap()        # 0.144 - measured between the solids, not claimed
hinge.snap_interference()   # 0.28 mm the jaws have to spread. Zero = falls out
print(hinge.checks().report())
```

### A mechanical feature: the clip hinge

![clip hinge](docs/img/hinge.png)

A hinge the temple clips into - a slotted fork on the frame, a cross pin on
the temple, pushed past a narrow point into a round socket. Both halves are
plain extrusions of a 2D outline: the snap is the **shape of the slot**, not
something cut into it afterwards. That is why it builds in milliseconds and
cannot fail a boolean.

Its checks are the ones a part like this actually fails:

```
ok   clip hinge parts clear each other      0.144 mm   want > 0 mm
ok   clip hinge gap matches the clearance   0.144 mm   want 0.15 +/- 0.06 mm
ok   clip hinge jaw thickness                2.10 mm   want >= 0.8 mm
ok   clip hinge snap interference            0.28 mm   want >= 0.05 mm
ok   clip hinge snap is not excessive        0.28 mm   want < 0.88 mm
```

### Inheritance that pays: temples

![three temple shapes](docs/img/temples.png)

Every temple is the same construction - a centre line, a section swept along
it, a rounded tip - and they differ in exactly one thing: what the centre line
does towards the ear. So that is the only method a subclass overrides.

```python
class SkullTemple(Temple):
    def drop(self, f):                     # f: 0 at the hinge, 1 at the tip
        t = np.clip((f - self.drop_start) / (1 - self.drop_start), 0, 1)
        return -self.drop_depth * (t * t * (3 - 2 * t))
```

`Temple` straight, `LibraryTemple` straight with a deeper tip, `SkullTemple`
bent behind the ear, `CableTemple` curled right round it. If you find yourself
overriding more than `drop()`, the base class is wrong and should be fixed
instead.

### Profile features

`Groove`, `EdgeBreak` and `Boss` change a wall rather than cutting it:

```python
wall = Groove(at=2.6, width=0.9, depth=0.7).apply_to(
       EdgeBreak(0.6).apply_to(WallProfile(6.0, outward=True)))

boss = Boss(angle_centre=170, angle_width=30, thickness=9.0)
shell.outer(outline, rim, thickness=boss.thickness_for(outline, 6.0))
```

A `Boss` returns a per-point thickness instead of a body, which is how a
raised pad gets made without a union - the operation that returned -2.4e6 mm³
when it was tried. Its limit is honest and enforced: a varying wall puts the
back face on no single surface, so it cannot be trimmed out of one, and a
ruled back face needs exactly one hole to span to. With more holes than that,
rgeo refuses and says why.

## What it is not

- **Not a CAD kernel.** It sits on CadQuery and OpenCascade and works around
  their weak spots; it does not replace them.
- **Not a sculpting tool.** Freeform surfacing, curvature-continuous blends
  and class-A surfaces are out of scope. OpenCascade's fillets are circular,
  therefore tangent-continuous only.
- **Not a mesh library.** It builds B-rep solids and exports STEP and STL.
- **No simulation, no CAM, no drawings.**

## Examples

```bash
python examples/eyewear/front.py              # build, export, render, check
python examples/eyewear/roundtrip.py          # render, trace it back, measure
python examples/eyewear/glasses.py            # the whole pair: front, hinges, temples
python examples/eyewear/glasses.py --temple cable
```

`front.py` builds a complete spectacle front - three openings, chamfers, lens
groove, face-form wrap - from parameters alone. The outlines are generated,
not traced, so the repository ships without anyone else's imagery.
`roundtrip.py` exercises the measuring half: it renders the model from a
viewpoint the fitter is not told about and checks that the fitter finds it
again. `glasses.py` puts the features together into seven parts - a front, two
clip hinges, two temples, two pins - and runs every check each of them brings.

## Origin

This came out of rebuilding two real eyewear frames from photographs: half a
frame front from a photo of a SolidWorks session (92.0 % silhouette overlap),
and a complete pair from product photography (outline off by 0.32 mm frontally,
1.31 mm in a view nothing was traced from). Every workaround in here is
something that project hit, measured, and had to route around.

## Licence

MIT. See [LICENSE](LICENSE).
