# V2: con Coil (due mani, uovo + lattina)

## Cosa mostra
Teleoperazione completa in simulazione: due guanti Rokoko + Coil Pro muovono entrambe le braccia G1 (IK a 7 gradi di liberta) e le mani Dex3. Sul tavolo ci sono un uovo (destra) e una lattina vuota (sinistra). La camera della testa localizza ogni oggetto e ogni mano usa il profilo dell'oggetto piu vicino: uovo, chiusura mai sopra 0.70 comunque tu stringa; lattina, fino a 1.0 e si ammacca se stringi forte. Aiuto alla presa vicino all'oggetto, offset congelato a presa chiusa. Finestra "forze" con la forza di contatto di sinistra e destra e le soglie di rottura/ammaccatura. Tasti: A/C allinea e ri-centra, R reset scena, Q esci.

## Comando esatto
```powershell
.\sims\v2_coil\run.ps1                  # = py -3.11 g1/sim/teleop_multi.py --cam   (driver Rokoko attivo, guanti + Coil)
.\sims\v2_coil\run.ps1 --calib          # rifa la calibrazione del tavolo
.\sims\v2_coil\run.ps1 --objs "egg:0.35,-0.15;can_empty:0.35,0.15" --cam
```
Opzioni utili: `--hands both|right|left`, `--gain`, `--smooth`, `--seconds`, `--headless`.

## Dati reali vs ipotesi
- Reali: pose dei guanti e della Coil (stream dal vivo), calibrazione assi (`data/arm_calib.json`, serie K, uguale per i due guanti), modello G1 + Dex3, limiti e filtri degli organizzatori.
- Ipotesi: soglie (uovo si rompe a 20 N, lattina si ammacca a 15 N; l'ammaccatura e solo visiva: il raggio si riduce), guadagni servo, attrito, dimensioni oggetti. Non verificati: posture di presa della mano sinistra (specchiate dalla destra), calibrazione del guanto sinistro, latenza reale dello stream Coil.

## Ultimi numeri
Nessuna sessione V2 registrata finora, quindi nessun numero. Le posture di presa vengono da `g1/sim/grasp_postures.json` (ricerca V1).

## Media: come registrare una sessione
Nessuna registrazione presente. Per farne una:
1. Lancia `.\sims\v2_coil\run.ps1` con finestre MuJoCo, camera e "forze" visibili.
2. Registra lo schermo (Win+Alt+R della Xbox Game Bar, oppure OBS) mentre fai: ri-centra con C, afferra l'uovo con la destra (non deve rompersi), afferra la lattina con la sinistra, solleva, rilascia.
3. Salva l'mp4 in `sims/v2_coil/media/` (gli mp4 sono ignorati da git) e annota data e numeri (picco forze, uovo integro, lattina ammaccata) in questo README.
