# G1 Dex3 grasp physics: first results (MuJoCo, right hand, simulated)

Command: `py -3.11 g1/sim/grasp_physics.py --levels 0,0.2,0.3,0.4,0.5,0.55,0.6,0.65,0.7,0.75,0.8,0.9,1.0 --render`
Output: `data/g1sim/grasp/report_kp1.5.json` + PNG (not committed). Setup and assumptions: docstring of `g1/sim/grasp_physics.py`.

The robot base is fixed. The forearm points forward and the palm faces the body midline, so the fingers close sideways.
Commands come from `robot.g1_dex3.G1Dex3Retargeter` (unchanged, thumb_0 pinned), at 30 Hz with its slew limit. The hand servos use kp 1.5 and kv 0.1 (assumed), with the URDF torque limits.
"Held" means the object moves less than 1.5 cm after the pedestal under it is removed.

| Object (model) | First contact | Minimum closure that holds | Break (assumed threshold) | Recommended max closure |
|---|---|---|---|---|
| Egg: ellipsoid 42x56 mm, 60 g | 0.55 | 0.65 (8 N) | 0.75 (> 20 N peak) | **0.70** (14 N) |
| Stress ball: sphere 66 mm, 30 g, soft contact | 0.40 | 0.50 (5 N) | none | **0.60** (19 N) |
| Can: cylinder 66x116 mm, 15 g empty | 0.20 | never held | 0.50 (> 15 N peak) | **not supported in this posture** |

The kp sensitivity check (0.75 / 1.5 / 3.0) ran on an earlier placement. In that run the egg's hold and break closures moved by only about 0.05 across gains: the closure where contact starts depends on the object's size more than on the servo gain.

## What it means
- **Egg:** the safe window is narrow. It holds from 0.65 and breaks above 0.75. A glove that closes "a bit too much" crushes the egg, so a per-object closure cap is needed. A cap of 0.70 keeps the egg held and intact.
- **Stress ball:** the window is wide. It holds from 0.50 and has nothing to break.
- **Can:** with a sideways three-finger pinch, the rigid 66 mm can is squeezed out of the hand instead of being held. It needs another posture, with the palm under it or the hand from above, or the thumb rotation (thumb_0), which is not commanded today. Do not demo the can with this grasp.

## Not verified / to replace with measurements
- The servo gains of the real Dex3. The break thresholds: egg 20 N and empty can 15 N are guesses. Measure them with a kitchen scale (press until it cracks or dents). Friction 1.0. The ball is not really deformable (soft contact only).
- Forces are model outputs, not measurements. Only the closure levels (contact, hold, cap) are expected to transfer, and only roughly.
- The real object sizes. Measure our egg, ball and can and update `OBJECTS`.
