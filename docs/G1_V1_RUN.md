# G1 V1 (senza Coil): procedura per l'unica prova sul robot vero

Policy: `g1/live_policy_v1.py`. Per ogni mano: **HOVER** 10 cm sopra l'oggetto più vicino dal suo lato → chiudi il guanto → **DESCEND** (1 s) → **GRASP** (cap per oggetto) → **LIFT** 12 cm da sola → apri il guanto → **RELEASE**.
La camera della testa trova gli oggetti **una volta**, al primo frame valido (circa 1 s; il robot resta fermo finché non finisce):

- **dove**: profondità sopra il piano del tavolo, tolto il robot stesso (modello cinematico ai giunti misurati, proiettato con `calibration.yaml`), poi `ai/locate.py` per il centro dell'oggetto;
- **cosa**: due voti. (1) `ai/perceive.py` di Tommaso (PR #149): ensemble `ai/recognize` sui ritagli (VLM se `--vlm`) più veto colore (bianco → uovo), lanciato sulla profondità con i pixel del robot azzerati. (2) Il voto geometrico di `g1/perception_v1.py`: altezza sul tavolo, impronta, bianco/arancione. Vale la regola "fragile prima": se un voto dice uovo, è uovo. Se i voti non concordano → `unknown`. Con `--perception g1` resta solo il voto geometrico (+ VLM);
- **cap** (quelli della V1 / `live_sim`): uovo 0,70; lattina vuota 1,0 (solo se il voto geometrico la vede in piedi, alta 9–20 cm, stretta e non bianca); sconosciuto 0,68; pallina 0,70 (1,0 solo con ≥ 2 voti concordi e confidenza ≥ 0,9). **Attenzione**: `ai/object_profile.py` su main dà alla lattina **0,45**. La policy usa 1,0 come da V1 e logga `ai_cap` accanto. Da decidere con Tommaso prima del giro senza limite; nel frattempo `G1_MAX_CLOSURE=0.45` limita tutte e due le mani;
- **mano**: destra = oggetto più vicino con y < 0 (frame pelvis), sinistra = y > 0.

Le etichette CLI `--right/--left` sono **override** opzionali; `--right-xy/--left-xy` sono **fallback** e **controllo**. Se la camera non vede o rifiuta l'oggetto, la policy usa la CLI con etichetta override o `unknown` (0,68): l'etichetta di un oggetto rifiutato non viene mai usata. Se camera e CLI differiscono più di `--xy-gate` (8 cm), vince la CLI.

## Cosa è verificato e cosa NO

| | stato |
|---|---|
| Runner finto, CLI fallback (`--right egg --left can_empty`) | 29,65 Hz, 0 clip, 0 blocchi, tutti gli stati |
| Runner finto + frame simulati (`--test-frames`), percezione vera (`ai.perceive` + geometria) | 29,2–29,5 Hz, 0 clip, 0 blocchi, uovo→destra 0,70, lattina→sinistra 1,0 dalla camera (anche senza --right-xy/--left-xy) |
| `--dry` sul runner finto | 29,2 Hz, 0 clip, comando costante (braccia ferme), piano completo nel log, anche dopo il reset del runner |
| `ai.perceive` da solo (solo colore, nessun VLM) | uovo 10/12 utilizzabile, lattina 0/12 (sempre `unknown`): per questo il voto geometrico |
| Banco visione MuJoCo, 24 disposizioni (`ai.perceive` + geometria, e anche solo `g1`) | etichetta uovo 24/24, lattina 23/24 (la 24ª: `unknown` 0,68, coperta dalla mano); errore xy mediano 0,2 cm (uovo) / 0,4 cm (lattina), max 2,3 cm |
| VLM (Gemma/Nemotron) | **NON verificato**: Google risponde 402 (crediti finiti), nessuna chiave Nemotron. Gli oggetti sim sono forme semplici: un VLM potrebbe non riconoscerli comunque. Il backend `color` di `ai/recognize` fallisce su Windows (`NamedTemporaryFile`), quindi i suoi voti sono ok=False |
| Camera vera, calibrazione vera, colori/luce veri, uovo marrone, lattina NOCCO | **NON verificato**. Extrinseci = URDF (provvisori, M7) |
| Fisica della presa sul Dex3 vero, piano del tavolo vero | **NON verificato** |

## Preflight (prima che lo staff avvii il runner)

1. Su `main` aggiornato: `py -3.11 -m pytest -q tests/test_perception_v1.py tests/test_perceive.py` → 9 passed.
2. `py -3.11 g1/sim/bench_vision_v1.py --n 12` → etichette corrette ed errore xy ≤ 2 cm (controllo che l'ambiente funzioni). Crea anche `data/g1sim/v1_frames.npz` (ignorato da git), che serve a `--test-frames`.
3. Prova generale sul runner finto (vedi sotto, terminali 3 e 4 con `--backend mock`), poi ferma la policy con Ctrl+C.
4. Misura con il metro, nel frame pelvis (x avanti, y a sinistra, origine sotto il bacino), il centro dei due oggetti. Mettili **non sotto le dita** della posa iniziale, circa x 0,35, y ±0,15, ad **almeno 10 cm** da qualsiasi altro oggetto (sotto i 6 cm due oggetti diventano un blob unico, etichetta `unknown` 0,68). Uovo **sdraiato**, lattina **in piedi** (la regola geometrica della lattina vuole 9–20 cm di altezza).
5. `G1_MAX_CLOSURE` impostato (vedi prima prova). Lo staff ha l'arresto d'emergenza in mano.

## Terminali (PowerShell, cartella Junction)

**Terminale 1, guanti Rokoko:**
```
rokoko-sdk --auto-stream-usb
```

**Terminale 2, guanto → UDP 14043** (all'avvio, per 8 s apri tutta la mano e chiudila a pugno pieno, più volte: è la calibrazione):
```
py -3.11 Rokoko/src/rgmp_client.py --bimanual-port 14043
```
`--bimanual-port` manda `{left, right}` per tutti e due i guanti, che è il formato letto dalla policy. Con un guanto solo: `--hand right --udp-port 14043`. Se la console operatore (PR #153) inoltra già i guanti su 14043, salta questo passo.

**Terminale 3, policy, PRIMO GIRO = DRY** (braccia e mani ferme, solo log):
```
$env:AALTO_REPO="C:\Users\giorg\Desktop\aaltonomous-humanoid"
$env:G1_MAX_CLOSURE="0.1"
py -3.11 g1/live_policy_v1.py --source udp:14043 --right-xy 0.35,-0.15 --left-xy 0.35,0.15 --host 0.0.0.0 --dry
```

**Terminale 4, controllo del log** (dopo l'avvio del runner):
```
Get-Content data\live\live_policy_v1.jsonl -Tail 5 -Wait
```

**Staff, runner reale** (sulla loro macchina):
```
python -m aaltonomous.deploy.runner --backend real --policy ws://<IP del tuo PC>:8000 --team giorgio --episodes 1
```

### Cosa guardare nel giro DRY
- Evento `PERCEPTION`: `table_z` plausibile, due oggetti con `depth_ok: true`, etichette giuste (`egg` e `can_empty` oppure `unknown`).
- Eventi `POSE`: `source: camera`, posizione entro 2–3 cm dal metro. Se compare `VISION_CLI_DISAGREE` o `VISION_REFUSED`: la policy userà la CLI con cap 0,68. Capisci il motivo prima di andare avanti.
- Righe per tick: `state` che segue il guanto (HOVER → DESCEND → GRASP → LIFT → RELEASE), `blocked: 0`, `reasons: []`, `arm_q_plan` = cosa verrebbe comandato. Le braccia del robot NON si muovono.
- L'immagine `data/live/head_latest.jpg` mostra il tavolo con i due oggetti interi (non tagliati dal bordo).

## Prima prova che si muove (10 %)

Solo se il dry è pulito. Stesso comando senza `--dry`, mano al 10 %:
```
$env:G1_MAX_CLOSURE="0.1"
py -3.11 g1/live_policy_v1.py --source udp:14043 --right-xy 0.35,-0.15 --left-xy 0.35,0.15 --host 0.0.0.0
```
- Il 10 % limita la **chiusura delle mani** (le dita si toccano appena: non può schiacciare l'uovo). Le braccia vanno comunque a ≤ 0,7 rad/s (70 % del limite del runner).
- Prima prova: **un oggetto solo**. Per l'altra mano non dare `--left-xy` e lascia vuoto il suo lato del tavolo: quella mano resta ferma (`NO_OBJECT`).
- Poi due mani, poi `G1_MAX_CLOSURE` 0,5, poi senza limite (cap per oggetto).

## Criteri di stop (Ctrl+C nel terminale 3; il runner tiene l'ultimo comando e dopo 1 s fa lo stop sicuro)

- Evento `ABORT` nel log (3 blocchi consecutivi della nostra sicurezza: tavolo, scatola di lavoro, auto-collisione, mani < 10 cm, velocità). La policy tiene già l'ultimo comando: ferma e capisci.
- Il runner segnala clip ripetuti (abort a 30 step) o `watchdog_hold` oltre il primo secondo.
- Il polso scende più in basso dell'oggetto, tocca il tavolo o va verso l'altra mano.
- Posizione dalla camera lontana più di 3 cm dal metro, o etichetta sbagliata con cap più alto del giusto (es. uovo visto come lattina, cap 1,0): niente giro che si muove.
- Qualsiasi rumore meccanico, dita che spingono sull'oggetto dopo il contatto, oggetto che scivola nel LIFT.

## Note

- Log: `data/live/live_policy_v1.jsonl` (eventi `START`, `PERCEPTION`, `POSE`, `VISION_*`, `NO_OBJECT`, `ABORT`; una riga per tick con `arm_q_target` per la console). Chiedi allo staff anche `runs/giorgio/...`.
- `--vlm auto` aggiunge i modelli con chiave nell'ambiente (la risposta arriva in ≤ 12 s, il robot aspetta fermo). Senza VLM l'etichetta viene solo da geometria e colore.
- `--test-frames` è **solo per il runner finto**: con il robot vero non va mai passato.
- Correzione rispetto alla versione precedente: i target erano nel frame sbagliato (il pelvis invece del mondo del modello, 0,79 m più in basso) e venivano schiacciati sul pavimento di sicurezza. Il braccio non saliva né scendeva davvero. Ora HOVER è a circa +10 cm e LIFT a +12 cm.
