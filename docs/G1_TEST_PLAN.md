# Prova sul G1 fisico: analisi e piano (deepseek, 14/11, rivisto da Claude)

## A. Perché la teleoperazione con Coil (`teleop_multi.py`) è scattosa e imprecisa: interventi in ordine di impatto
1. **Latenza dei filtri.** One Euro a 0,7 Hz (circa 230 ms) + filtro sulla chiusura (150 ms) + deadband: in totale circa 350–400 ms di ritardo percepito. Provare `--smooth 2.5`, filtro sulla chiusura a 0,05 s, deadband sul segnale grezzo invece che su quello filtrato.
2. **Limite di velocità sbagliato.** Il runner limita i *giunti* (1 rad/s), noi la velocità *cartesiana*: il bersaglio scappa avanti e il robot insegue a scatti. Va riscalato il passo in base alla velocità dei giunti, con il 30 % di margine.
3. **Salto tra aiuto e presa.** L'aiuto corregge al massimo 3 cm, mentre la presa scatta a 4 cm: in quel buco c'è un salto in un singolo tick. Servono raggi uguali, un limite su quanto velocemente può variare il peso dell'aiuto, e due tick consecutivi prima che la presa scatti.
4. **Postura naturale che si accende e si spegne.** Quando entra lo stato di presa la postura naturale viene disattivata di colpo e il gomito può cambiare piega: va fatta sparire gradualmente in 0,5 s.
5. **Oggetto bersaglio che cambia a ogni tick** (uovo o lattina, quindi limite 0,70 o 1,0): serve isteresi, oppure un'assegnazione fissa per mano.
6. **Deadband dopo il filtro:** movimento "appiccicoso" sotto i 3 mm.
7. **Prima posa:** l'orientamento iniziale è quello di presa e non quello neutro dell'operatore, quindi al primo tick il polso salta.
8. **Comandi bloccati:** il rialzo automatico si applica a qualsiasi blocco. Va applicato solo al blocco per quota del tavolo; sul robot vero bisogna fermarsi dopo 3 blocchi (il runner annulla la prova a 30).

## B. Due versioni per la prova unica
**Raccomandata: V1, senza Coil.** È quella con prove positive (`live_sim.py`) e ha meno modi di fallire.

### V1, senza Coil
La camera trova uovo e lattina, il braccio si posiziona da solo, il guanto comanda chiusura e sollevamento.
**Cosa manca:**
- braccia mosse dentro `g1/live_policy.py`, oggi ferme, riprendendo gli stati di `live_sim.py`;
- due mani e due oggetti, assegnati da riga di comando (`--right egg --left can_empty`), senza dipendere dal riconoscimento;
- `head_depth` + `ai/locate.py` con la posa reale della camera;
- un comando ogni tick (`CHUNK = 1`);
- contatore dei blocchi, con stop a 3;
- controllo di distanza tra le due mani.

### V2, con Coil
Le braccia seguono i polsi. Serve tutto quello di V1, più:
- i punti A1–A4 della sezione A (bloccanti);
- calibrazione al tavolo per entrambe le mani sul posto;
- un ricentraggio senza tastiera (file-flag oppure automatico);
- controllo collisioni del robot con sé stesso, già presente nel simulatore e da portare nella policy.

### Sequenza della prova (entrambe le versioni)
1. **Preflight:**
   - runner finto: 0 comandi bloccati e ≥ 28 comandi al secondo;
   - profondità della camera in metri (non mm) e posizione dalla camera < 2 cm su un oggetto a distanza nota;
   - verso delle dita con `G1_MAX_CLOSURE=0.1` su una spugna: se il pollice va al contrario, STOP.
2. Mano destra sull'uovo al 10 %, poi mano sinistra sulla lattina al 10 %.
3. Solo con l'ok dello staff: profilo pieno (uovo 0,70, lattina 1,0), poi le due mani insieme.

**Si interrompe subito se:**
- compare un comando bloccato dal runner;
- 3 blocchi nostri;
- meno di 25 comandi al secondo;
- la camera perde l'oggetto;
- le dita si muovono al contrario;
- uno scatto o un rumore anomalo.

## C. Checklist (sintesi)
- **Runner finto:** pulito (0 blocchi, ≥ 28 comandi/s); niente finestre né print pesanti nella policy.
- **Chiusura:** `G1_MAX_CLOSURE=0.1` al primo giro.
- **Oggetti e profili:** forzati da riga di comando; log al primo tick con il limite giusto.
- **Verso delle dita:** verificato.
- **Braccia:** ferme quando la mano è aperta.
- **Calibrazione:** fatta sul posto, il giorno della prova.
- **Camera:** profondità in metri, posizione < 2 cm, posa della camera verificata.
- **Primo comando:** dentro i limiti e dentro la scatola di lavoro.
- **Arresti:** Ctrl+C porta all'arresto sicuro in meno di 2 s (provato sul runner finto); lo staff ha l'arresto di emergenza a portata di mano.

**Ipotesi da verificare sul posto:** formato e unità di `head_depth`, posa reale della camera, che il filtro del runner coincida con i nostri controlli.
