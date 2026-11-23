"""rgeo - from an idea or a photograph to reusable, checkable geometry.

A small toolkit for building parametric CAD in code when the reference is a
picture rather than a drawing, and for proving afterwards how close you got.

    from rgeo import (Measured, Fitted, Assumed, ParamSet,
                      Torus, WallProfile, Shell, trace, fit_camera, CheckList)

The pipeline it is built around:

    reference -> trace -> outlines -> parameters -> shell -> check -> compare

Features add named, reusable geometry on top of that, in a hierarchy that
says what can go wrong with each kind:

    Feature -> ProfileFeature  (changes a wall, no body, no boolean)
            -> BodyFeature     (brings solids)
                 -> MechanicalFeature  (two parts that must fit, gap measured)

Each stage is usable on its own. See README.md for the full walk-through and
docs/WHY.md for the measurements behind the design decisions.
"""
from .anim import fixed_camera, rock, turntable, turntable_gif, write_gif
from .check import Check, CheckList, mass, mesh_report
from .features import (Boss, BodyFeature, ClipHinge, EdgeBreak, Feature, Groove,
                       MechanicalFeature, ProfileFeature, distance)
from .fit import (FitResult, comparison_strip, fit_camera, iou,
                  outline_distance, sweep)
from .outline import (align_by_angle, attachments, ccw, clean, cut_at_x,
                      mean_radial_gap, offset, point_at_angle, radius_at,
                      resample, sector, signed_area, smooth, subtract)
from .path import (circle_section, fixed_frames, resample_path, sweep_path,
                   transported_frames, tube)
from .params import (Assumed, Derived, Fitted, Measured, ParamSet, Provenance,
                     Value)
from .profile import WallProfile
from .render import (STANDARD_VIEWS, Camera, fit_to_frame, grid, label,
                     load_stl, merge, mesh, shade, silhouette, vertex_normals,
                     views)
from .shell import Shell, sew, sweep_sections
from .surface import (Cylinder, GeometryError, Plane, Sphere, Surface, Torus)
from .temple import CableTemple, LibraryTemple, SkullTemple, Temple
from .trace import Traced, frame_mask, mirror_mask, overlay, trace

__version__ = "0.5.0"

__all__ = [
    "Measured", "Fitted", "Assumed", "Derived", "Value", "Provenance", "ParamSet",
    "Surface", "Plane", "Cylinder", "Sphere", "Torus", "GeometryError",
    "WallProfile", "Shell", "sew", "sweep_sections",
    "trace", "Traced", "frame_mask", "mirror_mask", "overlay",
    "offset", "resample", "smooth", "clean", "ccw", "signed_area", "subtract",
    "cut_at_x", "radius_at", "point_at_angle", "align_by_angle",
    "mean_radial_gap", "attachments", "sector",
    "Camera", "mesh", "merge", "silhouette", "shade", "views", "grid", "label",
    "load_stl", "vertex_normals",
    "fit_to_frame", "STANDARD_VIEWS",
    "fit_camera", "iou", "outline_distance", "comparison_strip", "sweep",
    "FitResult",
    "turntable", "turntable_gif", "write_gif", "rock", "fixed_camera",
    "CheckList", "Check", "mesh_report", "mass",
    "Feature", "ProfileFeature", "BodyFeature", "MechanicalFeature",
    "Groove", "EdgeBreak", "Boss", "ClipHinge", "distance",
    "Temple", "SkullTemple", "LibraryTemple", "CableTemple",
    "__version__",
]
