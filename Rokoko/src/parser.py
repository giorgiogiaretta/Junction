"""Pluggable parser: raw Rokoko/mock UDP frame -> 5 finger values 0..1 (thumb,index,middle,ring,pinky; 0 open, 1 closed).
Real Rokoko schema is unverified: adapt `parse_rokoko` after `python src/listen.py --show`.
"""
from typing import List, Optional

def parse_mock(frame: dict) -> Optional[List[float]]:
    f = frame.get("fingers")
    if isinstance(f, list) and len(f) >= 5:
        return [min(1.0, max(0.0, float(x))) for x in f[:5]]
    return None

def parse_rokoko(frame: dict) -> Optional[List[float]]:
    """TODO(real frame): map hand joint rotations -> flexion per finger -> normalise to 0..1."""
    return None

def parse(frame: dict) -> Optional[List[float]]:
    return parse_mock(frame) or parse_rokoko(frame)
