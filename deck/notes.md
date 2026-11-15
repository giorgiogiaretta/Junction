# Deck speaker notes

Twelve slides. **Core** is the three-minute route: budget roughly fifteen seconds per slide. **Core + Detail** is the full twenty-to-twenty-five-second note, about four to five minutes overall. These are rehearsal targets, not measured delivery times. Do not read source paths aloud.

## 1 — Human motion. Object-aware grip limits.

**Core:** Rokoko gloves give us human motion. Our project adds object-aware closure limits: vision identifies what the hand is about to hold. We have real robot teleoperation evidence and a separate simulated grasp path.

**Detail:** Those are distinct results. We have not demonstrated vision-guided object grasping on the physical robot. The rest of this pitch keeps that boundary visible.

Sources: `docs/ARCHITECTURE.md`, `docs/SCORECARD.md`, `tools/g1_windows_runner/README.md`.

## 2 — Gloves cannot feel the object

**Core:** The gloves report motion, but they cannot feel an egg. A recognition error can therefore select the wrong grip policy. We constrain finger closure according to the object and stay conservative when the models disagree.

**Detail:** This is a software limit, not measured contact force. The cap and break thresholds remain toy assumptions tuned in simulation, so they require physical calibration before any hardware protection claim.

Sources: `docs/ORCH_BACKLOG.md`, `docs/STORY_MODELS.md`, `docs/SCORECARD.md`.

## 3 — The gloves drove the real G1

**Core:** Giorgio drove both arms and both Dex3 hands on the real G1 with the gloves: two runs of one hundred and twenty seconds, twenty-nine point eight hertz, and zero commands clipped by the safety filter.

**Detail:** The camera computer was off. There was no vision and no demonstrated object grasp. The box is a video placeholder, not evidence of a clip already attached or a grasp result.

Sources: `tools/g1_windows_runner/README.md`, `docs/G1_GUIDE.md`, `docs/G1_LIVE.md`.

## 4 — Motion and perception meet at the cap

**Core:** The operator supplies motion. Perception proposes an object label, and the policy turns that into a closure cap. Simulation lets us inspect held and broken outcomes before trying the full chain on hardware.

**Detail:** There are several code paths. The simple simulation bridge accepts a label or a single recogniser. Its existence must not be presented as a verified live ensemble-to-robot grasp demonstration.

Sources: `docs/ARCHITECTURE.md`, `docs/CODE_TOUR.md`.

## 5 — Fast eyes, a second key, a slow judge

**Core:** Nemotron is our real-time pre-grasp eyes. The Gemma family supplies a second opinion: PaliGemma runs on our remote GPU, while Gemma four was tested through Google’s API. Gemini judges recorded episodes asynchronously, outside motion control.

**Detail:** The current two-key gate counts distinct model families. Gemma and PaliGemma count as one key. Self-hosting still needs connectivity. Nemotron is not our only fast recogniser.

Sources: `docs/STORY_MODELS.md`, `docs/OBJECT_RECOGNITION_RESULTS.md`, `docs/SCORECARD.md`, `docs/VERDA_GEMMA.md`, `ai/recognize.py`.

## 6 — The measured recognition results

**Core:** On the same fifty labelled photos, Nemotron scored forty-eight, Gemma four forty-nine, and PaliGemma forty-nine. Nemotron reproduced its score in two runs. The errors matter: Nemotron called eggs balls, and PaliGemma called an egg a can.

**Detail:** These photos come from one person, one place and one day. The originals are outside git. Multiple prompts were tried on the same set, and there is no held-out generalisation result.

Sources: `docs/OBJECT_RECOGNITION_RESULTS.md`, `docs/evidence/recognition/README.md`.

## 7 — Confidence does not separate right from wrong

**Core:** Confidence does not separate right from wrong here: wrong answers and correct ones both scored point nine. Full ball closure needs agreeing model families plus a confidence gate, or explicit operator selection. Eligible egg votes take priority.

**Detail:** Otherwise the shared egg and ball cap is point seven. These are toy thresholds. The egg preference has a confidence condition, and agreement cannot guarantee correctness or physical safety.

Sources: `docs/OBJECT_RECOGNITION_RESULTS.md`, `docs/CODE_TOUR.md`, `docs/SCORECARD.md`.

## 8 — Agreement caught the observed errors

**Core:** Nemotron and API Gemma agreed on forty-seven of fifty labelled photos. Their three disagreements flagged single-model errors. Fragile-first voting scored fifty out of fifty from the saved answers, including the later three-recogniser combination.

**Detail:** That combination adds PaliGemma, not Gemini. Gemini remains the episode judge. These are offline computations on the same photos, without a held-out set or evidence of a live robot grasp.

Sources: `docs/OBJECT_RECOGNITION_RESULTS.md`, `docs/STORY_MODELS.md`, `docs/CODE_TOUR.md`.

## 9 — The cap changes the simulated outcome

**Core:** The documented simulation holds the egg intact with the cap and breaks it without the cap. Sharing the egg and ball cap also handles the observed mistake of calling an egg a ball in that simulation.

**Detail:** The command shown bypasses recognition and requires local assets. The physics and break thresholds are toy assumptions. Can holding remains unsupported in the shared profile, and none of these outcomes establishes a physical grasp.

Sources: `docs/SCORECARD.md`, `docs/CODE_TOUR.md`, `docs/OBJECT_RECOGNITION_RESULTS.md`.

## 10 — Grasp Advisor for unfamiliar objects

**Core:** The experimental Grasp Advisor proposes fragility, mass, size and handling advice for an unfamiliar object. It can lower the cap or ask for confirmation, but it never unlocks full closure. Model estimates are not measurements.

**Detail:** The first look covers three photos, with an additional complex scene falling back after malformed output. That is not an evaluation. General object manipulation, learned imitation and peeling remain outside the demonstrated result.

Sources: `docs/ADVISOR.md`.

## 11 — What we need to test next

**Core:** The next evidence should come from new photos with frozen prompts, weighed objects for the Advisor, and physical grasp evaluation. The hardware work needs verified camera frames and calibration, coordinated with the robot owner and staff.

**Detail:** These are proposed experiments, not completed results. We still need to measure physical damage reduction and whether the resulting demonstrations improve robot learning. The teleoperation result gives us a starting point.

Sources: `docs/SCORECARD.md`, `docs/ADVISOR.md`, `docs/G1_GUIDE.md`.

## 12 — What is proven / not proven

**Core:** We have documented real G1 teleoperation, small-set recognition evidence and simulated grasp limits. We have not demonstrated vision-assisted physical grasping, generalisation or real force calibration. The Advisor and slow judge still need quality evaluation.

**Detail:** The scorecard predates Giorgio’s hardware report. That report updates teleoperation only. It does not establish physical object handling or remove the scorecard’s remaining boundaries. Our claim is progress with explicit evidence, not a completed autonomous manipulation system.

Sources: `docs/SCORECARD.md`, `docs/CODE_TOUR.md`, `docs/ADVISOR.md`, `tools/g1_windows_runner/README.md`.
