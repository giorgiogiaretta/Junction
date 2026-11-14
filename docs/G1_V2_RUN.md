# G1 V2 con Coil: come si usa (simulatore e robot vero)

V2 = le braccia del G1 seguono i polsi dell'operatore (Coil Pro), i guanti Rokoko comandano le dita. Il simulatore (`g1/sim/teleop_multi.py`) e la policy per il runner (`g1/live_policy_v2.py`) usano **la stessa catena** (`g1/coil_chain.py`): stessi filtri, stessa mappatura, stesso aiuto alla presa, stessi limiti.

## Posizione dell'operatore
- Seduto **accanto al robot**, rivolto nella stessa direzione.
- All'avvio entrambi i guanti sono **appoggiati piatti e fermi sul tavolo**: quella posa corrisponde alla posa di riposo del robot, con le mani sopra il bancone. Il robot non si muove finché la mano non è rimasta ferma per 1 s ("waiting: hand flat + still on the table").
- Far scorrere la mano **in avanti** sul tavolo porta la mano del robot verso il suo oggetto, e intanto **scende** all'altezza di presa: è come un tavolo virtuale inclinato, perché tu non puoi scendere sotto il tuo tavolo, mentre il robot deve scendere sotto la sua quota di riposo. Sollevando la mano, il robot solleva.
- Mentre ti avvicini all'oggetto, l'orientamento neutro (mano piatta) passa gradualmente da quello di riposo a quello di presa.
- **Ri-ancoraggio automatico:** ogni volta che una mano resta ferma, aperta e appoggiata sul tavolo per 1 s, l'ancora viene ripresa e la deriva del Coil si azzera. La correzione viene distribuita su 1 s, senza scatti. La quota viene sempre corretta; posizione e rotazione solo se sei entro 6 cm dal punto di partenza.
- Muoviti **lentamente**: le giunture sono limitate a 0,7 rad/s (il runner ammette 1 rad/s) e il passo viene scalato senza piegare la traiettoria.

## Calibrazione corta (una volta per posizione del Coil, circa 12 s per mano)
Mano piatta e ferma, poi scorri avanti di ~15 cm, torna indietro, poi scorri a sinistra di ~15 cm (segui i bip).
- Simulatore: `py -3.11 g1/sim/teleop_multi.py --calib --cam`
- Robot (con `rgmp_client` acceso, vedi sotto): `py -3.11 g1/live_policy_v2.py --source udp:14044 --calib`

Il risultato viene salvato in `data/arm_calib.json`, sotto `"seated"`. Si salvano solo gli assi: il punto di partenza si riprende da solo a ogni avvio.

## Simulatore
```
py -3.11 g1/sim/teleop_multi.py --cam                       # live, uovo a destra e lattina a sinistra
py -3.11 g1/sim/teleop_multi.py --replay 77,86 --metrics out.json [--legacy]   # prova scriptata, senza guanti
```
Tasti: A/C = ri-ancoraggio manuale (poi mani piatte e ferme per 1 s), R = reset della scena, Q = esci.

