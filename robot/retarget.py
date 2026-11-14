"""Retarget glove fingers (5 floats 0..1, 1=closed: thumb,index,middle,ring,pinky) to robot hand commands.
Inspire RH56 (G1 dexterous hand): 6 DoF in order [pinky, ring, middle, index, thumb_bend, thumb_rot],
each 0..1000 where 1000 = OPEN, 0 = CLOSED (verify with Aalto mentors / hand manual).
Includes smoothing and a per-finger force/current limit hook for fragile grasps (#14).
"""
import os, time

INSPIRE_ORDER = ["pinky", "ring", "middle", "index", "thumb_bend", "thumb_rot"]


class Smoother:
    """Exponential smoothing + max slew rate (units/s) to avoid jerks; alpha in (0,1]."""
    def __init__(self, alpha=0.5, max_rate=4.0):
        self.alpha, self.max_rate, self.y, self.t = alpha, max_rate, None, None

    def __call__(self, x):
        now = time.time()
        if self.y is None:
            self.y, self.t = list(x), now; return list(x)
        dt = max(1e-3, now - self.t); self.t = now; lim = self.max_rate * dt
        for i, v in enumerate(x):
            target = self.y[i] + self.alpha * (v - self.y[i])
            self.y[i] += max(-lim, min(lim, target - self.y[i]))
        return list(self.y)


def thumb_rot_open():
    """Register value of thumb_rotation with the hand OPEN: 1000 (repo default) or 0.
    UNCONFIRMED: a third-party transcription of the RH56 manual says 0 = retracted, 1000 = across the palm (docs/RESEARCH_NIGHT.md #4),
    i.e. the opposite of our default. Flip on site with INSPIRE_THUMB_ROT_OPEN=0 after checking a 10% move by eye."""
    v = os.environ.get("INSPIRE_THUMB_ROT_OPEN", "1000").strip()
    if v not in ("0", "1000"): raise ValueError("INSPIRE_THUMB_ROT_OPEN must be 0 or 1000, got %r" % v)
    return int(v)


def to_inspire(fingers, thumb_rot_gain=0.7, close_cap=1.0, rot_open=None):
    """fingers: glove order, 1=closed. close_cap<1 limits max closure (fragile objects).
    rot_open: thumb_rotation value when open (1000 or 0); None -> env INSPIRE_THUMB_ROT_OPEN (default 1000).
    Returns 6 ints 0..1000 in INSPIRE_ORDER."""
    th, ix, md, rg, pk = [max(0.0, min(close_cap, float(x))) for x in list(fingers)[:5]]
    thumb_rot = thumb_rot_gain * th  # opposition grows as thumb closes
    out = [int(round(1000 * (1.0 - v))) for v in (pk, rg, md, ix, th, thumb_rot)]
    if (thumb_rot_open() if rot_open is None else rot_open) == 0: out[5] = 1000 - out[5]
    return out


def to_g1_inspire_q(fingers, close_cap=1.0):
    """Same 6 values normalised 0..1 (1=open) as used by unitree xr_teleoperate style hand targets."""
    return [v / 1000.0 for v in to_inspire(fingers, close_cap=close_cap)]
