"""Glove -> Unitree G1 Dex3 hand retargeting (pure Python, no Isaac / DDS). Spec: docs/g1_dex3_limits.json (Aalto INTERFACE.md).
hand_q = 14 values, left 7 then right 7, in the JSON order (left: thumb0-2, middle0-1, index0-1; right: thumb0-2, index0-1, middle0-1).
Closure input: 5 floats 0..1 (thumb,index,middle,ring,little; 1 = closed), e.g. fingers01 from calibrated episodes.
Rules: index/middle -> their two joints (proximal + distal); ring/little have NO Dex3 joint (ignored); left closes NEGATIVE, right POSITIVE (from the limits);
every target is clamped to the FILTER bounds and slew-limited to speed_cap/rate (3.0 rad/s at 30 Hz = 0.1 rad per tick).
THUMB IS UNVERIFIED: the glove thumb signal is unreliable (span 0.3-0.6 rad), so the thumb posture is an interim pinch coupled to INDEX closure.
Its joint directions are guessed from the limits, not measured on the robot: do not send to hardware without checking with the Aalto mentors."""
import json, math, os

LIMITS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "g1_dex3_limits.json")


def _load():
    d = json.load(open(LIMITS))
    return d["hand_q"], d["rate_hz"], d["speed_caps_rad_s"]["hand"]


class G1Dex3Retargeter:
    def __init__(self, pinch_gain=0.6):
        self.joints, self.rate, self.cap = _load()
        self.max_step = self.cap / self.rate
        self.pinch = pinch_gain
        self.idx = {j["joint"]: j for j in self.joints}
        self.q = [self._open(j) for j in self.joints]  # start open

    @staticmethod
    def _open(j):
        lo, hi = j["filter"]
        return min(max(0.0, lo), hi)  # value nearest 0 inside the filter bounds

    @staticmethod
    def _closed(j):
        lo, hi = j["filter"]
        return lo if abs(lo) > abs(hi) else hi  # the bound farthest from 0

    def _target(self, joint_name, c):
        j = self.idx[joint_name]; o, k = self._open(j), self._closed(j)
        return o + max(0.0, min(1.0, c)) * (k - o)

    def targets(self, side, fingers):
        """Unclamped-by-slew targets for one hand: {joint_name: rad}. fingers = 5 closure values or None (hold open)."""
        f = [0.0] * 5 if fingers is None else [0.0 if (x is None or (isinstance(x, float) and math.isnan(x))) else float(x) for x in fingers]
        t = {}
        for finger, c in (("index", f[1]), ("middle", f[2])):
            for k in (0, 1): t[f"{side}_hand_{finger}_{k}_joint"] = self._target(f"{side}_hand_{finger}_{k}_joint", c)
        # interim thumb (UNVERIFIED): pinch posture driven by index closure
        c = self.pinch * f[1]
        t[f"{side}_hand_thumb_0_joint"] = self._target(f"{side}_hand_thumb_0_joint", 0.0)
        t[f"{side}_hand_thumb_1_joint"] = self._target(f"{side}_hand_thumb_1_joint", c)
        t[f"{side}_hand_thumb_2_joint"] = self._target(f"{side}_hand_thumb_2_joint", c)
        return t

    def step(self, left=None, right=None):
        """One control tick: returns the 14-vector hand_q (clamped to filter bounds, slew-limited)."""
        want = {}
        want.update(self.targets("left", left)); want.update(self.targets("right", right))
        for i, j in enumerate(self.joints):
            lo, hi = j["filter"]
            tgt = min(max(want[j["joint"]], lo), hi)
            d = max(-self.max_step, min(self.max_step, tgt - self.q[i]))
            self.q[i] = min(max(self.q[i] + d, lo), hi)
        return list(self.q)

    def bounds_ok(self, q):
        return all(j["filter"][0] - 1e-9 <= v <= j["filter"][1] + 1e-9 for j, v in zip(self.joints, q))
