# Phase 1 integration: real takes in the MuJoCo scene

Tool: `python -m robot.play_real_data data/raw/take_NN.rgmp --obj cube|egg [--polarity auto|client|inverted] [--fingers real|synthetic] [--assist egg]`
Input: Series A (11 takes, right glove used, Coil Pro present, 83.5 Hz). Decoding reuses `Rokoko/src/analyze_takes.parse`. Files are `.rgmp` (raw stream); `takes.jsonl` is only the metadata.

## Method (and its limits)
- Fingers: per-take, per-finger 5-95 percentile normalisation of the finger-sensor rotation angle -> closure 0..1.
- Wrist: Coil Pro `arm_sensor` position (coil frame, assumed z-up, metres) relative to the **pick point** = lowest wrist height in the middle of the take. The cube is placed under the hand at that moment. So **the approach is not tested** (the object position is not recorded), only what happens from the pick on.
- Wrist target is clipped to the sim workspace (z 0.05-0.4 m, x/y +-0.4 m): real lifts of 0.25-0.62 m are truncated.

## Results (cube, 11 takes)
| Mode | Touched | Lifted + held | Reading |
|---|---|---|---|
| real fingers, polarity `client` (bigger angle = closed, as `rgmp_client`) | 5/11, peak 0.4-1.5 N | **0/11** | hand is ~open at the pick (closure 0.0-0.2) |
| real fingers, polarity `inverted` | 6/11, peak 0.1-0.6 N | **0/11** | hand is ~closed from the approach to the pick (closure 0.8-0.98) |
| real wrist path + scripted grip (`--fingers synthetic`) | 11/11, peak 2.4-5.8 N | **7/11** (held 2.3-4.6 s); not lifted: takes 02, 06, 08 | wrist trajectory is compatible with holding the cube in most takes; failures are lateral drift during the grip ramp (not analysed further) |

## Conclusions
1. With the finger angles as currently normalised, **real data does not produce a grasp in the sim**, under either polarity. We cannot yet say which is right: closure at the pick is ~0 (client) or ~0.9-0.98 (inverted), neither looks like "open hand approaches, closes, lifts".
2. The real wrist path (Coil Pro) is usable: replayed with a scripted grip it lifts and holds the cube in 7/11 takes.
3. `rgmp_client.py` assumes larger angle = closed, and the open/close sweep cannot tell the sign. The takes' timelines (fingers move from ~1.0 rad at rest to ~0.5 rad while holding) suggest it may be inverted, but this is an inference, not proof.

## What is needed to close it
- A 10 s labelled recording: **5 s flat open hand, 5 s tight fist** (per glove). That fixes polarity and normalisation without guessing.
- An object position per take (e.g. a mark at a known coil-frame point) so the approach can be tested too.
- Real latency is not measured here: sim step time only.

## Update: all 37 episodes (`python -m robot.replay data/episodes/take_NN.npz`, PLAN 2.3)
Same method on Giorgio's 30 Hz episodes (series A rigid, B fragile, C hand-off, D noise). Cube, wrist = real Coil Pro:
| Fingers | Touched | Lifted (A / B / C / D) |
|---|---|---|
| as recorded (`fingers01`) | 31/37 | 0 / 0 / 0 / 0 |
| inverted (`--invert`) | 23/37 | 0 / 0 / 0 / 0 |
| scripted grip | 35/37 | 8/11 / 9/11 / 9/10 / 1/5 |

Egg, series B (11 takes), real wrist + scripted grip: **no cushion: broken 10/11; with `--assist egg`: broken 1/11, lifted 8/11.** Toy-calibrated threshold (3 N) and scripted grip, so this shows the Force Cushion works on realistic wrist motion, not that the real fingers do.
Series D (noise) is not a grasp task; ignore its numbers. Still blocked on finger polarity (record series E: 5 s open hand + 5 s fist per glove). `data/calib.json` {"invert": bool} is applied automatically by `robot.replay` once it exists.

## Update: calibrated fingers (series E, `data/calib.json`, episodes rebuilt 5557d59)
`python -m robot.replay_all` (cube: pick x fingers on all A-D; egg: series B). Calibration sign is +1 on every finger, so `rgmp_client` polarity was right. Mean index..little closure peak per take (fist = 1): **A box 0.32, B can 0.41, C can 0.58** (D 0.78). The thumb is excluded (calibrated span only 0.3-0.6 rad).

