"""Real G1 arm postures with their wrist / palm poses: (wrist pose -> 14 arm joints) pairs from the organisers'
real teleop demos (zupermiez/g1_junction_drop_2 + drop_3, LeRobot v3.0, 30 Hz, VR teleop by Aalto staff).

Why: a Coil / glove gives wrist poses, the robot needs 7 arm joints per side. These pairs are postures the REAL
robot actually took for table-top pick-and-place, so they are good IK seeds / a nearest-neighbour IK prior
(natural elbow, inside the joint limits) and a sanity set for any wrist -> joint retargeting.

FK: pinocchio on the official URDF (xr_teleoperate g1_body29_hand14.urdf, same as the organisers' safety filter
and planner), fixed base = pelvis, legs/waist at 0 (stiff lower body). Frames: <side>_wrist_yaw_link (wrist) and
<side>_hand_palm_link (palm), positions in metres in the PELVIS frame (x forward, y left, z up), quaternions
(x, y, z, w).

Usage: python wrist_arm_pairs.py <out.npz> <drop_2 data parquet> [<drop_3 data parquet> ...]
"""
import sys

import numpy as np
import pandas as pd
import pinocchio as pin

URDF = "/root/aaltonomous-humanoid/third_party/xr_teleoperate/assets/g1/g1_body29_hand14.urdf"
ARM = ["left_shoulder_pitch_joint", "left_shoulder_roll_joint", "left_shoulder_yaw_joint", "left_elbow_joint",
       "left_wrist_roll_joint", "left_wrist_pitch_joint", "left_wrist_yaw_joint",
       "right_shoulder_pitch_joint", "right_shoulder_roll_joint", "right_shoulder_yaw_joint", "right_elbow_joint",
       "right_wrist_roll_joint", "right_wrist_pitch_joint", "right_wrist_yaw_joint"]
FRAMES = {"left_wrist": "left_wrist_yaw_link", "right_wrist": "right_wrist_yaw_link",
          "left_palm": "left_hand_palm_link", "right_palm": "right_hand_palm_link"}

out, files = sys.argv[1], sys.argv[2:]
model = pin.buildModelFromUrdf(URDF)
data = model.createData()
iq = np.array([model.joints[model.getJointId(n)].idx_q for n in ARM])
fid = {k: model.getFrameId(v) for k, v in FRAMES.items()}
assert all(f < model.nframes for f in fid.values()), fid

cols = {k: [] for k in ("source", "episode_index", "frame_index", "arm_q", "arm_q_cmd", "hand_q", "hand_q_cmd")}
poses = {k: [] for k in FRAMES}
for si, f in enumerate(files):
    d = pd.read_parquet(f, columns=["observation.state", "action", "episode_index", "frame_index"])
    S = np.stack(d["observation.state"].values).astype(np.float64)
    A = np.stack(d["action"].values).astype(np.float64)
    q = pin.neutral(model)
    for k in range(len(d)):
        q[iq] = S[k, :14]
        pin.framesForwardKinematics(model, data, q)
        for name, i in fid.items():
            M = data.oMf[i]
            poses[name].append(np.r_[M.translation, pin.Quaternion(M.rotation).coeffs()])  # x y z, qx qy qz qw
    cols["source"].append(np.full(len(d), si, np.int16))
    cols["episode_index"].append(d["episode_index"].to_numpy())
    cols["frame_index"].append(d["frame_index"].to_numpy())
    cols["arm_q"].append(S[:, :14]); cols["arm_q_cmd"].append(A[:, :14])
    cols["hand_q"].append(S[:, 14:]); cols["hand_q_cmd"].append(A[:, 14:])
    print(f"{f}: {len(d)} frames")

arr = {k: np.concatenate(v) for k, v in cols.items()}
for k in ("arm_q", "arm_q_cmd", "hand_q", "hand_q_cmd"):
    arr[k] = arr[k].astype(np.float32)
for k, v in poses.items():
    arr[k] = np.asarray(v, np.float32)   # (N, 7): x y z qx qy qz qw, pelvis frame
arr["sources"] = np.array(files)
arr["arm_names"] = np.array(ARM)
np.savez_compressed(out, **arr)
n = len(arr["arm_q"])
lw, rw = arr["left_wrist"][:, :3], arr["right_wrist"][:, :3]
print(f"saved {out}: {n} frames")
print("left wrist  xyz min", lw.min(0).round(3), "max", lw.max(0).round(3))
print("right wrist xyz min", rw.min(0).round(3), "max", rw.max(0).round(3))
