# Junction: a head camera gives glove-driven robot hands a sense of "how hard"

Rokoko Smartgloves drive a robot hand, but gloves have no force sensors: the robot cannot tell an egg from a can. We put a camera on the operator's head, let a vision-language model name the object, and turn the name into a **per-object closure limit** the robot hand cannot exceed. The robot side runs in MuJoCo simulation.

```
glove (Smartgloves + Coil Pro) ──UDP 14043──▶ simulated robot hand ◀──UDP 14070── {"profile": "egg"}
head camera ──▶ Nemotron VL (Gemini backup) ──▶ object ──▶ grip profile ────────────┘
```
Full diagram, ports and folder owners: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Run it (no hardware, mock glove)

```bash
pip install -r robot/requirements.txt -r demo/requirements.txt && demo/run_demo.sh --assist egg
```
Starts a mock glove stream, the MuJoCo egg scene with the egg limit, and the dashboard. In a second terminal, switch the object profile by hand (no API key needed) or from a photo (needs `VERDA_INFERENCE_KEY`):
```bash
python3 -m ai.pick_profile --set egg
```
```bash
python3 -m ai.pick_profile --image photo.jpg
```
Tests: `python3 -m pytest tests -q`.

## What is shown (each with its source)

| Claim | Command / document |
|---|---|
| 48 of 50 of our own head-camera photos recognised in one run (egg 18/20, stress ball 22/22, can 8/8); the 2 errors are eggs called stress ball | `python -m ai.eval_objects imgs --backend nemotron --mix`, [docs/OBJECT_RECOGNITION_RESULTS.md](docs/OBJECT_RECOGNITION_RESULTS.md) |
| The picker never leaves the hand without a limit (fallback `cup`); a low-confidence "stress ball" is treated as egg | `python3 -m pytest tests/test_picker_safety.py -q` |
| Per-object closure limit in sim: eggs broken 10/11 -> 1/11 (scripted grip on real wrist paths, 5-finger sim hand) | `python3 -m robot.replay_all`, [docs/PHASE1_REAL_DATA.md](docs/PHASE1_REAL_DATA.md) |
| G1 Dex3 hand: 12 commanded joints close in the right direction (URDF geometry only) | `python g1/sim/g1_sim.py`, `python3 -m pytest tests/test_g1_dex3.py -q` |
| Episode judge prompt: positives judged good 5/32 -> 22/32 (positives only, noise about ±3) | `python3 -m ai.judge --version 2`, [docs/JUDGE_RESULTS.md](docs/JUDGE_RESULTS.md) |

## What is NOT shown

- No single command yet runs photo -> object -> profile -> G1 grasp in MuJoCo -> held/broken.
- Two objects in simulation (egg, stress ball); the can is recognised but not grasped by the simulated G1 hand (PR #79).
- Grip limits are closure levels tuned in simulation; forces are outputs of the simulation model, not measurements.
- Recognition: 50 photos, one person, one place, one day, one run; the photos are not in git and the endpoint was down afterwards.
- Gemini never called live; no local model in the picker; head-to-hand tracking has no real data yet.
- Real glove finger closures do not yet produce grasps in sim (2/32).
- Nothing has run on the real G1.

Honest status and backlog: [docs/ORCH_BACKLOG.md](docs/ORCH_BACKLOG.md). Submission drafts: [docs/submission/](docs/submission/).

## Team workflow

Agents coordinate on a pinned GitHub issue via `tools/board`; rules and folder ownership in [AGENTS.md](AGENTS.md).
