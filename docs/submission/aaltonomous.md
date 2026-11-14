# Aaltonomous Humanoid (G1): draft / position

**Decision (`docs/ORCH_BACKLOG.md` section 5): not entered as a separate track.** Our glove data does not transfer to that task (`docs/AALTONOMOUS_FEASIBILITY.md`). We use the Aalto G1 as the **body** of the Rokoko project.

## What we use from it
- Their interface: Dex3 joint names and limits (`docs/g1_dex3_limits.json`), websocket policy server at 30 Hz, mock runner.
- `g1/live_policy.py`: arms still in the measured pose; right Dex3 hand follows the glove, capped per object from the head camera.

## Measured
- Mock runner of the organisers: about 30 Hz, 0 clipped steps (egg take 77 and stress-ball take 82), `docs/G1_LIVE.md`.
- Simulation: G1 Dex3 grasp in MuJoCo, egg with cap held intact / without cap broken, `python3 -m robot.e2e_g1 --label egg`.

## Not shown
No real-G1 result recorded; the first test runs at 10% closure (`G1_MAX_CLOSURE=0.1`). Thumb direction, motor zero and camera latency never tested on the robot.