## Robot vero: cosa deve girare
1. Driver Rokoko: `rokoko-sdk --auto-stream-usb`
2. **rgmp_client per V2** (polso + dita di entrambe le mani, un pacchetto per guanto):
   `py -3.11 Rokoko/src/rgmp_client.py --hand any --udp-port 14044`
   - La console operatore (PR #153) legge il driver per conto suo e manda **solo le dita** su UDP 14043. V2 ha bisogno anche del polso, per questo usa una **porta diversa (14044)**: così i pacchetti della console, che non hanno il polso, non si mescolano con quelli di V2.
   - **Da verificare:** il driver Rokoko accetta due client TCP contemporanei (console + rgmp_client)? Se non li accetta, durante la prova V2 spegnere il lettore guanti della console, oppure farle inoltrare anche `wrist_position` / `wrist_quaternion`.
   - Lo stream `--bimanual-port` porta solo le dita, quindi non basta per V2.
3. Policy:
   `G1_MAX_CLOSURE=0.1 py -3.11 g1/live_policy_v2.py --source udp:14044 --right egg --left can_empty --right-xy 0.35,-0.15 --left-xy 0.35,0.15 [--dry] [--host 127.0.0.1] [--port 8000]`
   - `--dry`: calcola e registra tutto, ma comanda la posa misurata, quindi il robot resta fermo. Da usare per il primo controllo con l'operatore vero.
   - Gli oggetti vengono dalla camera (`ai/locate.py`); se dopo 3 s non c'è un'immagine, si usano gli xy da riga di comando (frame pelvis, in metri).
4. Runner (finto: `py -3.11 g1/run_mock_gate.py --policy ws://localhost:8000 --team giorgio --episodes 1`).

Log per tick: `data/live/live_policy_v2.jsonl` (arm_q_target 14, hand_q 14, stati, blocchi). Immagine della testa: `data/live/head_latest.jpg` (al massimo 2 Hz, scrittura atomica), per la console.

## Sicurezza (ad ogni tick, prima di inviare)
Si controllano: limiti dei giunti del filtro, scatola di lavoro e zona vietata sopra il bancone (polso e palmo), collisioni del robot con sé stesso, palmi distanti più di 10 cm, velocità dei giunti rispetto all'**ultimo comando** ≤ 0,7 rad/s. Si inviano 3 target per chiamata.
- Se un controllo fallisce, entrambe le braccia restano sull'ultimo comando.
- **3 blocchi consecutivi → HOLD** fino alla fine dell'episodio. Il runner annulla a 30.
- Vicino all'uovo: al massimo 6 cm/s (3 cm/s entro 6 cm) e giunti a 0,3 rad/s. Chiusura dell'uovo ≤ 0,70.
- Finché il polso non è davvero nella posa di presa, le dita si chiudono solo fino a metà del limite. Mentre tieni l'oggetto, il robot non lo spinge contro il bancone.

## Cosa è cambiato (sezione A del piano di test)
| | prima | ora |
|---|---|---|
| A1 filtri | One Euro 0,7 Hz, presa 150 ms | One Euro 2,5 Hz adattivo, presa 50 ms |
| A2 velocità | limite cartesiano + 1 rad/s per giunto (taglio) | 0,7 rad/s, passo scalato (direzione mantenuta) |
| A3 aiuto/presa | aiuto 3 cm, presa a 4 cm (salto) | peso continuo fino alla posa di presa, limitato in velocità; la presa scatta dopo 2 tick |
| A4 postura naturale | on/off | sfuma in 0,5 s |
| A5 oggetto | il più vicino, ricalcolato ogni tick | uno per mano, fisso |
| A6 deadband | 3 mm dopo il filtro | guinzaglio continuo da 1,5 mm sul segnale grezzo |
| A7 primo tick | orientamento e ancora di presa | posa di riposo, mano piatta = neutro |
| A8 blocchi | rialzo su qualsiasi blocco | rialzo solo per il bancone; poi solo traslazione, poi +2 cm |
| in più | – | limitatore finale del target (0,30 m/s, 150°/s), nessun salto di stato |

## Numeri (replay scriptato, simulatore, 14/11)
Le prese registrate (take 77 uovo, take 86 lattina, mano destra) mantengono i tempi, il rumore e la presa reali. Lo spostamento di avvicinamento viene ruotato e scalato in modo da arrivare 2 cm sopra la posa di presa (sono prese registrate con un'altra impostazione, quindi è un **allineamento sintetico**). In entrambi i casi si aggiungono 1,5 s di mano ferma all'inizio.

| take | catena | ritardo filtro | jerk RMS (m/s³) | salti > 1 cm/tick | vel. max giunti | blocchi | presa |
|---|---|---|---|---|---|---|---|
| 77 uovo | prima | 197 ms | 66,6 | 9 | 1,0 rad/s | 0 | no (sollevato 0,1 cm) |
| 77 uovo | **ora** | **20 ms** | **22,3** | **0** | 0,7 rad/s | 0 | **sì** (sollevato 3,7 cm, intatto) |
| 86 lattina | prima | 190 ms | 141,0 | 22 | 1,0 rad/s | 0 | no (ammaccata 14 %) |
| 86 lattina | **ora** | **23 ms** | **13,0** | **0** | 0,7 rad/s | 0 | no (sollevata 0,5 cm, ammaccata 19 %) |
| 77 + 86 (due mani) | prima | 197 / 190 ms | 58,0 / 141,0 | 9 / 21 | 1,0 | 0 | uovo no, lattina no |
| 77 + 86 (due mani) | **ora** | **20 / 23 ms** | **19,2 / 12,4** | **0 / 0** | 0,7 | 0 | **uovo sì** (4,3 cm), lattina no |

Note sui numeri:
- **Ritardo del target:** vicino all'uovo è più alto di proposito (limite di 3–6 cm/s nella zona fragile).
- **Ritardo del braccio:** con 0,7 rad/s scalati, il braccio arriva in ritardo sulle rotazioni grandi (0,08–0,45 s).
- **Lattina:** nel take 86 l'operatore stringe a 0,8, quindi la chiusura arriva a 1,0; la lattina si ammacca e scivola (anche nell'originale il take è "crushed"). Il sollevamento della lattina in simulazione resta da migliorare.

Runner finto con `--source replay:77,86`: **29,07 comandi/s, 0 clip, 0 blocchi**, 900 tick, cicli presa/tenuta/rilascio su entrambe le mani.

## Non ancora verificato
- Con l'operatore vero e il Coil (il formato del quaternione da `rgmp_client` è "assunto" xyzw→wxyz).
- Due client contemporanei sul driver Rokoko.
- Le posizioni della camera vera via `ai/locate.py`: V2 assume il frame pelvis e le converte in mondo con `kin.base`.
- Il robot fisico.
