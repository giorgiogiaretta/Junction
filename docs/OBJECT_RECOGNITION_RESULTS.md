# Object recognition on real head-camera photos (Nemotron 3.5 Super VL, Verda endpoint)

Data: `imgs/` (not in git, 55 MB): `ball/` 22, `can/` 8, `egg/` 20, `mix/` 27 phone photos (1920x2560, egocentric, hand holding the object or object on the knees/table). Ground truth = folder name; `mix` (several objects) is not scored. Photos are downscaled to 1024 px before sending. Tool: `python -m ai.eval_objects imgs --backend nemotron --mix` (thinking disabled on the endpoint).

## Result (first and only full run, 11:31)
- **48 / 50 correct (96%)**; grasp profile correct 96%; 0 failed calls.
- Confusion: egg 18 right, 2 called `stress_ball`; ball 22/22; can 8/8.
- The two errors are `egg-012` and `egg-014`: a small white egg held in the fingertips (one with a printed stamp). **This is the dangerous direction**: an egg treated as a stress ball gets the `can` profile (max closure 0.8) instead of `egg` (0.5), which breaks it in the simulation.
- `mix` (27 photos, not scored): main object reported egg 9, stress ball 8, can 10.

## Caveats
- 50 photos from one person, one place and one day: no generalisation claim. Folder names are the only labels; some `egg` photos may show other objects in the background.
- Latency in that run was dominated by the client-side rate limiter (2 s gap): the real model latency was not measured. Earlier single calls with thinking off: ~0.3-0.4 s.
- **The Verda endpoint stopped answering after that run** (all calls time out at 20 s, 11:45). A second run for confidences and latency could not be completed. Design consequence: the picker must always have a fallback (conservative profile) and a second provider (Gemini; local Gemma later).

## Next
- Safety rule for the error direction: unknown/low-confidence -> conservative profile (`cup`), never a firm one; calibrate the threshold on the confidences of the wrong photos once the endpoint answers again.
- Cross-check the same photos with Gemini (`--backend gemini`, needs GEMINI_API_KEY and the model id) and review disagreements by hand.
- Crop around the hand (`ai/crop.py`) should help with the small eggs held in the fingers: measure crop vs full image on the same photos once the head-to-hand pose exists.

## Colour rule baseline (orange = ball, white = egg): 38/50 (76%), untuned
`python -m ai.color_baseline imgs` (HSV masks + blob shape on the same 50 photos): ball 19/22, egg 12/20, can 7/8; two eggs called stress ball, 5 eggs "other". Colour is a useful hint but **not a guarantee**: white sleeves/lights, orange items in the scene, small objects in the fingers and the gold can next to orange break it. After the B3 shared cap (egg and ball both 0.70) an egg/ball confusion no longer drops or crushes the egg, so colour is only a cheap offline cross-check, not the safety mechanism.

## Update 14/11 afternoon (network stable again; sequential runs per provider, 4 s gap for Google)
Same 50 labelled photos in `imgs/` (not in git). Reports in `data/photos_reports/` (local, git-ignored): `n2` Nemotron, `gma2` Gemma.

| Recogniser | Correct | Eggs | Latency (median HTTP) | Failed calls |
|---|---|---|---|---|
| Nemotron 3.5 Super VL (Verda, thinking off) - **second run, reproduces the first** | 48/50 (96%) | 18/20 (egg-012, egg-014 -> stress_ball) | 0.22 s (max 0.31 s) | 0 |
| Gemma 4 26B A4B (`gemma-4-26b-a4b-it`, Google API) | 49/50 (98%) | **20/20** | 7.7 s (max 33 s) | 0 |
| Gemini 3.5 Flash | run in progress (spot test 5/5 incl. both hard eggs) | | ~3-5 s | |
| Colour rule (local) | 38/50 (76%) | 12/20 | <0.5 s | - |
| **Ensemble Nemotron + Gemma, fragile-first** (`ai/recognize.py`, computed offline from the saved answers) | **50/50** | **20/20, 0 egg -> ball/can** | bound by the slower one | - |

- **Confidence does not separate right from wrong.** Nemotron: both wrong eggs have confidence 0.90, the lowest confidence among the 48 right answers is also 0.90 (median 0.95). Gemma: its one wrong answer has 0.90 and its lowest right answer 0.90. So a single model's confidence >= 0.9 must never unlock full force on the stress ball; only agreement of >= 2 independent recognisers or a manual choice does (`ai.object_profile.cap_for_votes`, `CONFIDENCE_VALIDATED=False`).
- In the ensemble 21/22 balls are confirmed by both models (Gemma said "other" for ball-016): full force would be unlocked for 21 of 22 balls and never for an egg.
- **Caveats:** one person, one place, one day, 50 photos; folder name = label; the ensemble rule was fixed before these results but the same photos were used to look at them (no held-out set). A second recogniser adds ~8 s of latency (Gemma): for a live take the call happens once before the grasp, with the 15 s timeout of `ai/recognize.py` and the conservative cap as fallback.
- The earlier all-failed Gemini run (77/77) was the venue network (66% packet loss), not a model problem.
