# G1 dal vivo: l'unico tentativo (guanto + camera del robot)

**Cosa succede:** il G1 resta fermo con le braccia nella posa misurata all'avvio, quindi non le muove. Al primo fotogramma della sua camera in testa (RealSense D435i) la policy chiede una volta sola "che oggetto è?". La chiusura della mano destra Dex3 segue il tuo guanto destro, ma arriva fino al limite di quell'oggetto:

| Oggetto riconosciuto | Chiusura massima del G1 | Tua presa "tipica" che la raggiunge (dati del 14/11) |
|---|---|---|
| uovo | 0,70 (delicato; in sim tiene da 0,65, si rompe sopra 0,75) | 0,29 |
| pallina antistress | 1,0 (forza piena; in sim non si rompe) | 0,36 (presa forte) |
| lattina vuota | 1,0 (forte; si può ammaccare) | 0,52 (presa forte) |
| sconosciuto, errore, nessuna risposta | 0,68 (prudente) | 0,30 |

Formula: chiusura G1 = limite × min(1, tua chiusura / tua presa tipica), con la chiusura media di indice e medio. Il codice è `g1/live_policy.py`.

## Prima di andare (sul tuo PC, 2 minuti)
1. Prova generale con il runner FINTO degli organizzatori, uguale al robot vero ma senza robot. Due terminali PowerShell, nella cartella Junction:
   ```powershell
   py -3.11 g1/live_policy.py --source replay:77 --object egg
   ```
   ```powershell
   $env:AALTO_REPO="C:\Users\giorg\Desktop\aaltonomous-humanoid"; py -3.11 g1/run_mock_gate.py --policy ws://localhost:8000 --team giorgio --episodes 1 --time-limit 20
   ```
   Deve finire con `clipped_steps: 0` e `command_hz` circa 30. Risultato del 14/11: uovo (take 77) 29,9 Hz e 0 clip; pallina forte (take 82, `--object stress_ball`) 29,8 Hz, 0 clip, chiusura che arriva a 1,0.
2. Chiudi la policy (Ctrl+C).

## Al robot: 3 terminali sul tuo PC, più il comando dello staff
Nella cartella Junction, guanto DESTRO sulla mano (il sinistro non serve).

**Terminale 1, driver dei guanti:**
```powershell
rokoko-sdk --auto-stream-usb
```

**Terminale 2, guanto verso UDP 14043:** appena parte, per 8 secondi apri la mano del tutto e chiudila a pugno pieno, più volte. È la calibrazione e deve coprire tutta l'escursione.
```powershell
py -3.11 Rokoko/src/rgmp_client.py --hand right --udp-port 14043
```

**Terminale 3, policy.** Prima prova al 10 % di chiusura:
```powershell
$env:G1_MAX_CLOSURE="0.1"; py -3.11 g1/live_policy.py --source udp:14043 --hand right --host 0.0.0.0
```
- Se lo staff fa girare il runner su un'altra macchina: `--host 0.0.0.0` e dagli l'indirizzo `ws://<IP del tuo PC>:8000`. Se gira sul tuo PC: togli `--host 0.0.0.0` e l'indirizzo è `ws://localhost:8000`.
- Per **forzare l'oggetto** senza modello (se la rete o Nemotron non vanno): aggiungi `--object egg` (oppure `stress_ball`, `can`, `none`). Il limite di chiusura viene solo da `ai.object_profile.cap_for` (una sola tabella): pallina e lattina arrivano a 1,0 solo se l'oggetto lo imposti tu con `--object` (o con conferma di 2 riconoscitori); un modello da solo dà al massimo il limite condiviso 0,70; l'uovo non supera mai 0,70.

**Staff, runner reale** (lo lanciano loro, sulla loro macchina):
```
python -m aaltonomous.deploy.runner --backend real --policy ws://<IP del tuo PC>:8000 --team giorgio --episodes 1
```

## Sequenza della prova
1. Oggetto davanti al G1, inquadrato dalla sua camera in testa. Mano del robot aperta, la tua mano aperta.
2. Lo staff avvia il runner. Nel terminale 3 compare `[live] picker -> ... => {'object': ..., 'max_closure': ..., 'why': ...}`, di solito entro 20–60 s. Finché non risponde, il profilo è quello prudente (0,68).
3. Lo staff mette l'oggetto nella mano del G1 (le braccia non si muovono). Tu chiudi la mano lentamente: il G1 chiude fino al limite dell'oggetto.
4. Al 10 % la mano si muove appena: serve a vedere che le dita vanno nel verso giusto. Se è tutto giusto, ripeti con `$env:G1_MAX_CLOSURE="1.0"`. Il secondo giro va concordato con lo staff, perché il tentativo è uno solo.

## Piano di abbandono
- Qualsiasi cosa strana: Ctrl+C nel terminale 3. Il runner tiene l'ultimo comando e dopo 1 s fa lo stop sicuro (watchdog). Lo staff ha l'arresto d'emergenza.
- Oltre 30 comandi bloccati dal filtro, l'episodio si chiude da solo.
- Se le dita chiudono nel verso sbagliato (pollice): STOP, e non riprovare senza correggere `robot/g1_dex3.py` (di Tommaso).

## Dopo
- `data/live/live_log.jsonl`: per ogni tick oggetto, risposta del modello, tua chiusura g, chiusura del robot c e comandi alle mani.
- `data/live/head_*.jpg`: il fotogramma che il modello ha visto.
- I log del runner (`runs/giorgio/...`) li ha lo staff: chiedi una copia.

## Cosa NON è verificato
- **Mai provato sul robot vero:** verso del pollice, zero dei motori, latenza della camera.
- **La chiamata al modello non è stata provata dal vivo da questo PC.** Nemotron/Verda oggi non risponde. Nel branch locale `ai/pick_profile.py` è la versione vecchia, senza riserva Gemini e senza regole di sicurezza: serve il merge di main (PR di Tommaso #87). Senza risposta si usa il profilo prudente, oppure `--object`.
- Il runner finto ha la camera NERA, quindi il riconoscimento lì non scatta. Testati: la mappatura dalla risposta del modello all'oggetto (uovo, pallina, lattina, fallback) e la catena guanto → mani con 0 clip a 30 Hz.
- **Scala del guanto:** i valori di presa tipica vengono dagli episodi (calibrazione E). Dal vivo `rgmp_client` usa la sua calibrazione di 8 s. Se apri e chiudi tutta la mano le scale sono simili, ma non è misurato.
- Il controllo dell'area di lavoro (Pinocchio) è saltato nel runner finto su Windows. Va bene solo perché le braccia non si muovono.
- I limiti di chiusura vengono dalla simulazione (guadagni e soglie di rottura ipotizzati). `g1/object_profiles.json` contiene ancora i vecchi valori per pallina (0,60) e lattina (non supportata): `live_policy.py` usa la sua tabella per pallina e lattina vuota, e prende dal json solo il limite dell'uovo.
- Braccia guidate dal guanto: NON incluse (TODO `--arms glove`, `g1/arm_ik.py`).
