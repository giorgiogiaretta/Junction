# Guida per Tommaso (Junction x Rokoko)

Repo privato: https://github.com/giorgiogiaretta/Junction — il tuo username: `TommyMaggi`.

## 1. Installa (se manca)
- Git for Windows (include Git Bash): https://git-scm.com
- GitHub CLI: https://cli.github.com
- Claude Code: `npm i -g @anthropic-ai/claude-code` (serve Node 20+)

## 2. Accetta l'invito
https://github.com/giorgiogiaretta/Junction/invitations (o dall'email di GitHub). Senza questo il repo privato risulta "not found".

## 3. Clona (in Git Bash)
```bash
gh auth login        # GitHub.com, HTTPS, login da browser
gh repo clone giorgiogiaretta/Junction
cd Junction
tools/board whoami   # deve stampare TommyMaggi
```

## 4. Attiva il tuo agente automatico
Lascia questo terminale aperto tutto l'hackathon:
```bash
tools/agent-loop.sh Tommaso
```
Quando qualcuno scrive sulla board o ti tagga, parte un Claude che legge `AGENTS.md`, agisce e risponde da solo.

## 5. Il tuo Claude interattivo
Apri la cartella `Junction` con Claude Code e digli: "leggi GUIDA_SETUP_CLAUDE.md e AGENTS.md ed entra nel team".

## Regole in breve (dettagli in AGENTS.md)
- Le tue cartelle di default: `robot/` e `demo/` (cambiabile: modifica la tabella in AGENTS.md).
- Comunicazione solo sulla board (issue #1): `tools/board post "[Tommaso's Claude] ..."`, tagga con `@giorgiogiaretta`.
- Nessuno chiede permesso agli umani: decidi, scrivi sulla board, vai avanti. Solo azioni distruttive (force-push, cancellazioni, spese) vanno confermate.
- Branch `<issue#>-<nome>`, commit piccoli, solo i tuoi file, `git fetch` + rebase prima di push.
- Progetto: guanti Rokoko, vedi `Rokoko/README.md` (guanti al hardware lab del venue, domande su Discord #rokoko).

## Test
Giorgio posterà un messaggio di prova: se il tuo loop è attivo, il tuo Claude risponde sulla board entro ~30 secondi.
