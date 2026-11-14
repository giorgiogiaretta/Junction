# G1 reale da Windows: versione FUNZIONANTE (14/11/2026, 21:30)

Provata sul G1 vero, collegato via Ethernet a questo PC. Il runner degli organizzatori gira su Windows.
- **Piano B** (`g1/live_policy.py`): braccia ferme, la mano destra segue il guanto. Funziona.
- **Braccia + mani** (`g1/arms_simple.py`): entrambe le mani, 2 run da 120 s, 29,8 comandi/s, 0 comandi tagliati dal filtro di sicurezza.
  - guanto aperto: braccio su;
  - guanto chiuso: il braccio scende di circa 11 cm, poi le dita si chiudono;
  - guanto aperto di nuovo: rilascio e il braccio risale.

## Setup (una volta sola, già fatto su questo PC)
1. Rete: IP fisso sull'adattatore Ethernet del robot (`Ethernet 5`). PowerShell come amministratore:
   `New-NetIPAddress -InterfaceAlias "Ethernet 5" -IPAddress 192.168.123.222 -PrefixLength 24`
   Spegni NordVPN.
   - Robot: 192.168.123.161 (controllore), 192.168.123.120 (LiDAR).
   - 192.168.123.164 (PC2, camere) era spento: niente camera.
2. Copia `winshim/` dentro `aaltonomous-humanoid\` (deve diventare `aaltonomous-humanoid\winshim`). Contiene:
   - un sostituto di Pinocchio, solo le funzioni usate dal filtro di sicurezza. Verificato contro MuJoCo con errore 3e-16 (`check_shim.py`) e contro la posa ufficiale della camera;
   - un sostituto di turbojpeg basato su OpenCV;
   - `run_real.ps1`.
3. In `aaltonomous-humanoid\third_party`, `git clone` alle revisioni di `aaltonomous/cloud/setup_instance.sh`:
   - xr_teleoperate @817fb00;
   - unitree_sdk2_python @814556d;
   - teleimager @8a8971a.

   Poi installa: `py -3.11 -m pip install --no-deps -e third_party\unitree_sdk2_python -e third_party\teleimager`, e `pip install pyzmq logging-mp`.
4. CycloneDDS 0.10.5: su Windows non esiste un pacchetto pronto, va compilato con `build_cdds.bat` (MSVC di Visual Studio 18).
   Dopo l'installazione, in `site-packages\cyclonedds\__library__.py`, sostituisci `library_path = '...'` con `library_path = r'...'` (bug con i backslash di Windows).
5. Verifica, in sola lettura: `py -3.11 dds_listen.py` deve mostrare migliaia di messaggi da `rt/lowstate` e `rt/dex3/*/state`.
   L'interfaccia DDS si indica col nome dell'adattatore (`"Ethernet 5"`), non con l'IP.

## Avvio (3 finestre)
```
cd C:\Users\giorg\Desktop\Junction-v1-vision; py -3.11 Rokoko/src/rgmp_client.py --bimanual-port 14043     # guanti (driver rokoko-sdk già avviato)
cd C:\Users\giorg\Desktop\Junction; $env:G1_MAX_CLOSURE='0.6'; py -3.11 g1/arms_simple.py --source udp:14043 --host 0.0.0.0
& C:\Users\giorg\Desktop\aaltonomous-humanoid\winshim\run_real.ps1 -Seconds 120                             # runner: Invio al messaggio "Place the cubes"
```
Il robot deve essere **fissato o appeso**: il runner spegne il controllo dell'equilibrio (modalità debug) e blocca le gambe.

## Cose imparate sul robot vero
- **Dita sinistre a riposo.** Indice e medio sono oltre il limite di fabbrica (-1,575 contro -1,571). Comandare la posa misurata fa scattare il filtro a ogni passo, e la prova si interrompe dopo 30. Ogni comando va tenuto dentro i limiti del filtro.
- **Polsi a riposo dentro la zona tavolo vietata** (z circa 0,01–0,05 m nel riferimento del bacino). Il filtro rifiuta ogni passo che aumenta la profondità: si esce solo salendo. `arms_simple` lo fa, e usa lo stesso controllo del filtro (`WorkspaceChecker`) prima di inviare.
- **Apertura della mano all'avvio.** Al collegamento il runner può aprire le mani, perché il suo primo comando arriva prima di aver letto la posizione delle dita.
- **Avviso ignorabile.** "Waiting to subscribe dds" all'avvio è normale (circa 3 s).

## Test offline
`py -3.11 arms_test.py`: parte dalla posa reale del robot, guanti finti, filtro ufficiale. Deve dare 0 comandi tagliati.
