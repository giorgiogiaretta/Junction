# Rokoko track: draft

## One line
Smartgloves tell a robot hand how the fingers move but not how hard to squeeze; we add a head camera that recognises the object and caps the robot's grip per object, so an egg gets a gentle limit and a confirmed stress ball a firm one.

## The problem
Smartgloves II have no force sensors. Retargeted to a robot hand, a confident human grip can crush a fragile object. The operator feels the egg; the robot does not.

## What we built
1. **Glove capture**: Smartgloves II + Coil Pro streamed as `hand_state v1` over UDP (`Rokoko/src/rgmp_client.py`, `docs/contracts.md`), with raw recording and replay; glove on the head gives hand-in-head pose in the episodes.
2. **Object recognition ensemble from a head camera**: Nemotron, Gemma 4, Gemini and a colour rule vote on one frame; any confident "egg" vote wins ("fragile first", `ai/recognize.py`).
3. **Object -> closure cap** (`ai/object_profile.py`, `cap_for_votes`): egg and stress ball share a gentle cap; the ball gets full closure only if 2 recognisers agree or the operator sets it; unknown -> conservative cap.
4. **Object position** from the G1 head RGB-D camera (`ai/locate.py`), tested on simulated renders.
5. **G1 Dex3 hand in MuJoCo, end to end** (`python -m robot.e2e_g1`) and a live policy for the real G1 (`g1/live_policy.py`), first test at 10% closure.

## Measured (with the command that produces it)
- **Recognition, same 50 of our own head-camera photos** (`docs/OBJECT_RECOGNITION_RESULTS.md`): Nemotron 48/50 in two runs, median 0.22 s; Gemma 4 49/50 with eggs 20/20; ensemble Nemotron + Gemma 50/50, computed offline from the saved answers. `python -m ai.eval_objects imgs --backend nemotron --mix`.
- **End to end in simulation**: egg with its cap held intact, without the cap broken; an egg mistaken for a stress ball is still held intact. `python3 -m robot.e2e_g1 --label egg`, `--true egg --label stress_ball`. Assumed gains and break thresholds: forces are model outputs, only closure levels transfer.
- **Grip rule tests**: `python3 -m pytest tests/test_cap_for.py tests/test_live_policy_cap.py tests/test_picker_safety.py -q`.
- **Object position**: median xy error 0.14-0.26 cm on simulated G1 head renders, with refusals for cut-off or occluded objects. `python -m ai.locate_bench`.
- **Glove stream quality**: 89 takes, 83.3 Hz, 0 dropouts, max gap 12 ms (glove clock). `Rokoko/src/episode_quality.py`.
- **G1 live policy** rehearsed on the organisers' mock runner: about 30 Hz, 0 clipped steps (`docs/G1_LIVE.md`).

## Caveats and not shown
- Recognition: one person, one place, one day, 50 photos, no held-out set; confidence does not separate right from wrong answers.
- No real-G1 result recorded yet; first test at 10% closure.
- Two objects grasped in simulation (egg, stress ball); the can is recognised but not grasped.
- `locate()` not wired into a grasp, not tested on real frames.

## Why it matters
Teleoperation data from gloves is cheap to collect but carries no force. Using vision to supply a per-object grip limit is a small, inspectable layer that makes glove-driven robot hands safer for fragile objects, and it can label Rokoko grasp datasets with the object being held.

## Run it
`python3 -m robot.e2e_g1 --label egg` (no key, no hardware); see the root `README.md`.
