"""Fragile-object grasp assist (#14): limits finger closure so cups/eggs are not crushed.
Feedback mode: a force/current reading (0..1 of max) drives a closure cap that backs off
above `force_limit` and relaxes below it. Open-loop mode (no sensor): fixed cap from an object profile.
Output cap feeds robot.retarget.to_inspire(close_cap=...) / InspireHand(close_cap=...).
"""
PROFILES = {"none": 1.0, "cup": 0.65, "egg": 0.5, "can": 0.8}  # open-loop caps, tune on hardware


class GraspAssist:
    def __init__(self, force_limit=0.3, cap_min=0.3, back_off=0.15, relax=0.01, profile="none"):
        self.limit, self.cap_min, self.back, self.relax = force_limit, cap_min, back_off, relax
        self.ceiling = self.cap = PROFILES.get(profile, 1.0)

    def update(self, force=None):
        """force: max finger force/current 0..1, or None if no sensor. Returns close_cap."""
        if force is None:
            return self.cap
        if force > self.limit:
            self.cap = max(self.cap_min, self.cap - self.back * (force / self.limit))
        else:
            self.cap = min(self.ceiling, self.cap + self.relax)
        return self.cap

    def apply(self, fingers, force=None):
        cap = self.update(force)
        return [min(float(x), cap) for x in fingers], cap


def simulate(assist=True, steps=100, stiffness=2.0, contact=0.4):
    """Toy object: force = stiffness*(closure-contact). Operator ramps closure 0->1 over 30 steps; returns peak force."""
    ga, peak, f = GraspAssist(), 0.0, 0.0
    for i in range(steps):
        want = min(1.0, (i + 1) / 30)
        cmd = ga.apply([want], force=f)[0][0] if assist else want
        f = max(0.0, stiffness * (cmd - contact))
        peak = max(peak, f)
    return peak


if __name__ == "__main__":
    print(f"peak force without assist: {simulate(False):.2f}, with assist: {simulate(True):.2f} (limit 0.30)")
