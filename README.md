# Tactile-less HandOff: gloves teach the robot's hands, vision decides how hard they may squeeze

Rokoko Smartgloves make teaching a humanoid easy: put them on, move naturally, and a Unitree G1's arms and Dex3 hands follow. But gloves cannot feel force, and a confident human fist crushes an egg. So the robot looks first: a head camera asks two model families (NVIDIA Nemotron, Google Gemma / PaliGemma), the fragile answer always wins, and the object sets a **closure cap** the fingers cannot exceed.

```
Smartgloves II + Coil Pro ──▶ rgmp_client (83 Hz) ──────────────────────────────▶ G1 arms + Dex3 fingers
head camera ──▶ Nemotron (NVIDIA) + Gemma/PaliGemma (Google) + colour ──fragile-first──▶ closure cap ──┘
```
Diagrams: [docs/submission/DIAGRAMS.md](docs/submission/DIAGRAMS.md) · architecture and ports: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · submission package: [docs/submission/](docs/submission/).

## Try it

```bash
python3 -m verify.run
```
Recomputes every recognition number below from the saved model answers in `docs/evidence/recognition/`, offline, no key.

```bash
python3 -m robot.e2e_g1 --label egg
```
Same egg grasp in the G1 MuJoCo simulation with and without the cap (needs `robot/requirements.txt` and the cached G1 assets). Add `--true egg --label stress_ball` to see a recogniser mistake. Tests: `python3 -m pytest tests -q`. Real robot: `start_g1.ps1` (Windows, organisers' runner, see [docs/DELIVERY_G1.md](docs/DELIVERY_G1.md)).

## What is shown

| Claim | Source |
|---|---|
| **Real G1:** Rokoko gloves drove both arms and both Dex3 hands, 2 runs of 120 s, 29.8 commands per second, 0 commands clipped by the organisers' safety filter | `g1/arms_simple.py`, [tools/g1_windows_runner/README.md](tools/g1_windows_runner/README.md) |
| Glove stream: 89 takes, 83 Hz, 0 dropouts, max gap 12 ms | `Rokoko/src/episode_quality.py` |
| On our 50 head-camera photos: Nemotron 48/50 (median 0.22 s), Gemma 4 49/50 with all 20 eggs right, PaliGemma 2 on our own Verda GPU 49/50 (median 0.24 s); fragile-first vote of the three 50/50, computed offline on the same photos | `python3 -m verify.run`, [docs/OBJECT_RECOGNITION_RESULTS.md](docs/OBJECT_RECOGNITION_RESULTS.md) |
| Each Nemotron/Gemma disagreement was exactly one model's error (3 of 3) | `python3 -m verify.run` |
| In the G1 simulation the egg with its cap is held intact, without the cap it breaks; an egg mistaken for a stress ball is still held intact | `python3 -m robot.e2e_g1 --label egg` |
| Full closure on the stress ball only when two model families agree, or the operator sets it; egg and unknown never | `python3 -m pytest tests/test_cap_for.py -q` |
| On the real G1 the operator sets hard caps (egg 0.50, empty can 0.90, ball 1.0) and the camera label can only lower them | `g1/live_policy_v2_vision.py` |

## What is NOT shown

- Vision-guided grasping on the real G1: the camera path ran there only as a capture test; the per-object cap is tested on simulated frames.
- Generalisation: one person, one place, one day, 50 photos, no held-out set; model confidence did not separate right from wrong answers. Photos are not in git (answers are).
- Real force: break thresholds and servo gains in simulation are assumed; we report only intact / broken.
- The can is recognised but not reliably held in simulation.
- The real arms lagged 0.6-1.4 s under load; a fix is on a branch, untested on the robot.

## Team workflow

Two humans and several AI agents in one repo: folder ownership and a pinned GitHub issue as message board ([AGENTS.md](AGENTS.md), `tools/board`); every number checked by `verify/`.
