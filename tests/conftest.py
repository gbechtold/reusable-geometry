import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture
def ring():
    """A plain annulus: outer outline and one hole, both counter-clockwise."""
    t = np.linspace(0, 2 * np.pi, 120, endpoint=False)
    outer = np.c_[np.cos(t) * 40, np.sin(t) * 25]
    hole = np.c_[np.cos(t) * 28, np.sin(t) * 15]
    return outer, hole


@pytest.fixture
def two_holes():
    t = np.linspace(0, 2 * np.pi, 120, endpoint=False)
    outer = np.c_[np.cos(t) * 60, np.sin(t) * 26]
    a = np.c_[np.cos(t) * 18 - 28, np.sin(t) * 16]
    b = np.c_[np.cos(t) * 18 + 28, np.sin(t) * 16]
    return outer, a, b
