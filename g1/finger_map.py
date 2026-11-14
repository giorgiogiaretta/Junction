"""One-to-one glove -> Dex3 finger mapping (from 14/11 evening): thumb -> thumb, index -> index, middle -> middle.

robot/g1_dex3.G1Dex3Retargeter (Tommaso's) drives the thumb from the INDEX closure (interim pinch). Here the thumb's two
flexion joints (thumb_1, thumb_2) follow the glove THUMB. thumb_0 (thumb rotation) stays PINNED OPEN as in the original:
its direction was never measured on the robot. Same filter clamps, same slew limit, same G1_MAX_CLOSURE scale.
Left Dex3: thumb + middle + index (3 aligned fingers, good for a can from the side); right: thumb, index, middle.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path: sys.path.insert(0, ROOT)
from robot.g1_dex3 import G1Dex3Retargeter


class DirectRetargeter(G1Dex3Retargeter):
    def targets(self, side, fingers):
        f = [0.0] * 5 if fingers is None else [0.0 if x is None else float(x) for x in fingers]
        t = {}
        for finger, c in (("index", f[1]), ("middle", f[2])):
            for k in (0, 1): t[f"{side}_hand_{finger}_{k}_joint"] = self._target(f"{side}_hand_{finger}_{k}_joint", c)
        t[f"{side}_hand_thumb_0_joint"] = self._target(f"{side}_hand_thumb_0_joint", 0.0)       # rotation: pinned open
        t[f"{side}_hand_thumb_1_joint"] = self._target(f"{side}_hand_thumb_1_joint", f[0])
        t[f"{side}_hand_thumb_2_joint"] = self._target(f"{side}_hand_thumb_2_joint", f[0])
        return t


def closures(glove, scale_ref, cap=1.0):
    """glove fingers01 [thumb, index, middle, ring, little] -> 5 robot closures, each finger on its own: cap * clip(f / ref)."""
    if glove is None: return [0.0] * 5
    return [cap * max(0.0, min(1.0, float(glove[i]) / scale_ref)) for i in range(3)] + [0.0, 0.0]
