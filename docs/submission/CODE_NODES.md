# F — Ten code nodes, explained simply

Follow one grasp from glove to finger. Each row: file and function, what it does in two lines, why it matters. Tests run offline: `python3 -m pytest tests -q`; numbers: `python3 -m verify.run`.

| # | File · function | What it does | Why it matters |
|---|---|---|---|
| 1 | `Rokoko/src/rgmp_client.py` · `decode`, `run` | Reads the Rokoko stream and turns each glove's finger rotations into five numbers from 0 (open) to 1 (closed), plus wrist pose from the Coil Pro. | Everything starts from human motion; this is the teacher's voice. |
| 2 | `Rokoko/src/episode_quality.py` · `stream_quality` | Measures each recording: rate, gaps, dropouts. | Shows the input is trustworthy: 83 Hz, 0 dropouts over 89 takes. |
| 3 | `g1/finger_map.py` · `DirectRetargeter`, `closures` | Maps human fingers to the robot's three: thumb to thumb, index to index, middle to middle, within joint limits. | The robot hand moves like the operator's hand, not like a single on/off gripper. |
| 4 | `g1/coil_chain.py` · `OneEuro`, `QuatEuro` | Smooths the Coil Pro wrist signal with little delay (197 ms → 20 ms on replay). | Smooth, fast arms are what make teleoperation feel natural. |
| 5 | `ai/perceive.py` · `perceive` | Takes one head RGB-D frame, finds every object on the table, crops each one and asks the recognisers what it is. | One call gives the robot "what" and "where" for every object. |
| 6 | `ai/recognize.py` · `collect` | Asks Nemotron, Gemma/PaliGemma and the colour rule in parallel, each with a deadline; a model that keeps failing is skipped for 30 s. | A dead endpoint can never freeze the robot. |
| 7 | `ai/recognize.py` · `decide` | The fragile-first vote: if a credible model says egg, it is an egg; otherwise the majority. | Mistakes go in the cheap direction (too gentle), not the expensive one (crushed). |
| 8 | `ai/object_profile.py` · `cap_for_votes` | Turns the object into the maximum finger closure; full closure on the ball only if two model families agree, or the operator says so. | No single confident model can unlock force; confidence did not separate right from wrong. |
| 9 | `g1/live_policy_v2_vision.py` · `LivePolicyV` | On the real G1: Coil Pro arms, glove fingers, and a camera label that can only **lower** the operator's hard cap. | The hardware rule is stricter than the simulation rule. |
| 10 | `robot/e2e_g1.py` · `simulate`, `verdict` | Runs the same egg grasp in the G1 MuJoCo simulation with and without the cap, prints held / broken. | The "wow" of the demo: same fist, egg intact vs broken (simulation, assumed thresholds). |

Bonus: `ai/intent_router.py` · `apply_intent` (voice → JSON → safety gate, "stop" never waits for a model); `ai/judge_gemini.py` · `judge_episode` (Gemini labels a recording after the run); `verify/run.py` (recomputes every published number from saved answers, offline).
