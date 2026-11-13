# Junction 2026 · Piano unificato (Rokoko) — PROPOSTA, in attesa di GO

Stato: **bozza per discussione.** Nessun agente apre issue o scrive codice a partire da questo file finché Tommaso e Giorgio non scrivono "GO" sulla board con le scelte della sezione 7.

Fonti fuse:
- **Piano A** = "Studio strategico e piano d'attacco" (Fable): concept HandOff, piano a livelli con criteri di uscita, Nemotron fuori dal loop di controllo, Jetson fuori dal percorso critico.
- **Piano B** = "Master Architecture & Multi-Agent Strategy": "Vision-Guided Force Cushion + Data Factory", stack di tech challenge, gerarchia Fable/Opus/Sonnet.
- **Stato reale del repo** al 13/11 sera (nessuno dei due piani lo aveva letto).

---

## 1. Verdetto in cinque righe

1. **Spina dorsale = HandOff (Piano A)**: teleop → registrazione → policy → il robot lavora da solo, l'umano col guanto subentra quando sbaglia, e ogni correzione torna nel dataset.
2. **Differenziatore = presa sicura su oggetti fragili (Piano B)**, ma fatta onestamente: limite di chiusura per profilo d'oggetto + anello chiuso sui sensori di forza della mano Inspire quando c'è. Nemotron sceglie il profilo *prima* della presa, non controlla le dita.
3. **Nemotron = giudice dei dati (N1) + selettore di profilo pre-presa (N2-lite)**, sempre asincrono. Gemini come secondo backend del giudice.
4. **Niente riorganizzazione delle cartelle**: teniamo `Rokoko/`, `ml/`, `robot/`, `demo/` e aggiungiamo solo `ai/`. Metà della Fase 1 del Piano B esiste già.
5. **Jetson congelato** (J0). Rientra solo come bonus a tempo (30 min).

---

## 2. Audit incrociato

### 2.1 Cosa prendiamo da ciascuno

| Da | Idea | Perché |
|---|---|---|
| A | Concept HandOff e metrica "quota di intervento prima/dopo riaddestramento" | Racconta un'economia (1 operatore : N robot) e produce un numero misurato dal vivo |
| A | Livelli con criterio di uscita eseguibile e linee di taglio | `main` resta sempre dimostrabile |
| A | Replay dello stream grezzo dei guanti + test di verità in CI | Unico modo perché gli agenti verifichino da soli senza hardware |
| A | Nemotron come "cervello lento", N1 giudice con accordo misurato vs etichette umane | Soddisfa il criterio NVIDIA "come avete migliorato l'output" con un numero |
| A | Orchestratore e giudice separati | Chi pianifica tende ad assolvere il proprio piano |
| B | Focus "oggetti fragili" come scena centrale | È il primo interesse dichiarato da Rokoko e si vede in 10 secondi sul palco |
| B | Gesto mano sinistra come meta-comando (REC/STOP) mentre la destra manipola | Ora abbiamo due guanti: costa poco e mostra il bimanuale |
| B | Segmentazione semantica delle fasi (`APPROACH → PINCH → LIFT → PLACE`) nel giudice | Rende il dataset "pronto per foundation model" |
| B | CRACI ed Entire a costo quasi zero | Da fare quando la CI è verde |

### 2.2 Cosa scartiamo o correggiamo

