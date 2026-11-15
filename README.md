# Tactile-less HandOff: gloves teach the robot's hands, vision decides how hard they may squeeze

Rokoko Smartgloves make teaching a humanoid easy: put them on, move naturally, and a Unitree G1's arms and Dex3 hands follow. But gloves cannot feel force, and a confident human fist crushes an egg. So the robot looks first: a head camera asks two model families (NVIDIA Nemotron, Google Gemma / PaliGemma), the fragile answer always wins, and the object sets a **closure cap** the fingers cannot exceed.

## Junction 2026 submission (Rokoko challenge)

**Tactile-less HandOff:** Rokoko gloves teach a Unitree G1 humanoid, and a head camera with vision models sets how far each hand may close for the object it is about to hold (egg, stress ball, can).

- **Video:** in the submission form · **Test videos:** [Videos](#videos) below · **Pitch deck (PDF):** `docs/submission/final/deck_text.txt` (text) and the PDF in the submission form
- **Reproduce the numbers:** `python3 -m verify.run` recomputes every recognition number from the saved model answers in `docs/evidence/recognition/` (offline, no key). Tests: `python3 -m pytest tests -q`.
- **Shown on the real G1:** the gloves drove both arms and both Dex3 hands: 2 runs of 120 s, 29.8 commands per second, 0 commands clipped by the safety filter. In later sessions (15 Nov) the Coil Pro also drove both wrists and the head camera set the per-object caps ([docs/G1_FINAL_RUN.md](docs/G1_FINAL_RUN.md)); its labels there were not yet reliable, so no vision-guided object grasp is claimed on the physical robot.
- **Shown in simulation only:** the camera recognises the object, sets the closure limit, and the grasp is held intact with the limit and breaks without it (MuJoCo, grasp assist ON in the demo clips; closure limits and break thresholds are toy values until calibrated on hardware).
- **Limit of the recognition numbers:** 50 labelled photos from one person, one place, one day, with no held-out set.
- **Final texts:** `docs/submission/final/` (form, video script, subtitles, jury cheat sheet) · all claims: `docs/submission/STORY.md`.


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

## Videos

Short clips (H.264, in this repo, [media/videos/](media/videos/)):

| Video | What it shows | Where |
|---|---|---|
| [gopro_headcam_9_grasps_aligned.mp4](media/videos/gopro_headcam_9_grasps_aligned.mp4) | 9 glove-recorded grasps (ball, can, empty can, egg) from the GoPro on the operator's head, aligned on the moment the hand closes, 1.25x | real, 14 Nov |
| [real_g1_headcam_vision_highlight_15s.mp4](media/videos/real_g1_headcam_vision_highlight_15s.mp4) | Real G1 head camera with the policy's own vision labels, gloves + Coil driving both arms | real G1, 15 Nov |
| [sim_egg_held_vision_on.mp4](media/videos/sim_egg_held_vision_on.mp4) | Camera recognises the egg, the cap stops the fingers, egg lifted intact | simulation |
| [sim_egg_broken_no_vision.mp4](media/videos/sim_egg_broken_no_vision.mp4) | Same glove take without vision: the egg breaks | simulation |
| [sim_cap_on_vs_off_side_by_side.mp4](media/videos/sim_cap_on_vs_off_side_by_side.mp4) | Same egg, same fist: cap on vs cap off | simulation |
| [sim_head_camera_recognition.mp4](media/videos/sim_head_camera_recognition.mp4) | Head camera recognising the three objects | simulation |
| [sim_stress_ball_grasp.mp4](media/videos/sim_stress_ball_grasp.mp4) | Stress ball grasp, full closure allowed | simulation |
| [g1_turntable_illustration.mp4](media/videos/g1_turntable_illustration.mp4) | The G1 model (illustration) | render |
| [media/g1_cv_demo.mp4](media/g1_cv_demo.mp4) | 35 s demo: gloves + head camera + caps, three objects | simulation |

Full recordings (GitHub releases):
- [test-videos](https://github.com/giorgiogiaretta/Junction/releases/tag/test-videos): all 29 GoPro head-camera glove takes (61-89, glove data for each in `data/episodes/`), real G1 head-camera runs, Coil simulator sessions, full demo renders.
- [g1-real-20261115](https://github.com/giorgiogiaretta/Junction/releases/tag/g1-real-20261115): final real-G1 runs with gloves + Coil + vision: annotated and raw head-camera video, runner data, Dex3 pressure, raw glove input.

## Real robot code

| File | What |
|---|---|
| `start_g1.ps1` | One command: glove driver, calibration, policy, organisers' runner (`-CoilVision -Both -Fast -LowLag`) |
| `g1/live_policy_v2_vision.py` | Coil Pro arms, glove fingers, per-object caps from the head camera (object nearest each hand) |
| `g1/coil_chain.py` | Coil Pro wrist chain: calibration, mirrored-hemisphere fix, low-delay smoothing |
| `g1/finger_map.py` | Thumb, index, middle mapped one-to-one onto the Dex3 |
| `g1/arm_prior.py` | Real-G1 posture prior from recorded wrist/arm pairs |
| `tools/coil_axes_check.py` | Axis-by-axis test bench of the Coil chain, both hands |
| `g1/sim/teleop_multi.py` | Live MuJoCo simulator with the same chain, gloves + Coil, recording |

## What is NOT shown

- Vision-guided grasping on the real G1: the camera path ran in the final runs, but with provisional head extrinsics it mislabelled the can as egg (the safe direction); the per-object cap is validated on simulated frames ([docs/G1_FINAL_RUN.md](docs/G1_FINAL_RUN.md)).
- Generalisation: one person, one place, one day, 50 photos, no held-out set; model confidence did not separate right from wrong answers. Photos are not in git (answers are).
- Real force: break thresholds and servo gains in simulation are assumed; we report only intact / broken.
- The can is recognised but not reliably held in simulation.
- Arm lag: the real arms lagged 0.6-1.3 s because the Unitree SDK checked every packet's CRC in pure Python on Windows. With a bit-identical fast CRC the lag onset on the real robot dropped to 0.38-0.45 s ([docs/ARM_DELAY.md](docs/ARM_DELAY.md)); the remaining delay is policy-side.

## Team workflow

Two humans and several AI agents in one repo: folder ownership and a pinned GitHub issue as message board ([AGENTS.md](AGENTS.md), `tools/board`); every number checked by `verify/`.
