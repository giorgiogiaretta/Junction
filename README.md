# Junction: a head camera gives glove-driven robot hands a sense of "how hard"

Rokoko Smartgloves drive a robot hand, but gloves have no force sensors: the robot cannot tell an egg from a stress ball. We put a camera on the head, let several vision models vote on the object ("fragile first"), and turn the answer into a **per-object closure limit** the robot hand cannot exceed. Robot side: Unitree G1 Dex3 hand in MuJoCo simulation, and the real G1 driven by the gloves (arms + hands, without vision so far).

```
head camera ──▶ Nemotron + Gemma + Gemini + colour ──vote, fragile first──▶ object ──▶ closure cap
glove (Smartgloves + Coil Pro) ─────────────────────────────────────────────────▶ G1 Dex3 hand (sim) ≤ cap
```
Diagram, ports, grip rule and folder owners: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Run it (one command, no key, no hardware)

```bash
python3 -m robot.e2e_g1 --label egg
```
Object -> cap -> G1 Dex3 grasp in MuJoCo, printed with and without the cap (needs `pip install -r robot/requirements.txt` and the G1 assets: run `python g1/sim/g1_sim.py` once). Try `--true egg --label stress_ball` (recogniser mistake) or `--image photo.jpg --recogniser nemotron` (needs `VERDA_INFERENCE_KEY`). Tests: `python3 -m pytest tests -q`.

## What is shown (each with its source)

| Claim | Command / document |
|---|---|
| Recognition on 50 of our own head-camera photos: Nemotron 48/50 in two runs (median 0.22 s), Gemma 4 49/50 with all 20 eggs right, ensemble Nemotron + Gemma 50/50 (computed offline on the same photos) | `python -m ai.eval_objects imgs --backend nemotron --mix`, [docs/OBJECT_RECOGNITION_RESULTS.md](docs/OBJECT_RECOGNITION_RESULTS.md) |
| In simulation the egg with its cap is held intact, without the cap it breaks; an egg mistaken for a stress ball is still held intact | `python3 -m robot.e2e_g1 --label egg`, `--true egg --label stress_ball` |
| Full closure on the stress ball only when 2 recognisers agree (confidence >= 0.9) or set by hand; egg and unknown never | `python3 -m pytest tests/test_cap_for.py tests/test_live_policy_cap.py -q` |
| Object position from the G1 head RGB-D, simulated renders only: median xy error 0.14-0.26 cm, with refusals for cut-off or occluded objects | `python -m ai.locate_bench` |
| Real G1: gloves drove both arms and Dex3 hands, 2 runs of 120 s, 0 commands clipped by the safety filter (no vision on the robot: camera computer off) | branch `g1-real-working`, `tools/g1_windows_runner/README.md` (not on `main` yet) |
| PaliGemma 2 on our own GPU: 49/50 on the same photos, 0.21 s; three-model vote 50/50 | [docs/OBJECT_RECOGNITION_RESULTS.md](docs/OBJECT_RECOGNITION_RESULTS.md) |
| Every object on the table from one G1 head RGB-D frame (label + position + cap), simulated frames only: egg 24/24, can 23/24 | `ai/perceive.py`, [docs/G1_V1_RUN.md](docs/G1_V1_RUN.md) |

## What is NOT shown

- On the real G1: no vision (camera computer off) and no object grasp outcome recorded. Say "the gloves drove the real G1", never "the G1 grasps the egg".
- Closure levels are tuned in simulation; simulated forces use assumed thresholds and are not measurements.
- Two objects grasped in simulation (egg, stress ball); the can is recognised but not grasped.
- Recognition: one person, one place, one day, 50 photos, no held-out set; model confidence does not separate right from wrong answers. Photos are not in git.
- Gemini 3.5 Flash full run not finished. `locate()` is not wired into a grasp and not tested on real frames.
- Real glove finger closures alone do not yet produce grasps in the older 5-finger sim (2/32, [docs/PHASE1_REAL_DATA.md](docs/PHASE1_REAL_DATA.md)).

Status and backlog: [docs/ORCH_BACKLOG.md](docs/ORCH_BACKLOG.md). Pitch deck: [deck/](deck/). Submission drafts: [docs/submission/](docs/submission/).

## Team workflow

Agents coordinate on a pinned GitHub issue via `tools/board`; rules and folder ownership in [AGENTS.md](AGENTS.md).
