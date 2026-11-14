# Aaltonomous Humanoid (G1): draft / position

**Decision (`docs/ORCH_BACKLOG.md` section 5): not entered as a separate track.** We use the Aalto G1 as the **body** of the Rokoko project.

## Real G1 (14/11), documented on branch `g1-real-working` (not on `main` yet)
- The organisers' runner runs on a Windows PC against the real G1 (`tools/g1_windows_runner/README.md`).
- `g1/arms_simple.py`: Rokoko gloves drive **both arms and both Dex3 hands**: glove open -> arm up; glove closed -> arm goes down about 11 cm, then fingers close; open again -> release. **2 runs of 120 s, 29.8 commands/s, 0 commands clipped by the safety filter.**
- `g1/live_policy.py` (arms still, right hand follows the glove): run on the robot ("works" in the branch README).
- Lessons on the real robot: rest pose with wrists inside the counter keep-out (first move must go up); resting left fingers past the URDF limits (every target clamped).
- **Not shown**: the head camera computer was off all session, so **no vision on the real robot**; no object grasp outcome recorded.

## Simulation and rehearsal (on `main`)
- V1 without Coil (`g1/live_policy_v1.py`, `docs/G1_V1_RUN.md`): camera finds the objects once (`ai.perceive`), hover -> descend -> capped grasp -> lift. Simulated frames: labels egg 24/24, can 23/24, position error median 0.2/0.4 cm; mock runner 29-30 Hz, 0 clipped.
- V2 with Coil (`g1/live_policy_v2.py`, `docs/G1_V2_RUN.md`): filter delay 197 -> 20 ms on replay; mock 29 Hz.
- Operator console `tools/console/app.py`: pre-flight checks, glove and robot views, closure slider, STOP.
- End to end in MuJoCo: `python3 -m robot.e2e_g1 --label egg` (egg with cap intact, without cap broken).
