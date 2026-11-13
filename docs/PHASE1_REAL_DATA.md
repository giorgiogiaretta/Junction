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
