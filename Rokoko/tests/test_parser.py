import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "src"))
from parser import parse

def test_mock_clamped():
    assert parse({"fingers": [-1, 0.5, 2, 0, 1]}) == [0.0, 0.5, 1.0, 0.0, 1.0]
def test_unknown_none():
    assert parse({"x": 1}) is None
