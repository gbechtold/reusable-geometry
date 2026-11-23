# Why rgeo is built the way it is

Every design decision in this package came out of something measured, not
something read. This file keeps the measurements, so a future maintainer can
tell which constraints are real and which have since been fixed upstream.

Measured in November 2026 with CadQuery 2.8.0 on cadquery-ocp 7.9.3
(OpenCascade 7.9), Python 3.12, macOS arm64.

## The kernel findings

### 1. `fillet()` does not complete on spline edges lying on a curved face

Four edges, radius 0.55 mm, on the spherical front and back faces of a frame
rim. Ran for over nine minutes without returning; killed, not crashed. Cutting
the edge count to four by filleting before the groove cut made no difference.

**Consequence.** `WallProfile.round_front()` / `round_back()` build the edge
break into the wall as a quarter-circle of offsets. Exact, free, and it cannot
fail on a topology change - which is the other thing fillets do.

### 2. Booleans against a large curved surface return an empty solid, silently

Intersecting a lofted spline body with a sphere of R = 88 mm:

| fuzzy tolerance | result |
|---|---|
| none (exact) | empty solid, no exception |
| 1e-6 | empty solid, no exception |
| 1e-4 | 12343.8 mm³ |
| 1e-3 | 12343.9 mm³ |

The same cut on a different body in the same model:

| fuzzy tolerance | result |
|---|---|
| 1e-4 | 3920.4 mm³, flagged invalid |
| 1e-3 | 2689.5 mm³, flagged invalid |

Two different answers for one operation, neither of them trustworthy, and the
invalid result then broke the next operation in the chain.

**Consequence.** `Shell` builds the body from faces and sews it. There is no
boolean in the base shape at all.

### 3. `union()` of two lofted spline bodies returns a negative volume

Two valid solids, 11 834 mm³ and 1 444 mm³, both closed, both `isValid()`:

| fuzzy tolerance | result |
|---|---|
| none | `ValueError: Null TopoDS_Shape object` |
| 1e-4 | -2 435 516 mm³ |
| 1e-3 | -2 435 516 mm³ |
| 5e-3 | -2 435 569 mm³ |
| 2e-2 | 8 024 mm³ (less than one input) |
| 5e-2 | 433 452 mm³ |

`cut()` between the same two bodies worked. Union is the fragile one.

**Consequence.** Features that would be a union - a boss, a lug, a thicker end
piece - are expressed as varying wall thickness instead.

### 4. A per-vertex normal offset folds over on concave runs

Offsetting an outline by moving each point along its vertex normal
self-intersects wherever the outline turns in on itself. The wire stays
"valid"; every loft built on it afterwards is not, and the error surfaces two
operations later where the cause is invisible. One measured symptom: a hinge
block came back from its boolean with volume 0.

**Consequence.** `rgeo.offset` goes through shapely's buffer, which resolves
self-intersection properly.

### 5. An outline's direction flips in parameter space

An outline running counter-clockwise in (x, y) can run clockwise in a
surface's (u, v). Trimming a toroidal face with it as given produced a face of
**area -5747 mm²**, flagged invalid - the complement of what was wanted.

### 6. Adding a hole to a trimmed face silently yields area 0

`BRepBuilderAPI_MakeFace(surface, outer_wire, True)` works. Calling `.Add(hole)`
on the resulting face returns `IsDone() == True` and a face of **area 0.0**,
whichever way round the hole wire runs.

**Consequence for 5 and 6.** `Surface.face()` goes through `ShapeFix_Face`,
which takes all the wires at once and sorts out orientation itself.

### 7. A trimmed face can have an area and no triangles

A toroidal face reported 1856 mm² and tessellated to **zero triangles**. The
cause was two holes overlapping once their wall profiles were applied: in the
sketch they were 0.2 mm apart, and chamfers of 0.6 mm on each widened them
into each other. Nothing raised. The body sewed, reported a plausible volume,
and its mesh had 3671 non-manifold edges.

**Consequence.** `Shell.build()` checks clearances between holes and against
the outer wall *after* applying the wall profiles, and refuses with a message
naming the gap.

### 8. Points spaced by angle instead of arc length blow up the spline

A square-ish superellipse sampled at even angles puts most of its points on
the flats and almost none on the corners. Segment lengths ran 0.227 mm to
13.087 mm on one outline. The periodic spline through them overshot, and the
body tessellated to 1.2 million triangles - 292 seconds - with 3521
non-manifold edges.

**Consequence.** `Shell` refuses an outline whose segment lengths vary by more
than 25x, and says to resample by arc length.

### 9. `Shell.makeShell` does not sew

