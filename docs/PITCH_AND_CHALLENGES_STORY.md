# The Golden Thread — one story, not a pile of challenges

Status legend used below: **[built]** works in the repo today, **[planned]** in `docs/PLAN.md` but not yet built. The pitch only claims what is [built] by demo time; everything else is told as the next step.

## The one-line pitch

> Rokoko gloves can teach any robot hand how humans move — but they can't feel. We add the missing sense (a vision-chosen force cushion), and turn every human correction into training data so one operator can supervise many robots.

## The thesis: "Tactile-Less HandOff"

Robotics companies are spending billions to collect human manipulation data. Two walls block them:

1. **The gloves cannot feel.** Smartgloves capture motion, not touch or force. An operator who closes their fist crushes an egg.
2. **The operator-to-robot ratio is stuck at 1:1.** A person has to drive the robot the whole time, so data and deployment don't scale.

Our system removes both walls with one pipeline.

## The pipeline (four beats, one flow)

| Beat | What happens | Challenge it naturally carries | Status |
|---|---|---|---|
| 1. **Teleop** | Rokoko Smartgloves II (+ Coil Pro for wrist position) drive a dexterous hand; dashboard shows latency p50/p95 | Rokoko (core) | glove ingest, retarget, sim hand, dashboard [built]; wrist from Coil Pro, egg scene [planned 1.3-1.5] |
| 2. **Vision-guided Force Cushion** | Before the grasp, a vision-language model looks at the scene ("egg", "cup", "block") and sets the force/closure profile; the operator can close the fist fully and the robot still holds the egg | NVIDIA Nemotron 3.5 Super VL | profile-based assist [built, `ml/grasp_assist.py`]; Nemotron picker [planned, phase 3] |
| 3. **Record and judge** | Every session becomes an episode; a judge model labels success/failure, segments phases and drops dirty demos; success rate is measured before and after | Nemotron + Gemini (second judge), Gemma (optional local helper) | recorder, judge [planned, phases 2-3] |
| 4. **HandOff flywheel** | The robot runs a learned policy alone; when it hits an edge case the operator presses the physical button on the Smartglove II, corrects for ~5 s, and that correction goes back into the dataset | Rokoko (policy + teleop); measured intervention rate | policy, hand-off switch [planned, phase 3] |

The thread: **motion in (Rokoko) -> safe grasp (vision sets the force) -> data out (judged) -> autonomy (human steps in only when needed).** Each beat feeds the next, and each challenge sponsor owns exactly one beat instead of being bolted on.

## Where each challenge fits (and what we will honestly claim)

| Challenge | Role in the story | Claim only if true at demo time |
|---|---|---|
| **Rokoko** (main) | Gloves + Coil Pro are the input of every beat | Live teleop with measured latency |
| **NVIDIA Nemotron 3.5 Super VL** | Beat 2 (profile picker before the grasp) and beat 3 (episode judge). Slow brain: never in the control loop | Agreement vs ~30 human-labelled episodes, before/after prompt iteration (a number) |
| **Google Gemini API** | Second backend of the episode judge; Nemotron-vs-Gemini comparison table | Comparison table exists |
| **Google Gemma** | Hands-free commands ("record", "stop", "next object") so the operator never lets go of the gloves | Only if something really runs locally; otherwise drop this claim |
| **Entire / CRACI** | Process story: a human + AI-agent team on GitHub, every build scanned | Repo connected, CI green |
| **Jetson, ElevenLabs, others** | Not part of the thread; bonus only if time remains | — |

Rule: a challenge enters the story only when the previous beat is green and its sponsor appears visibly in the demo.

## The demo (3 minutes)

1. **Problem (20 s):** "Gloves can't feel. One operator per robot."
2. **Teleop (30 s):** glove on, hand follows; dashboard shows latency p50/p95 and connection state.
3. **The egg (40 s):** full fist without the cushion -> `broken=True`; same fist with the Force Cushion -> egg lifted intact; the force bar on the dashboard shows why.
4. **Record and judge (30 s):** the demo just performed appears as an episode with an automatic verdict.
5. **HandOff (40 s):** robot runs alone; we nudge the object; press the glove button, correct, release.
6. **The number (20 s):** intervention rate before vs after retraining.

Fallbacks (always recorded on video): mock stream instead of gloves, MuJoCo instead of the Inspire hand, profile default if the API is down.

## Business model (one slide)

Teleoperation + data-quality service for teams training robot policies: pay per curated demo-hour plus a subscription for the supervision tool. Moat = judged, success-labelled episodes and a falling intervention rate per customer. Same market as the startups in Rokoko's list (teleoperation and data companies).

## What we say when asked "why this mix?"

Because it is one product: Rokoko gives us hands, vision gives them a sense of how hard to squeeze, the judge makes the data trustworthy, and the hand-off button turns a teleoperation job into supervision. Remove any beat and the next one stops working.
