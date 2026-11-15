# G1 x Rokoko gloves x computer vision: what we built (delivery summary)

## The idea
An operator wearing Rokoko Smartgloves (plus the optional Coil Pro for wrist position) drives a Unitree G1 with Dex3 hands. The G1 head
camera recognises the object in front of the hand (egg, stress ball, empty can), and the robot limits how hard it can squeeze according to
the recognised object: the egg is grasped gently and never crushed, while the ball and the can get a firm grip.

## What runs on the real G1 (tested 14-15 Nov, Windows laptop, organisers' runner)
| What | File | Command |
|---|---|---|
| One-command launcher (network check, glove driver, console, policy, runner) | `start_g1.ps1` | `& start_g1.ps1` (+ options below) |
| Gloves drive both arms (open = up, close = down + grasp, open = release) and both Dex3 hands | `g1/arms_glove.py` (`g1/arms_simple.py` = first version that ran) | `start_g1.ps1` / `-Safe` |
| Coil Pro wrist teleoperation, both hands, seated calibration | `g1/live_policy_v2.py`, `g1/coil_chain.py` | `start_g1.ps1 -Coil -Both` |
| Coil + head-camera recognition, per-object closure limit (egg 0.50, can 0.90, ball 1.0) | `g1/live_policy_v2_vision.py` | `start_g1.ps1 -CoilVision` |
| Thumb, index and middle finger each follow their own glove finger | `g1/finger_map.py` | (all of the above) |
| Start-up path accepted by the runner's safety filter (robot raised twice by the staff) | `g1/start_path.py` | (automatic) |
| Organisers' runner on Windows (CycloneDDS built from source, Pinocchio/turbojpeg shims) | `tools/g1_windows_runner/` | see its README |

Options: `-Fast` (staff-approved: arm speed 2 rad/s, no table keep-out, robot self-collision check kept), `-NoCamera`, `-NoConsole`,
`-Closure 0.6` (finger scale). Every command passes the organisers' safety filter (0 clipped commands in the recorded runs).

## Computer vision
- `g1/perception_v1.py` (geometry + colour vote, robot self-mask) and Tommaso's `ai/perceive.py` (VLM ensemble: NVIDIA Nemotron, Gemma,
  PaliGemma 49/50 on real photos, colour veto, fragile-first). Head RGB-D from the G1 camera computer (192.168.123.254 on 15 Nov).
- Codex + DeepSeek cross-review of the Coil policy: `docs/COIL_REVIEW.md` (found that the camera was never called in V2; fixed in
  `live_policy_v2_vision.py`).

## Demo video for the jury
`media/g1_cv_demo.mp4` (35 s, 1920x1080): the head camera recognises ball, can and egg; the closure limit follows the label; the grasps
replay the operator's real glove recordings (14 Nov takes 80, 85, 77); the same egg grasp with vision OFF breaks the egg.
Made with `g1/sim/demo_cv.py` (MuJoCo, `--live` = your own glove) and cut by `g1/sim/demo_montage.py`. The can and egg clips use a
grasp assist in simulation (marked "grasp assist ON" on screen); the ball clip is pure physics.

## Honest limits
- Vision on the real robot ran on real head frames only as a capture test; the per-object limit has been tested on simulated frames.
- The real arms follow the commands with 0.6-1.4 s delay under load (runner loop ~100 ms); our policy adds ~4-8 ms per command.
- Break / dent thresholds and hand gains in simulation are assumed, not measured.