| Piano | Affermazione | Problema | Correzione |
|---|---|---|---|
| B | Nemotron "vede il bicchiere e ferma le dita esattamente sulla superficie" | Il modello risponde in secondi con ~40 RPM; non può stare nel loop a 30–80 Hz. "Esattamente sulla superficie" richiede forza o contatto misurati | Nemotron sceglie il profilo una volta per presa; il limite fine lo fa `ml/grasp_assist.py` con la forza della mano Inspire (se disponibile) o un cap fisso |
| B | `NemotronLoadBalancer` con 4 chiavi a rotazione "una per membro" | Siamo in due, e moltiplicare chiavi per aggirare il rate limit va contro lo spirito dei termini | Una chiave a testa con backoff, cache per episodio, griglie di fotogrammi invece di video interi |
| B | Ristrutturare in `rokoko_bridge/`, `robot_control/`, `ai_supervisor/`, `dashboard_ui/`, `schemas/` + 4 Sonnet | Butterebbe via codice funzionante e i path dei contratti già in uso; abbiamo 2 umani | Si mantengono le cartelle esistenti (sezione 5) |
| B | "Rokoko Studio richiede Windows/Mac" come motivo per escludere il Jetson | L'SDK supporta anche Linux Arm64; il motivo vero è il tempo e un Nano vecchio | Stessa conclusione (J0), motivazione corretta |
| B | Gate "latenza < 35 ms" e "errore di replay < 2 %" | Numeri inventati, non misurati | I gate li fissiamo dopo la prima misura reale con la dashboard |
| B | Contratto "21 joint 3D per mano" | Il solver SDK espone 26 giunti; oggi usiamo 5 valori calibrati | Contratto a due livelli: 5 valori (già in uso) + campo opzionale `joints` quando il solver è licenziato |
| A | Showpiece "spelling del nome di un giudice" | Una mano a 6 DoF separa male molte lettere | Showpiece = uovo/bicchiere con e senza assist; spelling solo se resta tempo |
| A e B | Fasi pianificate da zero | Nessuno dei due aveva letto il repo | La Fase 1 parte da ciò che esiste (sezione 3) |

### 2.3 Colli di bottiglia comuni ai due piani

1. **Hardware conteso**: licenza SDK, tempo con i guanti, mano Inspire dell'Aalto Robotics Club. Tutto il resto dipende da questo.
2. **La simulazione oggi non ha oggetti**: `robot/sim.py` è una mano a 5 dita senza palmo fisico né oggetto. Senza un oggetto non esiste "presa riuscita", quindi niente test di verità né policy.
3. **Nessuno stream reale registrato**: il parser delle dita è ancora calibrato su mock.
4. **Scadenza reale ignota**: le finestre temporali sono indicative.

---

## 3. Cosa esiste già (13/11 sera)

| Area | File | Stato |
|---|---|---|
| Ingest guanti | `Rokoko/src/rgmp_client.py`, `mock_rgmp_server.py`, `mock_stream.py` | RGMP su TCP, 1 o 2 guanti, UDP 14043/14053. Testato contro mock, non su hardware |
| Baseline webcam | `Rokoko/src/webcam_fingers.py` | MediaPipe → stesso formato UDP |
| Dataset | `Rokoko/src/dataset.py`, `listen.py` | Load/windows/replay su jsonl |
| Retargeting | `robot/retarget.py`, `robot/inspire.py` | 5 → 6 DoF Inspire, smoothing, `close_cap`. Registri Modbus da verificare con i mentor |
| Backend mano | `robot/hand.py`, `robot/sim.py`, `robot/run_udp.py` | dry, sim (MuJoCo), serial, pca9685, inspire; `--hand`, `--assist` |
| Presa sicura | `ml/grasp_assist.py` | Profili cup/egg/can + anello sulla forza (toy model) |
| Gesti | `ml/gestures.py` | Baseline sklearn su dati sintetici |
| Demo | `demo/dashboard.py`, `run_demo.sh`, `fanout.py`, `PITCH.md` | Dita L/R, gesto, latenza, fps |
| Test | `tests/test_pipeline.py`, `tests/test_grasp_assist.py` | Pipeline headless |
| Aperte | #13 recorder, #15 policy, #7 Jetson | Giorgio su #13/#15 |

---

## 4. Piano a fasi

Ogni fase finisce con una demo presentabile, un tag git e un video di riserva. Non si apre lavoro di una fase finché la precedente non ha superato il gate.

### FASE 1 · Teleop reale e test di verità (livelli L0–L1 di A)

Obiettivo: guanto vero → mano (simulata e, se disponibile, Inspire) dal vivo, con latenza misurata e un test che dice "oggetto sollevato".

