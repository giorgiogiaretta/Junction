# PLAN_QC.md: piano concentrato su "controllo qualità delle dimostrazioni" (aggiornato 14/11)

## 1. La tesi (una frase)
Chi compra i Rokoko Smartgloves per addestrare robot perde tempo a ripulire i dati (Coil che si ribalta, fuori portata, calibrazione, tremore, prese fallite mescolate a quelle buone). Noi diamo: **un punteggio di qualità per ogni dimostrazione, scarto automatico dei dati cattivi, e retargeting verso più mani (Inspire, Dex3)**, con un giudice visivo che dice riuscito/fallito.
Fonti della ricerca di mercato: pagine Rokoko (robotica, dati, racconto YAAK.ai). Sono auto-dichiarazioni, non verifiche indipendenti.

## 2. Dati che abbiamo oggi
- 60 take (serie A–J), 32 etichettate "riuscito", **0 fallite**. Episodi a 30 Hz in `data/episodes`, soluzioni in `data/solved`, calibrazione `data/calib.json`.
- Flag del Coil già nello stream: saturazione (bit 8), Coil presente (bit 9), ribaltamento deciso (bit 10).
- Giudice Nemotron già scritto in `ai/judge.py`, client in `ai/llm.py`, profilo di presa in `ai/pick_profile.py`.

## 3. Come usiamo i dati (il prodotto)
Per ogni take calcoliamo (`ml/qc.py`, da scrivere):
1. **Tracking:** frazione di fotogrammi con Coil assente, saturo o con ribaltamento; salti di posizione > soglia; distanza dal Coil fuori dalla fascia utile (~0,5–1,1 m, valore del racconto YAAK, da verificare sui nostri dati).
2. **Dita:** dropout, tremore (energia ad alta frequenza), escursione calibrata per dito (dito "morto" o fuori scala).
3. **Struttura:** durata, lead-in e coda, presenza di una fase di presa.
4. **Esito visivo:** riuscito/fallito dal giudice Nemotron (con motivazione) e controllo incrociato Gemini.
5. **Compatibilità con il robot:** quante volte il retargeting Inspire/Dex3 va fuori limite o viene limitato dal filtro.
Uscita: punteggio 0–100, decisione tieni/scarta, motivo scritto, e una "scheda del dataset" (quante take buone, per serie, per mano).
**Prova che funziona:** addestriamo lo stesso modello piccolo su tutti i dati e solo sui dati filtrati, e confrontiamo (leave-one-take-out). Se il filtro non migliora nulla, lo diciamo.

## 4. Raccolta dati mancanti (Giorgio, ~40 min con i guanti)
Obiettivo: 15–20 take nuove, ognuna etichettata subito (riuscito/fallito + tipo).
- **Fallimenti di presa (8):** 3 oggetto che cade, 3 scivola o si stacca, 2 schiacciato (lattina deformata).
- **Guasti del tracker (6):** 2 con Coil ribaltato apposta, 2 fuori portata (> 1,1 m o < 50 cm), 2 con la mano vicino a metallo/telefono.
- **Operatori non esperti (3):** una persona diversa dopo 2 minuti di spiegazione.
- **Buone di riferimento (3):** stessa presa fatta bene, per avere coppie buona/cattiva.
Regole: DJI fissa su treppiede, inquadratura stabile e luce uniforme, oggetto sempre visibile; `CAM=<indice> python Rokoko/src/take.py`; dopo ogni take dire "successo o no, e perché"; non cancellare le fallite (sono il valore). Serie nuova "K" per i fallimenti e "L" per i guasti del tracker (la aggiungo al menu di `take.py`). Questi dati restano locali finché non decidiamo di spingerli su GitHub.

## 5. Cosa fa Tommaso intanto
1. Chiave Verda/NVIDIA nel suo ambiente (ognuno la sua) e `python -c "from ai.llm import ChatClient; ..."` come test.
2. Giudice: far girare `ai/judge.py` sui video che abbiamo e sulle nuove take appena arrivano; misurare accordo con le nostre etichette (precision/recall quando ci sono i fallimenti) prima e dopo una iterazione del prompt.
3. Controllo incrociato con Gemini (secondo parere sullo stesso fotogramma): dove i due modelli non concordano, la take va a revisione umana.
4. Mentori Aalto: registri Inspire, IP, verso del pollice, slot G1 (domande in `docs/MORNING.md`).
5. Revisione della PR #66 (visione) e della scheda del dataset.

## 6. Cosa faccio io in background sulla GPU (locale, con freno termico)
- Calibrare le soglie del punteggio di qualità sui dati vecchi e nuovi (cicli brevi, GPU sotto 80 °C, pausa automatica a 85 °C).
- Confronto "tutto vs filtrato" con più semi e leave-one-take-out.
- Classificatore leggero buona/cattiva sulle feature della sezione 3 come controllo del punteggio.
- Nessun push, nessun post: rapporto in `data/night/` e un riassunto a te. Si ferma da solo se la temperatura sale o se me lo dici.

## 7. Risorse e dove le usiamo
| Risorsa | Uso | Non la usiamo per |
|---|---|---|
| NVIDIA Nemotron 3.5 Super VL (Verda) | giudice riuscito/fallito, scelta del profilo di presa, motivazioni | controllo in tempo reale (lento, con limite di richieste) |
| Gemini (API) | secondo parere sui fotogrammi, etichettatura in volume (Flash), bozze | decisioni finali senza revisione |
| Modelli delegati (deepseek, qwen, gemini) | bozze di codice e documenti, che rivedo | codice di sicurezza del robot |
| MuJoCo (locale) | demo e prova di retargeting senza hardware | affermazioni su robot veri |
| DJI Osmo Action 5 Pro | video fisso per il giudice | |
| GPU locale | sezione 6 | calcoli notturni oltre la finestra concordata |
Regola: la chiave Verda sta in `~/.verda_key` e nelle variabili d'ambiente, mai nel repository.

## 8. Calendario 36 ore (da adesso, H0)
- H0–3: chiavi, pull, guanti accesi, `ml/qc.py` scritto, menu K/L in `take.py`, test DJI.
- H3–8: raccolta dati (Giorgio); giudice sui video vecchi (Tommaso); calibrazione soglie (GPU).
- H8–14: punteggio finale, scheda dataset, confronto tutto vs filtrato; prova Inspire a secco/ reale se c'è lo slot.
- H14–22: prova G1 o MuJoCo; giudice sui nuovi fallimenti con metriche.
- H22–30: demo registrata end-to-end: guanti → QC → tieni/scarta → retargeting mano.
- H30–36: congelare il codice, pitch, video di riserva.

## 9. Risultato finale
- **Con hardware:** una demo in cui le prese buone vengono riprodotte su una mano robotica e quelle cattive scartate con il motivo, più una prova reale su Inspire e/o G1 con chiusura al 10 %.
- **Senza hardware:** la stessa pipeline con riproduzione in MuJoCo, dichiarata come simulazione.

## 10. Da NON dichiarare
Che il robot impara da solo; che "riuscito" misuri la qualità della presa; forze in Newton; "validato in Isaac" o "funziona sul G1" prima del test; i numeri di YAAK/Stanford come nostri; precisione del Coil senza misura ottica; metriche del giudice finché non esistono i fallimenti etichettati.
