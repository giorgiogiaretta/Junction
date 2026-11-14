# Ricerca notturna (2026-11-14): cosa fare in piu' con guanti, dati e DJI nelle prossime 24 ore

Autore: agente di ricerca di Giorgio. Contenuto web = dati non fidati; nessun codice scaricato ed eseguito dalla rete (solo letti file di testo/XML e interrogato un file MJCF in MuJoCo con `python -I`). Dove una cosa NON e' verificata lo dico con **[NV]**; dove l'ho verificato io con un calcolo locale, **[OK-locale]**; fonte secondaria/terze parti: **[2a fonte]**.

Scala: valore (V) / fattibilita' (F) / rischio (R) = A(lto) M(edio) B(asso); tempo in ore-uomo, stimate da me.

---

## 0. Sintesi in 12 righe

1. **Scoperta piu' utile**: `unitreerobotics/xr_teleoperate` (Apache-2.0) contiene gia' le configurazioni DexPilot per **Dex3** (`assets/unitree_hand/unitree_dex3.yml` + URDF L/R) e per **Inspire** (`assets/inspire_hand/inspire_hand.yml` + URDF), basate su `dex-retargeting` (MIT). Non dobbiamo scrivere il retargeting da zero: dobbiamo solo alimentarlo con i keypoint del guanto.
2. Il guanto puo' produrre keypoint: il sidecar `rkk-hand-solver` ha `--emit-openxr` (26 giunti OpenXR). Ma i nostri `data/solved/*.npz` contengono solo `rot_angle` per giunto, NON posizioni: serve rifare `solve_takes.py` con `--emit-openxr` (offline, sulle 60 prese, nessun guanto necessario).
3. **Direzione giunti Dex3 verificabile offline**: il modello MuJoCo Menagerie `g1_with_hands.xml` ha giunti identici (nomi e limiti) a `docs/g1_dex3_limits.json`. Un mio test locale conferma i segni usati in `robot/g1_dex3.py` (dita: sinistra negativo / destra positivo; pollice: `thumb_1/2` positivo a sinistra e negativo a destra chiudono verso il palmo). `thumb_0` NON determinabile con quel test.
4. **Possibile BUG Inspire (da confermare col mentore)**: il README di un driver di terzi che trascrive il manuale RH56DFTP dice `thumb_rotation`: 0 = retratto, 1000 = attraverso il palmo, mentre `robot/retarget.py::to_inspire` produce 1000 a mano aperta (thumb_rot = 1000*(1-0.7*chiusura)). Se il README ha ragione, a mano aperta il pollice viene portato attraverso il palmo.
5. **Secondo rischio Inspire [2a fonte]**: lo stesso README riporta che il firmware sbaglia l'eco del transaction-id Modbus (pymodbus rifiuta le risposte) e che ogni scrittura va seguita dalla lettura dell'ACK a 12 byte, altrimenti la mano si blocca dopo pochi secondi. Il nostro `robot/inspire.py` usa pymodbus e il fake server dei test non riproduce il difetto: il test verde NON prova che funzioni sulla mano vera.
6. Indirizzi: ANGLE_SET 1486, SPEED_SET 1522, ANGLE_ACT 1546, FORCE_ACT 1582 confermati da quel README (che cita il manuale); **FORCE_SET 1498 non compare** nel suo elenco: resta [NV]. IP di fabbrica citato: 192.168.123.211 porta 6000 (il repo usa .210).
7. Con 10-60 prese e un solo operatore, la policy "vera" non e' difendibile; lo e' un **generatore di traiettorie condizionato da waypoint + action chunking + rumore di perturbazione** valutato in anello chiuso con baseline oneste. Letteratura: ACT (~10 min di demo, ma con immagini), DART, HG-DAgger, DexCap (che usa guanti Rokoko).
8. **DJI = verita' a terra per la posizione**: ArUco sui 4 angoli (opencv-contrib 4.12 gia' installato) -> errore del tracciato guanto+Coil Pro in cm. E' una metrica vera, e Rokoko dichiara l'ancoraggio Coil Pro come la parte meno validata del solver: e' un contributo utile da portare loro.
9. Dataset pubblici Unitree Dex3: usarli per **sanita' dei segni/intervalli e delle velocita'** leggendo solo i parquet (MB), non i video (GB). Non servono per addestrare: spazio azioni diverso (28 = 14 braccio + 14 mano) e niente guanti.
10. Giudice VLM: benchmark pubblici dicono che i giudici VLM sono **sbilanciati verso "successo"** e deboli su contatti fini (FailBench: migliore 0.77 balanced accuracy). Le nostre 60 prese sono TUTTE "non caduto": senza fallimenti registrati il giudice non e' valutabile.
11. "Surprise us" realistico: **One glove, any hand** (stessa registrazione su Dex3 sim + Inspire + metriche di saturazione/velocita') e **validazione ottica del Coil Pro**. Entrambi si mostrano in 5 min con replay.
12. Da NON dire: vedi sezione 7.

---

## 1. Retargeting mano umana -> Dex3 (3 dita, 7 DoF/mano) e Inspire (6 DoF)

### 1.1 Metodi e librerie

| Metodo | Cosa fa | Pro | Contro | Offline? | Fonte |
|---|---|---|---|---|---|
| Mappatura lineare (la nostra: `robot/retarget.py`, `robot/g1_dex3.py`) | chiusura 0..1 per dito -> giunti | zero dipendenze, stabile, gia' testata (56 episodi, nei limiti del filtro) | ignora la geometria; Dex3 ha 3 dita, ring/little scartati; pollice "interim" | si | repo |
| Position / Vector (dex-retargeting) | ottimizza i giunti robot perche' i punti/vettori del robot seguano quelli umani (NLopt + Pinocchio) | segue le punte, include scalatura mano (`scaling_factor`) | richiede posizioni 3D delle punte; Pinocchio su Windows (il PREFLIGHT dice: nessun wheel) | si (Linux/WSL/Mac) | https://github.com/dexsuite/dex-retargeting |
| **DexPilot** (in dex-retargeting) | ottimizza usando le distanze a coppie tra punte (pinch-aware) | miglior pinch tra pollice-indice; e' il default scelto da Unitree per xr_teleoperate | sensibile all'errore di posizione delle punte (nel guanto le punte sono derivate da cinematica, non misurate) | si | https://github.com/dexsuite/dex-retargeting ; https://github.com/unitreerobotics/xr_teleoperate (release note: default da Vector a DexPilot, via mirror, [2a fonte]) |
| Appreso (HumDex, marzo 2026) | rete addestrata su dati di teleop | migliore dell'ottimizzazione secondo gli autori | serve dato robot+umano che non abbiamo | no | https://arxiv.org/abs/2603.12260 (solo snippet, [NV]) |

Licenze: dex-retargeting MIT; xr_teleoperate Apache-2.0 (header LICENSE letto); `dex-urdf` ha l'Inspire con **CC BY-NC-SA 4.0** (https://github.com/dexsuite/dex-urdf) - ok per hackathon, da citare, non per uso commerciale.

### 1.2 Cosa c'e' gia' pronto (letto direttamente da GitHub raw, 2026-11-14)

`xr_teleoperate/assets/unitree_hand/unitree_dex3.yml`: tipo `DexPilot`, 7 giunti target per mano, punte `thumb_tip/index_tip/middle_tip`, indici umani `[[9,14,14,0,0,0],[4,4,9,4,9,14]]` (convenzione: polso=0, 4 punti per dito -> punte 4, 9, 14, 19, 24), `low_pass_alpha: 0.2`, `scaling_factor: 1.0` (solo per Vector). `assets/inspire_hand/inspire_hand.yml`: 6 giunti (`*_thumb_proximal_yaw/pitch`, index/middle/ring/pinky `proximal`), 5 punte, `scaling_factor: 1.20`. Il wrapper `teleop/robot_control/hand_retargeting.py` costruisce `RetargetingConfig` e riordina i giunti dall'ordine dell'ottimizzatore all'ordine API Dex3.

Ordine giunti: nel wrapper di xr_teleoperate la lista API della mano DESTRA e' thumb, **middle**, index; la scheda del dataset `G1_Dex3_PickApple_Dataset` e i nomi in `ObjectPlacement` elencano la destra come thumb, **index**, middle (come in `docs/g1_dex3_limits.json` di Aalto). Le due fonti Unitree non concordano: per la destra index/middle potrebbero essere scambiati a seconda del livello (DDS vs dataset). Danno limitato (stessi limiti, entrambe chiudono) ma e' una domanda da fare (vedi mentori).

### 1.3 Come alimentarlo col guanto Rokoko

- Il sidecar offre `--emit-openxr` (26 giunti OpenXR, polso all'origine; ruotato +90 gradi attorno a X rispetto al frame guanto) https://sdk.rokoko.com/guides/hand-solving/ . I suoi indici OpenXR a 26 punti hanno il palmo in posizione 0; la convenzione di xr_teleoperate (polso=0, punte 4/9/14/19/24) corrisponde a 25 punti senza palmo **[NV: da verificare stampando gli indici dei joint a video]**.
- Limiti dichiarati da Rokoko: "early release", flag di validita' sensori ignorati, il sidecar non applica la calibrazione di Studio, **yaw arbitrario per sessione**, ancoraggio Coil Pro poco validato. Le punte delle dita non hanno sensore [2a fonte, sito Rokoko]: le "punte" sono derivate. Il pollice e' il punto piu' debole (gia' osservato nel repo).
- Conseguenza pratica: per **aperto/chiuso** di indice e medio, la mappatura per angoli (la nostra) e' piu' robusta di DexPilot; DexPilot vale per **pinch** pollice-indice. Proposta: A/B offline, non scelta a priori.

### 1.4 Esperimento offline A/B (nessun hardware, 60 prese)

1. Rifare `Rokoko/src/solve_takes.py` con `--emit local --emit-openxr` (riga 24: `--emit local`) e leggere `joints_openxr`. Salvare posizioni per mano e frame.
2. Su Linux/WSL/Mac (Tommaso, M2): `pip install dex_retargeting` + config xr_teleoperate (Dex3 e Inspire). **[NV]** che Pinocchio ("pin") abbia wheel utilizzabile su Windows e su Mac arm64: il repo dice che su Windows no; per Mac non l'ho verificato.
3. Metriche per ogni presa e per ogni metodo (lineare vs DexPilot vs Vector): (a) % di tick con giunto saturato, (b) max passo per tick contro 0.1 rad (filtro Aalto, 3 rad/s a 30 Hz), (c) lunghezza del percorso (jitter), (d) correlazione tra apertura pollice-indice umana e apertura robot, (e) numero di NaN. Tutte calcolabili senza robot.
4. Ricordare: **il cubo grande non entra in 3 dita**: DexPilot non lo risolve; e' un limite del robot, non dell'algoritmo. Usare per il G1 la lattina.

### 1.5 Come verificare il VERSO dei giunti (tre livelli di prova, dal piu' economico)

1. **Simulazione (fatto, [OK-locale])**: `mujoco_menagerie/unitree_g1/g1_with_hands.xml` (BSD-3, https://github.com/google-deepmind/mujoco_menagerie/tree/main/unitree_g1) ha i 14 giunti mano Dex3-like con **gli stessi intervalli** del nostro JSON (es. `left_hand_thumb_1 [-0.724,1.047]`, `right_hand_thumb_2 [-1.745,0]`; letto dal file raw). Test: portare un giunto per volta a fondo corsa e misurare distanze tra centri dei link:
   - dita sinistra (index/middle 0 e 1 a negativo) e destra (positivo): distanza punta-palmo 0.111 -> 0.051 m (chiude).
   - sinistra `thumb_1 = +1.05`: distanza pollice-indice 0.160 -> 0.091; `thumb_2 = +1.75`: 0.160 -> 0.122; con segni opposti (-0.72) 0.192 (apre).
   - destra: speculare (`thumb_1 = -1.05`: 0.091; `thumb_2 = -1.75`: 0.122).
   - Coincide con `_closed()` in `robot/g1_dex3.py` (bound piu' lontano da 0). `thumb_0` (rotazione/opposizione): la mia proxy (centri dei link) non lo discrimina: **[NV]**.
   - Limiti: modello derivato dal MJCF Unitree "con attuatori da tarare", non il robot vero; proxy grezza.
   Snippet minimo (da incollare in `robot/` come `check_dex3_signs.py`, ~25 righe): `m=mujoco.MjModel.from_xml_path('g1_with_hands.xml')`; per ogni giunto imposta `d.qpos[m.joint(n).qposadr[0]]`, `mj_forward`, leggi `d.geom_xpos` dei geom con mesh `*_hand_*_link`.
2. **Dati reali Unitree (offline, MB)**: dai parquet di `unitreerobotics/G1_Dex3_PickApple_Dataset` (201 episodi, 30 fps, stato/azione 28-d, ultimi 14 = mani, Apache-2.0, https://huggingface.co/datasets/unitreerobotics/G1_Dex3_PickApple_Dataset) controllare i segni medi di ogni giunto mano durante la presa. Distingue il pollice (segno) ma NON index vs middle (si muovono insieme). Scaricare solo `data/*.parquet`+`meta`, non i video AV1 (GB).
3. **Sul robot** (gia' nel PREFLIGHT): `G1_MAX_CLOSURE=0.1`, un dito alla volta, mentore con e-stop. Resta l'unica prova per `thumb_0` e per l'ordine index/middle a destra.

### 1.6 Inspire RH56: cosa dice la fonte che ho trovato (README di `inspire_rh56dftp` su PyPI, che dichiara di trascrivere il manuale RH56DFTP V1.0.0 dic 2024) https://pypi.org/project/inspire-rh56dftp/  [2a fonte, non ho potuto aprire il PDF del manuale: 404]

| Punto | Fonte dice | Il repo (`robot/inspire.py`, `robot/retarget.py`) | Esito |
|---|---|---|---|
| Ordine DOF | `[pinky, ring, middle, index, thumb_bend, thumb_rotation]`, 0..1000 | `to_inspire`: `[pk, rg, md, ix, th, thumb_rot]` | coincide |
| Dita e thumb_bend | 1000 = esteso, 0 = chiuso | `1000*(1-v)`, v=chiusura | coincide |
| **thumb_rotation** | 0 = retratto, 1000 = attraverso il palmo; "pugno" = `[0,0,0,0,0,1000]`, "aperto" = `[1000]*5+[0]` | `thumb_rot = 0.7*th` poi `1000*(1-thumb_rot)`: **aperto -> 1000** | **POSSIBILE INVERSIONE** (la rotazione dovrebbe CRESCERE chiudendo, il repo la fa calare) |
| Registri | ANGLE_SET 1486, SPEED_SET 1522, ANGLE_ACT 1546, FORCE_ACT 1582 (6 reg ciascuno) | 1486, 1498 FORCE_SET, 1522 | FORCE_SET 1498: non confermato [NV] |
| Rete | IP fabbrica 192.168.123.211, porta 6000 | default `.210` | verificare |
| Modbus | eco transaction-id errato -> pymodbus rifiuta; **leggere sempre l'ACK da 12 byte dopo ogni scrittura** o la mano si blocca | pymodbus, nessuna lettura ACK esplicita | rischio concreto |
| Tattile | big-endian nonostante il manuale | non usato | irrilevante |
| Forza | https://correlllab.github.io/rh56dfx.html : la mano espone solo propriocezione NON calibrata; a contatto veloce overshoot del limite fino a +1618% | `close_cap` | non dichiarare Newton |

Azioni: (1) chiedere conferma al mentore Aalto sul verso di `thumb_rotation` e sul transaction-id; (2) se confermato, correggere `to_inspire` (rotazione = 1000 * 0.7 * th, cioe' cresce) e aggiornare il fake server nei test per riprodurre eco sbagliato + obbligo ACK; (3) se pymodbus fallisce, usare un client a socket grezzo di ~40 righe (NON installare il pacchetto PyPI v0.1.0 senza leggerlo: e' di terzi; copiare l'idea, non il codice alla cieca).

---

## 2. Imitation learning con pochissime demo

### 2.1 Cosa dice la letteratura (fonti lette, abstract)

| Metodo | Idea | Dati | Note per noi | Fonte |
|---|---|---|---|---|
| ACT | trasformer con **action chunking** (predice una sequenza di azioni; `--temporal_agg` per mediare) | "10 minuti di demo", 6 compiti reali, 80-90% (abstract); README: esempio 50 episodi simulati, `chunk_size 100`, "allenare piu' a lungo" se a scatti | usa immagini+joint; noi non abbiamo video allineati (vedi 3) | https://arxiv.org/abs/2304.13705 ; https://github.com/tonyzhaozh/act |
| Diffusion Policy | policy come denoising condizionato, receding horizon | abstract non dice quante demo | multimodale, piu' pesante da addestrare | https://arxiv.org/abs/2303.04137 |
| DART | **rumore iniettato nel supervisore durante la raccolta** per mostrare recuperi | on-line (serve raccogliere di nuovo) | claim: -5% reward persa vs DAgger -80% su Humanoid sim; +62% su BC in grasp reale | https://arxiv.org/abs/1703.09327 |
| HG-DAgger | l'umano prende il controllo (gating) e corregge; soglia di rischio dall'incertezza | on-line | e' esattamente HandOff | https://arxiv.org/abs/1810.02890 |
| DexCap (usa **guanti Rokoko**) | mocap + IK -> policy a nuvole di punti; correzioni umane | 30-60 min -> 55-251 demo per compito; **30 correzioni per compito**: successo 0->33%, 0->20%, 0->25% (compiti difficili) | prova che glove -> policy e' un percorso pubblicato; i miglioramenti con correzione sono reali ma modesti e su robot vero | https://arxiv.org/html/2403.07788v2 |
| LeRobot | implementa ACT, Diffusion, VQ-BeT, Pi0, SmolVLA; dataset v3 | - | training su CUDA (la RTX 5070 Ti ha `torch 2.11+cu128`, gia' installato) | https://github.com/huggingface/lerobot |

### 2.2 Cosa e' onesto fare con ~10-60 prese e senza oggetto misurato

Stato dei fatti (dal repo): serie H = 10 prese (5 per mano), un operatore, nessuna posizione dell'oggetto misurata; piccoli modelli: "un passo avanti" batte la velocita' costante, ciclo chiuso diverge (`corners_reached: 0` nel report). Questo e' il comportamento atteso di una BC su pochi dati (errori che si compongono, motivazione di DAgger/DART).

Priorita' (valore/fattibilita'):

1. **Condizionare su waypoint/fase, non sullo stato grezzo** (V:A F:A R:B, 3 h). Il compito H e' una sequenza nota BL->TL->TR->BR->BL con angoli gia' stimati (`data/square_fit.json`). Input = (posizione relativa al prossimo angolo, fase, chiusura); output = passo verso l'angolo. Si elimina la deriva di ciclo chiuso perche' il bersaglio e' esplicito. Dichiarare che e' un *generatore di traiettoria*, non apprendimento di manipolazione.
2. **Action chunking + media temporale** (V:M F:A R:B, 2 h): predire H passi e usare la media (idea di ACT) invece di un passo; riduce lo scatto e la deriva. Misurare con corner raggiunti e errore finale in cm.
3. **Rumore di perturbazione offline stile DART (variante sintetica)** (V:M F:M R:M, 3 h): DART vero richiede nuova raccolta con rumore; offline si puo' approssimare perturbando lo stato (spostamento delta) e usando come etichetta il passo che riporta sulla traiettoria nominale (`a = a_t - K*delta`). Valido solo se l'azione e' cinematica (posizione del polso) come qui. E' un'ipotesi mia, **non testata**; confrontarla con il baseline senza rumore (c'e' gia' uno sweep rumore in `tools/night_gpu.py`). La serie D "rumore" puo' fornire un modello di tremore umano reale (controllare cosa contiene).
4. **Baseline obbligatori**: velocita' costante, un-passo, **vicino piu' prossimo sulle demo** (recupero della traiettoria piu' simile): se l'MLP non batte il vicino piu' prossimo, non e' apprendimento utile. Leave-one-take-out, intervalli bootstrap, e dichiarare n=10.
5. **Augmentation**: per dati low-dim: rumore gaussiano sullo stato, piccole rotazioni/traslazioni del frame tavolo (DexCap applica traslazioni casuali), jitter di velocita'/tempo (re-timing 0.8-1.2x), mirror L/R. Per immagini (se arrivano dalla DJI): `ColorJitter`, `RandomAffine`, `RandomShadow` ecc. sono nativi in LeRobot https://huggingface.co/docs/lerobot/lerobot-dataset-v3 (applicati solo in training).
6. **HG-DAgger / HandOff**: vale solo con la policy in un anello (sim cinematica o robot). Realistico: simulatore cinematico del polso con la policy 1+2, l'"umano" = replay di una correzione reale della serie C; misurare la quota di intervento prima/dopo riaddestramento con i dati di correzione. Dichiarare "simulazione cinematica". Attenzione: il MARK della serie C e' temporizzato a mano (+-0.5 s, gia' nel repo).

Da non fare: Diffusion Policy o VLA (Pi0, SmolVLA) con 10 prese: non c'e' base per un confronto onesto e il tempo si perde.

---

## 3. DJI Osmo Action 5 Pro come fonte di verita'

| Uso | Come | V/F/R | Ore | Note |
|---|---|---|---|---|
| Webcam | modalita' Webcam USB-C, fino a 1080p30 MJPG (Magewell KB, [2a fonte]); in OpenCV provare gli indici e impostare `FOURCC=MJPG`, 1920x1080, 30 (**[NV]** per `cv2`) | - | 0.3 | `Rokoko/src/cam.py` e `take.py` hanno gia' la registrazione camera opzionale (commit 0e59fee) |
| Calibrazione tavolo | 4 marker **ArUco** sugli angoli (lato 29.7 cm +-0.5 cm da `data/setup_square.json`) + `cv2.solvePnP`/omografia -> coordinate tavolo in metri per ogni frame | V:A F:A R:B | 2 | `opencv-contrib-python 4.12` gia' installato; la lente grandangolo dell'action cam distorce: calibrare con scacchiera (`cv2.calibrateCamera`) |
| Posizione oggetto misurata | rilevare la lattina (colore/cerchio superiore) nel piano tavolo | V:A F:M R:M | 2 | da' per la prima volta "oggetto misurato" per condizionare/valutare |
| Errore del Coil Pro | polso (MediaPipe 2D, o marker sul guanto) in coordinate tavolo vs traccia glove+Coil convertita col frame `square_fit` | V:A F:M R:M | 3 | **solo 2D**: i world landmarks di MediaPipe non sono metrici in profondita' (z relativa al polso) https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python |
| Sincronizzazione | evento comune: (a) battito di mani (audio DJI + picco di velocita' polso nel guanto), oppure (b) cross-correlazione tra velocita' del polso (guanto) e del polso visto (MediaPipe); tutto timestampato con `time.time()` sul PC (le `t_start` del repo sono gia' epoch) | V:A F:A R:B | 1 | il guanto a 83 Hz, camera a 30: ricampionare a 30 Hz come in `ml/square_policy.py` (`FPS=30`) |
| Dataset LeRobot | `LeRobotDataset.create(...)` -> per frame `add_frame` -> `save_episode()` -> **`finalize()`** (senza finalize i parquet sono corrotti) -> v3.0 (`lerobot>=0.4.0`) https://huggingface.co/docs/lerobot/lerobot-dataset-v3 | V:M F:M R:B | 3 | schema suggerito: `observation.state` = [5 chiusure, posa polso 7], `action` = stato successivo, `observation.images.dji` video, `task` = "sposta la lattina BL->TL->TR->BR". Le immagini devono essere video (mp4). Installazione LeRobot su Windows **[NV]**: farla su un ambiente separato |

Nota: MediaPipe installato e' 0.10.14; l'API "Hand Landmarker" (Tasks) richiede un file `.task` scaricato (non l'ho scaricato; **[NV]** che 0.10.14 lo supporti: `webcam_fingers.py` usa gia' MediaPipe nel repo, riutilizzare quello).

Un uso piu' forte della DJI e' **etichettare i fallimenti**: registrare le 5-10 prese fallite del PREFLIGHT con video, cosi' il giudice VLM vede qualcosa (vedi 5).

---

## 4. G1 Dex3 in simulazione senza GPU da 24 GB e dataset pubblici

### 4.1 Simulazione

- **MuJoCo (CPU, gia' installato `mujoco 4.0.1`)**: `unitree_g1/g1_with_hands.xml` e `scene_with_hands.xml` (Menagerie, BSD-3, MuJoCo >= 2.3.4, derivato dall'MJCF Unitree; l'MJX e' tarato e "trasferito sull'hardware in MuJoCo Playground"). Ha i 14 giunti mano con i limiti Aalto. Uso consigliato: caricare solo le mani (o il modello intero con braccia bloccate), pilotare `qpos`/target da `G1Dex3Retargeter.step()`, e misurare saturazioni e velocita'. Nessun contatto affidabile con oggetti: **[NV]** se la presa su lattina nel modello e' fisicamente stabile (attuatori "da tarare" dice il README). Non promettere "presa riuscita in simulazione".
- `unitreerobotics/unitree_mujoco` (bridge DDS) esiste ma non ho verificato che includa Dex3 in MJCF; non necessario.
- **Isaac**: `unitree_sim_isaaclab` ha task Dex3 (es. `Isaac-PickPlace-Cylinder-G129-Dex3-Joint`), richiede Isaac Lab/Ubuntu, quindi RTX >= 24 GB o cloud Verda (come da `docs/AALTONOMOUS_FEASIBILITY.md`). Non e' realistico per noi in 24 h.

### 4.2 Dataset Unitree su Hugging Face (tutti LeRobot, Apache-2.0)

| Dataset | Verificato | Uso per noi |
|---|---|---|
| `unitreerobotics/G1_Dex3_BlockStacking_Dataset` | 301 episodi, 281 196 frame, 9.18 GB, 30 fps, stato/azione 28-d (14 braccio + 14 mano), 4 camere 640x480 AV1, **LeRobot v2.0** | solo sanita' mano da parquet; non scaricare i video |
| `datamentorshf/G1_Dex3_BlockStacking_Dataset` | stessa scheda e stesse cifre (301 ep, 9.18 GB): sembra un mirror; identita' dei contenuti **[NV]** | preferire l'originale Unitree |
| `unitreerobotics/G1_Dex3_GraspSquare_Dataset` | la scheda riporta cifre identiche a BlockStacking e descrive impilare cubi: **scheda sospetta/copiata**, non fidarsi del nome | evitare |
| `G1_Dex3_PickApple_Dataset` | 201 ep, 152 569 frame, 2.98 GB, 2 camere; nomi giunti: mano sx thumb0-2, middle0-1, index0-1; **dx thumb0-2, index0-1, middle0-1** | segni/intervalli mano |
| `G1_Dex3_ObjectPlacement_Dataset` | 210 ep, 98 266 frame, 3.47 GB, 4 camere | idem |

Elenco dei dataset dell'account letto da https://huggingface.co/api/datasets?author=unitreerobotics (primi 100 000 caratteri; ne esistono molti altri: PickBottle, PickGum, Pouring, CameraPackaging, ToastedBread...).

Conversione/addestramento: `unitreerobotics/unitree_IL_lerobot` (ACT, Diffusion, Pi0/Pi05, GR00T; `utils/convert_unitree_json_to_lerobot.py`, `eval_robot/eval_g1_dataset.py` per valutazione offline senza robot) https://github.com/unitreerobotics/unitree_IL_lerobot . Il dataset BlockStacking e' v2.0: la conversione a v3.0 (`convert_dataset_v21_to_v30`) parte da v2.1, quindi un passaggio intermedio **[NV]**.

Cosa ne ricaviamo davvero in 24 h (realistico):
1. **Controllo di coerenza**: i nostri comandi `hand_q` (output del retargeter) devono stare nella distribuzione di valori e di |delta| per tick dei dati reali teleoperati (istogrammi per giunto): ci dice se `max_closure` e le velocita' sono plausibili per quel robot.
2. **Segni** (vedi 1.5).
3. **Non** addestrare: lo spazio e' diverso (braccia G1, immagini) dal nostro (mano umana, nessuna immagine allineata).

---

## 5. VLM/LLM per giudicare gli episodi

### 5.1 Modelli (verifica: 2026-11-14)

- **Nemotron 3.5 Super VL 120B-A12B**: rilascio 15 ott 2026 (HPCwire, unite.ai: 2a fonte). Pagina NIM: testo, immagini, **frame di video campionati**, contesto 1M token, licenza OpenMDW 1.1, id HF `nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4`, listing `nvidia/nemotron-3.5-super-vl-120b-a12b` https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3_5-super-vl-120b-a12b . Numero massimo di frame, rate limit, id esatto dell'endpoint gratuito: **non trovati [NV]**: il PLAN gia' lo chiede ai mentori NVIDIA.
- **Nemotron Nano 12B v2 VL**: accetta immagini e video mp4/mov/webm (no reasoning sul video); variante gratuita su OpenRouter, ma **i prompt vengono registrati dal provider**: non mandare riprese con persone o nulla di privato https://openrouter.ai/nvidia/nemotron-nano-12b-v2-vl%3Afree .
- **Gemini API**: video a 1 fps di default con timestamp ogni secondo; parametro fps per movimenti rapidi; inline conservativo < 20 MB, File API per file grandi https://ai.google.dev/gemini-api/docs/generate-content/video-understanding (le fonti discordano sui limiti: verificare).
- Strategia gia' nel PLAN: mai nel loop di controllo, timeout, backoff, ripiego. Una chiave a testa.

### 5.2 Cosa dice la ricerca sull'affidabilita'

- FailBench (13 VLM, 2 197 tentativi): migliore **0.77 balanced accuracy**, **bias sistematico verso "successo"** con evidenza ambigua, quasi caso (<0.60) su assemblaggi ricchi di contatto; il ritaglio della regione rilevante migliora il migliore di +2.4 punti https://arxiv.org/abs/2609.03611 .
- OSCAR: un giudice GPT-5 su 100 clip bilanciate: 78/100 accordo, specificita' 0.90, **richiamo 0.66** (perde un terzo dei successi) https://arxiv.org/pdf/2606.04463 (da snippet di ricerca, [NV] sul dettaglio).
- Non ho trovato un lavoro che riporti il kappa di Cohen tra VLM ed etichette umane su episodi robot: il protocollo sotto e' mio, basato su pratica standard.

### 5.3 Protocollo proposto (eseguibile con `ai/judge.py`, `ml/label.py`)

1. **Serve variabilita' di classe**: oggi tutte le 60 prese sono "non caduto" (NOTES.md). Registrare 8-10 fallimenti veri (oggetto caduto, mancato, schiacciato se la lattina lo permette, presa a vuoto) con DJI attiva, e 8-10 prese buone nuove; 3 tipi di fallimento. Senza, precisione/richiamo sulla classe "fallito" non esistono.
2. **Etichette umane cieche**: Giorgio e Tommaso etichettano separatamente senza vedere il verdetto del modello; kappa umano-umano = tetto di accordo ottenibile. Usare l'etichetta di consenso; casi in disaccordo = "ambiguo" esclusi o tenuti a parte.
3. **Metriche**: matrice di confusione, precisione e richiamo **per classe** (soprattutto la classe "fallito"), balanced accuracy, kappa vs consenso, intervallo di Wilson. Con n=60 gli intervalli sono larghi: 54/60 corretti = 90% con IC 95% circa 80-95% (calcolo mio). Dichiarare n.
4. **Controlli di bias**: opzione "unclear" obbligatoria; richiedere un timestamp come prova; temperatura 0 e 3 ripetizioni (consistenza); per confronti A/B scambiare l'ordine e tenere solo i verdetti coerenti; confronto con baseline banale (soglia su chiusura/quota del polso: il verdetto testuale attuale usa gia' statistiche delle dita).
5. **Ingresso**: griglia di 6-8 fotogrammi ritagliata sul tavolo (non il video intero), piu' sintesi numerica. Dopo ogni modifica del prompt, rivalutare sullo stesso insieme **tenuto fermo**; non ottimizzare il prompt sul test (usare 50/50 sviluppo/test, o validazione incrociata).
6. **Nemotron vs Gemini**: stessa tabella, stesso insieme; riportare anche costo/latenza.
7. Report: "il giudice ha richiamo X e precisione Y sui fallimenti con n=..., rispetto a una soglia banale Z".

---

## 6. Idee "Surprise us" realistiche per Rokoko

| # | Idea | Cosa si mostra in 5 min | Metrica vera | V | F | R | Ore |
|---|---|---|---|---|---|---|---|
| 1 | **One glove, any hand**: stessa registrazione -> Dex3 (sim MuJoCo, 3 dita) + Inspire (6 DoF, sim o reale) in split-screen, con il filtro Aalto "0 passi tagliati" | video replay + una tabella | % saturazione, max rad/tick, 0 NaN, correlazione apertura pollice-indice umana vs robot | A | A | B | 4-6 (dopo A/B sez. 1.4) |
| 2 | **Validazione ottica del Coil Pro** con DJI+ArUco | grafico traccia guanto vs traccia ottica sul quadrato, "errore medio X cm" | RMSE in cm, deriva nel tempo, per mano | A | M | M | 5 |
| 3 | **HandOff in simulazione cinematica**: policy waypoint che deriva, il guanto corregge, quota di intervento prima/dopo | video + numero | quota di intervento (n episodi, IC); non "robot autonomo" | A | M | M | 6 |
| 4 | **Presa gentile con Inspire** (se si puo'): confronto `close_cap` 0.5 vs 1.0 sulla lattina vuota | video | picco FORCE_ACT **in unita' del registro**, non N (non calibrato); lattina non deformata (osservazione) | M | M | A (hardware una sola prova) | 3 |
| 5 | **REC/STOP col gesto della mano sinistra** mentre la destra opera (bimanuale) | live | tasso di errore del gesto su N prove | M | A | B | 2 |
| 6 | Voce di stato | - | - | B | A | B | 1 |

Consiglio: 1 + 2 sono veri, misurabili e non richiedono il robot vero; 3 se resta tempo; 4 solo se Inspire disponibile e dopo la sezione 1.6.

Per "manipolazione fragile": l'unica cosa difendibile e' "limite di chiusura per profilo d'oggetto" + osservazione che la lattina non si e' deformata; i guanti non hanno sensori di forza (NOTES.md).

---

## 7. Rischi e cose da NON dichiarare nel pitch

1. **"Il robot ha afferrato / la policy e' autonoma"**: non c'e' policy su robot; la BC in anello chiuso diverge (report). Dire "traiettorie umane registrate, replay e retargeting; policy in simulazione cinematica".
2. **"Successo" = non caduto** (NOTES.md): non e' qualita' di presa. Mai usarlo come tasso di successo.
3. **Nessuna forza in Newton**: i guanti non misurano forza; FORCE_ACT dell'Inspire e' non calibrato (correlllab). Parlare di "limite di chiusura" e "registro di forza".
4. **Nessuna precisione dei guanti** senza misura ottica: Rokoko stesso dice che l'ancoraggio Coil Pro e' poco validato; dichiarare solo l'errore misurato con DJI.
5. **Pollice**: segnale inaffidabile (nostro) + punte derivate (Rokoko): la presa a 3 dita col pollice e' "interim".
6. **Simulazione = simulazione**: Menagerie non prova contatti reali; la sim Aaltonomous (Isaac) non l'abbiamo mai girata. Niente "validato in Isaac".
7. **Segni Dex3 / registri Inspire** non verificati sul robot: dire "verificato in modello MuJoCo e con regola 10%" e basta. Non dire "100% sicuro".
8. **Giudice VLM**: con 60 prese tutte buone l'accordo e' banale; dichiarare n, precisione/richiamo per classe, bias noto verso "successo".
9. **Dataset Unitree**: mai dire "addestrato su dati G1": li usiamo solo come controllo di sanita'.
10. **Doppia candidatura** Rokoko + Aaltonomous: non assumere (domanda ai mentori nel PLAN).
11. **Modello "Nemotron 3.5 Super VL"**: nome, endpoint gratuito e limiti non verificati da me.
12. **Cubo grande**: non entra nelle 3 dita Dex3: non mostrarlo come "afferrato dal G1".
13. **Privacy**: i video DJI non devono contenere volti/ambiente identificabile quando vanno a provider esterni (OpenRouter registra i prompt).

---

## 8. Cosa NON ho potuto verificare

- Manuale ufficiale Inspire (PDF: 404): registri e verso di `thumb_rotation` vengono da un README di terzi; FORCE_SET 1498 non trovato in nessuna fonte aperta.
- Se `--emit-openxr` produce gli indici attesi da xr_teleoperate; se Pinocchio/`dex-retargeting` si installa su Windows e su Mac M2.
- Tutto cio' che riguarda l'endpoint gratuito Nemotron 3.5 Super VL (id, limiti frame/rate).
- Contenuti esatti dei parquet Unitree (ho letto solo le schede); identita' dei mirror `datamentorshf`.
- Che il test MuJoCo sul pollice (proxy dei centri link) riproduca il robot reale; `thumb_0` non testato.
- Numeri di OSCAR/HumDex/FailBench: letti da abstract/snippet, non dai PDF interi. Gli ID arXiv 2603/2606/2609 sono quelli restituiti dalla ricerca.
- Il PDF Rokoko "30 minuti di dati": il sito Rokoko cita 30 min, il paper DexCap ne usa 30 per alcuni compiti e 1 h per altri (verificato sul paper).

---

## 9. Top 5 da fare domani mattina

| # | Cosa | Comandi / file nel repo | Ore | Perche' | Gate |
|---|---|---|---|---|---|
| 1 | **Pre-flight Inspire**: confermare (mentore) `thumb_rotation`, FORCE_SET, transaction-id/ACK; correggere `to_inspire` e client; aggiornare il fake server per riprodurre eco sbagliato | `robot/inspire.py`, `robot/retarget.py::to_inspire`, `python -m pytest -q tests/test_preflight.py` | 1.5-2 | e' l'unica prova su Inspire: un pollice invertito o un blocco dopo pochi secondi la sprecano | test aggiornati verdi + conferma scritta sul verso |
| 2 | **Segni Dex3 in MuJoCo + sanita' sui parquet Unitree** | nuovo `robot/check_dex3_signs.py` (snippet sez. 1.5); XML da `google-deepmind/mujoco_menagerie/unitree_g1/g1_with_hands.xml`; `hf_hub_download` solo `data/*.parquet` di PickApple | 1.5 | riduce il rischio G1 gia' accettato nel PREFLIGHT | tabella segni per 14 giunti, nota su `thumb_0` e index/middle destra da chiedere |
| 3 | **Re-solve 60 prese con `--emit-openxr` + A/B lineare vs DexPilot (Dex3 e Inspire)** | `Rokoko/src/solve_takes.py` (riga `--emit local` -> `--emit local --emit-openxr`), poi `pip install dex_retargeting` + yml di xr_teleoperate (su WSL/Mac) | 4-5 | produce le metriche di "One glove, any hand" e dice se DexPilot batte la mappatura per angoli | tabella per presa: saturazione, max rad/tick, jitter |
| 4 | **DJI + ArUco: errore del tracciato guanto+Coil Pro** su 3 prese del quadrato | `Rokoko/src/cam.py`/`take.py` (camera), `Rokoko/src/square_fit.py`, `data/setup_square.json` | 4-5 | metrica vera e utile a Rokoko; da' anche la posizione della lattina | RMSE in cm per mano, sincronizzazione con battito di mani |
| 5 | **Fallimenti etichettati + protocollo giudice** (8-10 fallimenti + 8-10 buone con video; 2 etichettatori ciechi; Nemotron e Gemini) | `python ml/label.py`, `python -m ai.judge data/episodes/`, `ai/llm.py` | 3-4 | senza fallimenti il giudice non si misura | kappa umano-umano, precisione/richiamo sui fallimenti con IC |

Totale ~14-18 ore-uomo: le voci 1-2 sono prerequisiti di sicurezza per la prova di domani (Inspire e G1); 3-5 alimentano il pitch. Se il tempo manca, fare 1, 2, 4.

---

## 10. Cinque domande per i mentori

1. **Aalto / Inspire**: sul nostro modello (RH56DFX/DFTP/...), `thumb_rotation` e' 0 = retratto e 1000 = attraverso il palmo, e a mano aperta il valore giusto e' 0? FORCE_SET e' davvero 1498 e in che unita'? IP/porta/slave id effettivi e variante RS-485 vs Modbus TCP?
2. **Aalto / G1**: l'ordine dei giunti della mano DESTRA nel vostro `hand_q` e' thumb, index, middle (come INTERFACE.md) oppure thumb, middle, index (come il wrapper di xr_teleoperate)? Il verso di `thumb_0` per sinistra e destra e' misurato? Possiamo provare 10% per dito prima del cubo?
3. **Rokoko**: `--emit-openxr` fornisce 26 giunti con il palmo in posizione 0; per xr_teleoperate/dex-retargeting l'ordine atteso e' a 25 punti senza palmo? Come ricalibrare l'yaw per sessione e quale errore e' atteso per l'ancoraggio Coil Pro (siamo disposti a darvi la validazione ottica)? Le punte delle dita sono derivate: qual e' l'errore tipico del pollice?
4. **NVIDIA**: id esatto dell'endpoint gratuito di Nemotron 3.5 Super VL, numero massimo di frame video per richiesta, limiti di rate; e' ammesso un secondo backend (Gemini) per confronto nello stesso progetto?
5. **Organizzatori**: la doppia candidatura Rokoko + Aaltonomous e' ammessa; per l'esibizione conta di piu' un numero misurato in simulazione cinematica (HandOff) o un'esecuzione sul robot reale? Scadenza reale di consegna?

---

## Fonti principali (URL)

- dex-retargeting (MIT): https://github.com/dexsuite/dex-retargeting ; dex-urdf: https://github.com/dexsuite/dex-urdf
- xr_teleoperate (Apache-2.0): https://github.com/unitreerobotics/xr_teleoperate (file letti: `assets/unitree_hand/unitree_dex3.yml`, `assets/inspire_hand/inspire_hand.yml`, `teleop/robot_control/hand_retargeting.py`)
- Menagerie G1: https://github.com/google-deepmind/mujoco_menagerie/tree/main/unitree_g1
- unitree_IL_lerobot: https://github.com/unitreerobotics/unitree_IL_lerobot ; LeRobot: https://github.com/huggingface/lerobot ; dataset v3: https://huggingface.co/docs/lerobot/lerobot-dataset-v3
- Dataset: https://huggingface.co/datasets/unitreerobotics/G1_Dex3_BlockStacking_Dataset , .../G1_Dex3_PickApple_Dataset , .../G1_Dex3_ObjectPlacement_Dataset , .../G1_Dex3_GraspSquare_Dataset ; https://huggingface.co/datasets/datamentorshf/G1_Dex3_BlockStacking_Dataset
- ACT https://arxiv.org/abs/2304.13705 e https://github.com/tonyzhaozh/act ; Diffusion Policy https://arxiv.org/abs/2303.04137 ; DART https://arxiv.org/abs/1703.09327 ; HG-DAgger https://arxiv.org/abs/1810.02890 ; DexCap https://arxiv.org/html/2403.07788v2
- Rokoko hand solving: https://sdk.rokoko.com/guides/hand-solving/ ; robotica: https://www.rokoko.com/use-cases/robotics
- Inspire (terzi): https://pypi.org/project/inspire-rh56dftp/ ; https://correlllab.github.io/rh56dfx.html
- MediaPipe Hand Landmarker: https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python
- Nemotron 3.5 Super VL: https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3_5-super-vl-120b-a12b ; Nano 12B v2 VL (OpenRouter): https://openrouter.ai/nvidia/nemotron-nano-12b-v2-vl%3Afree ; Gemini video: https://ai.google.dev/gemini-api/docs/generate-content/video-understanding
- Giudici VLM: https://arxiv.org/abs/2609.03611 (FailBench), https://arxiv.org/pdf/2606.04463 (OSCAR)
