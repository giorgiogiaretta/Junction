# Real G1, final runs 15/11 (gloves + Coil, -CoilVision)

Command: `start_g1.ps1 -CoilVision -Fast -LowLag -Both -NoCalib -Video` (05:05 run; 04:42 run the same without `-Video`).
Operator: played with the empty can, both hands; "fairly smooth and fairly precise".
Files (GitHub release `g1-real-20261115`, private repo): annotated video, raw head-camera video, data zip (runner npz,
policy log, Dex3 pressure, raw Coil/glove input).

## Numbers (tools/g1_windows_runner/lag_report.py, docs/ARM_DELAY.md)

| run | length | runner loop | clipped by the runner | arm lag (onset) | median arm error |
|---|---|---|---|---|---|
| 14-15/11 before the fix (7 runs) | 71-247 s | 18-30 Hz, p95 47-94 ms | 0-1 | 0.6-1.3 s, staircase | 0.05-0.14 rad |
| 04:42 (LowLag) | 94 s | 30 Hz, p95 47 ms | 0 | 0.38 s, smooth | 0.069 rad |
| 05:05 (LowLag + video) | 144 s | 30 Hz, p95 47 ms | 0 | 0.45 s, smooth | 0.070 rad |

- No runner safety stop, no clipped step, watchdog never triggered (`mode` = ok on every tick).
- 24 % of ticks were "hold" ticks: the policy answered late (vision + IK in one process), the arm held its target.
- Policy-side blocks 14.7 % of ticks (05:05): 11.6 % `ws_scaled` (target pulled back inside the runner's workspace box),
  the rest robot self-collision, mostly the two hands touching each other. 04:42: 24 %, mostly elbow-torso.

## Computer vision: what it really recognised (video `g1_real_cv_20261115_0505.mp4`)

Every label in the annotated video is the policy's own log (CANDIDATES / TARGET events), projected with the organisers'
PROVISIONAL head extrinsics. Honest reading:
- First detection after 2.3 s (`ai.perceive+geometry`): right object labelled **egg**, left object **unknown**.
- Later detections labelled a **can_empty** with cap 0.90, but its position matches the robot's LEFT HAND, not the can;
  the object near the real can was labelled **egg** (cap 0.60). The right hand's target was the command-line
  `stress_ball` placed at the camera's "egg" position (cap 0.60).
- So in this run the camera did **not** reliably recognise the can: the most likely cause is the robot's own hands
  leaking through the self-mask (provisional extrinsics), plus the white Dex3 hand read as "egg".
  The error was on the safe side (egg cap 0.60 on the can), so the fingers were never allowed more force than intended.
- The phantom-egg filter (> 15 cm above the table) did not trigger here: these labels were at table height.

## Dex3 fingertip pressure (g1/dex3_press.py, first real use)

- 9 pads per hand, ~45 Hz in the policy; at rest noise ~10 Pa. Hand-pressed test (04:53): only pads 1, 3, 5 respond
  (7-30 kPa).
- With the can (05:05): small readings, left pad 6 up to 8.8 kPa (above 1 kPa for 16 % of the run), right pad 5 up to
  4.7 kPa; occasional negative spikes on pad 0 (sensor glitches, ignored). The empty can is light and soft: the
  contact mostly misses the sensing cells. The egg limiter (5 kPa) never triggered (no egg targeted at contact).

## Not done / next

- Vision on the real robot needs a fixed head extrinsic calibration and a better self-mask before its labels can be trusted.
- Policy latency (24 % hold ticks) is the next delay source, now that the runner side is fixed.
