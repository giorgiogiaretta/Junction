# Guida: usare Codex (app desktop) sul progetto G1

## Preparazione (una volta sola)
1. Apri l'app **Codex** e accedi con l'account a cui hai collegato i 2500 crediti.
2. Apri come progetto la cartella **`C:\Users\giorg\Desktop\Junction-gcodex`**. È una copia separata del repository (branch `codex/grasp-search`, aggiornata alla PR #84), così Codex non tocca i file su cui lavoro io.
3. Nelle impostazioni del progetto scegli:
   - **Permessi:** lettura e scrittura nella cartella del progetto;
   - **Esecuzione comandi:** su approvazione, oppure automatica solo dentro la cartella.

   Dalla riga di comando la sandbox di Windows non partiva; l'app usa la sua.
4. Ogni compito inizia con questa frase: **"Leggi AGENTS.md e g1/sim/demo_e2e.py prima di tutto. Python = `py -3.11`. Non fare push: lascia i file modificati e scrivi un riassunto."**
5. Quando Codex ha finito, scrivimi "Codex ha finito il compito N". Controllo, eseguo i test e faccio il commit.

## Compiti pronti (copia e incolla il testo nel campo del messaggio)

### 1. Livello di controllo di Erkka e Wendy
> Ecco il link del nuovo livello di controllo prima del caricamento sul G1: <INCOLLA IL LINK>. Leggilo tutto. Poi confrontalo con `g1/live_policy.py` e `docs/G1_LIVE.md` (la nostra policy per la prova unica: braccia ferme, mano destra Dex3 dal guanto con chiusura per oggetto, una chiamata al riconoscimento sull'immagine `head_rgb`). Scrivi `docs/ERKKA_CONTROL_LAYER.md` con:
> (a) cosa controlla il livello e con quali soglie (velocità, posizioni, forza, collisioni, tempi);
> (b) quali comandi della nostra policy verrebbero bloccati o modificati;
> (c) cosa dobbiamo cambiare (file e righe);
> (d) il comando esatto che lo staff usa per caricare la nostra policy.
>
> Se il livello si può eseguire in locale, eseguilo sui nostri comandi registrati: replay del runner finto con `--source replay:77`, come descritto in `docs/G1_LIVE.md`. Non inventare: se un punto non è nel codice, scrivi "non trovato".

### 2. Più zona del tavolo per uovo e pallina
> `g1/sim/coverage.py` mostra che con una sola postura per oggetto il G1 prende uovo e pallina solo in 22 e 19 posizioni su 117 (vedi `data/g1sim/coverage/coverage.json`). Estendi `g1/sim/grasp_search.py` per salvare le 3–5 posture migliori per oggetto (`grasp_postures.json`: campo `postures`, lista). In `coverage.py`, per ogni casella prova tutte le posture e tieni la migliore. Usa il multiprocessing (16 core). Obiettivo: almeno 50 caselle "presa ok" per uovo e pallina. Rigenera le mappe PNG. Non modificare i controlli di sicurezza (`D.checks`).

### 3. Policy dal vivo con la posizione dalla camera
> Partendo da `g1/sim/live_sim.py` (macchina a stati HOVER/DESCEND/GRASP/LIFT/RELEASE, guanto → chiusura per oggetto, sollevamento dal polso), scrivi `g1/live_policy_assisted.py` per il runner degli organizzatori, sulla base di `g1/live_policy.py`:
> - posizione dell'oggetto da `obs["head_rgb"]` + `obs["head_depth"]` con `ai/locate.py` di Tommaso;
> - braccio con IK verso la posizione vista, con la postura dell'oggetto da `g1/sim/grasp_postures.json`;
> - stessi controlli di sicurezza.
>
> Provalo sul runner finto: `aaltonomous.deploy.runner --backend mock`, repository di Erkka in `C:\Users\giorg\Desktop\aaltonomous-humanoid`. Obiettivi: ≥ 27 comandi al secondo, 0 comandi bloccati. Non serve hardware.

### 4. Soglia di rottura dell'uovo e controllo della forza
> In `g1/sim/demo_e2e.py` e `g1/sim/live_sim.py` la forza sull'uovo ha picchi di 21–30 N su singoli passi di simulazione, contro la soglia ipotizzata di 20 N. Aggiungi un'opzione di limite di forza in simulazione: se la forza media su 0,1 s supera l'85 % della soglia, la chiusura scende di 0,02 per tick. È la "lead cap" del filtro di Erkka: vedi `hand_max_lead` in `aaltonomous/interface/safety.py`. Misura di nuovo `egg_profile` e `egg_nolimit`. Riporta forze, sollevamento e rotture prima e dopo.
