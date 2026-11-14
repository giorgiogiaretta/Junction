# Raccolta dati con Coil + guanti per il G1 (2-4 ore)

Obiettivo: prese di uovo, pallina antistress e lattina, riuscite e fallite, con la camera in testa. Queste prese alimentano tre cose:
1. la replica sul G1 in simulazione (braccia + mani);
2. il riconoscimento dell'oggetto (Tommaso, `ai/`);
3. i limiti di chiusura per oggetto (`g1/object_profiles.json`).

## Prima di iniziare (10 min)
- [ ] Driver `rokoko-sdk --auto-stream-usb` acceso, guanti e Coil collegati. `python tools/morning_check.py` mostra 2 guanti.
- [ ] Coil fisso sul tavolo, a circa 50-100 cm dalle mani e lontano da metallo e telefoni. Il Coil non si sposta per tutta la sessione: se si sposta, rifai la serie K.
- [ ] Camera sul supporto da testa, indice trovato con `python Rokoko/src/cam.py --list`. L'oggetto deve essere inquadrato quando lo guardi.
- [ ] Segno sul tavolo per la posizione dell'oggetto. Uovo crudo? Meglio sodo o finto per le prove di schiacciamento: decidetelo prima.
- [ ] Misura i 3 oggetti (diametro e altezza) e pesali. Se possibile misura con una bilancia da cucina la forza che crepa l'uovo e ammacca la lattina. Sono i numeri da mettere in `g1/sim/grasp_physics.py`.

Avvio: `CAM=<indice> CAMPOS=head OPERATOR=giorgio python Rokoko/src/take.py`. Dopo ogni take il programma controlla i dati: se compare `!!!`, premi U per annullare la take e rifalla.

## Ordine della sessione
| Blocco | Serie | Quante | Note |
|---|---|---|---|
| 1. Calibrazione | E (aperta/pugno) x2, K (assi braccio) x2 per mano, S (sincronia) x1 | ~10 min | Senza K la replica del braccio usa una stima. Con la sinistra la stima vecchia fa collidere il braccio con il corpo. |
| 2. Prese buone | O, per oggetto 15 riuscite con la destra | ~45 min | Guarda l'oggetto 1 s prima di prenderlo. |
| 3. Fallimenti voluti | O, per oggetto 5 caduto + 5 scivolato + 3 schiacciato + 2 mancato | ~40 min | Dopo STOP dichiari l'esito (C, S, X, M). |
| 4. HandOff | P, 5 per oggetto | ~20 min | Errore voluto 2-3 s, poi correzione. |
| 5. Se resta tempo | O con la sinistra e con un altro operatore (`OPERATOR=...`) | | |

Totale per 2 ore: circa 45 riuscite + 45 fallite + 15 HandOff. Con 4 ore si raddoppiano i blocchi 2-3.

## Come muoversi (dalla replica sulle take vecchie)
- **Lentamente.** Il runner limita le braccia del G1 a 1 rad/s. Con i movimenti delle take vecchie il braccio simulato era al limite per il 64-93 % del tempo, con 5-8 cm di errore mediano. Senza limite l'errore sarebbe stato 0,3 cm. Muoviti a circa metà della velocità normale, soprattutto nelle rotazioni del polso.
- Resta nella zona di lavoro: mani tra 50 cm e 1,1 m dal Coil (oltre si degrada, dalla prova YAAK/Rokoko).
- Pollice, indice e medio: il Dex3 ha solo queste tre dita. Anulare e mignolo vengono ignorati.

## Subito dopo la sessione
```
py -3.11 g1/process_session.py --video
```
Il comando ricostruisce gli episodi, calibra gli assi con la serie K e controlla ogni take (Coil, posizione, dita ferme, video). Poi riproduce ogni presa sul G1 simulato, con la chiusura limitata in base all'oggetto, e scrive `data/session/report.md`: conteggi per oggetto ed esito, errore del braccio, avvisi.
Prima della sessione si può provare sulle take vecchie: `py -3.11 g1/process_session.py --since 47 --series H --no-episodes`.

## Cosa non è ancora pronto
- Il simulatore non mette l'oggetto davanti al G1 durante la replica delle braccia: oggetto e fisica sono per ora in `g1/sim/grasp_physics.py`, a braccio fermo.
- La posizione della camera in testa nel modello è stimata (`HEAD_CAM` in `g1/arm_ik.py`): va chiesta ai mentori.
- La lattina non è supportata con la presa laterale (vedi `g1/sim/GRASP_REPORT.md`).
