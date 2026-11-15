# 01 — Submission form, FINAL (paste-ready, English)

> Note per Tommaso (non incollare): i campi seguono `02_submission_rokoko/FORM.md`; nomi e limiti di caratteri del form vero sono **[DA VERIFICARE]**. Ogni numero viene dalla tabella "Numbers we may say" di `STORY.md` ed è stato ricontrollato su `verify_metrics.json`. Dove il form ha un limite più stretto, usa la versione "short".

---

## Project name
Tactile-less HandOff

## Punchline
Gloves teach the robot's hands. A camera decides how far they may close.

*Alternative:* The easy way to teach a humanoid: repetitive work, delicate work.

## Short description (about 125 words)
Rokoko Smartgloves make teaching a humanoid easy: put them on, move naturally, and a Unitree G1's arms and Dex3 hands follow. On the real G1 the gloves drove both arms and both hands: 2 runs of 120 s, 0 commands clipped by the safety filter. But gloves cannot feel, and a confident human fist crushes an egg. So the robot looks first. A head camera asks two model families, NVIDIA Nemotron and Google Gemma, and the fragile answer always wins. The object then sets how far the fingers may close. In our G1 simulation the same egg, with the same fist, is held intact with the cap and broken without it. Limits: our test set is 50 photos from one person, one place, one day.

## Short description, 60-word version (if the field is tight)
Rokoko Smartgloves drove a real Unitree G1's arms and Dex3 hands: 2 runs of 120 s, 0 commands clipped by the safety filter. Gloves cannot feel, so a head camera asks two model families, NVIDIA Nemotron and Google Gemma; the fragile answer wins and caps finger closure. In simulation: same egg, same fist, intact with the cap, broken without it.

## Long description (about 360 words)

**The problem.** Humanoids now have hands, and motion-capture gloves are the fastest way to teach them, for repetitive work (pick, place, sort) and for delicate work (eggs, fruit, glassware). Rokoko Smartgloves capture finger motion, but they do not sense touch. The operator feels the egg; the robot does not.

**What we built.**
1. *A glove pipeline.* Smartgloves II plus Coil Pro: 89 takes, 83 Hz glove stream, 0 dropouts, max gap 12 ms, retargeted finger by finger to the G1's three-finger Dex3 hands.
2. *Real hardware.* Through the organisers' runner and safety filter, the gloves drove the real G1's arms and hands: 2 runs of 120 s, 29.8 commands per second, 0 commands clipped by the safety filter.
3. *A camera that looks before the hand closes.* NVIDIA Nemotron 3.5 Super VL answers in a median 0.22 s per call. Google Gemma 4, and PaliGemma 2 on our own Verda GPU, give the second opinion. The two Google models count as one key. Fragile first: one credible "egg" vote means a gentle cap, and a stress ball gets full closure only when both model families agree.
4. *An end-to-end G1 simulation.* Same egg, same fist: with the cap held intact, without it broken.

**What we measured, on our 50 photos.** Nemotron 48 of 50 in two runs. Gemma 4 got all 20 eggs right, 49 of 50 overall. PaliGemma 2 on our own Verda GPU: 49 of 50, median 0.24 s. Together, fragile-first: 50 of 50 on our photos (computed offline, same photos). Each Nemotron/Gemma disagreement was exactly one model's error, 3 of 3.

**What we do not claim.** The 50 photos come from one person, one place, one day, with no held-out set. Wrong answers had the same confidence as the lowest right answers, so no single model can unlock full closure. Vision-guided grasping is shown in simulation only, and break thresholds there are assumed. On the real G1 the operator sets hard caps, egg 0.50, empty can 0.90, ball 1.0, and the camera can only lower them.

**Why it matters.** The glove teaches, the camera protects, and every demonstration comes out labelled with the object being held: training data for the next robot policy.

## Main challenge
Rokoko: The Robot Teleoperation Challenge

## Linked technology challenges
| Challenge | Link it? | What of theirs we used |
|---|---|---|
| NVIDIA: Best Use of Nemotron | **Yes** | Nemotron 3.5 Super VL on the Verda-hosted endpoint: object recognition before the grasp, and the NVIDIA key of the vote |
| Google DeepMind: Best Use of Gemma | **Yes** | Gemma 4 (Google API) and PaliGemma 2 (open weights, our own GPU): the Google key of the vote; Gemma 4 also routes the operator's voice (offline tests only) |
| Verda Compute Track | **Yes** | Verda-hosted Nemotron endpoint; a Verda GPU instance serving PaliGemma 2 (GPU type A100 **[DA VERIFICARE]**) |
| Google DeepMind: Best Use of Gemini API | **No**, unless Tommaso confirms **[DA VERIFICARE]** | Post-episode judge, offline tests only |

## Text for the Nemotron challenge field (required by NVIDIA: model, role, why, how we improved it)
**Model.** NVIDIA Nemotron 3.5 Super VL, called through the Verda-hosted endpoint, thinking off. (Serving id on the Verda endpoint: `nemotron-3.5-super-vl`, see `ai/llm.py`.)

