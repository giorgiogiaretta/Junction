# One-shot hardware tests (Inspire hand, G1): what is verified, what is NOT, and the procedure
"100 % in simulation" is not achievable for hardware: a simulator cannot prove register maps, joint sign conventions or the real DDS path. What IS verified offline:
- `python -m pytest -q tests/test_preflight.py`: all 56 recorded episodes through the G1 Dex3 retargeter (always inside the filter bounds, <= 0.1 rad/tick, finite, edge inputs incl. NaN) and the Inspire path (ints 0..1000, slew-limited); Inspire live code against a FAKE Modbus server (framing, only registers 1486/1498/1522 written, force/speed set before the first angle). This found a real crash (pymodbus `slave` kwarg), now fixed in robot/inspire.py.
- G1 through the organisers' runner + safety filter (mock backend): `g1/glove_policy.py` + `g1/run_mock_gate.py`: 900 ticks, command rate 30.0 Hz, 0 clipped steps, arms held. Rehearsal found 3 velocity clips at 100 % of the speed cap and 25 Hz with 1 target per call; fixed with 70 % margin and 3-target chunks.
NOT verified (needs a human check on the day): Inspire register addresses/units (from memory of the manual: ANGLE_SET 1486, FORCE_SET 1498, SPEED_SET 1522); Dex3 thumb joint directions (interim, guessed from the limits); the Pinocchio workspace check (no Windows wheel; irrelevant while the arms never move); the real G1 DDS/network path (the organisers' runner does it).
## Inspire hand, single attempt
1. Everything first in dry-run (`robot.run_udp --backend inspire`, prints commands). Power switch in hand reach, nobody near the fingers, no object yet.
2. READ-ONLY first: read ANGLE_ACT/ERROR registers and compare with the manual or a mentor. Garbage or errors => STOP, do not write anything.
3. Low limits: FORCE_SET and SPEED_SET at ~20-30 %. Then slowly open -> 50 % closure -> open with the glove; check the measured angles follow.
4. Only then the empty can. Abort on: any error flag, heat, jitter, fingers not following, anything unexpected. Log every command.
## G1, single attempt (hands only, arms never commanded)
1. A mentor present, e-stop in hand. Start the policy server (`g1/glove_policy.py --source udp:14043`) and the organisers' runner on the real backend with the safety filter ON.
2. First targets = the measured hand_q (no jump). Close each finger a little (10 %) and check the direction on the robot BEFORE the full range: if a direction is wrong, stop and flip the sign in robot/g1_dex3.py. Enforced in code: run with `G1_MAX_CLOSURE=0.1` (or `G1Dex3Retargeter(max_closure=0.1)`) so a full glove fist commands at most 10 % of each joint's range, thumb included; unset it (default 1.0) only after the directions are checked.
3. Then the cube. Abort on any safety stop or clipped step.
