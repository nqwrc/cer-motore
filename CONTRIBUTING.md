# Contribuire a cer-motore

Grazie: un motore di calcolo che ripartisce denaro fra i soci di una comunità energetica
vale quanto vale la fiducia che merita, e la fiducia la costruiscono le verifiche degli
altri. Questo documento serve a metterti in condizione di contribuire **senza rompere le
cose che contano**, che qui sono poche ma non negoziabili.

La lingua del progetto è l'**italiano** — codice, docstring, commenti, test, documentazione,
issue, messaggi di commit. Niente emoji da nessuna parte, nemmeno nei Markdown.

## Indice

- [Ambiente e comandi](#ambiente-e-comandi)
- [Le regole vincolanti, e perché](#le-regole-vincolanti-e-perché)
- [La regola del caso risolto a mano](#la-regola-del-caso-risolto-a-mano)
- [Come si cita una fonte normativa](#come-si-cita-una-fonte-normativa)
- [Cosa è fuori perimetro](#cosa-è-fuori-perimetro)
- [Prima di aprire una pull request](#prima-di-aprire-una-pull-request)

## Ambiente e comandi

Serve **Python 3.11 o superiore** e nient'altro. Il motore usa solo la libreria standard;
l'unica dipendenza, e solo per sviluppare, è `pytest`.

PowerShell (Windows):

```powershell
git clone https://github.com/nqwrc/cer-motore.git
cd cer-motore
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

bash / zsh (Linux, macOS):

```bash
git clone https://github.com/nqwrc/cer-motore.git
cd cer-motore
python3 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev]"
```

Con il venv attivo (`.\.venv\Scripts\Activate.ps1` oppure `source .venv/bin/activate`) i
due comandi che userai sempre sono:

```bash
python -m pytest -q      # la suite completa: 184 test, circa tre secondi
python -m cer_motore     # la demo end-to-end sui tre scenari mock
```

Se preferisci non attivare il venv, funzionano identici invocando l'interprete per esteso:
`.\.venv\Scripts\python.exe -m pytest tests/ -q` e `.\.venv\Scripts\python.exe -m cer_motore`.

Un singolo test si esegue per nome:

```bash
python -m pytest tests/test_ripartizione.py::test_scomponi_eccedentario_insiemi_caso_a_mano -q
```

La CI di GitHub Actions esegue gli stessi due comandi su Linux e Windows, su Python 3.11,
3.12 e 3.13, a ogni push e a ogni pull request verso `main`: se passano da te, passano lì.
Non c'è alcun passo di lint o di formattazione automatica, deliberatamente — il progetto non
ha un formattatore concordato e una CI che boccia su regole mai discusse scoraggia i
contributi invece di migliorarli.

**La demo è un test di non-regressione gratuito, e va usata come tale.** È deterministica
(`SEED = 42` in `mock.py`): dopo un refactor, se il rendiconto cambia di un centesimo
rispetto a prima, o hai cambiato il calcolo o hai introdotto un bug — in nessuno dei due
casi puoi non accorgertene. Salva l'output prima di toccare il codice e confrontalo dopo.
Tutto quello che la demo scrive sta sotto `data/`, che è già ignorata da git e si può
cancellare quando si vuole.

## Le regole vincolanti, e perché

Sono sei. Il "perché" non è decorativo: se una regola ti sembra un ostacolo, il perché ti
dice cosa stai per rompere.

### 1. Il motore è puro

Le funzioni in `src/cer_motore/` non fanno I/O, non leggono file, non hanno stato: input
espliciti, output deterministici. Il disco lo toccano solo `mock.py`, `__main__.py` e gli
adapter — oggi uno solo, `regole.leggi`, che è deliberatamente separato dalle funzioni pure
`regole.valida` e `regole.da_testo` che fanno il lavoro vero.

*Perché*: un calcolo che ripartisce denaro deve essere verificabile isolatamente e
riproducibile alla virgola. Se una funzione legge una variabile d'ambiente, un orologio o un
file, il suo risultato non è più una funzione dei suoi argomenti, e un test che passa non
dimostra più nulla. È anche la ragione per cui un domani si potrà scrivere un adapter per
l'export GSE reale senza toccare una riga di calcolo.

### 2. Il denaro è `Decimal`, mai `float`

Nel motore non deve comparire un `float` su un percorso che tocca importi. La conversione da
testo a `Decimal` avviene su **stringhe**, mai passando da un `float`.

*Perché*: `Decimal(0.1)` non è `Decimal("0.1")` — è
`0.1000000000000000055511151231257827…`, perché 0,1 in binario non esiste. `regole.py`
arriva al punto di **rifiutare** i decimali non quotati in TOML (`gestione = 0.10` è un
errore, si scrive `gestione = "0.10"`), e il messaggio d'errore mostra il valore binario che
sarebbe arrivato al motore. Un socio che copia una percentuale da un foglio di calcolo deve
prendere un errore, non un risultato leggermente sbagliato.

### 3. I riparti vanno in centesimi interi, col metodo del resto maggiore

Tutti gli importi da distribuire viaggiano in **centesimi (`int`)**. La primitiva è
`ripartizione.ripartisci_centesimi`: quote troncate, poi i centesimi residui assegnati alle
frazioni più alte. **L'invariante `somma(quote) == totale` è sacro** e va testato su ogni
funzione di riparto, nuova o modificata.

*Perché*: la divisione, anche in `Decimal`, non chiude. Dieci euro in tre parti non fanno
dieci euro. Un centesimo perso o creato in un rendiconto è un rendiconto che un socio può
contestare, ed è la prima cosa che chiunque controlla. Nota che la primitiva non sa nulla di
valuta: `condivisione.alloca_oraria` la riusa con unità da 1e-6 kWh per attribuire l'energia
condivisa agli impianti con lo stesso invariante esatto. Se ti serve ripartire qualcosa,
riusa quella funzione invece di dividere.

### 4. I parametri normativi stanno solo in `tariffe.py`

Tariffe base, cap per scaglione, correttivi zonali, fattore di cumulo, soglie del vincolo
eccedentario: sono **costanti nominate in `tariffe.py`**, ciascuna con la fonte e la data di
verifica nel commento. Mai un numero normativo inline nel flusso di calcolo, e mai un
parametro normativo ridefinibile da un file di statuto — è una delle ragioni per cui
`regole.py` tratta ogni chiave fuori schema come un errore invece che ignorarla.

*Perché*: cambiano. Le Regole Operative sono già state aggiornate tre volte. Il giorno in
cui la soglia passa dal 55% a un altro valore, deve esserci **una** riga da cambiare e i
test devono dire subito cosa si sposta. C'è un precedente istruttivo scritto nel codice: il
motore aveva una costante `VAR_MAX = 40` che troncava la parte variabile della tariffa. Dava
gli stessi numeri della forma normativa, ma solo per una coincidenza aritmetica
(`CAP − TP_base = 40` in tutti gli scaglioni), e avrebbe sbagliato in silenzio il giorno in
cui un aggiornamento avesse mosso i due parametri in modo non parallelo. È stata rimossa in
favore della forma che la norma scrive davvero.

### 5. Solo libreria standard nel motore

Python 3.11+, `pytest` per i test, nient'altro. Il TOML si legge con `tomllib`, che è
stdlib dalla 3.11 — è anche il motivo per cui il minimo è 3.11 e non 3.9.

*Perché*: una CER è un'associazione di volontari con un tesoriere, non un reparto IT. Il
costo di installazione deve restare "hai Python, hai finito", e la superficie di
manutenzione a vent'anni (tanto dura l'incentivo) deve restare piccola. Una pull request che
aggiunge una dipendenza deve argomentare perché la stdlib non basta, e sarà una discussione
seria, non una formalità.

### 6. Ogni regola di calcolo cita la sua fonte

Nel docstring, con documento, paragrafo e **numero di pagina**. Vedi la sezione dedicata più
sotto.

## La regola del caso risolto a mano

**Ogni formula ha almeno un test in cui il risultato atteso è stato calcolato a mano, passo
per passo, e il calcolo è scritto nel commento sopra le `assert`.**

E la parte che conta davvero:

> I valori attesi si ricavano **dalla formula**, non si copiano dall'output del codice.

*Perché*: un test costruito eseguendo la funzione e incollando quello che stampa non
verifica niente. È una fotografia. Se la funzione ha un bug, il test fotografa il bug e da
quel momento lo difende: ogni futuro tentativo di correggerlo fallirà "il test", e il test
avrà ragione. Questo progetto ne ha un caso reale e costoso, raccontato nel CHANGELOG e in
`docs/ROADMAP.md`: `scomponi_eccedentario` calcolava una frazione dove la norma vuole una
differenza in punti percentuali, sovrastimando l'importo eccedentario fino al 79%, e **tre
test a mano ne pinnavano i valori sbagliati** perché erano stati derivati dalla lettura
sbagliata della formula, non dalla formula. Quando la verifica sul PDF ufficiale ha chiuso
la questione, i tre test sono stati ricalcolati insieme al codice. Un test che copia
l'output non avrebbe nemmeno posto la domanda.

Il modello da imitare è
**`test_scomponi_eccedentario_insiemi_caso_a_mano`** in `tests/test_ripartizione.py`. Ha
tutto quello che serve:

- il commento riporta la formula normativa e il numero di pagina da cui viene;
- svolge il calcolo **numero per numero** per ciascuno dei due insiemi (rapporto, quota
  percentuale, arrotondamento, base per differenza) invece di scrivere solo il risultato;
- i valori nelle `assert` sono quelli del commento, e chi rilegge può rifarli su carta;
- chiude con l'`assert` sull'invariante, `base + ecc == 29000`, cioè il totale in ingresso.

Altri due esempi buoni, per generi diversi:
`test_alloca_oraria_caso_a_mano` in `tests/test_condivisione.py` (mostra come si documenta
un riparto col resto maggiore, incluso il criterio con cui si rompe il pareggio) e
`test_scomponi_eccedentario_caso_a_mano` in `tests/test_ripartizione.py`, che oltre al
calcolo giusto scrive esplicitamente **quale sarebbe stato il risultato con la formula
sbagliata** — un modo economico per impedire che l'errore torni.

Regole di contorno:

- **Numeri che si dividono male, di proposito.** Un test su 100,00 € diviso in due parti
  uguali non dice nulla. `test_ripartisci_centesimi_un_centesimo_tra_tre_membri` divide un
  centesimo fra tre membri; `test_scomponi_eccedentario_insiemi_arrotondamenti_che_non_chiudono`
  costruisce due insiemi che cadono entrambi esattamente su mezzo centesimo.
- **Anche le guardie sono contributi.** Non tutto è un caso a mano: molti test verificano
  che input assurdi vengano rifiutati con un messaggio utile. Il più prezioso della suite è
  probabilmente `test_scomponi_eccedentario_soglia_in_percento_non_passa_in_silenzio`,
  perché la soglia scritta `55` invece di `0.55` non produceva né eccezioni né numeri
  assurdi: azzerava l'importo destinato ai consumatori non-imprese, in silenzio. Quando
  scrivi una guardia, verifica **il messaggio**, non solo il tipo di eccezione: controllare
  solo `pytest.raises(ValueError)` ha già lasciato viva a lungo una guardia morta in questo
  repository.
- **Nome del test.** I casi a mano puri usano il suffisso `_caso_a_mano`; gli altri hanno un
  nome che descrive il fatto che dimostrano, in italiano, per esteso
  (`test_scomponi_eccedentario_insiemi_non_e_l_insieme_unico`). Un nome che si legge come una
  frase è metà della documentazione.

## Come si cita una fonte normativa

Ogni funzione che implementa una regola di calcolo cita nel docstring il documento, il
paragrafo e la pagina, e dove possibile riporta la formula **verbatim**. La mappa completa
delle regole con il loro stato di verifica sta in
[`docs/FORMULE.md`](docs/FORMULE.md), che distingue tre stati: `[verificato]` (letto sul
documento ufficiale), `[assunto]` (da confermare), `[modellazione]` (scelta di
implementazione, non imposta dalla norma). Se aggiungi una regola, aggiorna quella mappa.

**Attenzione al numero di pagina, che è il dettaglio che ha già fatto perdere tempo una
volta.** Il PDF ufficiale delle Regole Operative CACER (171 pagine, agg. DD 16/7/2025) ha la
numerazione stampata a piè di pagina **sfasata di 1** rispetto all'indice del lettore PDF:

> l'Appendice B è a **pagina stampata 160**, che è la **pagina 161 del lettore**.

La convenzione del progetto è: **si cita sempre il numero stampato a piè di pagina**, mai
quello che mostra il visualizzatore. Se ti serve indicare entrambi, si scrive come nella
riga qui sopra, esplicitando quale è quale. Una citazione ambigua su questo punto costringe
il prossimo lettore a riscaricare il PDF e ritrovare il punto a mano.

Il PDF è pubblico, non c'è alcun login, ed è interamente estraibile — il "troncamento"
citato in vecchie note del progetto era un limite dello strumento usato allora, non del
documento. Link e hash sha256 stanno in fondo a `docs/FORMULE.md`.

Se una regola non è verificabile su una fonte primaria, **non inventarla**: marcala
`[assunto]` in `docs/FORMULE.md`, aggiungila ai punti aperti e apri una issue. Un parametro
plausibile inventato è peggio di un parametro mancante, perché non protesta.

## Cosa è fuori perimetro

Questo è un **motore di calcolo puro**, non un prodotto. Sono esplicitamente fuori:

- gestionali, piattaforme, portali, dashboard;
- database di qualunque genere e anagrafiche dei soci;
- web UI e API HTTP;
- MQTT, integrazioni IoT, letture in tempo reale dai contatori;
- simulatori di fattibilità economica e strumenti di dimensionamento impianti;
- il trattamento fiscale del riparto ai membri (Risoluzione AE 33/2024). Il rendiconto deve
  **esporre** i dati che servono al commercialista, non calcolare le imposte.

L'ingresso e l'uscita del motore sono dati espliciti: chi vuole costruirci sopra
un'interfaccia lo fa nel proprio progetto, che è esattamente il punto di tenere il motore
piccolo. Se hai un'idea che richiede una di queste cose, aprila come issue di discussione:
può essere giusta, ma non qui e non ora.

Da notare anche lo **stato del progetto**: è uno spike su dati mock, il formato reale
dell'export GSE non è ancora stato osservato e il motore **non va usato per riparti reali**.
Se hai accesso a un export vero dall'area clienti GSE di una CER, quello è probabilmente il
contributo più prezioso che puoi dare — vedi il punto 9 di [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Prima di aprire una pull request

1. `python -m pytest -q` passa, per intero.
2. La modifica ha almeno un test, e se tocca una formula ha un **caso risolto a mano** col
   calcolo nel commento, derivato dalla formula e non dall'output.
3. Se hai toccato il calcolo, hai confrontato l'output di `python -m cer_motore` prima e
   dopo, e sai spiegare ogni differenza. Se non ce ne sono, dillo: è un'informazione.
4. Ogni regola nuova o modificata cita la fonte con il numero di pagina **stampato**, e
   `docs/FORMULE.md` è allineato.
5. Nessuna dipendenza nuova, nessun `float` sui soldi, nessun I/O fuori da `mock.py`,
   `__main__.py` e gli adapter.
6. Italiano ovunque, niente emoji.
7. Se hai trovato un problema che non sai risolvere, aprire una issue con il caso numerico è
   già un contributo pieno. Vedi [`SECURITY.md`](SECURITY.md) per cosa deve contenere la
   segnalazione di un errore di calcolo.

Le decisioni di merito e i punti ancora aperti stanno in [`docs/ROADMAP.md`](docs/ROADMAP.md);
lo schema del file di statuto in [`docs/REGOLE.md`](docs/REGOLE.md) con l'esempio commentato
in [`regole-esempio.toml`](regole-esempio.toml); il formato dei dati mock in
[`docs/MOCK-GSE.md`](docs/MOCK-GSE.md).
