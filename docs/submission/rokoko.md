# Rokoko — The Robot Teleoperation Challenge (main entry)

**One line:** Rokoko Smartgloves are the teacher; a head camera adds the one sense gloves do not have, how hard to squeeze.

## The problem
Teleoperation is the fastest way to teach a humanoid, for repetitive work (pick, place, sort) and delicate work (eggs, fruit). Smartgloves II capture finger motion and the Coil Pro gives precise wrist position, but there is no force sensing. A confident human fist becomes a crushed egg on a robot hand. Rokoko's judges asked for exactly this: precise manipulation of fragile objects and demonstration data for robot policies.

## Rokoko at the centre
```
Smartgloves II (fingers) ─┐                        ┌─▶ Dex3 fingers (thumb→thumb, index→index, middle→middle)
Coil Pro (wrist pose) ────┼─▶ rgmp_client (83 Hz) ─┼─▶ G1 arms (IK / glove open-close motions)
glove on the head ────────┘                        └─▶ recorded episodes (training data)
                                    camera vote ──▶ closure cap ──▶ limits the fingers
```

1. **Capture.** `Rokoko/src/rgmp_client.py` decodes the Rokoko stream and publishes normalised finger closures and wrist pose (`hand_state v1`, UDP). Raw streams can be recorded and replayed (`Rokoko/src/replay_rgmp.py`).
2. **Quality we measured.** 89 takes, glove stream at 83 Hz, 0 dropouts, max gap 12 ms (`Rokoko/src/episode_quality.py`, glove clock).
3. **On the real Unitree G1** (organisers' runner and safety filter): the gloves drove both arms and both Dex3 hands. Open glove = arm up; closed = arm down, then fingers close; open again = release. **2 runs of 120 s, 29.8 commands per second, 0 commands clipped** (`g1/arms_simple.py`, `tools/g1_windows_runner/README.md`). Later versions: `g1/arms_glove.py` (both hands), `g1/live_policy_v2.py` (Coil Pro wrist teleoperation, both hands, seated calibration), one command `start_g1.ps1`.
4. **Each finger follows its own glove finger** (`g1/finger_map.py`): the Dex3 has three fingers, so thumb, index and middle map one to one.
5. **Smoother Coil teleoperation** (`g1/coil_chain.py`): on replayed takes, filter delay went from 197 ms to 20 ms (`docs/G1_V2_RUN.md`).
6. **The missing sense.** A head camera and a two-family model vote set a per-object closure cap. In our G1 simulation, same egg, same glove grip: **held intact with the cap, broken without it** (`python3 -m robot.e2e_g1 --label egg`).
7. **Demonstrations become data.** Recorded glove takes carry the object, the outcome (ok / dropped / crushed) and the head-to-hand pose. A nearest-neighbour policy learned from 10 glove takes reproduced a square pick-and-place path in simulation; with scripted grip and final homing it placed 37 of 40 legs (PR #142, `ml/square_policy.py`).

## Proven / not proven
| Proven | Not proven |
|---|---|
| Glove-driven arms and hands on the real G1, 0 safety clips | Vision-guided grasp on the real G1 (camera path ran there only as a capture test) |
| Glove stream quality (83 Hz, 0 dropouts) | Real finger closures producing grasps in the older five-finger simulation (2/32) |
| Cap vs no cap decides egg intact / broken in simulation | Real force: break thresholds and gains are assumed |
| Recognition on our 50 photos (see `nvidia.md`, `gemma.md`) | Generalisation to other people, places and objects |

## Criteria map
Technical execution (35 %) → real G1 runs through the official safety filter, measured stream quality, simulation end to end. Originality (25 %) → vision as a replacement for missing touch, fragile-first across two model families. Usefulness (25 %) → safer demonstrations of delicate work plus automatic object labels for training data. Human-controlled robotics (15 %) → the operator just moves; the robot follows on real hardware.
