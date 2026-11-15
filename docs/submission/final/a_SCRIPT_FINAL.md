# (a) Video script, FINAL — 243 words, picture ends at 1:59

> Note per Tommaso: il limite è 2:00. La voce finisce a 1:58,6 e l'immagine a 1:59, per non rischiare lo sforamento al caricamento (come chiede il CREATIVE_BRIEF). Ritmo costante, circa 125-135 parole al minuto: per questo i tempi sono ribilanciati rispetto a `SPEECH_2MIN.md` (lì le scene 4 e 7 andavano lette a oltre 160 parole al minuto). Prova con il cronometro: se sfori, taglia per prima la frase "The operator feels the egg; the robot does not."

| # | Time | Words | Voice |
|---|---|---|---|
| 1 | 0:00 – 0:10.5 | 22 | Anaxagoras thought we are the wisest animals because we have hands. Aristotle turned it round: we have hands because we are wise. |
| 2 | 0:10.5 – 0:18.5 | 16 | Robots finally have hands. Teaching them should be easy, for repetitive work, and for delicate work. |
| 3 | 0:18.5 – 0:34 | 31 | With Rokoko Smartgloves you just move. On a real Unitree G1, the gloves drove both arms and both hands: two runs of 120 seconds, zero commands clipped by the safety filter. |
| 4 | 0:34 – 0:47 | 28 | But gloves cannot feel. The operator feels the egg; the robot does not. A confident fist on the human side is a crushed egg on the robot side. |
| 5 | 0:47 – 1:08.5 | 45 | So the robot looks first. A head camera asks two model families. NVIDIA Nemotron answers in a median 0.22 seconds. Google Gemma, and PaliGemma on our own Verda GPU, give the second key. Fragile first: if one credible model says egg, it is an egg. |
| 6 | 1:08.5 – 1:25 | 33 | The object sets how far the fingers may close. A stress ball closes fully only when both families agree. In simulation, same egg, same fist: with the cap, held intact. Without it, broken. |
| 7 | 1:25 – 1:47 | 45 | On our fifty photos, the vote got fifty of fifty, and every disagreement between Nemotron and Gemma was one model's mistake. One person, one place, one day: a start, not a proof. Confidence never told right from wrong, so no single model unlocks full closure. |
| 8 | 1:47 – 1:59 | 23 | Repetitive work: the glove teaches. Delicate work: the camera protects. And every demonstration comes out labelled for the next robot. Now it's easy. |

## Cosa è cambiato rispetto a SPEECH_2MIN.md
- "answers in 0.22 seconds" → "answers in **a median** 0.22 seconds" (formula di STORY: "median 0.22 s per call").
- "A stress ball gets full force" → "A stress ball **closes fully**"; "no single model unlocks force" → "unlocks **full closure**" (nessuna parola di forza).
- Aggiunto "**In simulation,**" prima di "same egg, same fist": la frase è vera solo in simulazione e così lo dice anche la voce, non solo la didascalia.
- Nessun numero nuovo. Numeri pronunciati: 120 seconds (2 runs), zero commands clipped, 0.22 seconds, fifty photos, fifty of fifty.

## Limite dichiarato nella voce
"One person, one place, one day: a start, not a proof." e "Confidence never told right from wrong".

## Descrizione del video (da incollare sotto il video)
Tactile-less HandOff — Junction 2026, Rokoko Robot Teleoperation Challenge. Rokoko Smartgloves drove a real Unitree G1's arms and Dex3 hands (2 runs of 120 s, 0 commands clipped by the safety filter). Clips marked "simulation" are MuJoCo simulations; vision-guided grasping is shown in simulation only. Recognition numbers are on our 50 photos: one person, one place, one day, no held-out set. Team: Giorgio Giaretta, Tommaso Magelli. Code: https://github.com/giorgiogiaretta/Junction [DA VERIFICARE: pubblico?]

Se la voce è sintetica aggiungi: "Voice-over: synthetic voice." [DA VERIFICARE]
