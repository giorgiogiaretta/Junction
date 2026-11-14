# G1: guida completa (14/11 sera)

## 0. Cosa unire, in quest'ordine
1. **#146** `collection-ready`: base di tutto (V1 iniziale, simulazioni, filtri, collisioni).
2. **#154** `v1-vision`: V1 con la visione. Corregge l'errore di riferimento del braccio (bacino/mondo) della prima V1.
3. **#156** `v2-coil`: V2 con Coil, catena `g1/coil_chain.py` e simulazione precisa.
4. **#153** `operator-console`: console operatore (`tools/console/app.py`).
5. **#148** `sim-folders`: cartelle `sims/v1_no_coil`, `sims/v2_coil`, `sims/old`.

Dopo ogni unione esegui `py -3.11 -m pytest -q tests`. I 2 test di Gemini e della visione falliscono solo su questo PC, per librerie mancanti.

## 1. Simulazioni (per provare e presentare)
| Versione | Comando | Cosa mostra |
|---|---|---|
| V1 senza Coil | `sims\v1_no_coil\run.ps1` (oppure `py -3.11 g1/sim/live_sim.py --obj egg --cam`) | la camera trova l'oggetto; il guanto chiuso fa scendere, prendere e sollevare il robot |
| V1, scenari video | `sims\v1_no_coil\run.ps1 e2e` | uovo con profilo, 1:1 e senza limite; pallina; lattina; video in `sims/v1_no_coil/media` |
| V2 con Coil | `py -3.11 g1/sim/teleop_multi.py --cam --calib` (prima volta), poi senza `--calib` | due mani, uovo + lattina, zona lenta attorno all'uovo, grafico delle forze |
| V2, replay misurato | `py -3.11 g1/sim/teleop_multi.py --replay 77,86 --metrics` | ritardo, jerk, blocchi, presa riuscita prima/dopo |

Postura dell'operatore: **seduto di fianco al robot, guanti appoggiati piatti sul tavolo** all'avvio (per la V2 questa è la posa di riposo del robot).

## 2. Robot: check iniziali (con la console)
1. `py -3.11 tools/console/app.py`, poi **Esegui tutti i check**. Devono essere tutti verdi:
   - driver Rokoko raggiungibile;
   - entrambi i guanti a circa 83 Hz (29 Hz se in replay);
   - per la V2: Coil al 100 %, saturazione 0 %, nessun ribaltamento;
   - calibrazione delle dita presente (`data/calib.json`);
   - calibrazione delle braccia recente (per la V2: **Calibra (Coil)** sul posto);
   - IP del PC runner raggiungibile (chiedilo allo staff);
   - porta 8000 libera prima dell'avvio.
2. **Prova generale (mock)** dalla console: `command_hz` sopra 27, `clipped 0`, `blocked 0`.
3. **Guanti:** nella console lo scheletro deve seguire le dita. Con il Coil, le mani devono stare entro circa 1 m dal Coil.
4. **Camera:** dopo l'avvio della policy, il pannello "camera testa" deve mostrare il fotogramma vero (`data/live/head_latest.jpg`).

## 3. Test V1 (senza Coil): quello raccomandato
Dettagli in `docs/G1_V1_RUN.md`.
1. **A secco:** policy V1 con `--dry`. Il robot non si muove; nel log controlla oggetti riconosciuti, posizioni (sorgente `camera`) e limiti (uovo 0,70, lattina: decidere tra 0,45 e 1,0).
2. **Al 10 %:** slider `G1_MAX_CLOSURE` a 0,1, poi **AVVIA POLICY V1**; lo staff avvia il runner reale.
   - Mano destra: chiudi piano, il robot scende sull'uovo e le dita devono chiudersi verso l'oggetto. **Se il pollice va al contrario: STOP.**
   - Poi la sinistra sulla lattina.
3. **Profilo pieno:** solo con l'ok dello staff. Prima una mano alla volta, poi entrambe.

## 4. Test V2 (con Coil)
Dettagli in `docs/G1_V2_RUN.md`.
1. **Calibrazione da seduto** (`--calib`): mani piatte, avanti, sinistra.
2. **A secco**, poi al 10 %, poi profilo pieno. Muoviti lentamente. Il robot si riallinea da solo quando appoggi le mani ferme per 1 s.
3. **Programmi:** `rgmp_client --hand any` sulla porta UDP 14044 (polso + dita). La console usa la 14043.

**Ancora da verificare con la V2:**
- il driver Rokoko con due lettori contemporanei;
- l'ordine del quaternione di `rgmp_client`;
- la lattina, che in simulazione scivola ancora.

## 5. Arresto
- **STOP rosso** nella console, oppure Ctrl+C: la policy si ferma.
- Arresto di emergenza dello staff.

**Si interrompe subito se:**
- compare un comando bloccato dal runner;
- `ABORT` nel log;
- meno di 25 comandi al secondo;
- oggetto spinto via;
- dita al contrario;
- uno scatto.

## 6. Cosa NON è verificato
- fotogrammi veri della camera e calibrazione reale della camera (oggi provvisoria, dal modello URDF);
- verso del pollice del Dex3 reale;
- altezza reale del tavolo;
- riconoscimento con il modello visivo (Gemma senza crediti, Nemotron senza chiave);
- prese fisiche reali: le simulazioni usano guadagni e soglie ipotizzati.
