# Vecchie simulazioni (intermedie)

## Cosa mostra
- `g1_sim.py`: controllo cinematico MuJoCo in un comando. Verifica per ogni giunto Dex3 se aumentare la chiusura chiude davvero il dito (URDF, nessuna fisica). Esito in `g1/sim/REPORT.md`: 12/14 giunti chiudono nel verso giusto, sinistra e destra sono specchi esatti per thumb_1/2; thumb_0 non viene mai comandato. Immagini: `media/left_levels.png`, `right_levels.png`.
- `grasp_physics.py`: fisica di presa con base fissa, mano destra, chiusura 0..1 su uovo, pallina, lattina (`media/egg_*.png`, `ball_*.png`, `can_*.png`, `pose.png`). Importato anche da altri script: non rimuoverlo.
- `demo_video.py`: video esplicativo `media/demo.mp4` (vista esterna + camera testa): braccia con la take 47 reale, uovo con tetto 0.70 contro senza tetto, pallina con tetto 0.60. Il video del solo braccio e `media/take_47.mp4`.

## Comando esatto
```powershell
.\sims\old\run.ps1 kinematic     # py -3.11 g1/sim/g1_sim.py
.\sims\old\run.ps1 physics       # py -3.11 g1/sim/grasp_physics.py --levels 0,0.2,...,1.0 --render
.\sims\old\run.ps1 video         # py -3.11 g1/sim/demo_video.py -> data/g1sim/demo.mp4
```

## Dati reali vs ipotesi
Reali: take di guanto + Coil (47), modello ufficiale G1 + Dex3, retargeter `robot/g1_dex3.py` non modificato. Ipotesi: guadagni servo (kp 1.5, kv 0.1), soglie di rottura (uovo 20 N, lattina 15 N), attrito 1.0, dimensioni oggetti, pallina non realmente deformabile. Base del robot fissa.

## Ultimi numeri (`g1/sim/GRASP_REPORT.md`, prime misure, mano destra)
| Oggetto | Primo contatto | Chiusura minima che tiene | Rottura (ipotesi) | Chiusura max consigliata |
|---|---|---|---|---|
| Uovo 42x56 mm, 60 g | 0.55 | 0.65 (8 N) | 0.75 (> 20 N di picco) | 0.70 (14 N) |
| Pallina 66 mm, 30 g | 0.40 | 0.50 (5 N) | nessuna | 0.60 (19 N) |
| Lattina 66x116 mm, 15 g | 0.20 | mai tenuta | 0.50 (> 15 N) | non supportata in questa postura |

La lattina con pinza laterale a tre dita viene espulsa; serviva un'altra postura (cercata poi in V1 con `grasp_search.py`). V1 e V2 hanno sostituito questi script, che restano per riferimento.

## Media
`media/demo.mp4` (circa 9.9 MB) e `media/take_47.mp4` (circa 5.7 MB) sono ignorati da git; i png sono nel repo.
