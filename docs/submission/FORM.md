# A — Submission form (English, paste-ready)

Field list follows the brief in `docs/DOC_CHAT_PROMPT.md`; check it against the live Junction form [DA VERIFICARE]. Every number traces to `STORY.md` ("Numbers we may say").

**Project name**
Tactile-less HandOff

**Punchline** (12 words)
Gloves teach the robot's hands. Vision decides how hard they may squeeze.

**Alternative punchline**
The easy way to teach a humanoid: repetitive work, delicate work.

**Short description (~120 words)**
Rokoko Smartgloves make teaching a humanoid easy: put them on, move naturally, and a Unitree G1's arms and Dex3 hands follow. On the real G1, the gloves drove both arms and both hands in two 120-second runs with zero commands clipped by the safety filter. But gloves cannot feel force, and a confident human fist crushes an egg. So the robot looks first. A head camera sends one frame to models from two families, NVIDIA Nemotron and Google Gemma, and the fragile answer always wins. The object sets a closure cap. In our G1 simulation, the same egg is held intact with the cap and broken without it. On our 50 photos the three-model vote got 50 of 50, a small set we declare as such.

**Long description (~350 words)**
*The problem.* Humanoids now have hands, and teleoperation with motion-capture gloves is the fastest way to teach them, both for repetitive work (pick, place, sort) and for delicate work (eggs, fruit, glassware). Rokoko Smartgloves capture finger motion, but they have no force sensors. The operator feels the egg; the robot does not.

*What we built.* (1) A glove pipeline: Smartgloves II plus Coil Pro, 89 recorded takes, a glove stream at 83 Hz with 0 dropouts, retargeted to the G1's three-finger Dex3 hands. (2) On the real Unitree G1, through the organisers' runner and safety filter, the gloves drove both arms and both hands: two runs of 120 s at 29.8 commands per second, 0 commands clipped. (3) A head camera that looks before the hand closes. NVIDIA Nemotron 3.5 Super VL answers in a median 0.22 s. Google Gemma 4 and PaliGemma 2 (self-hosted on a Verda GPU) give a second opinion from a different model family. A fragile-first vote turns the answers into a closure cap: an egg is always gentle, and a stress ball gets full force only when two model families agree. (4) An end-to-end G1 simulation: same egg, same fist, held intact with the cap and broken without it.

*What we measured.* On our 50 labelled head-camera photos: Nemotron 48/50 in two runs, Gemma 4 49/50 with all 20 eggs right, PaliGemma 49/50, and the fragile-first vote of the three 50/50 (computed offline on the same photos). Each Nemotron/Gemma disagreement was exactly one model's error. Model confidence did not separate right from wrong answers, which is why no single model can unlock force.

*What we do not claim.* The photos come from one person, one place, one day, with no held-out set. Vision-guided grasping is shown in simulation; on the real robot the camera path ran only as a capture test. Break thresholds in simulation are assumed. On the real robot the per-object caps are fixed by the operator, and the camera can only lower them.

*Why it matters.* The camera turns cheap, natural glove demonstrations into safer ones, and it labels every demonstration with the object being held: training data for robot policies.

**Challenges entered**
- Rokoko: The Robot Teleoperation Challenge (main)
- NVIDIA: Best Use of Nemotron
- Google DeepMind: Best Use of Gemma
- Verda Compute Track
- [DA VERIFICARE, human decision] Google DeepMind: Best Use of Gemini API (see `gemini.md`)
- [DA VERIFICARE, human decision] Aaltonomous Humanoid (see `aaltonomous.md`)

**Technologies used**
Rokoko Smartgloves II, Rokoko Coil Pro, Rokoko Device SDK / Studio stream; Unitree G1 with Dex3 hands; the organisers' Aaltonomous runner and safety filter; NVIDIA Nemotron 3.5 Super VL (Verda-hosted endpoint); Google Gemma 4 26B A4B (Google API); PaliGemma 2 3B (self-hosted on a Verda A100); Google Gemini API (post-episode judge); MuJoCo; Python, NumPy, OpenCV; CycloneDDS; GitHub with a multi-agent workflow (Claude Code, Codex).

**Links**
- Code: https://github.com/giorgiogiaretta/Junction [DA VERIFICARE: public?]
- Video (public, max 2:00): [PLACEHOLDER]
- Deck PDF: [PLACEHOLDER]
- Offline evidence check: `python3 -m verify.run`

**Credited**: yes. Team: Giorgio Giaretta, Tommaso Magelli.
