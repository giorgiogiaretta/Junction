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
