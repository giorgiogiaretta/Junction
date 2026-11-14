# Rokoko track: draft

## One line
Smartgloves tell a robot hand how the fingers move but not how hard to squeeze; we add a head camera that recognises the object and caps the robot's grip per object, so an egg gets a gentle limit and a can a firm one.

## The problem
Smartgloves II have no force sensors. Retargeted to a robot hand, a confident human grip can crush a fragile object. The operator feels the egg; the robot does not.

## What we built
1. **Glove capture**: Smartgloves II + Coil Pro streamed as `hand_state v1` over UDP (`Rokoko/src/rgmp_client.py`, contract in `docs/contracts.md`), with raw recording and replay (`Rokoko/src/replay_rgmp.py`).
2. **Object recognition from a head camera**: one frame goes to a vision-language model (Nemotron, Gemini as backup) that names the object (`ai/pick_profile.py`).
3. **Object -> grip profile**: each object maps to a maximum closure and speed (`ai/object_profile.py`), published on UDP 14070.
4. **Simulated robot hand**: MuJoCo hand driven by the glove stream, with a per-object closure limit ("Force Cushion", `robot/`), plus G1 Dex3 hand geometry (`g1/sim/g1_sim.py`).

## Measured (with the command that produces it)
- **Recognition**: 48 of 50 of our own head-camera photos correct in one run (egg 18/20, stress ball 22/22, can 8/8); the 2 errors are small eggs called stress ball. `python -m ai.eval_objects imgs --backend nemotron --mix`; details `docs/OBJECT_RECOGNITION_RESULTS.md`. One person, one place, one day; the photo folder is not in git.
- **Safety of the error direction**: the picker never leaves the hand without a limit (fallback `cup`), and a low-confidence "stress ball" is treated as an egg. `python3 -m pytest tests/test_picker_safety.py -q`.
- **Closure limit in simulation**: with a scripted grip on real recorded wrist paths, eggs broken 10/11 without the limit and 1/11 with it. `python3 -m robot.replay_all`; `docs/PHASE1_REAL_DATA.md`. Toy break threshold, 5-finger sim hand, not the G1. Forces are outputs of the simulation model, not measurements.
- **Real glove data in sim**: the real Coil Pro wrist path with a scripted grip lifts the cube in 7/11 takes; real finger closures alone do not yet produce grasps (2/32). `docs/PHASE1_REAL_DATA.md`.
- **Tests**: `python3 -m pytest tests -q`.

## Not shown (yet)
- No single command runs photo -> object -> profile -> G1 grasp -> outcome.
- Two objects in simulation (egg, stress ball); the can is recognised but not grasped by the simulated G1 hand.
- Head-to-hand tracking: no real head-sensor data yet, camera intrinsics assumed.
- Nothing on the real G1.

## Why it matters
Teleoperation data from gloves is cheap to collect but carries no force. Using vision to supply a per-object grip limit is a small, inspectable layer that makes glove-driven robot hands safer for fragile objects, and it can label Rokoko grasp datasets with the object being held.

## Run it
See the root `README.md` (one command, mock glove stream, no hardware needed).
