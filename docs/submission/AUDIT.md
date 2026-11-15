# Audit generale + audit della documentazione (14/11 sera, `main` a 843707e)

Riferimenti: `docs/ORCH_BACKLOG.md` (sez. 1, formule sicure), `docs/STORY_MODELS.md`, `docs/OBJECT_RECOGNITION_RESULTS.md`. Audit in sola lettura sui file altrui; correzioni fatte solo nelle cartelle di Tommaso's Docs (`docs/ARCHITECTURE.md`, `docs/submission/`, `README.md`). Per ogni problema: dove, perché, chi lo sistema.

## A. Audit generale (stato del progetto)

| # | Gravità | Problema | Prova | Chi |
|---|---|---|---|---|
| A1 | **Alta** | **Le prove sul G1 vero non sono su `main`.** Il 14/11 il G1 è stato guidato dai guanti (braccia + mani Dex3, 2 run da 120 s, 29,8 comandi/s, 0 comandi tagliati dal filtro), ma la documentazione e il codice sono solo nel branch `g1-real-working` (`tools/g1_windows_runner/README.md`, `g1/arms_simple.py`). Un giurato che clona `main` non lo trova. | `git show origin/g1-real-working:tools/g1_windows_runner/README.md` | Giorgio-agenti: PR del branch |
| A2 | **Alta** | **La visione non è mai girata sul robot vero**: il PC2 del G1 (camere) era spento in tutta la sessione. Tutto il riconoscimento e `ai.perceive` sono provati su foto nostre e su render simulati. | board 20:16, README del branch | Umani: chiedere allo staff il PC2 |
| A3 | Alta | **Nessun set di prova separato.** Tutti i numeri di riconoscimento (Nemotron, Gemma 4, PaliGemma, insiemi 50/50) sono sulle stesse 50 foto; il prompt B di Nemotron e il prompt a 3 opzioni di PaliGemma sono stati scelti guardando quelle foto. | `docs/PROMPT_ITERATION.md`, `docs/OBJECT_RECOGNITION_RESULTS.md` | ai/: valutare una volta, a regole congelate, sui fotogrammi DJI delle take 61-89 |
| A4 | Media | **La confidenza non separa giusto da sbagliato** (0,90 sia sugli errori sia sulle risposte giuste più basse). Già gestito da `cap_for_votes` (servono 2 modelli concordi): va detto, non nascosto. | `docs/OBJECT_RECOGNITION_RESULTS.md` | - |
| A5 | Media | Limite della lattina: risolto a 0,45 in codice (#154, da `g1/object_profiles.json`), ma `docs/G1_V1_RUN.md` dice ancora "lattina vuota 1,0". | `grep -n "1,0" docs/G1_V1_RUN.md` | Giorgio-agenti |
| A6 | Media | Imitazione (quadrato): 37/40 tratti in simulazione, ma la presa e l'avvicinamento finale sono **scriptati**. Formula: "percorso grezzo appreso + avvicinamento scriptato, simulazione". | board 16:13, PR #142 | - |
| A7 | Media | PaliGemma con la domanda "fragile o rigido?" risponde "fragile" a 48/50: inutile come classificatore. Usare solo il prompt a 3 opzioni. | `docs/OBJECT_RECOGNITION_RESULTS.md` | - |
| A8 | Bassa | CI copre solo una parte dei test; su Windows 5 fallimenti d'ambiente (sklearn, judge_gemini). | board 18:28 | B14, umano |
| A9 | Bassa | Forze stampate da `robot.e2e_g1` e `grasp_physics` con soglie ipotizzate (uovo 20 N): mai nel pitch. | `robot/e2e_g1.py` docstring | - |

## B. Audit della documentazione

| # | File | Problema | Correzione |
|---|---|---|---|
| D1 | `docs/ORCH_BACKLOG.md` sez. 1 | **Superata**: dice "nessun comando end-to-end" (ora `python -m robot.e2e_g1`), "Gemini mai chiamato" (ora prova a campione), "Niente sul G1 reale" (ora run reali, vedi A1). È il riferimento delle formule sicure: va aggiornata. | Orchestratore (non mio). Proposta di nuove righe in fondo a questo file |
| D2 | `README.md` su `main` | Ancora la versione della mattina ("nessun comando end-to-end", "niente sul G1 reale"). Le versioni aggiornate sono nelle PR #131, #132 non mergiate. | Mergiare questa PR (contiene #131 e #132) |
| D3 | `deck/notes.md` (Codex) | "Gemma is planned", "48 of 50, in one run", "Gemini is an unverified live backup": superate da `docs/STORY_MODELS.md`. | Tommaso's Codex: rifare il deck su `docs/STORY_MODELS.md` + `docs/submission/STORY.md` |
| D4 | `docs/STORY_MODELS.md` | Il titolo "Gemma 4 on our own GPU" e "49/50" mescolano due cose: Gemma 4 49/50 è stato misurato **via Google API**; sulla nostra GPU è stato misurato **PaliGemma 2** (49/50, 0,21 s). | Proprietario di STORY_MODELS: dire "Gemma 4 (Google API) e PaliGemma 2 (nostra GPU)" |
| D5 | `docs/submission/google.md` (mio) | Presentava Gemini come votante dell'insieme; secondo STORY_MODELS Gemini è il giudice lento fuori dal ciclo. Mancava PaliGemma. | **Corretto** in questa PR |
| D6 | `docs/submission/nvidia.md` (mio) | Mancava l'iterazione del prompt (A 47/49/49, B 49/50/50, tarato sulle stesse foto). | **Corretto** |
| D7 | `docs/ARCHITECTURE.md`, `README.md`, `rokoko.md`, `aaltonomous.md`, `STORY.md` (miei) | Dicevano "nessun risultato sul G1 vero", mancavano `ai.perceive`, PaliGemma, V1/V2, console. | **Corretti**, con la formula sicura per il G1 vero (sotto) |

## C. Formule sicure nuove (proposta per ORCH_BACKLOG sez. 1)

| Affermazione | Formula sicura | Fonte |
|---|---|---|
| G1 vero | "I guanti hanno guidato braccia e mani del G1 vero: 2 run da 120 s, 0 comandi tagliati dal filtro di sicurezza. La visione non era attiva sul robot (camere spente)." Non dire "il G1 afferra l'uovo" | branch `g1-real-working` (finché non è su main) |
| Riconoscimento | "Sulle nostre 50 foto: Nemotron 48/50 in 0,22 s, Gemma 4 49/50 con tutte le uova, PaliGemma sulla nostra GPU 49/50 in 0,21 s; insieme, prima il fragile, 50/50 sulle stesse foto" | `docs/OBJECT_RECOGNITION_RESULTS.md` |
| Due chiavi | "Sulle 50 foto le 3 discordanze Nemotron/Gemma sono esattamente i 3 errori dei singoli modelli; nessun errore in comune" | `docs/STORY_MODELS.md` |
| Imitazione | "Percorso grezzo appreso + avvicinamento scriptato: 37/40 tratti, simulazione" | PR #142 |
| Uovo | "In simulazione: con il limite l'uovo resta intero, senza si rompe" (mai unità di forza) | `python3 -m robot.e2e_g1 --label egg` |
