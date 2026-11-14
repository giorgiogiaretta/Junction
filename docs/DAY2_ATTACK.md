# Day 2: setup and attack plan (Tommaso's side, aligned with Giorgio's docs/PLAN_QC.md)

Focus agreed with Giorgio (08:14 post): **quality control of demonstrations** (0-100 score per take, keep/discard with reason, dataset card, same model on all vs filtered data) + **multi-hand retargeting** (Inspire, G1 Dex3). Not claimed anywhere: a robot that learns by itself, forces in Newton, "works on the G1" before a test, judge precision/recall before labelled failures exist.

## Setup (once, 10 min)
```
cd ~/Junction && git checkout main && git pull --rebase
export VERDA_INFERENCE_KEY='...'     # yours, never in a file or on the board
demo/morning_check.sh                # tests, keys, Nemotron ping, cameras, Inspire (INSPIRE_HOST=<ip>)
```
No automatic loop agent on this Mac (credits). Extra agents only via docs/CODEX_GUIDE.md (own worktree, own folder).

## Tommaso's tasks (from PLAN_QC section 5) and status
| # | Task | Owner | Status / next |
|---|---|---|---|
| 1 | Key in the environment + `ai.llm` test | Tommaso | done (Nemotron: chat, tool call, image verified) |
| 2 | Judge on videos + agreement with labels, before/after a prompt round | Claude (ai/) | **PR #71 must be merged first** (v2 did NOT send the timeline until then). Needs video frames (vision/, PR #66) and the failed takes from Giorgio (series K/L) |
| 3 | Gemini cross-check on the same frames, disagreements -> human review | Claude (ai/) | `python -m ai.compare_judges --a nemotron --b gemini` is in PR #71; needs `GEMINI_API_KEY`; Gemini model id unverified |
| 4 | Mentor questions (Aalto: Inspire registers/IP/thumb sign/G1 slot) | Tommaso (human) | list below |
| 5 | Review PR #66 (vision) and the dataset card | Claude + Tommaso | #66: 49 tests passed on the branch, no conflicts with robot/ or ai/; not run on real DJI footage |

## Order of work today
1. Merge PR #71 (`gh pr merge 71 --repo giorgiogiaretta/Junction --merge`), `git pull --rebase`.
2. Re-measure judge v2 WITH timeline: `python3 -m ai.judge --version 2 --out data/overnight/judge_v2c/judge.jsonl` (the directory is now created automatically).
3. While Giorgio records K/L takes (8 grasp failures, 6 tracker faults, 3 non-expert, 3 references): wire `vision/` frames into the judge (`ai/`), keep the text-only judge as fallback.
4. When labelled failures exist: precision/recall per class, v1 vs v2 vs v3 prompt, Nemotron vs Gemini, disagreements list.
5. Hardware slice (Inspire) only if the Aalto slot exists; else MuJoCo/G1 gate as agreed. Retargeting stays in `robot/`.
6. Pitch: update `demo/results.html` only with numbers that a command in the repo reproduces.

## Questions for the mentors (copy to docs/MORNING.md if you prefer)
- **Aalto Robotics Club (Inspire):** exact model (RH56?), IP/port, Modbus registers for ANGLE_SET, FORCE_ACT, SPEED_SET and scaling; sign/direction of thumb_rot; is there an emergency stop; can it sit on our table and when?
- **Aalto / Erkka (G1):** slot for the real G1, safety conditions, DDS topics and `hand_q` order (we use docs/g1_dex3_limits.json), who is present during the test.
- **NVIDIA:** is the Verda endpoint stable until the end; limits (RPM/tokens); does the endpoint accept video or only frames; which model id is the one to name in the submission form.
- **Google DeepMind:** Gemini model id for video/live; key and quota; what counts as "best use" in the form.
- **Rokoko (Victoria Stein):** how to read the Smartgloves II button via SDK (RGMP has none); the real stream rate (83 Hz vs 250 Hz) and latency; Coil Pro flip/out-of-range recommendations.

## UPDATE 14/11 ~09:00: new focus (approved by the Rokoko technician via Giorgio) supersedes the QC focus
**Camera + computer vision recognises the object (egg, stress ball, can) and the hand behaves accordingly (closure/speed per object), on the G1 (arms + hands, no Inspire), MuJoCo first, Isaac (Aalto, Verda) before the live test.** Gloves have no force sensors, so vision supplies the missing sense. Head camera (GoPro on the head); a glove on the head gives camera-to-hand relative pose from the Coil (relative = inverse(head pose) * hand pose).

Ownership (no overlap): Giorgio = `Rokoko/`, `ml/`, `vision/`, `g1/` (IK 7 DoF, Coil->torso calibration, physics, profile NUMBERS, Rokoko dataset converter, head-glove geometry). Tommaso's Claude = `ai/` (recognition, object -> profile table `ai/object_profile.py`, Nemotron + Gemini) and `robot/g1_dex3.py` (library). Tommaso's Codex = `demo/`.

Recognition tiers: Nemotron VL on one frame (verified, ~1-2 s, ~0.4 s with thinking off), Gemini VL as second opinion / egocentric video (needs key + model id), fast local detector on `vision/` (#66) for continuous tracking.
First measurable result: `python -m ai.eval_objects <photo folder> --backend nemotron|gemini` (photos named `egg_01.jpg`, `stress_ball_01.jpg`, `can_01.jpg`, `other_01.jpg`).
Extra mentor question: does the G1 runner accept arm commands or hands only, through which interface and limits; which head camera and how are frames read; are the hands Dex3.
