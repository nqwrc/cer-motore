# Adapter per l'export GSE reale — specifica dell'interfaccia

Questo documento **non chiude** la voce 9 della roadmap: la descrive abbastanza da poterla
chiudere in una sessione, il giorno in cui una CER ci passerà un export vero dall'area
clienti. Non è mai stato osservato un file reale, quindi qui non si inventa un formato: si
scrive il **contratto verso il motore**, che è la parte che non dipende da come il GSE
scrive i propri CSV, e si elencano le domande a cui solo un file vero può rispondere.

Chi legge per la prima volta: le assunzioni sulla *sostanza* del dato stanno in
[`MOCK-GSE.md`](MOCK-GSE.md), le formule in [`FORMULE.md`](FORMULE.md).

## 1. Il contratto, cioè la parte che non cambia

Il motore non legge file. Un adapter — reale o mock — è un modulo che tocca il disco e
consegna alle funzioni pure tre strutture, e solo queste:

| Nome | Tipo | Unità | Significato |
|---|---|---|---|
| `immissioni` | `Mapping[str, Sequence[Decimal]]` | kWh | POD di produzione → serie oraria immessa |
| `prelievi` | `Mapping[str, Sequence[Decimal]]` | kWh | POD di prelievo → serie oraria prelevata |
| `prezzi` | `Sequence[Decimal]` | €/MWh | prezzo zonale **orario** Pz della zona di mercato |

È la firma che `mock.carica` soddisfa oggi, ed è il solo punto di contatto: `condivisione`,
`tariffe` e `ripartizione` non sanno da dove vengano i numeri.

Cinque vincoli, tutti già esercitati dalla suite:

1. **Decimal, mai float.** Il denaro e l'energia si costruiscono da stringa
   (`Decimal(riga["energia_kwh"])`), non da `float`. `Decimal(0.1)` non è `Decimal("0.1")`.
2. **Allineamento posizionale.** L'indice `h` è l'unica cosa che lega fra loro le tre
   strutture: il motore non ha nozione di tempo, non legge timestamp e non ordina niente.
   È l'adapter a garantire che l'elemento `h` di ogni serie sia la stessa ora, e che
   l'ordine sia cronologico.
3. **Stessa lunghezza.** Serie di lunghezza diversa sollevano `ValueError` in
   `energia_condivisa`, `alloca_oraria`, `contributo_prelievo_coincidente` e
   `incentivo_periodo` — quattro guardie, una per confine. L'adapter non deve mai
   riempire con zeri né troncare per far combaciare: un buco nelle misure è un dato
   mancante, non un'ora a zero, e le due cose valgono denaro diverso.
4. **Un periodo per volta, ore vere.** La lunghezza è il numero di ore del periodo, che
   **non è sempre 24 × giorni**: i due giorni del cambio dell'ora legale ne hanno 23 e 25,
   e il motore ci passa già (`tests/test_casi_limite.py`). L'ora ripetuta di fine ottobre è
   un elemento in più, non un duplicato da deduplicare.
5. **Niente anagrafica.** Chi possiede quale POD, chi è impresa, chi appartiene alle
   categorie esenti dal fattore F (§2-bis di `FORMULE.md`): niente di tutto questo sta
   nell'export, che conosce i POD. Viene da un'altra fonte — lo statuto, il registro soci —
   e l'adapter reale non deve fingere di saperlo.

## 2. Cosa fa il mock oggi, colonna per colonna

Il formato è un'assunzione dichiarata, **fedele alla sostanza e non alla forma**. Serve qui
come descrizione precisa di ciò che l'adapter reale dovrà sostituire.

`misure.csv` — una riga per (timestamp, POD), separatore `;`, UTF-8 senza BOM, prima riga
di intestazione:

```
data_ora;pod;tipo;energia_kwh
2026-06-01T00:00:00;IT001E0000001A;IMMISSIONE;0.000
2026-06-01T00:00:00;IT001E0000101C;PRELIEVO;0.191
```

