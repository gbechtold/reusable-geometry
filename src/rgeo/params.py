"""Parameters that carry where their value came from.

The habit this package exists to enforce: a number in a CAD model is either
measured off something real, fitted against evidence, or assumed. Six months
later nobody remembers which - and an assumption that gets read as a
measurement is how a model quietly goes wrong.

    >>> from rgeo import Measured, Fitted, Assumed, ParamSet
    >>> p = ParamSet(
    ...     lens_width=Assumed(56.0, "typical aviator boxing", unit="mm"),
    ...     lens_height=Fitted(44.8, "silhouette sweep", evidence="93.4% at 51.5"),
    ...     rim_width=Measured(5.7, "front photo, median radial gap"),
    ... )
    >>> p.lens_width + 1.0          # behaves like a float
    57.0
    >>> p.provenance("lens_width").kind
    'assumed'
    >>> print(p.table())            # doctest: +SKIP

Values behave like floats everywhere, so downstream code never has to know.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterator


@dataclass(frozen=True)
class Provenance:
    """Where a value came from, and what backs it up."""

    kind: str                  # "measured" | "fitted" | "assumed" | "derived"
    source: str                # what it was measured off / fitted against
    evidence: str = ""         # the number that makes the claim checkable
    unit: str = ""

    SYMBOLS = {"measured": "M", "fitted": "F", "assumed": "A", "derived": "D"}

    def mark(self) -> str:
        return self.SYMBOLS.get(self.kind, "?")


class Value(float):
    """A float that remembers its provenance.

    Arithmetic on it returns plain floats on purpose: the moment a value is
    combined with another, its provenance no longer describes the result.
    """

    __slots__ = ("prov",)

    def __new__(cls, value: float, prov: Provenance):
        obj = super().__new__(cls, value)
        obj.prov = prov
        return obj

    def __repr__(self) -> str:
        u = f" {self.prov.unit}" if self.prov.unit else ""
        return f"{float(self)}{u} [{self.prov.kind}: {self.prov.source}]"


def Measured(value: float, source: str, evidence: str = "", unit: str = "mm") -> Value:
    """Taken off the reference: a photo, a drawing, a caliper."""
    return Value(value, Provenance("measured", source, evidence, unit))


def Fitted(value: float, source: str, evidence: str = "", unit: str = "mm") -> Value:
    """Chosen by optimising against evidence. `evidence` should carry the
    numbers that show the optimum is real, not a flat plateau."""
    return Value(value, Provenance("fitted", source, evidence, unit))


def Assumed(value: float, source: str, evidence: str = "", unit: str = "mm") -> Value:
    """A judgement call. The one kind that has to stay visible."""
    return Value(value, Provenance("assumed", source, evidence, unit))


def Derived(value: float, source: str, evidence: str = "", unit: str = "mm") -> Value:
    """Computed from other parameters."""
    return Value(value, Provenance("derived", source, evidence, unit))


@dataclass
class ParamSet:
    """A bag of named values, each with its provenance.

    Deliberately not a dataclass per model: parameter sets grow and shrink
    while a model is being worked out, and a frozen schema gets in the way.
    """

    values: dict[str, Any] = field(default_factory=dict)

    def __init__(self, **kwargs: Any):
        object.__setattr__(self, "values", {})
        for k, v in kwargs.items():
            self.values[k] = v

    # --- access ---------------------------------------------------------
    def __getattr__(self, name: str) -> Any:
        try:
            return self.values[name]
        except KeyError as e:
            raise AttributeError(name) from e

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "values":
            object.__setattr__(self, name, value)
        else:
            self.values[name] = value

    def __getitem__(self, name: str) -> Any:
        return self.values[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self.values)

    def __contains__(self, name: str) -> bool:
        return name in self.values

    def provenance(self, name: str) -> Provenance:
        v = self.values[name]
        if isinstance(v, Value):
            return v.prov
        return Provenance("assumed", "no provenance recorded")

    def with_(self, **kwargs: Any) -> "ParamSet":
        """A copy with some values replaced, keeping provenance unless a new
        Value is given."""
        out = ParamSet(**dict(self.values))
        for k, v in kwargs.items():
            if not isinstance(v, Value) and k in self.values and \
                    isinstance(self.values[k], Value):
                v = Value(v, replace(self.values[k].prov, evidence="overridden"))
            out.values[k] = v
        return out

    # --- reporting ------------------------------------------------------
    def by_kind(self, kind: str) -> dict[str, Any]:
        return {k: v for k, v in self.values.items()
                if isinstance(v, Value) and v.prov.kind == kind}

    def assumptions(self) -> dict[str, Any]:
        """The values a reader has to be warned about."""
        return self.by_kind("assumed")

    def table(self, order=("measured", "fitted", "assumed", "derived")) -> str:
        """Markdown table, grouped by provenance. Goes straight into a report."""
        rows = ["| | Parameter | Value | Source | Evidence |",
                "|---|---|---|---|---|"]
        for kind in order:
            for name, v in self.by_kind(kind).items():
                unit = f" {v.prov.unit}" if v.prov.unit else ""
                rows.append(f"| {v.prov.mark()} | `{name}` | {float(v):g}{unit} "
                            f"| {v.prov.source} | {v.prov.evidence} |")
        plain = {k: v for k, v in self.values.items() if not isinstance(v, Value)}
        for name, v in plain.items():
            rows.append(f"| ? | `{name}` | {v} | no provenance recorded | |")
        return "\n".join(rows)

    def to_dict(self) -> dict[str, Any]:
        out = {}
        for k, v in self.values.items():
            if isinstance(v, Value):
                out[k] = {"value": float(v), "kind": v.prov.kind,
                          "source": v.prov.source, "evidence": v.prov.evidence,
                          "unit": v.prov.unit}
            else:
                out[k] = v
        return out

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ParamSet":
        out = cls()
        for k, v in d.items():
            if isinstance(v, dict) and "kind" in v:
                out.values[k] = Value(v["value"], Provenance(
                    v["kind"], v.get("source", ""), v.get("evidence", ""),
                    v.get("unit", "")))
            else:
                out.values[k] = v
        return out
