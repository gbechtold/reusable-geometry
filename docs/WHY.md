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

### Where the method is weakest

An orthographic renderer compared against a perspective photograph
systematically *understates* length. On the frame this package came out of,
the fit preferred a temple length of 128-136 mm where 140-145 is normal. The
fitted value is a lower bound, and it is reported as one.
