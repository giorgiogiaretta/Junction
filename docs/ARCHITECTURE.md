# Architecture

Gloves have no force sensors. A head camera sees **what** the hand is about to grasp; several recognisers vote on the object; the result selects a per-object **closure limit** the robot hand cannot exceed. The robot side runs in MuJoCo simulation; on the real G1 the gloves have driven arms and hands, without vision so far.

Status as of 15/11 morning (`main` at 7947365). Audit: `docs/submission/AUDIT.md`. Wording follows the safe phrasing of `docs/ORCH_BACKLOG.md` section 1.

## Data flow

```mermaid
flowchart LR
  subgraph Rokoko["Rokoko/  (Giorgio)"]
    G[Smartgloves II + Coil Pro] -->|RGMP| C[rgmp_client.py]
  end
  subgraph Head["Head camera"]
    CAM[Operator: DJI webcam + glove on head<br/>G1: RealSense D435i]
  end
  subgraph ai["ai/  (Tommaso's Claude)"]
    RE[recognize.py ensemble<br/>Gemini + Gemma + Nemotron + colour<br/>vote: fragile first]
    PP[pick_profile.py<br/>single model + fallback]
    LO[locate.py<br/>object position from RGB-D]
    OP[object_profile.py<br/>cap_for_votes]
  end
  subgraph demo["demo/  (Codex)"]
    F[fanout.py] --> D[dashboard.py]
  end
  subgraph robot["robot/ + g1/"]
    E2E[robot.e2e_g1<br/>label -> cap -> G1 Dex3 MuJoCo<br/>held / broken, with and without cap]
    S[robot.sim_server<br/>5-finger MuJoCo, Force Cushion]
    LP[g1/live_policy.py<br/>G1 right hand = cap x glove]
  end
  C -->|hand_state v1 UDP 14043 / 14053| F
  CAM --> RE --> OP
  CAM --> PP --> OP
  CAM --> LO
  OP -->|"{object, profile, max_closure} UDP 14070"| S
  OP --> E2E
  OP --> LP
  F --> S
  C --> LP
  S -->|state UDP 14060| D
  LO -.not wired into a grasp yet.-> LP
```

Dashed arrows are not wired today.

## Grip rule (`ai/object_profile.py`, `cap_for_votes`)
- Egg and unknown objects never get full closure. Unknown, error or no answer -> conservative cap 0.68.
- Egg and stress ball share one cap (0.70), so an egg/ball mix-up neither drops nor crushes the egg in the simulation.
- The stress ball gets full closure (1.0) **only** if at least 2 independent recognisers agree with confidence >= 0.9, or the operator sets it by hand (`--set stress_ball`). One confident model is not enough: confidence does not separate right from wrong answers (`docs/OBJECT_RECOGNITION_RESULTS.md`).
- The can is recognised but not grasped (vision only, `supported=false` in `g1/object_profiles.json`).
- Closure levels are tuned in simulation; forces printed by the simulation are model outputs with assumed thresholds, not measurements.

Tests: `python3 -m pytest tests/test_cap_for.py tests/test_picker_safety.py tests/test_live_policy_cap.py -q`.

## Recognisers (same 50 head-camera photos, `docs/OBJECT_RECOGNITION_RESULTS.md`)

| Recogniser | Where | Result |
|---|---|---|
| Nemotron 3.5 Super VL (NVIDIA, Verda) | `ai/pick_profile.py`, `ai/recognize.py` | 48/50 in two runs, median 0.22 s per call (second run) |
| Gemma 4 26B A4B (Google API) | `ai/recognize.py` | 49/50, eggs 20/20, median 7.7 s |
| Gemini 3.5 Flash | `ai/recognize.py` | full run not finished (spot test only) |
| Colour rule (local, no network) | `ai/color_baseline.py` | 38/50, untuned |
| **Ensemble Nemotron + Gemma, fragile first** | `ai/recognize.py` | **50/50**, computed offline from the saved answers |
| PaliGemma 2 3B on our A100 (Verda), 3-option question | `ai/paligemma.py`, `tools/paligemma_server.py` | 49/50, median 0.24 s |
| Three-model vote Nemotron + Gemma 4 + PaliGemma | offline from saved answers | 50/50, every ball confirmed by >= 2 |
| YOLO-World-S (local) | `cv/` | 12/50, not used (`docs/CV_RESULTS.md`) |

Fragile-first vote: any answer "egg" with confidence >= 0.6 makes the result egg; otherwise majority. Backends run in parallel with a 15 s timeout; no answer -> conservative cap. Command: `python -m ai.recognize photo.jpg --backends gemini,gemma,nemotron,color`.

