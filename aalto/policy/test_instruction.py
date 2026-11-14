"""Parser tests: the 8 organiser templates x all colour/bin permutations (both palettes) + paraphrases."""
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from team_aalto.instruction import REAL_FIXED, colour_mapping, parse  # noqa: E402

TEMPLATES = (
    "Put the {c0} objects in the {b0} bin, the {c1} objects in the {b1} bin and the {c2} objects in the {b2} bin.",
    "{C0} goes to the {b0} bin, {c1} to the {b1} bin, {c2} to the {b2} bin.",
    "Sort the objects: {c0} into {b0}, {c1} into {b1}, {c2} into {b2}.",
    "Place every {c0} object in the {b0} bin. {C1} objects belong in the {b1} bin, and {c2} ones in the {b2} bin.",
    "The {b0} bin is for {c0} objects, the {b1} bin for {c1}, the {b2} bin for {c2}.",
    "Move {c0} objects to the {b0} bin, {c1} objects to the {b1} bin, and {c2} objects to the {b2} bin.",
    "Drop the {c0} ones into the {b0} bin, the {c1} ones into the {b1} bin, the {c2} ones into the {b2} bin.",
    "Use the {b0} bin for {c0}, the {b1} bin for {c1} and the {b2} bin for {c2} objects.",
)


def test_templates_all_permutations_both_palettes():
    n = 0
    for palette in (("red", "yellow", "blue"), ("yellow", "purple", "orange")):
        for cols in itertools.permutations(palette):
            for bins in itertools.permutations(("left", "center", "right")):
                for t in TEMPLATES:
                    w = {f"c{i}": c for i, c in enumerate(cols)}
                    w.update({f"C{i}": c.capitalize() for i, c in enumerate(cols)})
                    w.update({f"b{i}": b for i, b in enumerate(bins)})
                    assert colour_mapping(t.format(**w)) == dict(zip(cols, bins)), t.format(**w)
                    n += 1
    assert n == 2 * 6 * 6 * 8


PARAPHRASES = [
    ("Yellow on the left, purple in the middle, orange on the right.", REAL_FIXED),
    ("orange -> left; yellow -> centre; purple -> right",
     {"orange": "left", "yellow": "center", "purple": "right"}),
    ("Please put purple things into the right box and yellow ones into the left box. Orange goes in the middle one.",
     {"purple": "right", "yellow": "left", "orange": "center"}),
    ("The violet blocks belong in the central box, and the rest goes to the left.",
     {"purple": "center", "yellow": "left", "orange": "left"}),
    ("Everything orange to the left bin, everything else to the right bin.",
     {"orange": "left", "yellow": "right", "purple": "right"}),
    ("Left box: yellow. Middle box: orange. Right box: purple.",
     {"yellow": "left", "orange": "center", "purple": "right"}),
    ("Could you sort them so that purple ends up on the left, orange in the centre and yellow on the right?",
     {"purple": "left", "orange": "center", "yellow": "right"}),
    ("Put the yellow objects in the right bin, then the orange ones in the left bin, then purple in the center.",
     {"yellow": "right", "orange": "left", "purple": "center"}),
]


def test_paraphrases():
    for text, want in PARAPHRASES:
        assert colour_mapping(text) == want, (text, colour_mapping(text))


def test_shapes_and_pairs():
    p = parse("Put the cubes in the left bin, the cylinders in the center bin and the prisms in the right bin.")
    assert p["shapes"] == {"cube": "left", "cylinder": "center", "triangle": "right"}
    p = parse("Put the orange cube in the right box.")
    assert p["pairs"] == {("orange", "cube"): "right"}
    assert colour_mapping("Put the orange cube in the right box.") == {"orange": "right"}


def test_fallbacks():
    assert colour_mapping("") == REAL_FIXED
    assert colour_mapping("sort the objects") == REAL_FIXED
