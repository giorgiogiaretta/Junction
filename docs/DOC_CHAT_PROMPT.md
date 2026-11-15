# Prompt per la chat "documentazione" + checklist upload

Deadline submission: **domenica 15 novembre ore 10:00**, nessuna proroga. Il progetto va messo da DRAFT a FINAL (i DRAFT non vengono valutati). Video pitch: **massimo 2 minuti, severissimi**. Il nostro `docs/SPEECH.md` è da 3 minuti e va ridotto.

---

## A. File da caricare nella chat documentazione (in quest'ordine)

**1. Le regole (le tue)**
- Brief di ogni challenge in .md: Rokoko, NVIDIA Nemotron, Google (Gemma/Gemini), Aaltonomous (`~/Downloads/aaltonomous_challenge_brief.md`), con i criteri di valutazione.
- Testo delle regole della submission (campi richiesti, video max 2 min, deck PDF, link codice/demo).

**2. La verità del progetto (dal repo)**
- `docs/submission/STORY.md` (arco narrativo e tabella "Numbers we may say": unica fonte dei numeri)
- `docs/submission/*.md` (rokoko, nvidia, google, aaltonomous, entire, VISION_MODELS, AUDIT)
- `docs/SCORECARD.md`, `docs/CODE_TOUR.md`, `docs/ARCHITECTURE.md`
- `docs/OBJECT_RECOGNITION_RESULTS.md`, `docs/STORY_MODELS.md`, `docs/PROMPT_ITERATION.md`
- `docs/DELIVERY_G1.md`, `docs/G1_LIVE.md`, `docs/G1_GUIDE.md` (robot reale, Giorgio)
- `docs/CODE_AUDIT.md` o l'audit sicurezza (`docs/` PR #185), `docs/VERDA_GEMMA.md`, `docs/ADVISOR.md`
- `deck/notes.md`, `deck/index.html` (deck attuale, 12 slide)
- `docs/SPEECH.md` (bozza speech, versione 3 minuti)
- Il file `docs/DOC_CHAT_PROMPT.md` stesso non serve; serve il prompt qui sotto.

**3. Evidenza (solo se la chat legge tabelle)**
- `docs/evidence/recognition/README.md` (non i JSON grezzi)

**Non caricare:** chiavi, token, `.env`, foto personali, `data/`.

---

## B. Prompt da incollare (copia tutto il blocco)

