# MORNING.md: i primi 60 minuti (bozza di gemini-pro, rivista da Claude su TOMORROW.md, PREFLIGHT.md, RESEARCH_NIGHT.md)

Prima di tutto: `python tools/morning_check.py --tests` (guanti, driver, camere, GPU, git, chiavi presenti, rapporto notturno).

## (a) Primi 60 minuti, in ordine
1. **Chiavi (Tommaso):** `VERDA_INFERENCE_KEY` (o `NVIDIA_API_KEY` + `LLM_MODEL`) solo nel suo ambiente. Riuscito se `python -c "from ai.llm import ChatClient; print(ChatClient().chat([{'role':'user','content':'ping'}]))"` risponde.
2. **Mentori Aalto (Tommaso):** IP/porta/registri Inspire, modello esatto, slot G1 con Erkka. Riuscito se scritti in `robot/inspire.py` e `docs/contracts.md`.
3. **Inspire a secco (Giorgio):** `python -m robot.run_udp --backend inspire` stampa i comandi, nessun movimento; `pytest tests -q` verde. Poi, con la mano vuota e un mentore presente: `INSPIRE_FREEZE_THUMB_ROT=1`, lettura di ANGLE_ACT, chiusure al 10 %.
4. **G1 al 10 %:** `G1_MAX_CLOSURE=0.1` con `g1/glove_policy.py --source udp:14043` e il runner degli organizzatori. Riuscito se le dita chiudono nel verso atteso e il filtro non blocca nulla.
5. **Slice hardware:** `demo/run_demo.sh --real --bimanual --backend inspire --assist egg` con la lattina; video con la DJI (`CAM=<indice> python Rokoko/src/take.py`). Riuscito se un oggetto tenuto e integro e' filmato.

## (b) 5 domande ai mentori
1. **Aalto/Inspire:** `thumb_rotation` 0 = retratto e 1000 = attraverso il palmo? FORCE_SET e' il registro 1498 e in che unita'? IP di fabbrica .210 o .211? L'eco del transaction-id Modbus e' sbagliato?
2. **Aalto/G1:** ordine giunti mano destra thumb-index-middle o thumb-middle-index? Zero e verso fisico del pollice?
3. **Rokoko:** `--emit-openxr` da' 26 giunti con il palmo a 0: come mapparli sui 25 punti attesi da dex-retargeting? Come ricalibrare lo yaw per sessione?
4. **Rokoko:** errore atteso del polso ancorato al Coil Pro (siamo disposti a dare una validazione ottica con la DJI)?
5. **NVIDIA:** id esatto dell'endpoint gratuito Nemotron 3.5 Super VL, limiti di frame e rate?

## (c) Da NON dichiarare nel pitch
1. Che il robot sia autonomo (e' replay e retargeting).
2. Che "successo" misuri la qualita' della presa (significa solo "non caduto").
3. Valori di forza in Newton (Inspire non calibrata, i guanti non la misurano).
4. "Validato in Isaac" (mai eseguito) o "funziona sul G1" prima del test.
5. Precisione dei guanti o del Coil Pro senza una misura ottica; i risultati dei modelli piccoli (ciclo chiuso divergente) come policy addestrata.

## (d) Rischi hardware e contromisure gia' nel repo
1. **G1:** clip di velocita' e comandi/s sotto 27 Hz: margine 70 % sulla velocita', 3 target per chiamata (0 passi bloccati sul runner mock), tetto di chiusura `G1_MAX_CLOSURE=0.1` alla prima prova. Versi del pollice e dello zero reali ancora non verificati.
2. **Inspire:** eco Modbus errato e registri non confermati: client raw tollerante di default, handshake di sola lettura, `INSPIRE_FREEZE_THUMB_ROT=1`; l'hardware non parte se la lettura fallisce.
3. **Dati e giudice:** tutte le prese sono "non caduto": servono 5-10 fallimenti etichettati prima di misurare precision/recall.
