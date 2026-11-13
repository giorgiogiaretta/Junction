"""MuJoCo grasp scene (PLAN 1.3): five-finger Inspire-STYLE hand over a pedestal with ONE object: a rigid cube or a fragile egg.
Not the real RH56 model: 5 actuated fingers (2 hinge joints each), thumb opposing the four fingers, wrist = 3 slide joints.
Fingers point down; four fingers curl toward -y, the thumb toward +y, the object sits between them.

Egg "breaks" (latched `broken=True`) when any contact normal force on it exceeds BREAK_FORCE_N. BREAK_FORCE_N and the actuator gains
are calibrated TOY values (see tests/test_truth.py), not measurements of a real egg or hand.

Wrist: pass `wrist` = target hand position in metres (workspace frame) or use `wrist_from_coil()` to turn Coil Pro `wrist_position`
into a target (relative to the first sample); without a Coil Pro use `mock_wrist(phase_time)`.
Run scripted demo: python -m robot.scene --obj egg --cap 0.5   (headless, prints the result)
"""
import argparse, math
import mujoco
import numpy as np

BREAK_FORCE_N = 3.0        # egg breaks above this contact normal force (toy value)
HOVER_Z, GRASP_Z = 0.26, 0.09   # hand height above table: hovering / grasping
LIFT_MIN = 0.05            # object must rise this much (m) to count as lifted
FINGER_MAX = 1.0           # rad per joint at closure 1.0
NAMES = ["thumb", "index", "middle", "ring", "pinky"]

OBJECTS = {
    "cube": '<geom name="obj" type="box" size="0.02 0.02 0.02" mass="0.05" rgba="0.2 0.4 0.9 1" friction="1.5 0.005 0.0001"/>',
    "egg": '<geom name="obj" type="ellipsoid" size="0.025 0.022 0.02" mass="0.06" rgba="0.95 0.92 0.8 1" friction="1.5 0.005 0.0001"/>',
}
OBJ_HALF_Z = {"cube": 0.02, "egg": 0.02}
GRASP_Z_FOR = {"cube": 0.09, "egg": 0.09}   # palm height that puts the fingers around the object


def _xml(obj, obj_xy=(0.0, 0.0), pedestals=((0.0, 0.0),), ped_half=(0.03, 0.015)):
    fing = ""
    # four fingers on +y side (curl toward -y), thumb on -y side (curl toward +y)
    layout = [("thumb", 0.0, -0.08, 1.0), ("index", -0.03, 0.08, 1.0), ("middle", -0.01, 0.08, 1.0),
              ("ring", 0.01, 0.08, 1.0), ("pinky", 0.03, 0.08, 1.0)]
    for n, x, y, w in layout:
        ax = "1 0 0" if y < 0 else "-1 0 0"
        r = 0.008 * w
        fing += f"""
      <body name="{n}" pos="{x} {y} -0.01">
        <joint name="{n}_j1" type="hinge" axis="{ax}" range="0 {FINGER_MAX}" damping="0.02" armature="0.0005"/>
        <geom type="capsule" fromto="0 0 0 0 0 -0.05" size="{r}" mass="0.01" friction="1.5 0.005 0.0001"/>
        <body pos="0 0 -0.05">
          <joint name="{n}_j2" type="hinge" axis="{ax}" range="0 {FINGER_MAX}" damping="0.02" armature="0.0005"/>
          <geom type="capsule" fromto="0 0 0 0 0 -0.04" size="{r * 0.9}" mass="0.01" friction="1.5 0.005 0.0001"/>
        </body>
      </body>"""
    acts = "".join(
        f'<position name="{n}_a{k}" joint="{n}_j{k}" kp="{KP}" kv="{KV}" ctrlrange="0 {FINGER_MAX}"/>' for n in NAMES for k in (1, 2))
    acts += ('<position name="wx" joint="hx" kp="400" kv="40" ctrlrange="-0.4 0.4"/>'
             '<position name="wy" joint="hy" kp="400" kv="40" ctrlrange="-0.4 0.4"/>'
             '<position name="wz" joint="hz" kp="400" kv="40" ctrlrange="0.05 0.4"/>')
    ped = "".join(f'<geom name="pedestal{i if i else ""}" type="box" pos="{x} {y} -0.02" size="{ped_half[0]} {ped_half[1]} 0.02" friction="1.5 0.005 0.0001"/>'
                  for i, (x, y) in enumerate(pedestals))
    return f"""<mujoco><compiler angle="radian"/><option timestep="0.002"/>
  <worldbody>
    <geom name="table" type="plane" pos="0 0 -0.06" size="1 1 0.1" friction="1.5 0.005 0.0001"/>
    {ped}
    <body name="hand" pos="0 0 0" gravcomp="1">
      <joint name="hx" type="slide" axis="1 0 0" damping="1"/><joint name="hy" type="slide" axis="0 1 0" damping="1"/>
      <joint name="hz" type="slide" axis="0 0 1" damping="1"/>
      <geom name="palm" type="box" size="0.05 0.1 0.01" mass="0.3" rgba="0.5 0.5 0.5 1"/>{fing}
    </body>
    <body name="object" pos="{obj_xy[0]} {obj_xy[1]} {OBJ_HALF_Z[obj] + 0.0005}"><freejoint/>{OBJECTS[obj]}</body>
  </worldbody>
  <actuator>{acts}</actuator></mujoco>"""


KP, KV = 1.0, 0.04


