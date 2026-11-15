# Story and the numbers we may say (single source for every text, video and slide)

Language: English. Every number in `FORM.md`, `SPEECH_2MIN.md`, the challenge pages, the deck and the video must appear in the table below. Recognition numbers are recomputed offline by `python3 -m verify.run` from `docs/evidence/recognition/`.

## The line
**"The easy way to teach a humanoid. Repetitive work. Delicate work. Now it's easy."**
Pitch line: "Hands made us human. Now we lend ours to robots, and give them eyes so they don't break what they hold." (`PHILOSOPHY.md`)

## Arc (video: `SPEECH_2MIN.md`; deck, 10 slides: `CREATIVE_BRIEF.md`)
1. Hands made us human (Anaxagoras, Aristotle, Bruno, paraphrased).
2. Teaching a humanoid should be easy: repetitive work, delicate work.
3. Gloves teach: Rokoko gloves drove the real G1.
4. But gloves cannot feel: a fist crushes an egg.
5. The robot looks first: two model families vote, fragile first.
6. Same egg, same fist: cap ON intact, cap OFF broken (simulation).
7. Measured honestly on our 50 photos.
8. Two safety layers: models decide in simulation, the operator caps the real robot and vision can only lower them.
9. Glove teaches, camera protects. Now it's easy.

## Numbers we may say (source)

| Number | Exact safe wording | Source |
|---|---|---|
| 0.22 s | "Nemotron: median 0.22 s per call, 48 of 50 in two runs" | `verify.run` (`nemotron_run2.json`) |
| 20/20 | "Gemma 4 got all 20 eggs right, 49 of 50 overall" | `verify.run` (`gemma4_api.json`) |
| 7.7 s | "Gemma 4 through the API: median 7.7 s per call" | `verify.run` |
| 0.24 s | "PaliGemma 2 on our own Verda GPU: 49 of 50, median 0.24 s" | `verify.run` (`paligemma2_local.json`) |
| 50/50 | "Together, fragile-first: 50 of 50 on our photos (computed offline, same photos)" | `verify.run` |
| 22/22 | "Every stress ball confirmed by both model families" | `verify.run` (family count, #190) |
| 3 of 3 | "Each Nemotron/Gemma disagreement was exactly one model's error" | `verify.run` |
| egg-012 | "The one photo two models got wrong was saved by the third model's egg vote" | `verify.run` details |
| 47/49/49 → 49/50/50 | "Prompt A 47, 49, 49 of 50; prompt B 49, 50, 50, tuned on the same photos" | `docs/PROMPT_ITERATION.md` |
| 0.90 | "Wrong answers had the same confidence as the lowest right answers" | `docs/OBJECT_RECOGNITION_RESULTS.md` |
| 48 of 50 (PaliGemma) | "Asked 'fragile or rigid?', PaliGemma said fragile for 48 of 50 photos" | same |
| held vs broken | "In simulation: with the cap held intact, without it broken" (no force values) | `python3 -m robot.e2e_g1 --label egg` |
| 83 Hz, 0 dropouts | "89 takes, 83 Hz glove stream, 0 dropouts, max gap 12 ms" | `Rokoko/src/episode_quality.py` |
| real G1 | "Gloves drove the real G1's arms and hands: 2 runs of 120 s, 29.8 commands per second, 0 commands clipped by the safety filter" | `tools/g1_windows_runner/README.md` |
| real G1 caps | "On the real G1 the operator sets hard caps, egg 0.50, empty can 0.90, ball 1.0, and the camera can only lower them" | `g1/live_policy_v2_vision.py` |
| 0.6-1.4 s / 4-8 ms | "Real arms lagged 0.6-1.4 s under load; our policy takes 4-8 ms per command" | `docs/DELIVERY_G1.md` |
| 197 → 20 ms | "Coil filter delay 197 ms → 20 ms on replayed takes" | `docs/G1_V2_RUN.md` |
| 24/24, 23/24 | "On simulated G1 head frames: egg 24/24, can 23/24" | `docs/G1_V1_RUN.md` |
| 37/40 | "Learned path from 10 glove takes + scripted grip and homing: 37 of 40 legs, simulation" | PR #142, `ml/square_policy.py` |
| 35 s | "Jury clip `media/g1_cv_demo.mp4`, simulation, grasp assist marked" | `docs/DELIVERY_G1.md` |

## Do not say
Vision-guided grasping on the real G1; any force value; a percentage without "on our 50 photos"; "it generalises"; "it learns by itself"; "safe" without a qualifier.
