# Google DeepMind — Best Use of Gemini API

> **Recommendation: do not enter unless a live result exists by 08:00.** The brief asks for use that goes beyond adding an LLM, with a technically impressive result. Our Gemini path is real code with only offline tests (`docs/SCORECARD.md` self-score 2-4/10). Decision for the human [DA VERIFICARE].

## Role: the slow judge
After a recorded glove episode, Gemini reads the whole episode (downsampled finger and wrist timeline) and answers whether the hand-off worked, with phases and a reason. It never sits in the real-time loop.

## How it is integrated
- `ai/judge_gemini.py` · `judge_episode`, `judge_async`: builds the episode payload, calls Gemini, parses strict output; unclear results are marked unclear, never "success".
- **Quota-aware model chain:** `gemini-3.1-flash-lite` → `gemini-3-flash-preview` → `gemini-2.5-flash`; a model that hits its daily quota is skipped; invalid JSON does not burn the other models' quota.
- `compare_with_nemotron`: disagreements between the Gemini judge and the Nemotron judge go to human review.

## Why it would matter
Every glove demonstration becomes a labelled training example (held / dropped / crushed) without a human watching each one.

## Proven / not proven
- Proven: offline tests with a fake SDK (`python3 -m pytest tests/test_judge_gemini.py -q`).
- Not proven: live judge quality (no labelled failed episodes, no precision number); exact deployed model id [DA VERIFICARE].
