import os, re, sys, tempfile
import numpy as np, mujoco
sys.path.insert(0, r"C:\Users\giorg\Desktop\aaltonomous-humanoid\winshim")
import pinocchio as pin
os.chdir(r"C:\Users\giorg\Desktop\aaltonomous-humanoid")
u = "third_party/xr_teleoperate/assets/g1/g1_body29_hand14.urdf"
m = pin.buildModelFromUrdf(u); d = m.createData()
s = open(u).read()
s = re.sub(r"<visual>.*?</visual>|<collision>.*?</collision>", "", s, flags=re.S)
s = re.sub(r"<mujoco>.*?</mujoco>", "", s, flags=re.S)
s = s.replace("</robot>", '<mujoco><compiler fusestatic="false" discardvisual="false"/></mujoco></robot>')
t = os.path.join(tempfile.gettempdir(), "g1_nomesh.urdf"); open(t, "w").write(s)
mm = mujoco.MjModel.from_xml_path(t); dd = mujoco.MjData(mm)
P = lambda f: dd.xpos[mujoco.mj_name2id(mm, mujoco.mjtObj.mjOBJ_BODY, f)]
rng = np.random.default_rng(0); err = 0
names = [n for n in m.names[1:] if any(k in n for k in ("shoulder", "elbow", "wrist", "waist"))]
for _ in range(30):
    q = pin.neutral(m); dd.qpos[:] = 0
    for n in names:
        v = rng.uniform(-1, 1); q[m.joints[m.getJointId(n)].idx_q] = v
        dd.qpos[mm.jnt_qposadr[mujoco.mj_name2id(mm, mujoco.mjtObj.mjOBJ_JOINT, n)]] = v
    pin.forwardKinematics(m, d, q); mujoco.mj_kinematics(mm, dd)
    for f in ("left_wrist_yaw_link", "right_wrist_yaw_link", "right_hand_palm_link", "left_hand_palm_link"):
        a = pin.updateFramePlacement(m, d, m.getFrameId(f)).translation
        err = max(err, np.abs(a - (P(f) - P("pelvis"))).max())
print("joints", len(names), "max err m", err, "root", m._root)
