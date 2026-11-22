import pytest

from rgeo import Assumed, Fitted, Measured, ParamSet


def test_value_behaves_like_a_float():
    v = Measured(5.7, "photo")
    assert v + 1 == pytest.approx(6.7)
    assert v * 2 == pytest.approx(11.4)
    assert float(v) == 5.7


def test_provenance_survives_the_set():
    p = ParamSet(a=Measured(1.0, "caliper"), b=Assumed(2.0, "guess"))
    assert p.provenance("a").kind == "measured"
    assert p.provenance("b").kind == "assumed"
    assert list(p.assumptions()) == ["b"]


def test_table_groups_by_kind():
    p = ParamSet(a=Assumed(1.0, "guess"), b=Measured(2.0, "photo"),
                 c=Fitted(3.0, "sweep", "70% vs 69%"))
    rows = p.table().splitlines()[2:]
    assert rows[0].startswith("| M")
    assert rows[1].startswith("| F")
    assert rows[2].startswith("| A")
    assert "70% vs 69%" in rows[1]


def test_roundtrip_through_dict():
    p = ParamSet(a=Measured(1.5, "photo", "bbox", unit="mm"))
    q = ParamSet.from_dict(p.to_dict())
    assert float(q.a) == 1.5
    assert q.provenance("a").source == "photo"


def test_with_keeps_provenance_but_marks_the_override():
    p = ParamSet(a=Measured(1.0, "photo"))
    q = p.with_(a=2.0)
    assert float(q.a) == 2.0
    assert q.provenance("a").kind == "measured"
    assert q.provenance("a").evidence == "overridden"


def test_plain_values_are_flagged_as_unsourced():
    p = ParamSet(a=1.0)
    assert "no provenance recorded" in p.table()