**What it does.** Before a Unitree G1 hand closes, one head-camera frame goes to Nemotron, which names the object: egg, stress ball, can or other. Its answer is the NVIDIA key of a two-family vote that sets how far the fingers may close.

**Why it matters.** Rokoko gloves give the robot human motion without touch. Without a recogniser every object gets one conservative cap; with Nemotron the cap follows the object, within the time before the hand closes: median 0.22 s per call.

**How we improved its output.**
- Repeats, not single runs: Nemotron 48 of 50 in two runs on our 50 photos.
- Prompt iteration: prompt A 47, 49, 49 of 50; prompt B 49, 50, 50, tuned on the same photos, so B is optimistic.
- Error analysis: both errors were eggs called stress ball, and wrong answers had the same confidence as the lowest right answers (0.90). So one confident answer never unlocks full closure.
- A second family checks it: each Nemotron/Gemma disagreement was exactly one model's error, 3 of 3.
- Outages: every call has a timeout, and no answer means a conservative cap.

**Limit.** 50 photos, one person, one place, one day, no held-out set. Nemotron deciding a grasp is shown in simulation only.

## Text for the Gemma challenge field
Gemma is the second key. A stress ball gets full closure only if the NVIDIA key and the Google key agree. Gemma 4 got all 20 eggs right, 49 of 50 overall, on our 50 photos; through the API it takes a median 7.7 s per call. So we also serve open weights ourselves: PaliGemma 2 on our own Verda GPU: 49 of 50, median 0.24 s. Gemma 4 and PaliGemma share a family, so they count as one key: two Google models agreeing is not a second opinion. The one photo two models got wrong was saved by the third model's egg vote (egg-012). What did not work: asked "fragile or rigid?", PaliGemma said fragile for 48 of 50 photos; a concrete three-option question works. Limit: one person, one place, one day, no held-out set; three prompts were tried on the same photos.

## Text for the Verda challenge field
We used two Verda products. The NVIDIA Nemotron endpoint hosted by Verda is the fast first look: median 0.22 s per call. A Verda GPU instance (A100 **[DA VERIFICARE]**) serves PaliGemma 2 with open weights, reached through an SSH tunnel and never exposed to the internet: 49 of 50 on our 50 photos, median 0.24 s. Why our own GPU: the hosted Gemma 4 API took a median 7.7 s per call under a daily quota, too slow to sit in front of a closing hand; on our instance there is no quota and the photos never leave it. Honest scale: we did not train a policy or run rollouts at scale on Verda. Compute buys independence here: the second model family does not depend on one vendor's endpoint. Path to scale (not built yet): one self-hosted vision model per robot cell behind an auto-scaling container, with demonstrations labelled and stored in the EU. Credits spent: **[DA VERIFICARE]**.

## Technology stack
- **Capture:** Rokoko Smartgloves II, Rokoko Coil Pro, Rokoko Studio / Device SDK stream
- **Robot:** Unitree G1 with Dex3 hands, the organisers' runner and safety filter (Windows, CycloneDDS)
- **Perception:** NVIDIA Nemotron 3.5 Super VL; Google Gemma 4; PaliGemma 2; a colour rule (veto only); G1 head RGB-D camera
- **Compute:** Verda-hosted Nemotron endpoint; Verda GPU instance for PaliGemma 2
- **Simulation and checks:** MuJoCo G1 + Dex3; offline checker that recomputes every published number from saved model answers (`python3 -m verify.run`)
- **Engineering:** Python, NumPy, OpenCV; GitHub with a multi-agent workflow (Claude Code, Codex)

## Links
- Code: https://github.com/giorgiogiaretta/Junction **[DA VERIFICARE: repo pubblico?]**
- Video (public, max 2:00): **[DA VERIFICARE: incollare il link dopo il caricamento]**
- Deck PDF: `output/02_DECK/Tactile-less_HandOff_deck.pdf`

## Team
Giorgio Giaretta, Tommaso Magelli

---

## Cosa ho cambiato rispetto a FORM.md (per il controllo con `verify.run`)
- "full force" → "full closure" (niente parole di forza); "safer demonstrations" tolto.
- "the fragile-first vote of the three 50/50" → formula esatta di STORY: "Together, fragile-first: 50 of 50 on our photos (computed offline, same photos)".
- Tolto "on the real robot the camera path ran only as a capture test" dal testo lungo: resta "shown in simulation only", più corto e senza ambiguità.
- "A100" marcato [DA VERIFICARE] (verda.md e ASSUMPTIONS non lo confermano).
- Aggiunti i tre testi per i campi delle challenge collegate (NVIDIA lo richiede esplicitamente nel brief).
- Tolta la riga su Aaltonomous e la riga "Training" dello stack (37 of 40: fonte non presente nella cartella).
- Nessun numero nuovo.
