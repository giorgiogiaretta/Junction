# Revisione Coil G1 (15/11): due revisori + integrazione

Codice: `g1/live_policy_v2.py` (branch `claude/coil-review-vision-6c2be1`, da `g1-real-working` ca25259).
Revisori indipendenti con lo stesso brief: **Codex** (worktree `Junction-coil-codex`, branch `codex/coil-review`, workspace-write,
non esegue Python) e **DeepSeek** (`delegate`, file senza dati personali). Poi revisione incrociata: ognuno ha letto il risultato dell'altro.

## Cosa hanno trovato

| Punto | Codex | DeepSeek | Deciso |
|---|---|---|---|
| Visione in v2 | `_locate` chiama `live_policy_v1.LivePolicy._locate`, che **non esiste**: la camera non è mai stata usata, sempre CLI | idem | bug corretto (vedi sotto) |
| Cap lattina | v2 usava `demo_e2e.PROFILE` = **1.0** per can_empty, non 0.45 | idem | ora 0.45 (`perception_v1.CAP`) |
| Base dei tempi | `t = tick/RATE`: con il runner a ~100 ms per chiamata (2 target) i filtri girano a 2/3 del tempo reale (OneEuro 5→3.3 Hz, grip 40→60 ms, assist 0.4→0.6 s) | idem; la sua prima proposta `max(tick/RATE, wall)` è **pericolosa** (dt≈0 tra i 2 sub-tick → derivata OneEuro esplode); Codex propone una formula per-sub-tick che può tornare indietro | base per chiamata ancorata al wall clock, sub-tick a 1/RATE, recupero ≤ 2/RATE (formula di DeepSeek, round 2) |
| Flush del log | flush a ogni target (60/s) sul thread di controllo | idem | flush ogni 0.5 s, subito su eventi e tick bloccati |
| JPEG testa | scrittura sincrona ≤ 2 Hz (5-30 ms) | idem | thread, un solo slot |
| Registratore UDP | coda asincrona con scarto se piena | già bufferizzato, lasciarlo (perderebbe pacchetti) | **lasciato sincrono** |
| Cap stress_ball | 0.70 (`PV.CAP`) | 1.0 (non si rompe, presa debole) | **1.0**: un cap più basso fa solo scivolare la palla |
| Worker visione | thread nuovo per episodio, `import live_policy_v1` | thread nuovo = renderer MuJoCo rotto dopo un reset (bug già visto in V1); l'import di V1 riscrive `arm_ik.ARM_STEP` e fa `assert AALTO_REPO`; `shape` deve essere `[:2]`; manca la guardia di episodio; `_init` ricostruiva la catena dell'altra mano a ogni tick se una mano non aveva posa | tutte le correzioni di DeepSeek |
| Ritardo principale | runner/robot, filtri ~30-40 ms, cap articolari | idem: 0.6-1.4 s non spiegabili dai filtri | confermato dalle misure (sotto) |

## Cosa ho implementato (`g1/live_policy_v2.py`)
1. **Visione all'avvio**: dopo il percorso di start-up, UN frame RGB-D va a un worker persistente (`ThreadPoolExecutor(1)`,
   `perception_v1.perceive_with_ai` = ai.perceive + geometria, solo colore/locale, VLM opzionali con `G1_VLM=nemotron,gemma`).
   `act()` non aspetta mai: le braccia restano ferme a riposo; dopo `G1_VISION_TIMEOUT` (10 s) o senza camera (3 s) → oggetto + xy da CLI.
   Risultati di un episodio precedente scartati. Eventi `VISION` (engine, errore, latenza, etichette) e `POSE` (cap, sorgente).
2. **Cap per oggetto**: cap = cap del profilo CLI, **solo abbassato** dall'etichetta della camera; massimi rigidi egg 0.70, can_empty 0.45,
   stress_ball 1.0. Se CLI o camera dice egg → 0.70. Il cap entra nel profilo della catena, quindi vale per pre-shape e comando dita.
3. **Posizione**: dalla camera solo se `depth_ok` ed entro `G1_XY_GATE` (12 cm) dalla xy CLI, altrimenti CLI; altezza del tavolo misurata solo se entro 5 cm dal nominale.
4. **Base dei tempi** ancorata al wall clock (offline identica a prima). Il passo articolare per target (`JOINT_SPEED/RATE`) e il controllo `arm_speed` non cambiano.
5. Log: flush ogni 0.5 s (eventi subito), JPEG testa in thread; `v2_filter_test.py` ora usa questo checkout e stampa i tempi di `act()`.

Invariati: self-collision, limiti giunti/mani, `_ws_safe`, semantica `G1_FAST`, CHUNK=2, velocità, start-up.

## Numeri (prima → dopo)
| Test | Prima | Dopo |
|---|---|---|
| pytest | 215 ok, 2 fallimenti noti | 215 ok, 2 fallimenti noti (test_cv_eval, test_judge_gemini) |
| `v2_filter_test.py` normale / `G1_FAST=1` | 0 clip / 0 clip | 0 clip / 0 clip |
| `act()` offline (CHUNK 2) | media 7.2 ms, p95 12.0 | media 7.9 ms, p95 12.5 |
| replay `teleop_multi --replay 77` (stress_ball) | arm_delay 73 ms, jerk_rms 18.1, jumps 0 | identico (coil_chain invariato) |
| runner mock, `G1_FAST`, 30 s | 29.7 Hz, 0 clip, latenza 34.9 ms | 29.6 Hz, 0 clip, latenza 34.7 ms |
| ritardo polso→comando, runner lento 100 ms/chiamata, take a tempo reale | normale 140 ms, FAST 10 ms | normale 120 ms, FAST 0 ms |
| ritardo, runner 66.7 ms/chiamata (normale) | 30 ms | 10 ms |
| visione su frame sim (`v1_frames.npz`) | mai usata (bug) | etichette in 1-3 s, nessuna chiamata `act()` > 60 ms durante la visione; timeout e "niente camera" → CLI |

**Conclusione**: in FAST la policy aggiunge ~0-10 ms; i 0.6-1.4 s misurati sul robot stanno nel runner (loop a ~100 ms) e nel controllo
del braccio. Il calcolo della policy è ~4 ms per target: non è il collo di bottiglia. Resta un picco una tantum di ~200 ms per mano
quando si costruiscono le catene (`_init`, a braccia ferme; già presente prima).

## Test finale sul robot (un solo run)
Prima porta questo branch nel checkout principale (decide l'operatore), poi, palla prima dell'uovo:
```
& C:\Users\giorg\Desktop\Junction\start_g1.ps1 -Coil -Fast -NoConsole -Right stress_ball -Closure 0.6
```
Senza `-NoCamera` (serve il frame per la visione; con `-NoCamera` funziona lo stesso, oggetto da CLI dopo 3 s).
Controlla in `data/live/live_policy_v2.jsonl` gli eventi `VISION` e `POSE` (cap, source) prima di toccare l'oggetto.

## Ricevute
- Codex round 1: 84,711 token (`CODEX_REVIEW.md`); round 2: 75,878 token (`FINAL_CODEX.md`); un tentativo fallito per le virgolette nel prompt (0 token).
- DeepSeek round 1: 233 s, codice troncato nel trasporto (tabella ricevuta), ricevuta 0 token registrati; round 2: 37,469 in + 39,832 out = 77,301 token, $0 (quota gratuita), 195 s.