What the calibrated timelines show:
- **Series A (empty box): the fingers stay open (~0) through the whole hold.** It is a flat-hand/palm hold, not a finger grasp, so a 5-finger closure replay of A on a small cube cannot work by design.
- **Series C (can): a clear grip, 0.7-0.9 on index..little, at mid height, NOT at the lowest wrist point.** The old pick rule (lowest wrist) misses the grasp.

New options: `--pick closure` (grasp moment = onset of the strongest grip in the middle 60% of the take, half-peak over the 2 s before it, smoothed 0.3 s) and `--fingers gain` (per take, strongest grip -> fully closed, since a can/box grip is only 0.3-0.6 of a fist and the sim cube is a different size).

| Cube, real wrist | A | B | C | D |
|---|---|---|---|---|
| real fingers, pick wrist | 0/11 | 0/11 | 0/10 | 0/5 |
| real fingers, pick closure | 0/11 | 0/11 | 0/10 | 0/5 |
| gain fingers, pick closure | 1/11 | 1/11 | 0/10 | 0/5 |
| gain fingers, pick wrist | 0/11 | 0/11 | 0/10 | 2/5 |
| scripted grip, pick wrist | 8/11 | 9/11 | 9/10 | 1/5 |
| scripted grip, pick closure | 1/11 | 0/11 | 3/10 | 0/5 |

Egg, series B, gain fingers + pick closure: broken 4/11 with or without `--assist egg`. Scripted grip + pick wrist: 10/11 -> 1/11 with the cushion (unchanged).

Erratum: a first version of `--pick closure` (no mid-window) reported 8/32 cube lifts and "cushion fails on real grips, 7/11 broken". Both were artifacts: in series B the hand starts half-closed, so the grip onset fired at t~0.1 s, the object was placed there and the wrist then went 13-39 cm BELOW it, crushing the egg against the table (an open hand broke it too). It was not a finger or cushion effect.

Wrist floor check (`--floor`: the wrist never goes below the grasp height; `replay_all` now also reports breaks at/before the pick). Per-break contact logging showed the remaining 4/11 egg breaks are also not grip breaks: 3 happen at or before the pick, with the hand pushing the egg into the pedestal (pedestal contact 3.3-3.7 N, one palm hit at t=0.02 s). Egg B, gain fingers + pick closure: **no cushion 4/11 broken -> 1/11 with the floor; with the cushion 4/11 -> 2/11** (1 still pre-pick). No lifts with the floor (0/11), so the real grips neither crush nor hold the egg here. A sweep of feedback-mode cushion settings (contact force fed back, scale 3-10 N, back_off 0.15-0.3) and a contact-triggered closure slew limit (0.2-0.5 /s) changed nothing or made it worse (4 -> 6/11), as expected when the force comes from the wrist and not the fingers. Cube lifts unchanged by the floor. The cushion stays as it is; there is nothing to retune until real grips reach the egg.

Conclusions:
1. Calibrated real fingers still do not produce grasps in the sim (2/32). Grip timing and wrist height do not line up with "object on the table under the hand": in the real takes the grip happens at mid height and the hand later goes lower. Without the object position (obj_pos) the pick point is a guess, so this is not evidence against the fingers.
2. The Force Cushion result stands only for the scripted grip; on real grips it is untested until the pick point is right.
3. Series A should not be used to train finger closure (palm hold); keep it for wrist/approach only.
4. What unblocks it: obj_pos per series (coil-frame point of the object), or a take where the object starts on the table at a marked spot.

## Series H (square, known geometry): replay ready, no takes yet
`python -m robot.replay_square data/episodes/take_NN.npz --fingers gain|events` maps the Coil-frame wrist into the table frame from `data/square_calib.json` (origin = square centre, x right, y away from the operator, z up), puts a 66x115 mm can at BL and scores each leg BL->TL->TR->BR->BL on its own (can reset upright at the leg start; success = can within 6 cm of the target corner after the release, and lifted). Tested on a synthetic take in a rotated + offset Coil frame (`tests/test_square_replay.py`): with the clean grip (`events`, closure 0.6) 4/4 legs, error < 2 cm. Limits: the sim hand grips from above with a horizontal palm (the human grips the can from the side), the sim can weighs 100 g (a 15 g can is toppled by the toy fingers), and the wrist height at the corners is mapped to the sim grasp height (the wrist-to-palm offset is unknown). A full squeeze (closure 1.0) tips the can at release on the synthetic take, so expect `--fingers gain` to score worse than `events`: that gap is the measure of the real grip, not of the wrist path.
