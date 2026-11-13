"""MuJoCo 5-finger hand: each finger = 2 hinge joints (proximal+distal) driven by one 0..1 value.
Run: python -m robot.sim   (animates a sine; needs `mjpython` on macOS for the viewer)
"""
import math, time
import mujoco
from robot.hand import Hand, clamp5

NAMES = ["thumb", "index", "middle", "ring", "pinky"]


def _xml():
    fingers = ""
    for i, n in enumerate(NAMES):
        x = (i - 2) * 0.03
        fingers += f"""
      <body name="{n}" pos="{x} 0 0.05">
        <joint name="{n}_j1" type="hinge" axis="1 0 0" range="0 1.6" damping="0.01" armature="0.001"/>
        <geom type="capsule" fromto="0 0 0 0 0 0.05" size="0.008"/>
        <body pos="0 0 0.05">
          <joint name="{n}_j2" type="hinge" axis="1 0 0" range="0 1.6" damping="0.01" armature="0.001"/>
          <geom type="capsule" fromto="0 0 0 0 0 0.04" size="0.007"/>
        </body>
      </body>"""
    acts = "".join(
        f'<position name="{n}_a1" joint="{n}_j1" kp="3" kv="0.1" ctrlrange="0 1.6"/>'
        f'<position name="{n}_a2" joint="{n}_j2" kp="3" kv="0.1" ctrlrange="0 1.6"/>' for n in NAMES)
    return f"""<mujoco><compiler angle="radian"/><default><geom contype="0" conaffinity="0"/></default><option gravity="0 0 0" timestep="0.002"/><worldbody>
    <body name="palm" pos="0 0 0"><geom type="box" size="0.08 0.01 0.05" pos="0 0 0.02"/>{fingers}
    </body></worldbody><actuator>{acts}</actuator></mujoco>"""


class SimHand(Hand):
    def __init__(self, viewer=False):
        self.m = mujoco.MjModel.from_xml_string(_xml())
        self.d = mujoco.MjData(self.m)
        self.v = None
        if viewer:
            from mujoco import viewer
            self.v = viewer.launch_passive(self.m, self.d)

    def set_fingers(self, fingers):
        for i, x in enumerate(clamp5(fingers)):
            self.d.ctrl[2 * i] = self.d.ctrl[2 * i + 1] = 1.6 * x
        for _ in range(10):
            mujoco.mj_step(self.m, self.d)
        if self.v:
            self.v.sync()

    def angles(self):
        return [round(float(self.d.qpos[2 * i]), 3) for i in range(5)]


if __name__ == "__main__":
    h = SimHand(viewer=True); t0 = time.time()
    while True:
        t = time.time() - t0
        h.set_fingers([0.5 + 0.5 * math.sin(2 * t + i) for i in range(5)]); time.sleep(1 / 60)
