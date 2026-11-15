# Google DeepMind — Best Use of Gemma

**Models:** Gemma 4 26B A4B (`gemma-4-26b-a4b-it`, Google API) and **PaliGemma 2 3B, open weights, self-hosted on our own Verda A100** (`tools/paligemma_server.py`, reached through an SSH tunnel).

## The problem
Rokoko gloves cannot feel force, so a G1 robot hand must know what it is holding before it closes. One model is not enough: our fastest model (Nemotron) called 2 eggs "stress ball", with the same confidence as its right answers.

## What Gemma does: the second key and the voice
1. **The independent second opinion.** Gemma is the **Google key** of our two-family vote. A stress ball gets full grip only if the NVIDIA key and the Google key agree. Gemma 4 got **all 20 eggs right, 49 of 50** overall on our photos.
2. **Open weights on our own GPU.** PaliGemma 2 runs on a Verda A100 we control: **49/50, median 0.24 s**, no quota, no photo leaves our infrastructure. Gemma 4 and PaliGemma count as **one** key (same family), so the vote cannot be fooled by two Google models.
3. **The operator's voice.** The operator can say "object dropped, switch to firm grip". Gemma returns strict JSON; a safety gate allows a firm grip only for the stress ball; "stop" never waits for a model (`ai/intent_router.py`).

```
frame ──▶ Gemma 4 (API) ─┐
      ──▶ PaliGemma 2 ───┴─▶ Google key ─┐
      ──▶ Nemotron ─────────▶ NVIDIA key ─┴─▶ fragile-first ──▶ cap
voice ──▶ Gemma 4 router ──▶ JSON ──▶ safety gate ──▶ (only lowers, or firm for the ball)
```

## Measured (our 50 labelled photos, recomputable with `python3 -m verify.run`)
- Gemma 4: 49/50, eggs 20/20, median 7.7 s per call (API).
- PaliGemma 2: 49/50 (egg 19/20, ball 22/22, can 8/8) with a 3-option question, median 0.24 s.
- Three-model fragile-first vote: 50/50, eggs 20/20, every ball confirmed by both families (22/22).
- The one photo two models got wrong (egg-012: Nemotron said ball, PaliGemma said can) was saved by Gemma 4's "egg" vote.

## What we learned (honest notes)
- "Is this object fragile or rigid?" is useless on PaliGemma: it answered "fragile" for 48 of 50 photos. A concrete 3-option question works.
- PaliGemma cannot produce JSON, so the voice router stays on Gemma 4.
- Three prompts were tried on the same photos: the 49/50 is optimistic.

## Code you can open
| File · function | What it does |
|---|---|
| `ai/paligemma.py` · `recognise_bytes`, `normalise` | Calls our PaliGemma server, maps its one-word answer to a vote. |
| `tools/paligemma_server.py`, `tools/serve_gemma.sh` | Serve PaliGemma / Gemma on our own GPU. |
| `ai/recognize.py` · `decide` | Fragile-first vote across families. |
| `ai/intent_router.py` · `route_async`, `apply_intent` | Voice → strict JSON → safety gate. |

## Proven / not proven
- Proven: recognition numbers above (saved answers in `docs/evidence/recognition/`).
- Not proven: generalisation beyond our 50 photos; the voice router has only offline tests; Gemma deciding a grasp on the real robot.
