# A cosa servono i guanti Rokoko nel progetto (14/11, dati e simulazione)

## In una frase
I guanti **misurano come un umano afferra ogni oggetto**: quanto chiude le dita, come muove il polso e quando solleva. Questi dati diventano i profili di presa per oggetto. Durante la prova dal vivo il guanto dice al robot **quando stringere e quando sollevare**. La **camera del robot** dice **cos'è** l'oggetto e **dov'è**.

## Tre ruoli, con i numeri di oggi
1. **Raccolta dati (fatto, 29 take con Coil + DJI + guanto in testa, take 61-89).**
   - Chiusura media di indice e medio mentre l'oggetto è sollevato:
     - pallina 0,23, presa forte 0,36;
     - uovo 0,29;
     - lattina piena 0,34;
     - lattina vuota presa forte 0,52.
   - Pollice a circa 0,9 nella pinza fine dell'uovo.
   - Traiettoria del polso (posizione e orientamento, Coil), sollevamento di 14-26 cm, durata delle fasi.
   - Video della testa allineato (ritardo camera misurato: 0,57 s) e posizione della mano rispetto alla testa (`hand_in_head`).
2. **Taratura dei profili per oggetto.** Il G1 ha una mano diversa dalla nostra. Il tuo 0,29 sull'uovo, passato 1 a 1, non lo tocca nemmeno (simulazione). Per questo la chiusura del robot è `cap_oggetto × (tua chiusura / tua chiusura tipica su quell'oggetto)`:
   - stringi come al solito sull'uovo → il G1 va a 0,70, tiene senza rompere;
   - sulla pallina e sulla lattina vuota va a 1,0.
3. **Comando dal vivo (teleoperazione "assistita").** Il guanto dà l'istante della presa, quanto stringere entro il limite dell'oggetto e il sollevamento. La posizione **non** viene dal guanto: la presa del G1 tollera circa 1,5 cm e il guanto + Coil sbaglia di più (calibrazione degli assi ~8°, differenze di forma tra mano umana e Dex3). La posizione la dà la camera in testa del robot (RGB-D, `ai/locate.py` / `g1/sim/perceive.py`).

## Cosa dire e cosa no
- **Sì:** "dimostrazioni umane raccolte con i guanti Rokoko per oggetto, usate per tarare la forza e per comandare il robot; la visione riconosce e localizza".
- **No:** "il robot impara da solo", "forza in Newton misurata", "teleoperazione completa del braccio dal guanto" (in simulazione la mira del polso dal guanto non basta per l'uovo).
