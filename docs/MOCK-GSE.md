# Mock dell'export GSE — assunzioni dichiarate

Il formato reale dei file che il referente scarica dall'area clienti GSE (portale SPC) è dietro
login e **non è stato ancora osservato**. Questo mock è fedele *alla sostanza* del dato (ciò che il
GSE misura e calcola è documentato pubblicamente), non alla forma (nomi colonne, layout).
Quando arriverà un export reale, si scrive un adapter e il mock resta per i test.

## Cosa è certo (fonti pubbliche)

- Il GSE riceve dai distributori le **misure orarie** per POD (immissioni dei produttori,
  prelievi dei consumatori) e calcola lui l'energia condivisa oraria per configurazione.
- Il referente riceve corrispettivi con cadenza definita (acconti/conguagli) e ha visibilità
  dei dati della configurazione in area clienti.

## Cosa è assunto (da verificare con un export reale)

- Granularità oraria (non quartoraria) nei file scaricabili.
- Struttura: una riga per (timestamp, POD), colonne `energia_kwh` e `tipo` (IMMISSIONE/PRELIEVO).
- Disponibilità del prezzo zonale orario nel file (nel dubbio, il mock lo genera a parte:
  in reale si prende da GME).

## Formato mock

`misure.csv`: `data_ora;pod;tipo;energia_kwh` (ISO 8601, kWh con 3 decimali, separatore `;`
in stile italiano). `prezzi_zonali.csv`: `data_ora;zona;prezzo_eur_mwh`.

## Scenari

Il generatore (`cer_motore/mock.py`) produce un mese di dati deterministici (seed fisso) per una
CER fittizia romagnola, zona di mercato NORD. La produzione è una curva a campana 6-20 con
nuvolosità pseudo-casuale; i consumi sono profili orari di forma perturbati con rumore.

Il **formato dei file non dipende dallo scenario**: cambia solo quanti POD ci sono e come
consumano. Uno `Scenario` è la descrizione della configurazione (impianti, utenze, anagrafica
dei membri, zone) e i due previsti sono:

| `nome` | Configurazione | EC/EI |
|---|---|---:|
| `equilibrata` | 2 impianti FV (60 e 20 kW), 8 utenze: 5 residenziali, 2 uffici, 1 bar | 0,27 |
| `concentrata` | 1 impianto FV da 30 kW, 5 utenze: officina, supermercato, palestra comunale, 2 residenziali | 0,98 |

Servono entrambi perché il rapporto energia condivisa / energia immessa decide se scatta il
vincolo dell'importo eccedentario (`FORMULE.md` §4): con il solo scenario `equilibrata` quel
ramo del motore non veniva mai percorso dalla demo. Nella `concentrata` l'impianto è
sottodimensionato rispetto ai prelievi (4.474 kWh immessi contro 11.229 prelevati nel mese),
quindi `EC_h = min(immesso, prelevato)` coincide quasi sempre con l'immesso.

L'anagrafica dei membri (chi possiede quale POD, chi è impresa) **non fa parte dell'export GSE**,
che conosce i POD: sta nello `Scenario` solo perché deve restare in sincronia con la lista dei
POD. Un adapter reale la prenderà da un'altra fonte.

## Altre assunzioni del generatore

- **Fine settimana**: i profili sono scalati di un fattore per giorno non feriale, 0,75 di
  default, dichiarato per profilo dove non ha senso (officina 0,15 — chiusa, solo standby;
  supermercato 0,80; palestra 0,60). È una semplificazione: non c'è distinzione fra sabato e
  domenica né calendario delle festività.
- **Zona di mercato e area tariffaria sono campi distinti**: `NORD` è la zona di mercato
  elettrico scritta nel CSV dei prezzi, `nord` è l'area del correttivo geografico FC_zonale
  (Regole Operative Appendice B §2 pag. 160). Sono due partizioni diverse dell'Italia e
  coincidono solo perché questa CER è in Emilia-Romagna.
- I profili di consumo sono **di forma, non campionari**: nessuno dei due scenari è la copia di
  una CER esistente.
