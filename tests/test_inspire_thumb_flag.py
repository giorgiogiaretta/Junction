"""INSPIRE_THUMB_ROT_OPEN flag in robot.retarget.to_inspire (#63). Raw Modbus client tests live in tests/test_preflight.py."""
import sys, pathlib
import pytest
ROOT = pathlib.Path(__file__).parents[1]; sys.path.insert(0, str(ROOT))
from robot import retarget


def test_thumb_rot_flag(monkeypatch):
    open_, fist = [0] * 5, [1] * 5
    monkeypatch.delenv("INSPIRE_THUMB_ROT_OPEN", raising=False)
    assert retarget.to_inspire(open_)[5] == 1000 and retarget.to_inspire(fist)[5] == 300      # repo default
    monkeypatch.setenv("INSPIRE_THUMB_ROT_OPEN", "0")
    assert retarget.to_inspire(open_)[5] == 0 and retarget.to_inspire(fist)[5] == 700         # manual-README convention
    assert retarget.to_inspire(fist)[:5] == [0] * 5                                           # other DOFs unchanged
    monkeypatch.setenv("INSPIRE_THUMB_ROT_OPEN", "500")
    with pytest.raises(ValueError): retarget.to_inspire(open_)