class Scene:
    def __init__(self, obj="cube", break_force=BREAK_FORCE_N, obj_xy=(0.0, 0.0), pedestals=((0.0, 0.0),), ped_half=(0.03, 0.015)):
        """obj_xy: start position of the object; pedestals: (x, y) of each support (default: one under the origin), ped_half: half size."""
        assert obj in OBJECTS
        self.obj, self.break_force = obj, break_force
        self.m = mujoco.MjModel.from_xml_string(_xml(obj, obj_xy, pedestals, ped_half))
        self.d = mujoco.MjData(self.m)
        self.g_obj = mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_GEOM, "obj")
        self.b_obj = self.m.geom_bodyid[self.g_obj]
        self.rest_z = OBJ_HALF_Z[obj]
        self.reset()

    def reset(self):
        mujoco.mj_resetData(self.m, self.d)
        self.d.qpos[2] = HOVER_Z  # hz is the absolute hand height (body at origin)
        self.d.ctrl[-1] = HOVER_Z
        self.peak_force = 0.0
        self.force = 0.0
        self.broken = False
        self.t = 0.0
        mujoco.mj_forward(self.m, self.d)

    def place_hand(self, x, y, z):
        """Teleport the hand (and its wrist targets) to a pose, e.g. the first sample of a recorded take."""
        self.d.qpos[0:3] = (x, y, z)
        self.d.ctrl[-3:] = (max(-0.4, min(0.4, x)), max(-0.4, min(0.4, y)), max(0.05, min(0.4, z)))
        mujoco.mj_forward(self.m, self.d)

    # --- state
    def obj_pos(self):
        return self.d.xpos[self.b_obj].copy()

    def hand_pos(self):
        return self.d.xpos[mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_BODY, "hand")].copy()

    def contact_force(self):
        """Largest contact normal force (N) on the object from the hand (table excluded)."""
        best, f6 = 0.0, np.zeros(6)
        for i in range(self.d.ncon):
            c = self.d.contact[i]
            if self.g_obj in (c.geom1, c.geom2):
                other = c.geom2 if c.geom1 == self.g_obj else c.geom1
                if self.m.geom_bodyid[other] == 0:
                    continue  # table
                mujoco.mj_contactForce(self.m, self.d, i, f6)
                best = max(best, abs(f6[0]))
        return best

    def lifted(self):
        return float(self.obj_pos()[2] - self.rest_z) > LIFT_MIN

    def held(self):
        """Object lifted AND still between the fingers (not flung away)."""
        o, h = self.obj_pos(), self.hand_pos()
        return self.lifted() and abs(o[0] - h[0]) < 0.05 and abs(o[1] - h[1]) < 0.05

    # --- control
    def step(self, fingers, wrist=None, dt=1 / 60):
        """fingers: 5 closure values 0..1 (thumb,index,middle,ring,pinky; 1=closed). wrist: (x,y,z) target in m or None (hold)."""
        for i, f in enumerate(list(fingers)[:5]):
            v = FINGER_MAX * max(0.0, min(1.0, float(f)))
            self.d.ctrl[2 * i] = self.d.ctrl[2 * i + 1] = v
        if wrist is not None:
            self.d.ctrl[-3] = max(-0.4, min(0.4, wrist[0])); self.d.ctrl[-2] = max(-0.4, min(0.4, wrist[1]))
            self.d.ctrl[-1] = max(0.05, min(0.4, wrist[2] if len(wrist) > 2 else HOVER_Z))
        n = max(1, int(round(dt / self.m.opt.timestep)))
        for _ in range(n):
            mujoco.mj_step(self.m, self.d)
            f = self.contact_force()
            self.force = f
            if f > self.peak_force: self.peak_force = f
            if self.obj == "egg" and f > self.break_force: self.broken = True
        self.t += dt
        return self.state()

    def state(self):
        o = self.obj_pos()
        return {"t": self.t, "obj_z": float(o[2]), "force": self.force, "peak_force": self.peak_force,
                "broken": self.broken, "lifted": self.lifted(), "held": self.held()}


# ---- wrist sources -------------------------------------------------------------------------------------------------
def wrist_from_coil(pos, origin, scale=1.0, base=(0.0, 0.0, HOVER_Z)):
    """Coil Pro wrist_position [x,y,z] (m) -> hand target. `origin` = first sample (operator's rest pose)."""
    return tuple(b + scale * (p - o) for b, p, o in zip(base, pos, origin))


def mock_wrist(t, hover=HOVER_Z, grasp=GRASP_Z, t_descend=(0.5, 1.5), t_lift=(3.0, 4.0)):
    """Scripted wrist path used when no Coil Pro is available: hover -> descend -> hold -> lift. Returns (x,y,z)."""
    def ramp(t, a, b): return min(1.0, max(0.0, (t - a) / (b - a)))
    z = hover + (grasp - hover) * ramp(t, *t_descend) + (hover - grasp) * ramp(t, *t_lift)
    return (0.0, 0.0, z)


def mock_fingers(t, close=(2.0, 3.0), open_=(4.5, 5.0)):
    def ramp(t, a, b): return min(1.0, max(0.0, (t - a) / (b - a)))
    c = ramp(t, *close) * (1 - ramp(t, *open_))
    return [c] * 5


def run_script(obj="cube", cap=1.0, duration=4.5, scene=None):
    """Scripted pick (mock wrist + closing fist, closure limited to `cap`). Returns final state dict."""
    sc = scene or Scene(obj)
    t, dt = 0.0, 1 / 60
    while t < duration:
        f = [min(x, cap) for x in mock_fingers(t, close=(2.0, 3.0), open_=(99, 100))]
        s = sc.step(f, mock_wrist(t), dt); t += dt
    return s


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--obj", default="cube", choices=list(OBJECTS)); ap.add_argument("--cap", type=float, default=1.0)
    a = ap.parse_args(); s = run_script(a.obj, a.cap)
    print(f"obj={a.obj} cap={a.cap} lifted={s['lifted']} held={s['held']} broken={s['broken']} peak_force={s['peak_force']:.2f}N")
