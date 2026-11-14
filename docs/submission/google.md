# Google (Gemini) prize: draft

> Submit only if backlog B5 is green: `python -m ai.eval_objects imgs --backend gemini --mix` has produced a live table. Today Gemini has **never been called live** (`docs/ORCH_BACKLOG.md` section 1). Fill the bracketed fields from that run; do not submit with them empty.

## Model
Gemini via the Google GenAI SDK, model id `gemini-2.5-flash` (set by `GEMINI_MODEL`; id still to confirm with Google DeepMind). Key from `GEMINI_API_KEY` in the environment only.

## Role in the system
Gemini is the **second recognition tier**. When the primary recogniser (Nemotron) times out, the picker asks Gemini the same question on the same head-camera frame and uses its answer, still passing through the same safety rules (`ai/pick_profile.py`). It is also an independent second judge of recorded glove episodes (`ai/judge_gemini.py --compare`), where disagreements with Nemotron go to human review.

## Why it matters
Our primary endpoint stopped answering during the hackathon (`docs/OBJECT_RECOGNITION_RESULTS.md`). Without a second provider the robot hand falls back to one conservative grip for every object. Gemini keeps per-object behaviour available when one provider is down.

## Measured
- Gemini on our head-camera photos: [N of 50 correct, per-object breakdown, disagreements with Nemotron] from `python -m ai.eval_objects imgs --backend gemini --mix`.
- Picker with Nemotron disabled reports `backup: gemini`: [paste output of `python -m ai.pick_profile --image <egg.jpg>`].

## Limits
Same 50 photos, one person, one place, one day. Gemma (local) is not used.