Faces assembled with it keep their own edges, so the shell stays open and the
volume it reports is meaningless. `BRepBuilderAPI_Sewing` is required, and
`Closed(True)` has to be set by hand afterwards - OCC does not set it.

### 10. `Solid.Volume()` is not reliable on ruled faces

One body reported 3937 mm³ from the B-rep and 2321 mm³ from its mesh. The mesh
figure matched a hand calculation. Where the number matters - mass, material
cost, a check - use `mesh_report()`.

### 11. A socket arc swept the wrong way puts material where the pin goes

The snap socket of `ClipHinge` is an arc around the pin centre. Sweeping it
from -(180-snap) through **0** wraps the front half of the pin, which is what
is wanted; sweeping through 180 wraps the back half and leaves solid material
at the pin position. Both produce a valid, watertight, plausible-looking
solid. The difference only shows up as a measurement: `measured_gap()`
returned **0.000 mm** instead of 0.144 mm.

This is the argument for `MechanicalFeature` measuring its own fit. No check
on either body alone would have caught it.

### 12. A repeated point in an outline fails with a message about nothing

Two coincident points make `polyline()` raise `Standard_Failure: BRep_API:
command not done`, which says nothing about the cause. It happens naturally
when an arc is built to start exactly where the straight run ends - that is,
when the geometry is *right*.

**Consequence.** `_dedupe` drops repeated points before any wire is built.

### 13. A pinned-up frame collapses wherever the path runs vertical

`across = up x tangent` with `up` pinned to (0, 1, 0) is right for anything
with a real up - a temple never runs vertically - and degenerate for a closed
rim, which runs vertically at both its left and right extremes. There the
cross product goes to zero, the section has no area, and the loft comes out
broken.

Found by a consumer of this package that needed a 1.2 mm wire rim and had to
write its own sweep. Parallel transport has no preferred direction and
therefore no singularity; `frame="auto"` uses the pinned frame where it works
and falls back where it does not.

### 14. A shared GIF palette is worse than one per frame

Quantising every frame to one palette looked like it should help GIF's
between-frame compression. Measured on a 36-frame sweep at 860 x 560:

| colours | per-frame palette | one shared palette |
|---|---|---|
| 32 | **594 kB** | 1010 kB |
| 48 | 699 kB | 1014 kB |
| 64 | 782 kB | 1014 kB |
| 128 | 971 kB | 1021 kB |

Worse at every setting. Pillow's own optimiser handles the per-frame case
better than a hand-shared palette does. The same table settles the colour
count: 32 against 128 differ by 0.13 of 255 on average, which is nothing on a
greyscale render, and save 40 %.

Recorded because the theory was plausible and wrong, and the next person will
have the same idea.

## The method findings

These cost more time than the kernel ones, and generalise further.

### Measure the reference; do not estimate it

Reproducing a frame front from a photograph, by hand-estimating the outline:
**69.6 %** silhouette overlap. Tracing the same outline out of the photograph:
**92.0 %**. Same model code, same parameters, one change.

### Fit the camera, never the geometry

Any comparison against a photograph has a free viewpoint. If the optimiser is
allowed to move the part as well, the overlap number stops meaning anything.
Fit the camera only, and what is left over is a statement about shape.

### Report millimetres as well as overlap

IoU punishes thin shapes unfairly. A frame is a 5 mm wide rim: half a
millimetre of offset costs ten points of overlap. On the same model that
scored 85.0 % IoU, the outline was **0.32 mm** off on average - which is the
number an engineer can act on.

### Say when a parameter is not constrained

Sweeping the face-form wrap radius from 220 to 320 mm moved overlap by 0.7
points. Reporting "220 mm, best of the sweep" would be a lie of omission.
`sweep()` detects a flat optimum and says so.

### Distinguish measured, fitted, and assumed

On a model with 18 parameters, 11 were assumptions. That is normal and fine -
as long as nobody later reads one as a measurement. One of those assumptions,
the boxing width, set the scale of the entire part.

### Measure a fit, do not declare one

A clearance in a parameter is a claim. The distance between two solids is a
measurement, and the two part company exactly when something is wrong - a
mirrored arc, a sign, an offset applied twice. `MechanicalFeature.check_fit()`
compares the two and reports both numbers.

One detail worth knowing: a socket approximated by 24 arc segments measures
0.144 mm where the parameter says 0.150. That gap is the polygon
approximation, and it is reported as measured rather than rounded away.

### Where the method is weakest

An orthographic renderer compared against a perspective photograph
systematically *understates* length. On the frame this package came out of,
the fit preferred a temple length of 128-136 mm where 140-145 is normal. The
fitted value is a lower bound, and it is reported as one.
