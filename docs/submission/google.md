# Google (Gemma / Gemini) prize: draft

## Models
- **Gemma 4 26B A4B** (`gemma-4-26b-a4b-it`, open weights, called through the Google API).
- **Gemini 3.5 Flash** (`gemini-3.5-flash`), Google GenAI SDK.
Key from `GEMINI_API_KEY` in the environment only.

## Role in the system
Gemma and Gemini are independent voters in our object-recognition ensemble (`ai/recognize.py`): each looks at the same head-camera frame and names the object (egg / stress ball / can / other). A "fragile first" rule combines the votes, and the result sets the closure cap of the robot hand (`ai/object_profile.py`). Gemini is also the backup when the primary endpoint does not answer (`ai/pick_profile.py`) and a second episode judge (`ai/judge_gemini.py`).

## Why it matters
Our fastest model (Nemotron) gets 2 of 20 eggs wrong, calling them stress balls, and its confidence on those errors is as high as on right answers. Gemma gets **all 20 eggs right**. A second independent recogniser is what lets us give the stress ball full closure safely: full closure needs 2 agreeing recognisers, never one confident model.

## Measured (same 50 photos, `docs/OBJECT_RECOGNITION_RESULTS.md`)
- **Gemma 4**: 49/50, eggs 20/20, median 7.7 s per call (max 33 s), 0 failed calls (sequential run, report `gma2` kept locally, not in git).
- **Ensemble Nemotron + Gemma, fragile first**: 50/50, 20/20 eggs, computed offline from the saved answers. With it, full closure would be unlocked for 21 of 22 balls and for no egg.
- **Gemini 3.5 Flash**: full run not finished at the time of writing (spot test only). Fill in before submitting if the run completes; otherwise do not claim a Gemini number.

## Caveats
One person, one place, one day, 50 photos; folder name = label; no held-out set. Confidence does not separate right from wrong answers. Gemma adds about 8 s, so live it is called once before the grasp, with a 15 s timeout and the conservative cap as fallback.
