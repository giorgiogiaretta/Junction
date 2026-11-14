# Getting the most out of the vision models (plan, not results)

Today each model only answers "which object?" on one full frame. Below: what each model is best at, how to use it harder, and the command that would prove it. Nothing here is measured yet; results go to `docs/OBJECT_RECOGNITION_RESULTS.md` (owner of `ai/`: Tommaso's Claude).

**First fix the evaluation:** all numbers so far are on the same 50 photos used to design the rules. Giorgio's DJI take videos (`data/video/take_NN.mp4`, objects in `index.json`) are a **held-out set** from a different camera: freeze the rules, then run every idea below on them once.

## Nemotron 3.5 Super VL (NVIDIA): the fast reflex
Strength: 0.22 s median, structured tool calls. Role: the always-on first vote.
1. **Crop around the hand.** `hand_in_head` now exists in the episodes (#84) and `ai/crop.py` is ready: send the crop, not the full frame. The two errors were small eggs in the fingertips, exactly what a crop enlarges. Test: crop vs full on the held-out frames.
2. **Ask for attributes, decide by rule.** Instead of only a label, ask `{shell_or_foam, colour, approx_size_cm, rigid}`; an egg is "shell, white/brown, ~5 cm". Rules on attributes are easier to audit than a label.
3. **Several frames, not one.** Its speed allows 3-5 frames over the 0.5 s before the grasp; majority vote (fragile first). Cost about 1 s.
4. **Think only when in doubt.** Thinking off by default; if Nemotron and the colour rule disagree, re-ask with thinking on.

## Gemini 3.5 Flash (Google): eyes that point
Strength: spatial output and video. Role: the "where" and the "what happened".
1. **Bounding box / point of the object** in the same call (normalised coordinates, JSON schema). Feed it straight into `ai/locate.py` as `bbox`, replacing the colour mask. Test: `python -m ai.locate_bench` with Gemini boxes on the simulated renders.
2. **Whole-take video labelling.** Send a take video and ask for object + outcome (held / dropped / slipped / crushed) with timestamps. That labels Rokoko grasp datasets automatically, the "data out" story. Test: agreement with the human `outcome` field of series O takes.
3. **Structured output** (`response_schema`) instead of free text, so no parse errors.
4. Ask Google mentors whether a robotics-specialised Gemini (pointing / grasp points) is available to us; unverified.

## Gemma 4 (Google, open weights): the careful vote
Strength: 20/20 eggs; open weights. Role: the second independent vote that unlocks full force on the ball.
1. **Local run** as the no-network fallback (venue network dropped 66% of packets once). Check whether a quantised 26B A4B fits the M2 Pro; unverified.
2. Run it **in parallel** with Nemotron from the first frame so its ~8 s is hidden behind the approach.

## The ensemble: abstain, don't guess
- Fragile first stays. Add **abstain**: if votes disagree, conservative cap and show "?" to the operator, who can confirm by hand. Every disagreement is logged as a hard example for the dataset.
- Never use one model's confidence to unlock force (measured: it does not separate right from wrong).

## Priority (most value per hour)
1. Held-out run on DJI frames (credibility). 2. Nemotron crop. 3. Gemini bbox -> locate. 4. Gemini take labelling (Rokoko data story). 5. Gemma local.
