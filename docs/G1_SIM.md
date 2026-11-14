# G1 Dex3 in simulazione

Due livelli: (A) controllo locale leggero in MuJoCo (qui, Windows, nessuna GPU grossa); (B) Isaac Sim ufficiale Aalto su istanza Verda (RTX >= 24 GB, Ubuntu).

## A. Controllo locale MuJoCo (`g1/sim/`)

```
pip install -r g1/sim/requirements.txt          # mujoco, numpy, opencv-python (ffmpeg opzionale)
python g1/sim/g1_sim.py [--take 51] [--out data/g1sim] [--no-video]
```

Cosa fa (un solo comando, ~1-2 min):
1. scarica (una volta) il modello ufficiale G1 29-DoF + Dex3 da `unitreerobotics/xr_teleoperate` (`assets/g1`, Apache-2.0, revisione fissata `817fb00` = la stessa usata da `aaltonomous/cloud/setup_instance.sh`) in `data/g1sim/assets_g1`. Il file `g1_body29_hand14.urdf` NON e' nel repo pubblico `zupermiez/aaltonomous-humanoid` (viene clonato a runtime da `setup_instance.sh`); lo script usa l'MJCF `g1_body29_hand14.xml` dello stesso upstream, stessa geometria e stessi assi/limiti dell'URDF.
2. applica `robot/g1_dex3.py` (NON modificato) a chiusura 0 / 10 / 50 / 100 % e al caso preflight (fist con `max_closure=0.1`), mano sinistra e destra: PNG in `data/g1sim/{left,right}_*.png` (+ `*_levels.png` riassuntivi, vista laterale e vista palmo).
3. riproduce `data/episodes/take_NN.npz` (`left/right_fingers01`, 30 Hz) nel retargeter e scrive `data/g1sim/take_NN.mp4`.
4. verifica automaticamente per ogni giunto Dex3 se il verso "chiudi" del retargeter avvicina la punta al palmo (thumb: anche al punto medio indice/medio) e scrive `g1/sim/REPORT.md`.

`data/g1sim/` e' in `.gitignore` (asset, PNG e video non si committano).

