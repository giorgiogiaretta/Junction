"""Make OUR local copy of the organisers' sim match the real venue (organisers: "feel free to edit the sim").

Objects: yellow / purple / orange (real foam blocks); sort_fixed: yellow -> left, purple -> center,
orange -> right (Discord, erkka 2026-11-14 15:07); bins: the real, redder orange (H ~5 vs objects H ~13).
Idempotent; keeps *.orig backups. Usage: python apply_real_colours.py <aaltonomous-humanoid repo root>
"""
import pathlib
import shutil
import sys

root = pathlib.Path(sys.argv[1]) / "aaltonomous"


def edit(rel, pairs):
    p = root / rel
    orig = p.with_name(p.name + ".orig")
    if not orig.exists():
        shutil.copy(p, orig)
    s = orig.read_text()
    for a, b in pairs:
        assert a in s, (rel, a)
        s = s.replace(a, b)
    p.write_text(s)
    print("edited", rel)


edit("interface/tasks.py", [
    ('COLORS = ("red", "yellow", "blue")', 'COLORS = ("yellow", "purple", "orange")'),
    ('FIXED_MAPPING = {"red": "left", "yellow": "center", "blue": "right"}',
     'FIXED_MAPPING = {"yellow": "left", "purple": "center", "orange": "right"}'),
    ('"Put the red objects in the left bin, the yellow objects in the center bin "\n'
     '                     "and the blue objects in the right bin."',
     '"Put the yellow objects in the left bin, the purple objects in the center bin "\n'
     '                     "and the orange objects in the right bin."'),
])
edit("scene/scene.yaml", [
    ("    red: [200, 30, 30]\n    yellow: [235, 200, 20]\n    blue: [30, 70, 200]",
     "    yellow: [235, 215, 60]\n    purple: [105, 95, 225]\n    orange: [245, 125, 35]"),
    ("  rgb: [230, 110, 30]                         # (default) orange",
     "  rgb: [225, 70, 30]                          # real venue boxes (H ~5), redder than orange objects"),
])
