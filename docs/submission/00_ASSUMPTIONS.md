# 00 — Assunzioni, contraddizioni, cose DA VERIFICARE (leggere prima di tutto)

Pacchetto finale per la submission (15/11, scadenza 10:00). Fonte dei numeri: tabella "Numbers we may say" in `STORY.md`, ricalcolata con `python3 -m verify.run --json` sulle risposte salvate in `docs/evidence/recognition/`. Dove un documento e il ricalcolo non coincidono, vince il ricalcolo.

## Assunzioni (10 righe)
1. `main` a 7947365 (dopo #188 e #191): il codice del G1 vero (`start_g1.ps1`, `g1/arms_glove.py`, `g1/live_policy_v2_vision.py`, `tools/g1_windows_runner/`) è su `main`.
2. Il prompt è stato eseguito da questa sessione ("Tommaso's Docs") e non da una chat esterna; i brief delle sei challenge sono quelli in `~/Downloads/*_brief.md`.
3. **Due submission separate.** (1) **Rokoko** (priorità): challenge principale Rokoko, con collegate le challenge tecnologiche di cui usiamo la tecnologia: NVIDIA Nemotron, Best Use of Gemma, Verda Compute Track (Gemini opzionale). (2) **Aaltonomous** (secondaria, Giorgio, dopo): progetto indipendente, scheletro in `aaltonomous.md`.
4. Il video da 2:00 usa `media/g1_cv_demo.mp4` (simulazione) più i video del G1 vero che ha Giorgio (non nel repo).
5. "Due chiavi" = due **famiglie** di modelli: NVIDIA (Nemotron) e Google (Gemma 4 o PaliGemma, che contano come una sola chiave).
6. Tutti i numeri di riconoscimento sono sulle stesse 50 foto (una persona, un luogo, un giorno), senza un set di prova separato.
7. Le forze della simulazione si basano su soglie ipotizzate: non le scriviamo mai, diciamo solo "intatto" o "rotto".
8. Sul robot vero sono provati il movimento con i guanti e la catena del Coil; la presa guidata dalla visione è provata solo su fotogrammi simulati.
9. Il deck finale ha al massimo 10 slide (oggi ne ha 12, e il deck è di Codex).
10. Nessuna chiave, nessun dato personale, niente da `data/` nei testi.

## Contraddizioni trovate (e come le abbiamo risolte nei testi)
| # | Dove | Contraddizione | Scelta nei testi finali |
|---|---|---|---|
| C1 | `STORY_MODELS.md`, `README.md`, `ARCHITECTURE.md`, `rokoko.md` | PaliGemma "0,21 s"; ricalcolo sulle risposte salvate: **mediana 0,24 s** (`verify.run`: FAIL) | Scriviamo **0,24 s** |
| C2 | `OBJECT_RECOGNITION_RESULTS.md` | "nessun errore in comune" nel voto a tre; ricalcolo: **1 foto sbagliata da due modelli** (Nemotron e PaliGemma), salvata dal voto "uovo" di Gemma | Tra Nemotron e Gemma: 0 errori in comune. Nel voto a tre: 1 foto sbagliata da due modelli, salvata dal terzo |
| C3 | Prompt della chat ("rottura uovo ~3 N"), `SPEECH.md` | 3 N è la soglia della vecchia mano a 5 dita; la simulazione del G1 usa un'altra soglia ipotizzata | Nessuna forza nei testi: "soglia di rottura ipotizzata" |
| C4 | `STORY_MODELS.md` (ultima riga) | "la prima prova sul G1 vero è al 10 % di chiusura" è superata: il lanciatore usa 0,6 di default (`docs/CODE_AUDIT.md` F01) e i limiti per oggetto sono 0,50 / 0,90 / 1,0 | Non citiamo il 10 % |
| C5 | Simulazione e politica (`ai/object_profile.py`) contro robot vero (`g1/live_policy_v2_vision.py`) | Sim: uovo e pallina condividono 0,70, lattina non supportata (0,45), pallina a 1,0 solo con 2 famiglie. Robot vero: limiti fissi scelti dall'operatore, uovo 0,50, lattina vuota 0,90, pallina 1,0, e **la camera può solo abbassarli** | Lo spieghiamo come "doppio livello" (`DIAGRAMS.md` diagramma 3) |
| C6 | `DELIVERY_G1.md` (35 s) contro la board (75 s) | Durata di `media/g1_cv_demo.mp4` | **35 s** confermati con ffprobe sul file di `main` |
| C7 | `SCORECARD.md` | "Il conteggio non distingue le famiglie" | Superato da #190: `verify` conta per famiglia, palle confermate 22/22 |
| C8 | `deck/notes.md`, `SCORECARD.md`, `OBJECT_RECOGNITION_RESULTS.md` | Contengono una parola vietata dal lint di `verify.run` (FAIL "forbidden phrase") | Da correggere dai proprietari |
| C9 | `docs/submission/STORY.md`, `AUDIT.md`, `README.md` (miei) | Le liste "Never say" contenevano le parole vietate, quindi `verify.run` dava FAIL | **Corretto** in questa PR |
| C10 | `judge_gemini.py` | La docstring dice `gemini-2.5-flash`, il codice usa `gemini-3.1-flash-lite` con catena di riserva | Nel form: "catena Gemini 3.1 Flash-Lite → 3 Flash → 2.5 Flash" [DA VERIFICARE id effettivo] |

## DA VERIFICARE (lista unica di domande per Tommaso/Giorgio)
1. **Campi esatti del form Junction** (questi testi seguono i campi chiesti nel prompt; confrontarli con il form vero).
2. ~~Video del G1 vero~~ **Risposto (board 02:07): sì, la clip del G1 vero con i guanti si può usare nel video pubblico.**
3. **Risposto (board 02:05): `-CoilVision` non è ancora stato provato sul robot** (dopo le 00:33 solo prove con il runner finto). I testi restano "provato su fotogrammi simulati"; aggiornarli solo se la prova avviene e viene registrata.
4. **Gemini**: ci iscriviamo? Il ruolo è solo giudice asincrono, senza una misura di qualità (`SCORECARD.md`: 2-4/10). Consiglio: **no**, salvo che ci sia una tabella dal vivo entro le 08:00.
5. **Aaltonomous**: Giorgio vuole presentarla come submission **separata** se ci arriva (board 02:09); è secondaria, si fa dopo Rokoko. Scheletro in `aaltonomous.md`.
6. **Verda**: confermare GPU usata (A100) e crediti spesi (non scritti nel repo).
7. **Id esatto di Nemotron** sull'endpoint Verda (in `ai/llm.py` è marcato come non verificato).