- `data_ora`: ISO 8601 **senza offset e senza zona**, cioè ora locale italiana implicita.
  Il generatore somma `timedelta(hours=1)` a un `datetime` naive, quindi **non simula il
  cambio dell'ora legale**: un mese generato ha sempre 24 ore al giorno. Che il motore
  regga 23 e 25 ore è verificato a parte, non dai file del mock.
- `pod`: identificativo del punto di connessione, formato `ITxxxExxxxxxxY`.
- `tipo`: vocabolario chiuso a due valori, `IMMISSIONE` e `PRELIEVO`. È l'unico campo che
  separa produttori da consumatori; `mock.carica` smista su questo.
- `energia_kwh`: **kWh, 3 decimali, punto decimale**, mai negativo. Tre decimali è la
  risoluzione delle misure dei distributori, ed è il numero su cui è dimensionata la
  risoluzione del riparto orario (1e-6 kWh, `condivisione.DECIMALI_KWH`).

`prezzi_zonali.csv` — una riga per ora:

```
data_ora;zona;prezzo_eur_mwh
2026-06-01T00:00:00;NORD;113.99
```

- `zona`: zona di **mercato elettrico** (`NORD`, `CNOR`, `CSUD`, `SUD`, `CALA`, `SICI`,
  `SARD`). Non è l'area del correttivo geografico FC_zonale (`sud`/`centro`/`nord`), che è
  una partizione diversa dell'Italia e sta nella configurazione, non nelle misure.
- `prezzo_eur_mwh`: **€/MWh, 2 decimali**, può essere negativo — con molto fotovoltaico in
  rete il prezzo zonale va sotto zero, e la parte variabile `max(0; 180 − Pz)` lo prevede.

Cosa **non** c'è, e cosa il caricamento non fa: `mock.carica` legge i timestamp come
testo e non li usa — accoda i valori nell'ordine del file e basta. Se l'export reale non
fosse ordinato, o mescolasse più periodi, o saltasse un'ora, il file si caricherebbe
comunque e le serie sarebbero sfasate in silenzio. **È il primo controllo che l'adapter
reale deve avere e il mock no.**

## 3. Cosa deve produrre un parser reale

Oltre alle tre strutture del §1, un adapter reale deve fare quattro cose che il mock non fa
perché genera i propri dati:

1. **Validare la griglia temporale.** Ricostruire le ore attese del periodo, verificare che
   ogni POD abbia esattamente una misura per ora, e fermarsi con un messaggio che dice
   quale POD e quale ora se manca o è doppia. Un'ora mancante ripartita come zero sposta
   denaro.
2. **Risolvere il fuso una volta sola, al confine.** Convertire i timestamp dell'export in
   una griglia oraria locale e restituire liste posizionali. Da lì in poi il motore non sa
   più che ora sia, e va bene così.

   *Vincolo pratico, verificato il 22 agosto 2026*: `zoneinfo` è nella libreria standard
   dalla 3.9, ma **su Windows non trova alcun fuso** senza il pacchetto `tzdata`
   (`ZoneInfoNotFoundError: 'No time zone found with key Europe/Rome'`, misurato con
   Python 3.13.14), perché il sistema non ha un database tz e `zoneinfo.TZPATH` è vuoto. La CI
   gira anche su Windows
   (`test.yml`) e il motore dichiara di non avere dipendenze di runtime: chi scriverà
   l'adapter sceglie fra prendersi `tzdata` come dipendenza dichiarata dell'adapter — non
   del motore — e derivare la regola aritmeticamente, che per l'Unione Europea è fissa e
   citabile (direttiva 2000/84/CE: ultima domenica di marzo e ultima domenica di ottobre,
   alle 01:00 UTC). La seconda strada evita la dipendenza; la prima evita di riscrivere
   una regola che qualcun altro mantiene. Nessuna delle due si può imboccare prima di
   sapere come l'export rappresenta i timestamp, che è la domanda 2 del §4.
