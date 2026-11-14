# Google (Gemma / Gemini) prize: draft

Reference story: `docs/STORY_MODELS.md`. Numbers: `docs/OBJECT_RECOGNITION_RESULTS.md`.

## Models and roles
- **Gemma 4 26B A4B** (`gemma-4-26b-a4b-it`, Google API): the **independent second key**. A different model family looks at the same head-camera frame; full closure on the stress ball needs it to agree with Nemotron. Also the language router: the operator speaks ("object dropped, switch to firm grip") and Gemma returns strict JSON that a safety gate validates (`ai/intent_router.py`); "stop" never waits for a model.
- **PaliGemma 2 3B** (Gemma family, open weights) **on our own A100 (Verda)** via SSH tunnel (`tools/paligemma_server.py`, `ai/paligemma.py`): a third, local vote with no quota and no data leaving our machine.
- **Gemini**: the **slow judge**. After a recording it reads the whole episode and says whether the hand-off worked (`ai/judge_gemini.py`). Never in the real-time loop.

## Why it matters
Our fastest model (Nemotron) calls 1-2 of 20 eggs a stress ball, with the same confidence (0.90) as its right answers, so confidence cannot warn us. A second model family can: on the 50 labelled photos, the 3 Nemotron/Gemma disagreements are exactly the 3 single-model errors, and no mistake is shared (`docs/STORY_MODELS.md`).

## Measured (same 50 photos; one person, one place, one day)
- **Gemma 4**: 49/50, eggs 20/20, median 7.7 s per call (Google API), 0 failed calls.
- **PaliGemma 2 on our GPU**: 49/50 (egg 19/20, ball 22/22, can 8/8) with a 3-option question, median 0.21-0.24 s, 0 failed calls. Honest note: the question "fragile or rigid?" is useless on it (answers "fragile" for 48/50).
- **Three-model vote, fragile first** (Nemotron + Gemma 4 + PaliGemma, computed offline from the saved answers): 50/50, eggs 20/20, every ball confirmed by at least 2 models.

## Caveats
50 photos, one person, one place, one day; no held-out set; three PaliGemma prompts were tried on the same photos (optimistic). Agreement is not accuracy. Vision has not run on the real G1 (its camera computer was off). Gemini judge: no precision number (no labelled negatives).
