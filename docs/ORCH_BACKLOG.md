# Audit dell'orchestratore e backlog per le prossime 20 ore

Stato letto: `main` a `8c6d836` (14/11, dopo PR #87), board fino alle 09:57 UTC, PR aperte #66 #71 #72 #78 #79 #84.
Audit in sola lettura. In questo giro ho eseguito un solo comando di verifica: `python3 -m pytest tests -q` -> **89 passed**. Tutti gli altri numeri sono riportati dai documenti del repo con il comando che li rigenera; dove il comando oggi non può girare lo scrivo.

Focus approvato: camera + riconoscimento oggetto (uovo, pallina antistress, lattina) -> il G1 (braccia e mani Dex3 guidate dai guanti) adatta la presa; sensore in testa per la posa camera-mano. MuJoCo prima, G1 dal vivo solo se la simulazione funziona.
Giuria Rokoko: 35% esecuzione tecnica, 25% originalità, 25% utilità, 15% demo.

## 1. Cosa è dimostrato e cosa no

### Dimostrato (con comando)
| Fatto | Comando | Limite |
|---|---|---|
| 89 test verdi in locale | `python3 -m pytest tests -q` | La CI ne esegue solo 7 file su 16 (`grep pytest .github/workflows/truth.yml`) |
| Nemotron riconosce 48/50 foto reali (uovo 18/20, pallina 22/22, lattina 8/8) | `python -m ai.eval_objects imgs --backend nemotron --mix` | Un solo giro, 50 foto, una persona. `imgs/` non è in git (55 MB) e l'endpoint Verda è caduto alle 11:45: **oggi non è riproducibile da un clone** |
| Il selettore non lascia mai la mano senza limite: ripiego `cup`, pallina con confidenza < 0.9 -> `egg`, < 0.6 -> al più `cup` | `python3 -m pytest tests/test_picker_safety.py -q` | Soglie scelte a occhio, provate solo con trasporti finti |
| Ritaglio attorno alla mano dalla posa in testa | `python3 -m pytest tests/test_crop.py -q` | Intrinseci ipotizzati, nessun fotogramma reale |
| Le 12 articolazioni Dex3 comandate chiudono nel verso giusto, pollice `thumb_0` bloccato | `python g1/sim/g1_sim.py`, `python3 -m pytest tests/test_g1_dex3.py -q` | Solo geometria URDF, non il robot vero |
| Force Cushion su uovo: rotture 10/11 -> 1/11 | `python3 -m robot.replay_all` (non rieseguito qui) | Presa scriptata, soglia giocattolo 3 N, mano a 5 dita, non il G1 |
| Giudice Nemotron: positivi giudicati buoni 5/32 -> 22/32 | `python3 -m ai.judge --version 2` | Misura solo il prompt di definizione del compito (la timeline non veniva inviata), rumore circa ±3, nessun negativo etichettato |

### Non dimostrato
- **Nessun comando collega foto -> oggetto -> profilo -> presa sul G1 simulato -> esito.** I pezzi esistono separati. È il cuore del 35% tecnico.
- Fisica di presa G1 (PR #79) e IK delle braccia (PR #84) non sono su `main`; #84 è in conflitto.
- **La lattina non viene tenuta** dal G1 simulato (pinza laterale la espelle: `g1/sim/GRASP_REPORT.md` in #79).
- Posa del sensore in testa e `hand_in_head` non esistono in nessun episodio su `main`.
- Gemini non è mai stato chiamato dal vivo; id modello `gemini-2.5-flash` non verificato. Anche l'id Nemotron in `ai/llm.py` è marcato non verificato.
- Le dita reali dei guanti non producono prese in simulazione (2/32 sollevamenti, `docs/PHASE1_REAL_DATA.md`).
- Niente sul G1 reale.

### Affermazioni del pitch a rischio
| Affermazione | Problema | Formula sicura |
|---|---|---|
| "96% di riconoscimento" | 50 foto, un giro, non riproducibile oggi | "48 su 50 foto nostre, un giro; i 2 errori sono uova scambiate per pallina" |
| "Il robot si comporta di conseguenza con tre oggetti" | Lattina non supportata, nessun comando end-to-end | "Due oggetti in simulazione (uovo, pallina); la lattina è riconosciuta ma non afferrata" finché B4/B10 non sono verdi |
| "Misuriamo la forza" | Soglie di rottura 20 N / 15 N e guadagni dei servo sono ipotesi | "Limite di chiusura per oggetto, tarato in simulazione; le forze sono uscite del modello" |
| "Tracciamento testa-mano" | Nessun dato reale, intrinseci ipotizzati | Dirlo solo dopo B7 e B8 |
| "Funziona sul G1" | Mai provato | Solo dopo B13 |
| "Giudice con timeline 22/32" | Timeline non inviata | "Prompt con definizione del compito: 5/32 -> 22/32, solo positivi" |
| `demo/PITCH.md` | Racconta ancora Inspire, latenza < 100 ms e policy: storia vecchia | Da riscrivere (B11) |

## 2. Rischi tecnici
| Rischio | Stato | Mitigazione nel backlog |
|---|---|---|
| Endpoint Nemotron caduto | Reale: tutte le chiamate in timeout dalle 11:45. Il ripiego è `cup` (0.65), che per l'uovo è proprio la soglia minima di tenuta | B5 Gemini verificato dal vivo, B6 classificatore locale senza rete, `--set <oggetto>` come ultima risorsa manuale |
| Uovo scambiato per pallina | 2/20. Con i numeri di default l'uovo riceve chiusura 0.80 e si rompe. Con i numeri di #79 la pallina ha 0.60, sotto la tenuta minima dell'uovo (0.65): l'uovo cade invece di rompersi | B1 poi B3 (matrice di sicurezza), B5 ritaglio attorno alla mano |
| Tabelle dei profili incoerenti | `ai/object_profile.py`: uovo 0.50. `g1/object_profiles.json` (#79): uovo tiene da 0.65. **Finché #79 non è su main il profilo uovo non tiene l'uovo sul G1 simulato** | B1 |
| Intrinseci camera ipotizzati | 1920x1080, fx 960, nessuna distorsione, offset zero, assi ipotizzati. Le foto reali sono 1920x2560 verticali | B7; fino ad allora inviare l'immagine intera (il ripiego esiste) |
| Forze in simulazione giocattolo | Soglie e guadagni ipotizzati; trasferisce solo il livello di chiusura | B9 bilancia da cucina; nel pitch mai Newton |
| Lattina non afferrabile | Vedi sopra | B10 oppure taglio |
| Braccio al limite di velocità 64-93% del tempo | Nota di Giorgio su #84 | Muoversi lenti in raccolta; controllo in B13 |
| PR in conflitto (#84, #66, #72) | `gh pr view <n> --json mergeable` | B2; #72 e #66 non servono al percorso critico |
| La CI non copre i test nuovi | 7 file su 16 | B14 (serve un umano che autorizzi la modifica al workflow) |

## 3. Backlog ordinato (20 ore)
Proprietari: **Giorgio-agenti** = `Rokoko/ ml/ vision/ g1/`; **Sonnet** = `ai/ robot/`; **Codex-1** = `demo/` e `docs/PITCH*.md`; **Codex-2** = `cv/` (cartella nuova, da reclamare in AGENTS.md). I comandi segnati *(da creare)* fanno parte della voce.

| # | Ore | Voce | Proprietario | Comando di accettazione | Dipende da |
|---|---|---|---|---|---|
| B1 | 0-1 | Portare #79 su main (profili G1 per oggetto) | Giorgio-agenti | `python3 -c "from ai import object_profile as o; print(o.load_overrides())"` stampa `['egg', 'stress_ball', 'can']` | nessuna |
| B2 | 0-2 | Ribasare #84 su main (IK braccia, serie O, `wrist_quat`) | Giorgio-agenti | `gh pr view 84 --json mergeable -q .mergeable` = `MERGEABLE` e `python3 -m pytest tests -q` verde | B1 |
| B3 | 1-3 | Matrice di sicurezza: per ogni coppia (oggetto vero, etichetta data) la chiusura assegnata non supera il `max_closure` dell'oggetto vero; i casi che violano vanno ammorbiditi | Sonnet | `python3 -m pytest tests/test_picker_safety.py -q` con il nuovo test | B1 |
| B4 | 1-6 | **Comando end-to-end in simulazione**: oggetto -> profilo -> presa G1 Dex3 MuJoCo -> `held`/`broken`, con e senza limite | Giorgio-agenti (g1/), Sonnet per il contratto UDP 14070 | *(da creare)* `python -m g1.sim.demo_e2e --set egg` stampa `held=1 broken=0`; con `--no-cap` stampa `broken=1`; idem `--set stress_ball` | B1 |
| B5 | 2-5 | Secondo fornitore verificato dal vivo: Gemini sulle stesse foto, e selettore con Nemotron spento | Sonnet (chiave: umano) | `python -m ai.eval_objects imgs --backend gemini --mix` scrive la tabella; `python -m ai.pick_profile --image <uovo.jpg>` riporta `backup: gemini` | chiave Gemini, foto condivise |
| B6 | 2-8 | Classificatore locale senza rete (uovo / pallina / lattina / altro) come terzo livello | Codex-2 (`cv/`) | *(da creare)* `python -m cv.classify imgs --report` stampa matrice di confusione; criterio: zero uova classificate come oggetto rigido | foto condivise |
| B7 | 3-8 | Posa del sensore in testa e `hand_in_head` negli episodi; intrinseci reali della camera in un JSON | Giorgio-agenti | `python3 -c "import numpy as np,sys; print(np.load(sys.argv[1])['hand_in_head'].shape)" data/episodes/<take>.npz`; `data/cam_intrinsics.json` senza `"assumed": true` | B2, sessione di raccolta |
| B8 | 6-10 | Ritaglio su fotogrammi reali: la mano cade dentro il ritaglio; confronto ritaglio contro immagine intera | Sonnet | `python -m ai.pick_profile --image <f.jpg> --hand-in-head X Y Z --intrinsics data/cam_intrinsics.json`; test su 5 fotogrammi annotati in `tests/test_crop.py` | B7, B5 |
| B9 | 4-8 | Misure reali di uovo, pallina, lattina (dimensioni, massa, forza di rottura) dentro `g1/` e rigenerare il rapporto | Giorgio-agenti (misura: umano) | `python g1/sim/grasp_physics.py --levels 0,0.2,0.3,0.4,0.5,0.55,0.6,0.65,0.7,0.75,0.8,0.9,1.0` rigenera `GRASP_REPORT.md` | B1 |
| B10 | 6-10 | Lattina: postura alternativa (dall'alto o palmo sotto). Se non tiene entro le 10 ore, tagliare | Giorgio-agenti | stesso comando di B9: riga lattina con "tiene" | B1 |
| B11 | 4-12 | Demo e pitch sul nuovo focus: passo `ai.pick_profile` in `run_demo.sh`, `results.html` con i numeri di questa pagina, `demo/PITCH.md` riscritto | Codex-1 | `demo/run_demo.sh` (mock) pubblica un profilo su 14070; `grep -ci inspire demo/PITCH.md` = 0 | B4 per i numeri |
| B12 | 8-12 | Rieseguire Nemotron quando l'endpoint torna: confidenze, latenza reale, taratura soglie 0.9 / 0.6 | Sonnet | `python -m ai.eval_objects imgs --backend nemotron --mix` (secondo giro, tabella aggiornata in `docs/OBJECT_RECOGNITION_RESULTS.md`) | endpoint vivo |
| B13 | 10-16 | G1: prima il runner finto, poi dal vivo con limite 10% | Giorgio-agenti + umani presenti | `AALTO_REPO=<clone> python g1/run_mock_gate.py --policy ws://localhost:8000 --team giorgio --episodes 1` senza violazioni; dal vivo `G1_MAX_CLOSURE=0.1` | **B4 verde**, slot Aalto |
| B14 | quando capita | Aggiungere alla CI i test nuovi | chi è autorizzato sul workflow | `gh run list --limit 1` verde con i 16 file | via libera umano |
| B15 | 12-16 | Video di riserva della demo in simulazione | Codex-1 + umano | file in `docs/media/` citato in `demo/README.md` | B4, B11 |
| B16 | 16 | **Blocco delle funzioni.** Da qui solo prove, correzioni e pitch | tutti | `python3 -m pytest tests -q` verde su main | - |
| B17 | secondario | #71 (timeline del giudice) e rimisura | Sonnet (merge: Tommaso) | `python3 -m ai.judge --version 2 --out data/overnight/judge_v2c/judge.jsonl` | endpoint vivo |

Ordine critico: B1 -> B4 -> B11 -> B15. Tutto il resto migliora un punteggio ma non blocca la demo.

## 4. Umani e agenti
**Serve un umano**
- Chiavi nel proprio terminale (Verda, Gemini). Mai in file, PR o board.
- Chiedere ai mentori: NVIDIA (endpoint Verda caduto, id esatto del modello), Google (id Gemini, quota), Aalto (il runner accetta comandi alle braccia? quale camera in testa? slot per il G1), Rokoko (dataset promesso, assi del sensore in testa).
- Misurare gli oggetti con la bilancia e fotografare. Rendere `imgs/` disponibile a Giorgio e a Codex-2 (fuori da git).
- Indossare guanti e sensore in testa per la raccolta (serie O, S).
- Presenza fisica e arresto di emergenza durante ogni prova sul G1.
- Decidere i tagli della sezione 6 alle ore 10 e 16, registrare il video, fare il pitch.
- Autorizzare modifiche a `.github/workflows` e merge delle PR bloccate.

**Non serve un umano**
- Ribasare, risolvere conflitti, scrivere test, rieseguire le valutazioni, aggiornare documenti e pagina dei risultati, revisione delle PR, scelte di routine (decidere, scrivere sulla board, proseguire).

## 5. Premi tech
| Premio | Decisione | Motivo |
|---|---|---|
| Rokoko (principale) | **Sì, tutto il tempo critico** | È il focus approvato dal loro tecnico; i quattro criteri si giocano su B4, B11, B13 |
| NVIDIA Nemotron | **Sì** | È già il riconoscitore, con un numero misurato (48/50) e una storia di miglioramento. Rischio: endpoint caduto. Serve B12 o almeno il giro già fatto più il ripiego dimostrato |
| Google Gemini | **Sì, a basso costo** | Il codice del backup esiste (#87, #82). Vale solo se B5 produce la tabella dal vivo; senza chiave entro 5 ore, lasciar perdere |
| Google Gemma | **No**, salvo che B6 usi davvero un modello Gemma locale | Oggi nulla gira in locale; dichiararlo sarebbe falso |
| Entire / CRACI | **Solo se costa meno di 30 minuti e un umano lo autorizza** | Tocca la CI, che gli agenti non modificano |
| Aaltonomous | **No come traccia separata** | I nostri dati non si trasferiscono a quel compito (`docs/AALTONOMOUS_FEASIBILITY.md`). Usiamo solo il loro G1 come corpo |
| Jetson, ElevenLabs | **No** | Fuori dal filo della storia, zero punti sui criteri Rokoko |

## 6. Tagli se il tempo scarseggia (in quest'ordine)
1. Giudice degli episodi e #71, #72, #78 (controllo qualità): già secondari.
2. B10 lattina afferrata: resta riconosciuta, non afferrata.
3. B8 ritaglio attorno alla mano: si invia l'immagine intera (ripiego già presente).
4. B6 classificatore locale: resta Gemini come secondo livello e `--set` manuale.
5. B12 secondo giro Nemotron: si presenta il giro unico, dichiarato tale.
6. B13 G1 dal vivo: se B4 non è verde entro l'ora 10, si presenta solo la simulazione con il video.
7. Mai tagliare: B1, B4, B11, B15, B16.
