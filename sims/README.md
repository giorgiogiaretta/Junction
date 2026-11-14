# Simulazioni G1 (MuJoCo)

Tutte le simulazioni usano il modello ufficiale G1 29-DoF + mani Dex3 in MuJoCo. Il codice sta in `g1/sim/` (non spostato); qui ci sono README, launcher `run.ps1` e `media/`.

| Versione | Cartella | Input | Cosa mostra | Script reale |
|---|---|---|---|---|
| V1 senza Coil | [v1_no_coil](v1_no_coil/README.md) | guanto Rokoko (solo dita), camera testa | la camera trova l'oggetto, chiudere il guanto fa scendere il robot, presa con tetto per oggetto, sollevamento, rilascio | `g1/sim/live_sim.py`, `demo_e2e.py` |
| V2 con Coil | [v2_coil](v2_coil/README.md) | due guanti + Coil (posizione/orientamento polso) | due mani, uovo a destra e lattina vuota a sinistra, grafico forze live | `g1/sim/teleop_multi.py` |
| Vecchie | [old](old/README.md) | take registrate | prime verifiche cinematiche, fisica di presa, video esplicativo | `demo_video.py`, `grasp_physics.py`, `g1_sim.py` |

## Cronologia (14/11)
1. Mattina: `g1_sim.py` verifica cinematica dei giunti Dex3, poi `grasp_physics.py` (fisica di presa, chiusura minima/massima per oggetto), `demo_video.py` e video del braccio con take 47.
2. Primo pomeriggio: V1, pipeline end-to-end (`demo_e2e.py`, `perceive.py`, `live_sim.py`) con tetto di chiusura per oggetto (uovo 0.70, pallina e lattina 1.0).
3. Poi: `grasp_search.py` (postura di presa per oggetto) e `coverage.py` (mappa di dove il robot vede e afferra).
4. Dopo: V2 con Coil, `teleop_sim.py` e `teleop_multi.py` (due mani, due oggetti).

## Media
I file `.mp4` sono ignorati da git (`.gitignore`, `sims/**/media/*.mp4`): restano su disco. Per rigenerarli lanciare i `run.ps1`. Immagini e json piccoli sono nel repo. Dati originali: `data/g1sim/` (non versionato).

Tutto e simulato: forze, guadagni dei servo, soglie di rottura e dimensioni degli oggetti sono ipotesi, non misure sul robot.
