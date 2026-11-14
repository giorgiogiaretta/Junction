"""Instruction -> colour/shape -> bin mapping, offline and deterministic (no network at the finals).

Rules (organisers, Discord 2026-11-14): bins are named only by position (left / center / right); instructions
may name colour, shape or both; no negation. Real colours: yellow, purple, orange (sort_fixed: yellow -> left,
purple -> center, orange -> right). The sim still uses red / yellow / blue: both sets are understood.

parse(text) -> {"colors": {colour: bin}, "shapes": {shape: bin}, "pairs": {(colour, shape): bin}}
Each clause (split on . ; , and "and"/"then") is assigned to the single bin it names; every colour / shape
named in that clause goes to that bin. "the rest" / "everything else" / "remaining" sends the not yet
mapped colours to that bin.
"""
from __future__ import annotations

import re

BINS = {"left": "left", "center": "center", "centre": "center", "middle": "center", "central": "center",
        "right": "right"}
COLORS = {"yellow": "yellow", "purple": "purple", "violet": "purple", "lilac": "purple", "lavender": "purple",
          "magenta": "purple", "orange": "orange", "red": "red", "blue": "blue"}
SHAPES = {"cube": "cube", "cubes": "cube", "square": "cube", "squares": "cube", "box-shaped": "cube",
          "block": "cube", "blocks": "cube",
          "cylinder": "cylinder", "cylinders": "cylinder", "cylindrical": "cylinder", "round": "cylinder",
          "circle": "cylinder", "circular": "cylinder", "can": "cylinder",
          "triangle": "triangle", "triangles": "triangle", "triangular": "triangle", "prism": "triangle",
          "prisms": "triangle", "wedge": "triangle", "wedges": "triangle", "pyramid": "triangle"}
REST = re.compile(r"\b(the rest|everything else|all else|anything else|remaining|others|other objects|"
                  r"other ones|leftover)\b")
REAL_FIXED = {"yellow": "left", "purple": "center", "orange": "right"}
SIM_FIXED = {"red": "left", "yellow": "center", "blue": "right"}

_SPLIT = re.compile(r"[.;,\n]|\band\b|\bthen\b|\bwhile\b|\bwhereas\b")
_WORD = re.compile(r"[a-z]+(?:-[a-z]+)?")


def _clauses(text: str):
    return [c.strip() for c in _SPLIT.split(text.lower()) if c.strip()]


def parse(text: str) -> dict:
    colors, shapes, pairs = {}, {}, {}
    rest_bin = None
    for clause in _clauses(text or ""):
        words = _WORD.findall(clause)
        bins = [BINS[w] for w in words if w in BINS]
        if len(set(bins)) != 1:
            continue
        b = bins[0]
        cs = [COLORS[w] for w in words if w in COLORS]
        ss = [SHAPES[w] for w in words if w in SHAPES]
        if REST.search(clause) and not cs and not ss:
            rest_bin = b
            continue
        if cs and ss and len(cs) == 1 and len(ss) == 1:
            pairs[(cs[0], ss[0])] = b
        else:
            for c in cs:
                colors.setdefault(c, b)
            if not cs:
                for s in ss:
                    shapes.setdefault(s, b)
    if rest_bin is not None:
        named = set(colors) | {c for c, _ in pairs}
        palette = REAL_FIXED if named & set(REAL_FIXED) or not named & set(SIM_FIXED) else SIM_FIXED
        for c in palette:
            if c not in named:
                colors[c] = rest_bin
    return {"colors": colors, "shapes": shapes, "pairs": pairs}


def colour_mapping(text: str) -> dict:
    """colour -> bin used by the planner. Pairs (colour+shape) fall back to their colour; if nothing parses,
    use the fixed mapping of the palette the text mentions (real by default)."""
    p = parse(text)
    m = dict(p["colors"])
    for (c, _s), b in p["pairs"].items():
        m.setdefault(c, b)
    if m:
        return m
    low = (text or "").lower()
    if any(w in low for w in ("red", "blue")) and not any(w in low for w in ("purple", "orange", "violet")):
        return dict(SIM_FIXED)
    return dict(REAL_FIXED)
