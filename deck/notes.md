# Speaker notes — Tactile-Less HandOff

Each full note is intended for 20–25 seconds at a measured speaking pace. Ten full notes take approximately 3½–4 minutes. For a strict three-minute pitch, deliver the **Core** paragraphs only, targeting 18 seconds per slide; use **Extra** for rehearsal or questions. Timing is a rehearsal target, not a measured result.

## 1 — Motion from gloves. Grip limits from vision.
**Core:** We are building Tactile-Less HandOff. Rokoko gloves provide human motion, and a head camera identifies the object. That label selects a closure limit for a simulated robot hand. Our prototype explores object-aware grasping in MuJoCo.

**Extra:** Today’s evidence is simulation and a small recognition experiment, with hardware validation still ahead.

Sources: `README.md`; `docs/PITCH_AND_CHALLENGES_STORY.md`; `AGENTS.md`.

## 2 — Gloves cannot feel
**Core:** Smartgloves capture movement but have no force sensors. An operator can close confidently while the robot crushes a fragile object. Our simulation illustrates that gap. For robot-learning teams, the opportunity is more useful demonstrations with less dependence on careful manual gripping.

**Extra:** Data scarcity is our motivation; we have not measured market demand or a reduction in collection effort.

Sources: `docs/submission/rokoko.md`; `docs/PITCH_AND_CHALLENGES_STORY.md`; `g1/sim/GRASP_REPORT.md`.

## 3 — See the object before closing
**Core:** The idea is to use the head camera to choose grasp behaviour before closing. A Rokoko sensor on the head would locate the hand relative to the camera, helping focus recognition. Real head-to-hand tracking is a next step, not demonstrated evidence.

**Extra:** Camera intrinsics are assumed, and the crop has not been validated on real frames.

Sources: `docs/ARCHITECTURE.md`; `docs/ORCH_BACKLOG.md` §1, B7–B8.

## 4 — An inspectable control path
**Core:** Gloves and Coil provide motion for retargeting. Camera recognition supplies object context. Nemotron and colour have evaluation results; Gemini is an unverified live backup, and Gemma is planned. A proposed fragile-first vote feeds closure rules before commands reach the simulated Dex3 hand.

**Extra:** Agreement checks exist in the cap policy; a complete live ensemble is not proven.

Sources: `docs/ARCHITECTURE.md`; `docs/OBJECT_RECOGNITION_RESULTS.md`; `docs/submission/google.md`; `ai/object_profile.py`; `robot/e2e_g1.py`.

## 5 — Same egg. A closure limit changes the outcome.
**Core:** This is the supplied G1 Dex3 simulation comparison. With the cap, the egg is held intact; without it, the toy model marks it broken. The command shown supplies the egg label directly, so this demonstration does not test recognition.

**Extra:** The image’s force annotations are model outputs, not physical measurements. Gains and break thresholds are assumed.

Sources: `docs/media/g1_egg_cap_vs_nocap.jpg`; `g1/sim/GRASP_REPORT.md`; `robot/e2e_g1.py`. Command: `python -m robot.e2e_g1 --label egg`. Execution requires dependencies and local G1 assets; the still is repository evidence, not a new run by the deck author.

## 6 — 48 of 50, in one run
**Core:** Nemotron recognised forty-eight of fifty of our photos in one run. Both mistakes were eggs called stress balls, exactly the dangerous direction. The colour baseline got thirty-eight right. These are small, local experiments from one person, one place and one day.

**Extra:** The photos are not in git, and the endpoint stopped responding after the run.

Source: `docs/OBJECT_RECOGNITION_RESULTS.md`. Every table count comes from that file. `docs/CV_RESULTS.md` is a separate YOLO-World baseline, not an updated Nemotron run, and does not supersede this table.

## 7 — Design around the dangerous mistake
**Core:** Egg and ball share a closure cap of zero point seven in the simulation policy. Full ball closure requires operator confirmation or agreement and confidence checks. Unknown objects get a conservative fallback. The first real G1 trial is planned at ten percent closure.

**Extra:** These thresholds are hand-picked toy rules, not calibrated hardware safety guarantees.

Sources: `ai/object_profile.py` (`cap_for_votes`, `cap_for`); `docs/OBJECT_RECOGNITION_RESULTS.md` colour section; `docs/G1_LIVE.md`; `docs/ORCH_BACKLOG.md` §1/B13. Full closure means closure command, not a measured force. Current rule: confidence at least 0.9 plus at least two recognisers, or manual selection. This does not prove that two recognisers are independent or that agreement is safe.

## 8 — Proven here / still to prove
**Core:** We have recognition results on our photos, simulated grasp evidence, and a label-to-simulation bridge. We have not demonstrated generalisation, a verified live photo-to-grasp chain, real head tracking, or real G1 grasp performance. The can is recognised but not held in this posture.

**Extra:** We keep those boundaries visible so the next experiments test the missing links directly.

Sources: `docs/ORCH_BACKLOG.md` §1; `robot/e2e_g1.py`; `g1/sim/GRASP_REPORT.md`. The bridge code is newer than the backlog’s statement that no end-to-end command exists. Its presence does not prove a live vision run.

## 9 — Better demonstrations for robot-learning teams
**Core:** Our proposed customer is a team training robot manipulation policies. We would offer teleoperation support and data-quality tooling, charging for curated demonstration hours and a supervision subscription. The next business test is whether object-aware limits improve the demonstrations those teams can actually use.

**Extra:** This is a business hypothesis; we are not claiming customers, revenue, or measured learning gains.

Source: `docs/PITCH_AND_CHALLENGES_STORY.md`, business model and planned record/judge workflow.

## 10 — Validate the grasp. Then collect better data.
**Core:** Giorgio’s side covers capture, learning, vision and G1 simulation; Tommaso’s covers robot integration, AI and the demo. Next we validate real camera frames, calibrate object limits, and pass the mock gate before a supervised hardware trial. Our goal is human motion with object-aware grasp limits.

**Extra:** Better demonstrations are the next outcome to measure, not an improvement we have already established.

Sources: `AGENTS.md`; `docs/ARCHITECTURE.md` folder boundaries; `docs/ORCH_BACKLOG.md` B7–B9/B13.
