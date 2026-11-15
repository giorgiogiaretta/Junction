# For Giorgio: real G1 arm postures from the Aalto drops, for Coil wrist -> arm

*Tommaso's Aalto-Orchestrator, 2026-11-15 night. Branch `aalto/spike`, folder `aalto/data/`. No keys, no personal data.*

## What you can use right now

| File | What | Use for the Coil |
|---|---|---|
| `g1_wrist_arm_pairs.npz` (5.5 MB) | 19,371 REAL robot frames (drop 2: 48 episodes, drop 3: 15 episodes, 30 Hz, Aalto staff VR teleop, table-top pick-and-place). Per frame: measured `arm_q` (14), commanded `arm_q_cmd` (14), `hand_q` / `hand_q_cmd` (14), and FK poses `left_wrist`, `right_wrist`, `left_palm`, `right_palm` = (x, y, z, qx, qy, qz, qw) in the **pelvis frame** (m; x forward, y left, z up) | a dictionary of postures the real G1 really took near the table: natural elbow, inside the limits |
| `knn_arm_seed.py` | `ArmPrior(npz).seed(side, pos, quat=None)` -> nearest real 7-joint arm posture + its distance | IK seed for each Coil wrist target (or the answer when the match is < ~1-2 cm); pure numpy, Windows-safe |
| `wrist_arm_pairs.py` | how the npz was made (pinocchio on the official `g1_body29_hand14.urdf`, fixed pelvis, legs/waist 0) | regenerate / add frames (e.g. your own robot logs) |
| `retime_actions.py` | makes any joint-target stream pass the organisers' filter: clamp into URDF limits minus margin (arm 0.06, hand 0.03 rad), then rate-limit per tick (arm 0.9 rad/s, hand 2.7 rad/s, 10 % under the caps) | the same projection, online, after the IK and before sending |
| `train_night.sh` | merge drops 2+3, safe copy, ACT training command (LeRobot 0.7, 3 GPUs) | reference only |

Quick test (output on the npz): left wrist at (0.30, 0.15, 0.15) m -> nearest real posture 1.0 cm away;
right wrist at (0.30, -0.15, 0.15) -> 0.5 cm; left (0.25, 0.20, 0.30) -> 6.8 cm (outside what the demos covered).
Workspace covered by the demos (pelvis frame): left wrist x 0.05-0.38, y 0.00-0.27, z 0.04-0.38 m;
right wrist x 0.10-0.38, y -0.26 to -0.02, z 0.03-0.34 m.

## Suggested pipeline for Coil -> arm (your folder, your call)

1. **Calibrate once**: map the Coil wrist frame to the robot pelvis frame (e.g. hold 3-4 known robot wrist poses,
   fit a rigid transform; the npz gives you the wrist pose of any joint vector through the same FK).
2. **Per Coil sample**: `q_seed = prior.seed(side, pos, quat)`; refine with your `g1/arm_ik.py` (or the organisers'
   `ArmKinematics.solve`) starting from `q_seed`; if the target is far (> ~5 cm) from every demo posture, trust
   the IK less (outside the region the real robot was driven in).
3. **Before sending**: clamp + rate-limit exactly like `retime_actions.py` (online version: keep the last command,
   move at most 0.9 rad/s * dt per joint). This removes the 0-clip / abort risk you hit with the measured rest pose.

## Facts found tonight that matter on the real robot

- **Every teleop episode in drops 2+3 exceeds the 1 rad/s arm cap** (19-22 % of ticks, up to 11 rad/s; hands > 3
  rad/s on 6-8 %). Teleop commands are spiky: rate-limit anything you replay or learn from them.
- **Real head-camera colours** (drop 2 `cam_high`, OpenCV HSV, H 0-180): purple cube H 109-112 S ~150; yellow
  H 44-47 S 70-82 (washed out); orange H 12-14 S 133-224; the orange boxes H 4-6 S 175-198 V ~100; wooden table
  S < 35. Real objects are yellow / purple / orange (sort_fixed: yellow -> left, purple -> center, orange -> right).
- **Arm lag**: you measured 0.6-1.4 s on the robot; the demos' commanded-vs-measured gap is a median 0.045 rad.

## Models

- **ACT (LeRobot 0.7)** trained on drops 2+3 with safety-retimed actions, 3x RTX PRO 6000, checkpoints every 10k
  steps on the Verda box (`/root/runs/act_drop23_safe/checkpoints/`, ~200 MB each). Inputs: 3 RGB cameras +
  28 joint states -> chunks of 50 joint targets. It is NOT wrist-conditioned, so not a Coil retargeter; ask if you
  want a checkpoint copied.
- **Aalto submission** (other track): organisers' classical planner + our offline instruction parser + the HSV
  above, image `docker.io/tommymagelli/aalto-policy` (see `aalto/policy/`).
