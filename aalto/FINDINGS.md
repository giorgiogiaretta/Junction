# Aaltonomous: findings (dataset drop 2, public data, architecture decision)

*Tommaso's Aalto-Orchestrator, 2026-11-15. Companion to [PLAN.md](PLAN.md). No keys, no hostnames in this file.*

## 1. Official real data: `zupermiez/g1_junction_drop_2` (public, read 2026-11-14)

Read from `meta/info.json`, `meta/episodes`, `meta/tasks.parquet` and the full joint table
`data/chunk-000/file-000.parquet` (videos not downloaded: 158 MB per camera).

| Fact | Value |
|---|---|
| Format | LeRobot v3.0, `robot_type` Unitree_G1_Dex3_Mono, 30 fps |
| Size | 48 episodes, 14,548 frames; episode length 5.2 / 8.3 / 23.3 s (min / median / max) |
| Content | **one object per episode**: orange cube -> right (16), purple cube -> center (14), orange cube -> left (13), orange triangular prism -> right (5) |
| Keys | `observation.state` 28, `action` 28 (left arm 7, right arm 7, left hand 7, right hand 7; rad); cameras `cam_high`, `cam_left_wrist`, `cam_right_wrist` (640x480 RGB) |
| Missing | **no head depth**, **no `meta/aalto_episodes.jsonl`** (no success labels, no layouts); README: "a significant part of the data is suboptimal" |

Problems that change our plan:
1. **Object colours are orange and purple**, not the red / yellow / blue of the rules, and the bins are orange too:
   an orange object next to an orange bin breaks the baseline's HSV thresholds. Ask the organisers on Discord which
   objects the finals use.
2. **Every episode breaks the arm velocity cap.** Finite difference of `action` at 30 Hz: arm > 1 rad/s on 19.1 % of
   ticks (p99 2.87, max 11.0 rad/s), in 48 / 48 episodes; hand > 3 rad/s on 8.1 % of ticks (p99 14.4 rad/s).
   A policy cloned on raw actions would be clipped (sim gate = 0 clips). Any imitation use needs the actions
   re-timed under the caps first.
3. Commanded vs measured arm gap: median 0.045 rad (the teleop leads the robot).

Best use in the time left: **calibration, not training**. Test our perception on real `cam_high` frames, and read
the real Dex3 closure at the grasp moment (cube, prism) to tune the baseline's grasp.

## 2. Public data and models (checked on the HF / GitHub APIs)

- `unitreerobotics/G1_Dex3_*`: 13 LeRobot datasets, same Dex3 hands (BlockStacking, GraspSquare, ObjectPlacement,
  PickApple, PickBottle, ...). Check action space and rate on each card before mixing with ours.
- `datamentorshf/G1_Dex3_BlockStacking_Dataset` and `unitreerobotics/G1_Stack_Block` (named in the organisers'
  STARTER_PATHS).
- `nvidia/GR00T-N1.6-G1-PnPAppleToPlate` (GR00T fine-tuned for G1 pick and place); Isaac-GR00T has a `REAL_G1`
  embodiment tag (relative EEF + relative joints). Base checkpoints: `nvidia/GR00T-N1.6-3B`, `GR00T-N1.7-3B`.
- Organisers list LeRobot ACT / Diffusion / SmolVLA, openpi (pi0 / pi0.5) and Isaac-GR00T.

## 3. Architecture decision: "brain + spinal cord"

| Part | What | Why |
|---|---|---|
| Brain (1-5 Hz, background thread) | deterministic instruction parser -> colour->bin map (once, in `reset`); PaliGemma 2 `detect` -> boxes + head depth -> 3D grasp point; sequencer picks the next object | parser = testable, offline, instant; PaliGemma is not an instruction follower, its strength is detection (robust to held-out textures / lighting) |
| Spinal cord (30 Hz, `act`) | organisers' classical IK planner (0 clips, 30 Hz, 76-82 % rung 1 sim) + our safety projector: joint limits minus margin, arm step <= 1 rad/s, hand <= 3 rad/s, workspace check, first move up out of the counter keep-out | passes the gate by construction; Giorgio's real-G1 traps handled |
| Link | lock-protected "current goal" slot with a sequence number; brain replaces it only between phases; `act()` never blocks, holds when the goal is stale | held ticks returned by us count toward the 27 Hz command rate |

Rules that bind it: weights inside the image (no network guaranteed at the finals), <= 32 GB VRAM (PaliGemma 2 3B
~7 GB bf16 fits), server up within 120 s. The remote PaliGemma on our A100 is for development only.

Rejected for this entry: a fine-tuned VLA as the spinal cord (48 single-object, over-cap demos; < 10 h; 0-clip gate).
Optional side experiment on free GPUs: LeRobot ACT on drop 2 with re-timed actions, for originality, not the entry.

## 4. Sim box

No `aalto-sim:v1` image tarball yet (link is on Discord, no persistent volume on the box): go bare metal with
`aaltonomous/cloud/setup_instance.sh` (~30-40 min), then `aalto.sh sim / check / snap / baseline`.
