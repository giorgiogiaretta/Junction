# Gemini post-grasp judge (`ai/judge_gemini.py`)

Reads a **whole episode** (not 0.5 s aggregates) and answers: did the grasp / hand-off work?

```
export GEMINI_API_KEY=...            # or GOOGLE_API_KEY; only from the environment, never printed
python -m ai.judge_gemini data/episodes/take_05.npz
python -m ai.judge_gemini --all data/episodes --compare data/overnight/<run>/judge.jsonl
```
Per episode it prints `HandOff riuscito: True|False, Motivo: ...` and writes `data/judge_gemini_report.md` (`--out` to change).
Input: `take_NN.npz` episodes (index..little closure, wrist position, optional `hand_in_head`) or a `.jsonl` of per-sample dicts. Sent at up to ~15 Hz as compact JSON; thumb dropped (unreliable), NaN -> null.
`--compare` reads a Nemotron judge `judge.jsonl` and prints raw agreement plus the disagreements for human review.

## What this is NOT
- Our human labels only say "object not dropped" (32 positives). There are **no labelled failures**, so there is **no precision**, and the verdict is the model's reading of finger closure + wrist motion, not ground truth. Agreement with Nemotron is not accuracy.
- On API errors or invalid JSON (after retries) the result is *unclear*: printed as `False ... NON VALUTATO`, marked `unclear` in the report.

## Unverified
- Model id: default `gemini-2.5-flash` (override with `GEMINI_MODEL`); confirm at the Google DeepMind booth / AI Studio.
- The `google-genai` call shape (`client.models.generate_content` with a dict `response_schema`, `response_mime_type=application/json`) matches the installed SDK types but was tested only with a fake client (no network, no key).