## Object position (`ai/locate.py`)
G1 head RGB-D -> object centre in the pelvis frame, with refusals (`depth_ok=False`) for mixed depth, objects cut by the frame edge and occluded balls. Measured only in simulation: `python -m ai.locate_bench` on MuJoCo renders of the G1 head camera, 20 placements per object, median xy error 0.14-0.26 cm with a perfect mask. Not tested on real G1 frames, not wired into a grasp.

## All objects at once (`ai/perceive.py`)
One G1 head RGB-D frame -> every object on the table with label (ensemble on crops + colour veto), position (`locate`) and cap. Used once at the first frame by `g1/live_policy_v1.py`. Simulated frames only: egg 24/24, can 23/24, xy median 0.2/0.4 cm (`docs/G1_V1_RUN.md`).

## G1: simulation and real robot
- **Simulation, end to end**: `python -m robot.e2e_g1 --label egg` (no key needed) or `--image <photo> --recogniser nemotron`. Egg with its cap: held intact; without the cap: broken. Egg mistaken for a stress ball (`--true egg --label stress_ball`): held intact thanks to the shared cap. Right hand only, fixed base, assumed gains and break thresholds.
- **Policies**: `g1/live_policy.py` (arms still, hand from glove), `g1/live_policy_v1.py` (camera finds objects, hover -> descend -> capped grasp -> lift), `g1/live_policy_v2.py` (Coil arms), operator console `tools/console/app.py`. Mock runner 29-30 Hz, 0 clipped.
- **Real G1 (14-15/11, organisers' runner on Windows, `tools/g1_windows_runner/`): Rokoko gloves drove both arms and both Dex3 hands, 2 runs of 120 s, 29.8 commands/s, 0 commands clipped by the safety filter (`g1/arms_simple.py`).** Later on the robot: `g1/arms_glove.py`, Coil Pro wrist teleoperation `g1/live_policy_v2.py`, one command `start_g1.ps1` (`docs/DELIVERY_G1.md`).
- **Real G1 with vision** (`g1/live_policy_v2_vision.py`, `start_g1.ps1 -CoilVision`): the operator declares the object, hard caps egg 0.50 / empty can 0.90 / ball 1.0, and the camera label can only lower the cap. Vision on the real robot ran on real head frames only as a capture test; the per-object cap is tested on simulated frames. Second safety layer diagram: `docs/submission/DIAGRAMS.md`.

## UDP ports (all 127.0.0.1)

| Port | Payload | Producer -> consumer |
|---|---|---|
| 12276 | Raw RGMP | Rokoko Studio / `Rokoko/src/replay_rgmp.py` -> `rgmp_client.py` |
| 14043 | hand_state v1 `{fingers[5], hand, t, ...}` | `rgmp_client.py` / mock -> fanout, `g1/live_policy.py --source udp:14043` |
| 14053 | Bimanual `{left, right, t}` | `rgmp_client.py --bimanual-port` -> fanout |
| 14044 / 14045 / 14046 | Copies of the glove stream | fanout -> dashboard / `robot.run_udp` / `robot.sim_server` |
| 14060 | Sim state `{obj, force, broken, lifted, cap, profile}` | `robot.sim_server` -> dashboard |
| 14070 | `{object, profile, max_closure, max_speed}` | `ai.pick_profile` / `ai.recognize --publish` -> sim_server, run_udp |

Contracts: `docs/contracts.md`.

## Folder boundaries (AGENTS.md section 4)

| Folder | Owner | Role |
|---|---|---|
| `Rokoko/`, `ml/`, `vision/`, `g1/` | Giorgio's agents | Glove capture, episodes, G1 IK, grasp physics, live policy |
| `ai/`, `robot/` | Tommaso's Claude | Recognition ensemble, locate, object -> cap, e2e sim command, Dex3 retargeting |
| `demo/`, `deck/`, `docs/PITCH*.md` | Tommaso's Codex | Dashboard, demo, pitch |
| `cv/` | Tommaso's Codex-CV | Local detector benchmark |
| `docs/ARCHITECTURE.md`, `docs/submission/`, `README.md` | Tommaso's Docs | This page, submission drafts |

## What is not shown yet
- Real G1: vision-guided grasp not shown (capture test only); real arms lagged 0.6-1.4 s under load.
- The live G1 policy uses the single-model picker, so there the ball reaches full closure only with a manual `--object stress_ball`.
- `locate()` is not wired into a grasp and not tested on real frames.
- The can is recognised but not grasped.
- Recognition: one person, one place, one day, 50 photos, no held-out set; the ensemble 50/50 is computed offline on the same photos.
