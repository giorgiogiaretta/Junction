# V1: senza Coil (guanto Rokoko + camera)

## Cosa mostra
- La camera della testa (D435i simulata, 640x480) trova l'oggetto (`perceive.py`).
- HOVER: la mano robot sta aperta 10 cm sopra l'oggetto. Quando chiudi il guanto (> 30% della tua presa abituale) il robot scende (DESCEND), poi chiude (GRASP) con chiusura = tetto dell'oggetto x (tua presa / tua presa abituale): uovo tetto 0.70, pallina e lattina vuota 1.0. Senza Coil non c'e la posizione del polso: il robot solleva da solo di 12 cm 1.5 s dopo la chiusura (LIFT). Apri il guanto e rilascia.
- Scenari video (`demo_e2e.py`): `egg_profile` (con tetto), `egg_naive` (mappatura diretta), `egg_nolimit` (senza tetto, l'uovo si rompe), `ball_profile`, `can_profile`.
- Ricerca della postura di presa per oggetto (`grasp_search.py`) e mappa di copertura sul tavolo (`coverage.py`).

## Comando esatto
```powershell
.\sims\v1_no_coil\run.ps1                          # = py -3.11 g1/sim/live_sim.py --obj egg --replay 77 --cam
.\sims\v1_no_coil\run.ps1 live --obj egg --cam     # guanti dal vivo (driver rokoko-sdk attivo)
.\sims\v1_no_coil\run.ps1 e2e                      # tutti gli scenari -> data/g1sim/e2e/
.\sims\v1_no_coil\run.ps1 e2e --only egg_profile
.\sims\v1_no_coil\run.ps1 search                   # g1/sim/grasp_search.py
.\sims\v1_no_coil\run.ps1 coverage                 # g1/sim/coverage.py
.\sims\v1_no_coil\run.ps1 perceive                 # banco di prova percezione
```

## Dati reali vs ipotesi
- Reali: sessione Coil del 14/11 (guanto destro: dita, posizione e orientamento polso, 30 Hz), calibrazione assi braccio (`data/arm_calib.json`), frame DJI della stessa take, modello ufficiale G1 + Dex3, numeri dell'interfaccia degli organizzatori (home pose, banco z 0.01, limiti 1 rad/s braccio e 3 rad/s mano).
- Ipotesi: guadagni dei servo Dex3 (kp 1.5), soglie di rottura (uovo 20 N, lattina vuota ammaccata sopra 15 N), attrito, dimensioni degli oggetti, offset del sensore al polso. In simulazione il rilevatore e il colore dell'oggetto (sul robot: il detector di Tommaso). Le forze sono output del modello, non misure.

## Ultimi numeri
Da `media/e2e_run.log` (esecuzione completa, 15:07) e `media/e2e_report.json` (ultima esecuzione, 15:08, solo `can_profile`):

| Scenario | Tetto | Chiusura max | Picco forza | Sollevato | Esito |
|---|---|---|---|---|---|
| egg_profile (take 77) | 0.70 | 0.70 | 21.7 N | 17.6 cm | tenuto e sollevato, non rotto |
| egg_naive | 0.70 | 0.33 | 0 N | 0 cm | non afferra (chiusura troppo bassa) |
| egg_nolimit | 0.70 | 1.00 | 32.5 N | 0.9 cm | uovo rotto |
| ball_profile (take 82) | 1.0 | 1.00 | 74.9 N | 12.0 cm | tenuta e sollevata |
| can_profile (take 86), run completa | 1.0 | 1.00 | 81.0 N | 5.0 cm | non tenuta, ammaccata |
| can_profile, ultima run (`e2e_report.json`) | 1.0 | 1.00 | 90.6 N | 6.1 cm | tenuta e sollevata, ammaccata |

Errore di percezione: uovo 1.4 cm, pallina 1.31 cm, lattina 0.41 cm. Errore IK mediano 0-1 cm; nessun tick di sicurezza segnalato.

Banco percezione (`media/perceive_bench.json`, 20 posizioni per oggetto): uovo visibile 19/20, errore xy mediano 0.1 cm (max 2.12); pallina 19/20, 0.15 cm (max 2.26); lattina 20/20, 0.7 cm (max 1.34).

Copertura del tavolo (`coverage.py`, 117 celle; `data/g1sim/coverage/coverage.json`): uovo visibile in 84 celle, tenuto in 30; pallina visibile in 95, tenuta in 26. Errore di percezione mediano 0.11 cm (uovo, max 2.23) e 0.20 cm (pallina, max 3.22). Mappe: `media/egg.png`, `media/stress_ball.png`, `media/both.png`.

Ricerca postura (`g1/sim/grasp_postures.json`): uovo 10 prese su 648 prove (robustezza 0.5 sulla migliore), pallina 5/864, lattina 49/648.

## Media
`media/*_profile.mp4`, `egg_naive.mp4`, `egg_nolimit.mp4` (circa 11-13 MB ciascuno, ignorati da git), `*_headcam.jpg`, mappe di copertura `.png`, report json e log.