```
Sei il responsabile documentazione e storytelling del team Junction (Tommaso, Giorgio) per Junction 2026. Progetto: "Tactile-less HandOff". I guanti Rokoko Smartgloves non sentono la forza; una camera sulla testa + modelli di visione scelgono un tetto di chiusura della mano (uovo / palla antistress / lattina) per un Unitree G1 con mani Dex3. Concorriamo a: Rokoko, NVIDIA Nemotron, Google Gemma/Gemini, Aaltonomous (la parte Aaltonomous è un task separato fatto da Giorgio: non inventare risultati).

Ti ho caricato: i brief e i criteri di valutazione di ogni challenge, le regole della submission, e la documentazione tecnica del repo. REGOLE FERREE:
1. Usa SOLO numeri presenti nella tabella "Numbers we may say" (STORY.md) e nei documenti caricati. Nessun numero inventato, nessuna percentuale senza "sulle nostre 50 foto".
2. Mai dire: "funziona sul G1" per la visione; forze in Newton come reali; "generalizza"; "impara da solo". La visione che guida la presa è provata SOLO in simulazione. Sul robot reale abbiamo provato il movimento coi guanti (2 run da 120 s, 29,8 Hz, 0 comandi tagliati dal filtro di sicurezza) e, dove documentato in DELIVERY_G1.md, la pipeline CV; riporta solo ciò che quei file dicono.
3. Dichiara i limiti: soglie toy (rottura uovo ~3 N in sim), 50 foto di una persona/luogo/giorno, la confidenza non distingue giusto da sbagliato, lattina non supportata nella regola di sim. Nota: sul robot reale Giorgio ha scelto limiti hard diversi (uovo 0,50, lattina vuota 0,90, palla 1,0, decisione dell'operatore) rispetto alle regole della sim (palla piena forza solo con 2 famiglie di modelli e conf >= 0,9 o manuale): spiegalo con onestà come "doppio livello" senza nasconderlo.
4. Regola dei due voti: contata per FAMIGLIA di modello (Gemma + PaliGemma = una chiave).
5. Tono: concreto, incisivo, onesto. La giuria premia numeri verificabili e limiti dichiarati.

PRODUCI, in quest'ordine, come file/markdown separati e pronti da copiare:

A. FORM DI SUBMISSION (tutti i campi richiesti): nome progetto, punchline (max ~12 parole), descrizione (corta ~120 parole + lunga ~350 parole), challenge, tecnologie usate (elenco), link demo/codice (placeholder), "credited" sì.

B. SPEECH VIDEO 2:00 ESATTI (in inglese, con tempi per battuta, ~260 parole parlate) + versione 90 secondi di riserva. Parti dal gancio, momento "wow" (uovo intatto con tetto vs rotto senza), una frase onesta sui limiti, chiusura. Indica per ogni battuta cosa si vede a schermo (clip, grafica, 3D).

C. DOCUMENTAZIONE PER CHALLENGE, una pagina ciascuna, scalata in modo che il challenge provider veda al CENTRO la sua tecnologia:
   - NVIDIA: Nemotron 3.5 Super VL come occhio in tempo reale (0,22 s mediana, 48/50 in due run), come lo usiamo, endpoint Verda, perché.
   - Google: Gemma 4 (49/50, 20/20 uova), PaliGemma self-hosted su GPU, Gemini come giudice asincrono quota-aware; Gemma Router con gate di sicurezza.
   - Rokoko: guanti come insegnante, 89 take, flusso 83 Hz 0 dropout, retargeting verso Dex3, e il buco che risolviamo (nessuna forza).
   - Aaltonomous: SOLO ciò che è documentato (non inventare risultati).
   Per ognuna: problema, ruolo della loro tecnologia, snodi salienti del codice (file e funzione, spiegati per un non esperto), cosa è provato / cosa no.

D. ARCHITETTURA + DIAGRAMMI DI FLUSSO in formato Mermaid: (1) pipeline end-to-end guanto -> camera -> voto -> tetto -> mano; (2) voto fragile-first con famiglie; (3) doppio livello di sicurezza (sim vs robot reale); (4) dove entra ciascuna tecnologia sponsor (colora per sponsor).

E. FILOSOFIA: una sezione breve (mani, Anassagora/Aristotele/Bruno, parafrasati e attribuiti, mai citazioni letterali inventate) collegata al progetto: "le mani insegnano, la visione protegge".

F. "SNODI DEL CODICE SPIEGATI BASE": 8-10 passaggi chiave (file, funzione, cosa fa in 2 righe, perché conta).

G. RISPOSTE ALLA GIURIA: 12 domande difficili con risposte brevi e oneste (per ogni challenge).

H. BRIEF PER GLI AGENTI CREATIVI: (1) storyboard del video 2:00 scena per scena (durata, visual, voce, musica, motion graphics, modelli 3D da usare: mano Dex3/G1/uovo/palla/lattina); (2) struttura del deck PDF (max 10 slide: slide per slide titolo, messaggio, visual, momento wow), con grafica dinamica; (3) lista asset da produrre (clip, logo sponsor, render 3D, grafici dei numeri).

Prima di scrivere, elenca in 10 righe le tue assunzioni e qualunque contraddizione che trovi tra i documenti caricati (numeri diversi, claim non supportati). Segnala tutto ciò che non è verificabile con [DA VERIFICARE]. Se qualcosa manca, chiedimelo UNA volta con una lista unica, poi procedi.
```

---

## C. Dopo la chat documentazione (ordine consigliato)

1. Tu: verifichi i numeri contro `docs/submission/STORY.md` (5 min).
2. **Audit generale** prima dei creativi: `python3 -m verify.run` verde, test verdi, nessun claim fuori tabella nei testi finali.
3. Agenti creativi: video (storyboard dalla sezione H), deck PDF, grafici 3D.
4. Registrazione voce, upload video (YouTube *unlisted* non basta: **pubblico**), compila il form, **FINAL prima delle 10:00**.
