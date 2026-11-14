# NVIDIA Nemotron prize: draft

Reference story: `docs/STORY_MODELS.md`. Numbers: `docs/OBJECT_RECOGNITION_RESULTS.md`, `docs/PROMPT_ITERATION.md`.

## Model
Nemotron 3.5 Super VL via the hackathon Verda endpoint (OpenAI-compatible API, image input, tool call `set_grasp_profile`, thinking off). Client `ai/llm.py`; confirm the exact model id with the NVIDIA mentors (marked unverified in the code).

## Role: the real-time eyes
One head-camera frame before the grasp -> object + grasp profile, median **0.22 s**. It is one of the two keys of the vote (`ai/recognize.py`, `ai/perceive.py`) that sets the closure cap of the robot hand (`ai/object_profile.py: cap_for_votes`).

## Why it is essential
Gloves cannot feel force, so the hand must know what it holds before it closes. Nemotron is the only API model we measured that is both accurate and fast enough to sit inside that decision (Gemma 4 via API: 7.7 s median).

## How we improved its output (measured, same 50 photos)
1. **Latency**: thinking off, 0.22 s median (max 0.31 s); the first full result (48/50) was reproduced in a second run.
2. **Prompt iteration**, three repeats each (`docs/PROMPT_ITERATION.md`): prompt A 47, 49, 49 of 50; prompt B with visual cues (pale oval shell, orange ball, metal can) 49 (one failed call, no wrong answer), 50, 50. B was written after seeing the failing eggs of this set, so it is optimistic; run-to-run variation (47-49 at temperature 0) means single runs are weak evidence.
3. **Safety layer around it**: confidence does not separate right from wrong (0.90 on errors and on the lowest right answers), so one confident answer never unlocks full force; egg and ball share a cap; fragile-first vote; fallback is conservative, never "squeeze".
4. **Second key**: its disagreements with Gemma 4 catch exactly its errors on the 50 photos (3 of 3, none shared, `docs/STORY_MODELS.md`).
5. **Outages**: every call has a timeout and a conservative fallback, after the endpoint went down mid-day.

## Caveats
50 photos, one person, one place, one day; no held-out set. Vision has not run on the real G1 yet (its camera computer was off during the session).