3. **Dichiarare la provenienza di ogni serie.** Misura effettiva o stimata, acconto o
   conguaglio: se l'export lo distingue, l'informazione va portata fuori dall'adapter, non
   persa. Un rendiconto costruito su misure stimate deve poterlo dire.
4. **Non ricalcolare ciò che il GSE ha già calcolato senza confrontarlo.** Se l'export
   contiene l'energia condivisa oraria che il GSE ha determinato, quella è la grandezza
   ufficiale: `condivisione.energia_condivisa` diventa una **verifica** (`min(immesso;
   prelevato)`, `FORMULE.md` §1) e una divergenza va segnalata, non appianata.

Il mock resta, declassato a fixture di test: è l'unica sorgente su cui si possono scrivere
casi deterministici (`SEED = 42`) e coprire configurazioni che nessuna CER reale ci
presterà.

## 4. Le domande a cui solo un file vero può rispondere

In ordine di quanto cambiano il codice se la risposta è quella che non ci aspettiamo.

1. **Granularità: oraria o quartoraria?** Tutto il motore lavora su liste di ore, e
   `MOCK-GSE.md` lo dichiara come assunzione. Se l'export fosse a quindici minuti,
   l'aggregazione oraria diventerebbe una scelta dell'adapter — con la domanda immediata
   se sommare i quarti d'ora *prima* o *dopo* il `min(immissioni; prelievi)`, perché i due
   ordini danno energia condivisa diversa.
2. **Come sono rappresentati i due giorni del cambio d'ora?** Timestamp con offset
   (`+01:00` / `+02:00`), UTC, o ora locale ambigua? L'ora ripetuta di fine ottobre è
   distinguibile? Il giorno da 23 ore ha una riga in meno o una riga a zero? Il motore
   regge 23 e 25 elementi, ma qualcuno deve decidere quali sono.
3. **L'export contiene già l'energia condivisa oraria?** Se sì, il motore passa da
   "calcola" a "verifica e riparte", ed è un cambio di ruolo, non di formula.
4. **Il prezzo zonale è nel file?** Oggi il mock lo genera a parte perché non lo sappiamo.
   Se non c'è va preso dal GME, e diventa una seconda sorgente da allineare alla prima —
   con il suo fuso, la sua granularità e i suoi giorni anomali.
5. **Separatore, decimali, codifica.** `;` con virgola decimale (stile italiano) o `,` con
   punto? BOM UTF-8 in testa, che è comune negli export pensati per Excel? Intestazioni in
   italiano, con maiuscole e accenti?
6. **Unità e segni.** kWh o Wh? Quanti decimali? Le immissioni e i prelievi sono due
   colonne, due valori di un campo `tipo`, o un valore unico con il segno?
7. **Che cosa distingue un POD di produzione da uno di prelievo?** Un campo nel file, il
   codice stesso, o solo il registro della configurazione?
8. **Un file per periodo o cumulativo?** Se cumulativo, il filtro sul periodo diventa parte
   dell'adapter, e con esso il rischio di sommare due mesi per errore.
9. **Come sono marcate le misure stimate o rettificate**, e cosa succede quando il GSE
   rettifica un mese già rendicontato.
10. **Configurazione e cabina primaria** compaiono nel file? Servono se un referente
    gestisce più configurazioni e scarica un export solo.

## 5. Due avvertenze prima di aggiungere un file reale al repository

- **Un export vero contiene codici POD, cioè dati personali** riferibili a utenze
  domestiche. Non va committato così com'è: la fixture va ridotta a poche ore e i POD
  sostituiti con identificativi fittizi, come quelli del mock.
- Il passaggio alla versione **0.1.0** è legato proprio a questa voce (vedi `CHANGELOG.md`):
  è il momento in cui il motore smette di lavorare solo su dati mock. Finché l'adapter non
  esiste, ogni documento del progetto dice la stessa cosa — *spike, non usare per riparti
  reali* — e la versione con essi.