| # | Deliverable | Cartella | Owner proposto | Accettazione |
|---|---|---|---|---|
| 1.1 | Licenza SDK attiva, 10 min di stream grezzo L+R registrati nel repo (`data/raw/*.rgmp`) e server di replay byte-per-byte | `Rokoko/` | Giorgio (umano + agente) | `python Rokoko/src/replay_rgmp.py data/raw/x.rgmp` fa girare `rgmp_client.py` identico al live |
| 1.2 | Contratto `hand_state` v1 congelato: `t`, `hand`, `fingers[5]`, `joints?`, `wrist_quat?`, `button?` | `docs/contracts.md` | Lead (Giorgio) | Approvato sulla board |
| 1.3 | Scena MuJoCo con palmo, mano a 6 attuatori stile Inspire, tavolo, cubo e oggetto "fragile" (rottura sopra soglia di forza) | `robot/` | Tommaso | `python -m robot.sim --headless --script grasp` stampa `lifted=1 broken=0` |
| 1.4 | Test di verità in CI: replay registrato → retarget → sim headless → `lifted` + latenza p50/p95 | `tests/` | Tommaso | `pytest tests/test_truth.py` verde in GitHub Actions |
| 1.5 | Dashboard: stato connessione, latenza p50/p95, pulsante del guanto | `demo/` | Tommaso | Visibile con `demo/run_demo.sh --real --bimanual` |
| 1.6 | Mano Inspire reale (se l'Aalto Robotics Club la presta): IP/registri verificati, `--live` | `robot/` | Tommaso | Mano reale copia il guanto per 60 s senza scatti |

**Gate F1**: sollevare il cubo in sim 5 volte su 5 col guanto vero; latenza misurata e scritta nella dashboard.

### FASE 2 · Registrazione, replay e presa sicura (L2 di A + Force Cushion di B)

Obiettivo: ogni teleop diventa un episodio pulito; l'oggetto fragile non si rompe.

| # | Deliverable | Cartella | Owner proposto | Accettazione |
|---|---|---|---|---|
| 2.1 | Recorder di episodi: guanto + stato robot + webcam sincronizzati, formato compatibile LeRobot (#13) | `Rokoko/` | Giorgio | 10 episodi su disco, riapribili con `dataset.py` |
| 2.2 | REC/STOP col gesto della mano sinistra o col pulsante dello Smartgloves II | `ml/` + `Rokoko/` | Giorgio | Episodio parte e si chiude senza tastiera |
| 2.3 | Replay di un episodio su sim e su Inspire | `robot/` | Tommaso | `python -m robot.replay ep.jsonl --backend sim` riproduce e il cubo si solleva |
| 2.4 | Presa sicura v2: profilo per oggetto + anello sulla forza Inspire (lettura `FORCE_ACT`) o forza simulata | `ml/` + `robot/` | Giorgio (logica), Tommaso (lettura forza dal backend) | Uovo/oggetto fragile in sim: 10 prese con assist, 0 rotture; senza assist almeno 1 rottura |

**Gate F2**: 10 episodi registrati e riprodotti; demo fragile con/senza assist ripetibile.

### FASE 3 · HandOff e cervello lento (L3–L4 di A + AI di B)

Obiettivo: il robot lavora da solo, l'umano interviene, il sistema misura e migliora.

| # | Deliverable | Cartella | Owner proposto | Accettazione |
|---|---|---|---|---|
| 3.1 | Policy (behaviour cloning in sim, ACT se c'è tempo) su ~50 episodi (#15) | `ml/` | Giorgio | ≥1 run autonoma riuscita su video + conteggio su 10 tentativi |
| 3.2 | Hand-off: pulsante/gesto passa il controllo dalla policy al guanto e ritorno; le correzioni sono episodi etichettati `intervention` | `robot/` + `ml/` | Tommaso (switch), Giorgio (dataset) | Quota di intervento misurata su due giri, prima e dopo riaddestramento |
| 3.3 | Giudice dati N1 con Nemotron 3.5 Super VL: esito, motivazione, istruzione, fasi; accordo vs 30 etichette umane, prima e dopo iterazione sul prompt | `ai/` (nuova) | Tommaso | `python -m ai.judge data/episodes/` scrive `judge.jsonl` + report di accordo |
| 3.4 | Selettore di profilo pre-presa (N2-lite): un fotogramma → tool call `set_grasp_profile(object, profile)` → `GraspAssist` | `ai/` | Tommaso | In demo, cambiando oggetto cambia il profilo entro ~2 s; ripiego al profilo di default se l'API non risponde |
| 3.5 | Secondo backend Gemini per il giudice + confronto | `ai/` | Tommaso | Tabella accordo Nemotron vs Gemini |

**Gate F3**: numero di quota di intervento sul palco; giudice con accordo misurato.

### Bonus (solo con F3 verde), in ordine
1. One Glove, Any Hand: stessa registrazione su una seconda mano simulata (Dex3 a 3 dita).
2. CRACI + Entire sul repo.
3. Voce (ElevenLabs) per stato del robot.
4. Jetson J1 come registratore, test a tempo di 30 min.

### Linee di taglio
- F1 non verde a sabato metà giornata: solo simulazione, si chiede aiuto ai mentor, niente hardware extra.
- F2 non verde a sabato sera: si presenta F1 + replay; il tempo va su presa sicura e giudice.
- F3.1 non verde a domenica mattina: si presenta F2 + giudice N1; HandOff raccontato come passo successivo, senza fingerlo.

---

## 5. Cartelle e proprietà (proposta per AGENTS.md)

| Area | Owner | Cartelle | Cosa contiene |
|---|---|---|---|
| Capture + dati + ML | giorgiogiaretta | `Rokoko/`, `ml/` | Ingest RGMP, replay grezzo, recorder episodi, gesti, grasp assist, policy |
| Robot + demo + AI | TommyMaggi | `robot/`, `demo/`, `ai/` | Retarget, backend sim/Inspire, scena MuJoCo, replay, hand-off switch, dashboard, pitch, Nemotron/Gemini |
| Contratti | Lead (Giorgio) | `docs/contracts.md` | Unico punto di verità delle interfacce |
| Test di integrazione | Chi tocca l'interfaccia | `tests/` | Ognuno aggiunge i test della propria cartella |

Modelli: Opus per contratti, matematica di retarget/forza e review delle PR di interfaccia; Sonnet per issue ben specificate. Un giudice in sessione pulita approva le PR di fine fase guardando solo criteri, diff e output dei test.

---

## 6. Regole operative aggiuntive

- Ogni issue: obiettivo in una frase, fase, comando di accettazione, file toccabili.
- WIP limitato: issue aperte solo della fase corrente.
- Checkpoint ogni 3–4 ore sulla board contro il gate della fase.
- `main` sempre dimostrabile; tag `phase-1`, `phase-2`, `phase-3`.
- Feature freeze qualche ora prima della consegna.
- Nemotron e Gemini: mai nel loop di controllo, sempre con timeout, backoff e ripiego.

---

## 7. Decisioni da prendere (Tommaso + Giorgio)

| # | Decisione | Proposta | Scelta |
|---|---|---|---|
| D1 | Concept | HandOff + presa sicura fragile; F (Any Hand) come primo bonus | |
| D2 | Robot target | Sim MuJoCo sempre; Inspire reale se l'Aalto Robotics Club la presta; G1 no | |
| D3 | Simulatore | MuJoCo (CI headless); Isaac solo se si sceglie il ponte Aaltonomous | |
| D4 | Compito | Sollevare cubo → poi oggetto fragile (uovo/bicchiere) | |
| D5 | Jetson | J0, J1 bonus a tempo | |
| D6 | Tech challenge | Nemotron (N1 + N2-lite) → Gemini → CRACI/Entire | |
| D7 | Showpiece | Uovo con/senza assist | |
| D8 | Livello minimo di consegna | F2 completo + giudice N1 | |
| D9 | Ruoli umani | Giorgio: hardware guanti + recorder/policy; Tommaso: mentor Aalto/Inspire + NVIDIA + pitch | |

## 8. Domande per i mentor (domattina)

- Rokoko: frequenza reale via SDK (83 Hz o 250 Hz) e latenza tipica; pulsante e LED Smartgloves II leggibili via RGMP?
- Aalto Robotics Club: modello esatto della mano Inspire, IP/porta Modbus, registri `ANGLE_SET`/`FORCE_ACT`, possiamo averla sul tavolo e quando?
- NVIDIA: identificativo esatto di Nemotron 3.5 Super VL sull'endpoint gratuito; accetta video o solo immagini?
- Organizzatori: scadenza reale di consegna; doppia candidatura Rokoko + Aaltonomous ammessa? Tech challenge da iscrivere a parte?
- Quale Jetson abbiamo esattamente.
