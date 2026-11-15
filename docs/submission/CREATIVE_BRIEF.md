# H — Brief for the creative agents (video, deck, assets)

Read first: `SPEECH_2MIN.md` (voice and timing), `STORY.md` (the only numbers allowed), `PHILOSOPHY.md`, `DIAGRAMS.md`. Banned in any visual or caption: vision grasping on the real G1, force values, a percentage without "on our 50 photos", "generalises", "learns by itself". Every simulation clip carries a small "simulation" tag; clips with grasp assist keep "grasp assist ON".

## 1. Video storyboard, 2:00 (public upload, hard limit)

| # | Time | Visual | Voice (from `SPEECH_2MIN.md`) | Music / motion graphics | 3D |
|---|---|---|---|---|---|
| 1 | 0:00-0:10 | Black screen, three names typed in: Anaxagoras · Aristotle · Bruno | Hands and wisdom | Low single piano note, slow build | Dex3 hand, slow 360° turn, rim light |
| 2 | 0:10-0:22 | Split screen: repetitive (cubes into boxes) / delicate (egg). Title card "The easy way to teach a humanoid" | Robots have hands; teaching should be easy | Beat starts | G1 silhouette |
| 3 | 0:22-0:40 | **Real G1 footage** (Giorgio's video) side by side with the operator's gloved hands; counter "2 × 120 s · 0 safety clips" | The gloves drove the real G1 | Counter ticks up | none (real footage) |
| 4 | 0:40-0:52 | `media/g1_cv_demo.mp4`, segment "vision OFF": egg breaks. Red flash, caption "simulation" | Gloves cannot feel | Hard stop of the music on the break | Egg crack (optional particle) |
| 5 | 0:52-1:14 | Head-camera frame → three model cards (Nemotron green, Gemma blue, PaliGemma blue with "Verda GPU" badge) → animated vote, "egg" chip wins | The robot looks first; two families; fragile first | Cards fly in at 0.22 s pace; "0.22 s" chip on Nemotron | Floating egg, ball, can models |
| 6 | 1:14-1:32 | `media/g1_cv_demo.mp4`: capped egg held vs uncapped broken, side by side. Labels "cap ON / cap OFF", "simulation" | Same egg, same fist | Music back, confident | Closure gauge overlay on the fingers |
| 7 | 1:32-1:48 | Number cards 48 · 49 · 49 → 50/50, caption "our 50 photos, computed offline"; line "one person, one place, one day" | Honest numbers | Calm | none |
| 8 | 1:48-2:00 | Glove icon + camera icon merge into the logo; names; repo URL; sponsor logos (Rokoko, NVIDIA, Google, Verda) | Glove teaches, camera protects | Resolve chord | Dex3 hand closes gently on the egg |

Delivery: 1920×1080, 30 fps, burned-in English subtitles, voice peaks at -3 dB, final length ≤ 1:59 to be safe.

## 2. Deck PDF, max 10 slides (owner: Tommaso's Codex, `deck/`)

| # | Title | Message | Visual | Wow moment |
|---|---|---|---|---|
| 1 | Hands made us human | Anaxagoras / Aristotle / Bruno, paraphrased | Dex3 render on black | The question, 2,500 years old |
| 2 | The easy way to teach a humanoid | Repetitive and delicate work | Split image | — |
| 3 | Gloves teach | Rokoko gloves + Coil Pro drive the real G1: 2 × 120 s, 0 safety clips | Real G1 still + gloves | Real hardware |
| 4 | But gloves cannot feel | A fist crushes an egg | Broken egg frame (simulation tag) | — |
| 5 | The robot looks first | Two families vote, fragile first | Diagram 2 from `DIAGRAMS.md`, animated | "Egg" wins the vote |
| 6 | Same egg, same fist | Cap ON intact / cap OFF broken | Side-by-side frames from `media/g1_cv_demo.mp4` | The core demo |
| 7 | Measured, honestly | 48 · 49 · 49 → 50/50 on our 50 photos; 3 of 3 disagreements = errors; confidence did not help | Bar chart + caveat line | Two wrong models, saved by the third |
| 8 | Two safety layers | Sim: models decide under the two-family rule. Real G1: operator caps, camera can only lower | Diagram 3 | Hardware stricter than sim |
| 9 | Sponsors in the loop | Rokoko motion · NVIDIA eyes · Google second key + voice · Verda own GPU · Gemini judge | Diagram 4, sponsor colours | — |
| 10 | Proven / next | Proven: real glove teleop, sim grasp, photo recognition. Next: vision on the real G1, more people and places, labelled datasets | Two columns | Honest close |

Dynamic graphics: animate diagram 2 step by step; number cards count up; one slide with an embedded short loop of the cap ON/OFF clip.

## 3. Assets to produce

| Asset | Source | Status |
|---|---|---|
| Real G1 teleop clip (10-15 s) + operator hands | Giorgio's phone / G1 view (not in repo) | Approved for the public video (Giorgio, 15/11 02:07); file to collect from Giorgio |
| Cap ON / OFF egg clip | `media/g1_cv_demo.mp4` (35 s, simulation) | In repo |
| Head-camera frame with the three objects | `docs/media/` or a G1 head frame from Giorgio | [DA VERIFICARE] |
| 3D renders: Dex3 hand, G1, egg, stress ball, can | MuJoCo assets (`g1/sim/`, cached G1 meshes) or a simple render | To produce |
| Sponsor logos: Rokoko, NVIDIA, Google (Gemma), Verda, Unitree, Aalto | Official press kits only | To download by a human |
| Number cards / bar chart | `STORY.md` numbers only | To produce |
| Diagrams 1-4 | `DIAGRAMS.md` (Mermaid → SVG) | To export |