### Verificato (sim, solo cinematica)
- Per tutti i 12 giunti comandati (thumb_1/2, index_0/1, middle_0/1, sinistra e destra) il verso scelto dal retargeter e' quello che nella geometria URDF avvicina punta e palmo: vedi tabella in `g1/sim/REPORT.md`.
- Sinistra e destra sono lo specchio esatto per thumb_1/2 (differenza 0.0 mm) e entro 0.5 mm per indice/medio.
- Nessuna auto-penetrazione della mano a chiusura 0/50/100 % con l'uscita del retargeter; tutti i target restano nei limiti URDF.
- A chiusura 100 % il pollice (accoppiato 0.6 alla chiusura dell'indice) si piega sopra le dita senza compenetrarle; a 50 % la distanza pollice-punte e' ~41 mm, a 100 % ~77 mm (le dita lo superano): la "pinza" migliore con questo accoppiamento e' attorno a 50 %, non a pugno chiuso.
- thumb_0 non e' mai comandato (tenuto a 0): se lo si comandasse, con il bound `filter` (+/-1.027 simmetrico) il retargeter sceglierebbe +1.027 per ENTRAMBE le mani, che NON e' lo specchio (la doc Aalto dice thumb_0 mirrored): oggi irrilevante, ma da non attivare senza correggerlo.

### NON verificato
- Il verso fisico dei motori/offset di zero del robot reale: la sim controlla solo che segni e limiti del retargeter siano coerenti con l'URDF. Il verso indice/medio concorda con la doc Aalto (misurato sul robot), ma per il pollice la doc non fornisce una misura: resta da confermare sul G1 (preflight a 10 %).
- Nessuna dinamica, nessun contatto con oggetti, nessuna coppia/PD, nessuna presa reale. Il test dice "il pollice si muove verso palmo e dita", non "la presa riesce".
- La mano Inspire non e' coperta.
- Isaac Sim ufficiale non e' stato lanciato (richiede la VM Verda): la parte B qui sotto e' presa da `aaltonomous/cloud/QUICKSTART.md`, non eseguita.

## B. Isaac Sim ufficiale su Verda

Requisiti (da `QUICKSTART.md`): GPU RTX-class >= 24 GB (RTX Pro 6000 / L40S / A6000 / 4090 / 5090; A100/H100 NON vanno, niente RT core), driver NVIDIA >= 580.65.06, Ubuntu 22.04/24.04 x86_64, >= 8 core, >= 32 GB RAM, >= 80 GB disco, istanza on-demand (non spot), volume persistente su `/data`. Lavorare in `tmux`.

```bash
# sull'istanza (SSH + tmux)
docker load -i /path/to/aalto-sim-v1.tar.zst        # oppure: docker pull <registry>/aalto-sim:v1 (immagine fornita dagli organizzatori)
docker run -d --name aalto --gpus all --network host --ipc host \
    -v aalto-kitcache:/root/miniforge3/envs/isaac/lib/python3.12/site-packages/isaacsim/kit/cache \
    -v /data:/data aalto-sim:v1 sleep infinity
docker exec -it aalto bash                          # i comandi seguenti girano nel container
aalto sim        # sim headless in background (primo avvio ~5-10 min per gli shader; log /tmp/aalto_sim.log)
aalto check      # deve stampare 8 PASS / 0 FAIL
aalto snap       # un'immagine per camera in /tmp/aalto_snap (media ~0 = shader ancora in cache: attendere)
aalto baseline   # baseline oracle, rung 1, 3 trial
aalto eval --policy ws://localhost:8000 --team giorgio --trials 1    # valuta una policy server
aalto stop       # mai pkill -f sim_main
```
Se manca `nvidia-container-toolkit`: `sudo apt-get install -y nvidia-container-toolkit && sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker`. Fallback bare metal (~30-40 min): `bash aaltonomous/cloud/setup_instance.sh` poi `bash aaltonomous/cloud/aalto.sh sim`.

### Far girare la policy da guanto sul sim ufficiale
Il codice sta in `/opt/aalto` nel container (`AALTO_REPO`). Portare dentro questo repo (nessun segreto nel repo; il clone e' privato: usare `gh auth login` o un deploy token solo sull'istanza, oppure `docker cp`/`scp` di una tar):

```bash
docker cp Junction aalto:/root/Junction              # dall'host (o git clone dentro il container)
docker exec -it aalto bash
export AALTO_REPO=/opt/aalto
cd /root/Junction
# terminale 1 (tmux): policy server con le dita da un take registrato
aalto py g1/glove_policy.py --source replay:51 --port 8000
# terminale 2: valutazione sul sim (il runner passa dal safety filter ufficiale)
aalto eval --policy ws://localhost:8000 --team giorgio --trials 1
```
`g1/glove_policy.py` richiede `AALTO_REPO` e usa solo numpy + `robot/g1_dex3.py` (le braccia restano ferme alla prima posa misurata; le mani partono dalla `hand_q` misurata). L'attributo `G1_MAX_CLOSURE=0.1` limita la chiusura come nel preflight.

`g1/run_mock_gate.py` e' il wrapper per il runner MOCK senza il controllo Pinocchio (utile su Windows, dove Pinocchio non ha wheel): su Verda Pinocchio c'e', quindi li' basta `aalto eval`. Resta utilizzabile anche nel container: `AALTO_REPO=/opt/aalto python g1/run_mock_gate.py --policy ws://localhost:8000 --team giorgio --episodes 1`.

Cosa aspettarsi: il task Sort non verra' risolto (le braccia non si muovono): il test serve a vedere che il comando mani passa il safety filter (0 clip, >= 27 Hz) e controllare a occhio (`aalto snap`) che le dita nel sim si chiudano nel verso giusto. Non provato qui: l'Isaac Sim ufficiale non e' stato lanciato.
