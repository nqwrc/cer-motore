# Changelog

Tutte le modifiche degne di nota a `cer-motore` sono annotate qui.

Il formato segue [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) e il progetto
adotta il [versionamento semantico](https://semver.org/lang/it/).

**Convenzione di questo progetto**: quando una modifica sposta denaro fra i membri, la voce
ne dichiara l'entità con un numero. "Corretto un errore di arrotondamento" non è
un'informazione; "sovrastimava l'importo eccedentario fino al 79%" lo è.

Il progetto è in fase di **spike pre-v0.1**: non esiste ancora alcuna release pubblicata,
quindi tutto il lavoro svolto finora sta sotto `[Non rilasciato]`. Lo stato dei punti aperti
e il piano verso la v0.1 stanno in [`docs/ROADMAP.md`](docs/ROADMAP.md).

**Sulla versione `0.0.1`.** È un marcatore di spike, non una release: non esiste alcun tag
git e nulla è mai stato pubblicato su PyPI. Vive in un posto solo,
`cer_motore.__version__`, da cui `pyproject.toml` la legge (`dynamic = ["version"]`); un
test lo verifica, perché due numeri di versione in due file divergono al primo aggiornamento
dimenticato. Il passaggio a **0.1.0** è legato a una cosa precisa, non al tempo che passa:
l'esistenza di un adapter per un export GSE vero (voce 9 della roadmap), cioè il momento in
cui il motore smette di lavorare solo su dati mock. Fino ad allora ogni documento del
progetto dice la stessa cosa — *spike, non usare per riparti reali* — e la versione con essi.

## [Non rilasciato]

Il repository è stato pubblicato su <https://github.com/nqwrc/cer-motore> l'8 agosto 2026,
con licenza MIT. Il lavoro qui sotto è quello precedente alla pubblicazione, ricostruito
dalla sezione "Fatti" di `docs/ROADMAP.md`.

### Aggiunto

- Motore di calcolo completo dalla misura oraria al rendiconto per membro: energia condivisa
  (`condivisione.py`), tariffa premio e valorizzazione ARERA (`tariffe.py`), ripartizione
  statutaria in centesimi (`ripartizione.py`), rendiconto in Markdown (`rendiconto.py`).
  Solo libreria standard, Python 3.11+.
- `condivisione.alloca_oraria` — attribuzione dell'energia condivisa ai singoli impianti,
  pro-quota oraria delle immissioni (*7 agosto 2026*). Prima il calcolo era inline nella
  demo. L'invariante `somma(quote) == EC_h` è **esatto**, garantito dal metodo del resto
  maggiore su unità da 1e-6 kWh: la sola divisione `Decimal` non lo conserva. Gestite le ore
  a immissione nulla. Il rendiconto della demo è rimasto invariato byte per byte.
- `ripartizione.InsiemeIncentivato` e `scomponi_eccedentario_insiemi` — aggregazione degli
  impianti incentivati nei **due insiemi** previsti dalle Regole Operative pag. 42
  (*7-8 agosto 2026*). Ogni insieme ha il proprio rapporto EC/EI, la propria soglia e il
  proprio contributo; gli importi eccedentari si sommano solo alla fine. La `soglia` è un
  campo obbligatorio senza default, e i costruttori `sola_tariffa` /
  `cumulo_conto_capitale` la pescano dalle costanti di `tariffe.py`. Un test misura l'errore
  che si commetterebbe aggregando tutto in un insieme solo: **−37%** sull'importo destinato
  ai non-imprese. La demo attraversa la nuova forma anche avendo un insieme solo, perché una
  funzione che nessun percorso reale percorre è una funzione di cui non si sa se è cablata
  bene.
- `regole.py` — statuto di ripartizione dichiarativo, letto da TOML con `tomllib`, stdlib
  dalla 3.11, nessuna dipendenza nuova (*7-8 agosto 2026*). L'adapter che tocca il disco
  (`leggi`) è separato dalle funzioni pure che validano (`valida`, `da_testo`). I decimali
  non quotati sono **rifiutati**, non convertiti: il TOML ha i float nativi e `Decimal(0.1)`
  non è `Decimal("0.1")`, quindi il messaggio d'errore mostra il valore binario che
  arriverebbe al motore e come riscrivere la riga. Ogni errore dice quale chiave, che valore
  ha trovato, cosa si aspettava e come si corregge, con suggerimento sui refusi. Schema in
  [`docs/REGOLE.md`](docs/REGOLE.md), esempio commentato in `regole-esempio.toml`, che un
  test tiene allineato allo statuto della demo.
- Secondo scenario mock `concentrata` (*7 agosto 2026*). `mock.py` non genera più una sola
  CER: espone uno `Scenario` (impianti, utenze, anagrafica, zone) e ne definisce due, con lo
  stesso formato di file e lo stesso statuto. `equilibrata` è la configurazione storica,
  invariata al decimale (rapporto EC/EI 0,272); `concentrata` è una CER artigianale con un FV
  da 30 kW davanti a un'officina, un supermercato e una palestra comunale, dove il prelievo
  eccede quasi sempre l'immissione e il rapporto arriva a 0,976. Lì il vincolo eccedentario
  scatta e 241,72 € dei 567,16 € di tariffa premio vanno ai soli consumatori diversi dalle
  imprese. Lo scenario esercita anche il ruolo "prosumer", che prima nessun percorso
  end-to-end toccava.
- Guardie della primitiva del vincolo eccedentario, in `ripartizione._valida_eccedentario`
  (*8 agosto 2026*). Vedi "Corretto".
- Suite di test cresciuta a **184 test**, di cui una parte consistente sono casi risolti a
  mano con il calcolo passo per passo nel commento (*obiettivo dichiarato: 20 prima della
  v0.1; superato il 7 agosto 2026*). Coperti prosumer, impianti misti FV / non FV, giorni da
  23 e 25 ore per il cambio dell'ora legale, periodi interamente senza immissioni,
  arrotondamenti costruiti apposta per non chiudere, bordi del cap tariffario e bordi di
  entrambe le soglie del vincolo eccedentario.
- `rendiconto.rendiconto_csv` — export del rendiconto in CSV (*20 agosto 2026*). Stessa
  sostanza del Markdown per un altro pubblico: una riga per destinatario e l'importo
  scomposto per titolo (quota da produttore, da consumatore, eccedentaria, fondo), più
  ruolo e qualità di impresa del percettore, cioè i due campi da cui dipende il
  trattamento fiscale del riparto (Risoluzione AE 33/2024, fuori dal perimetro del
  motore). Separatore `;` e punto decimale come i CSV di misura, ordine delle colonne
  fisso in `INTESTAZIONE_CSV`, nessuna riga di totali e nessun commento: il file resta
  rettangolare, così `SOMMA(totale_eur)` è il totale ripartito e non il doppio. Il fondo
  `finalita_sociali` sta nella colonna dell'eccedentario e non fra i fondi statutari,
  perché le Regole Operative pag. 41 danno all'importo eccedentario una sola destinazione
  con due forme. La guardia di coerenza degli arrotondamenti è ora in una funzione sola
  condivisa dalle due scritture, `rendiconto._componenti_cent`. La demo scrive i tre CSV
  accanto ai tre Markdown, che restano identici byte per byte.
- `condivisione.partiziona_esente_fattore_f` — partizione dell'energia condivisa fra quota
  esente e quota non esente dal fattore F (*20 agosto 2026*), il pezzo che mancava al
  cumulo con contributo in conto capitale. La decurtazione `TIP × (1 − F)` non si applica
  all'energia afferente a punti di prelievo di enti territoriali, enti religiosi, enti del
  terzo settore, enti di protezione ambientale e persone fisiche (Regole Operative
  pag. 41): le due serie orarie si tariffano separatamente, F = 0 sulla prima e F
  sull'altra, e non sui totali di periodo, perché `TIP_h` dipende dal prezzo zonale
  dell'ora. **Misurato: applicare F a tutta l'energia dell'impianto toglie il 29% del
  contributo** a un impianto che la norma non decurtava per intero. L'esenzione è
  verificata verbatim, il criterio di attribuzione no — la norma dice quale energia è
  esente ma non come misurarla — quindi si adotta il criterio pro-quota oraria già usato
  per attribuire l'EC agli impianti, applicato ai prelievi, dichiarato `[modellazione]`
  nel nuovo §2-bis di [`docs/FORMULE.md`](docs/FORMULE.md). Un POD esente scritto male è
  rifiutato al confine: non sarebbe un prelievo nullo, ma tariffa premio decurtata a chi
  la norma esentava, in silenzio.
- [`docs/ADAPTER-GSE.md`](docs/ADAPTER-GSE.md) (*20 agosto 2026*): specifica dell'interfaccia
  per l'adapter dell'export GSE reale. Il contratto verso il motore (le tre strutture, le
  unità, l'allineamento posizionale, il fuso, la granularità) non dipende da come il GSE
  scrive i propri file ed è scritto per intero; il documento elenca anche le quattro cose
  che un parser reale deve fare e il mock no, e le dieci domande a cui solo un export vero
  può rispondere. **Non chiude** la voce 9 della roadmap: manca il file, non il progetto.
- Documentazione: [`docs/FORMULE.md`](docs/FORMULE.md) (mappa delle regole con fonte, pagina
  e stato di verifica), [`docs/MOCK-GSE.md`](docs/MOCK-GSE.md),
  [`docs/REGOLE.md`](docs/REGOLE.md), [`docs/ROADMAP.md`](docs/ROADMAP.md).
- Documenti di progetto alla pubblicazione del repository (*8 agosto 2026*):
  [`CONTRIBUTING.md`](CONTRIBUTING.md), [`SECURITY.md`](SECURITY.md), questo `CHANGELOG.md`
  e la licenza [MIT](LICENSE).
- Integrazione continua con GitHub Actions (*8 agosto 2026*): la suite e la demo end-to-end
  su Linux e Windows, su Python 3.11, 3.12 e 3.13.
- Terzo scenario mock `paese` (*8 agosto 2026*): una CER di paese con 90 kW di fotovoltaico
  davanti a otto utenze, rapporto EC/EI **0,606**. Presidia la fascia 0,55-0,70, dove il
  vincolo eccedentario scatta ma prende solo il 5,6% della tariffa premio — ed è il regime
  in cui l'errore corretto il 7 agosto sbagliava di più *e passava più inosservato*: lì
  avrebbe assegnato 97,46 € invece di 59,09 €, cioè **+65%**, su un importo abbastanza
  piccolo da non insospettire nessuno. Verificato su tutti e dodici i mesi del 2026: il
  rapporto resta fra 0,596 e 0,606, quindi la posizione nella fascia è strutturale e non
  un caso del seed. Copre anche un prosumer che **non** è un'impresa, combinazione che gli
  altri due scenari non esercitavano.
- Nomi riservati `VOCE_FONDI` e `FONDO_ECCEDENTARIO`, e vocabolari chiusi per ruoli e
  criteri di riparto (*8 agosto 2026*). Vedi "Corretto" per cosa succedeva senza.
- Quarto scenario mock `cumulo` (*21 agosto 2026*): un impianto FV comunale da 47 kW che
  cumula la tariffa premio con un contributo in conto capitale (F = 0,30), davanti a
  cinque utenze, tre esenti dal fattore F (il comune stesso, ente territoriale, e due
  famiglie) e due no (studio e bar, imprese). `__main__.elabora` smista ora ogni
  impianto in uno di DUE secchi possibili secondo il proprio fattore F, e un impianto
  in cumulo passa da `condivisione.partiziona_esente_fattore_f` prima di tariffare,
  con `tariffe.incentivo_periodo` chiamata due volte (F = 0 sulla parte esente, F
  sull'altra). L'insieme passato a `scomponi_eccedentario_insiemi` è così, per la
  prima volta, quello `cumulo_conto_capitale` e non `sola_tariffa` — resta UN insieme
  alla volta: `elabora` rifiuta esplicitamente, con `NotImplementedError` e un test
  dedicato che ne verifica il messaggio, uno scenario che ne popolasse due
  contemporaneamente. Chiude un rilievo di revisione permanente: fino a
  questa voce `partiziona_esente_fattore_f` era scritta e testata a sé ma priva di un
  percorso reale che la chiamasse — la stessa specie di difetto da cui erano già nati
  cinque bug da denaro (`docs/ROADMAP.md`, voci 6 e 8).

  Il rapporto EC/EI dello scenario, **0,4881**, sta fra le due soglie del vincolo
  eccedentario: sopra il 45% del cumulo con conto capitale, sotto il 55% della sola
  tariffa premio. Con questi stessi numeri e la sola tariffa premio il vincolo NON
  scatterebbe — è la dimostrazione che le due soglie del §4 sono indipendenti, non un
  secondo numero ridondante. Il vincolo eccedentario scatta e prende **14,76 € del
  387,17 € di TIP (3,8%)**. Verificata anche l'identità esatta (non solo a livello di
  centesimo) fra "l'esenzione preserva T_esente × F" e "applicare F a tutta l'energia
  costerebbe il 19,75% del contributo in più" — le due grandezze sono uguali come
  `Decimal`, non solo simili dopo un arrotondamento indipendente.

  I tre scenari precedenti (`equilibrata`, `paese`, `concentrata`) restano identici
  byte per byte: verificato per confronto diretto dei sei file di rendiconto (Markdown
  e CSV) con lo stato prima di questa voce.

### Corretto

- **Un ruolo scritto male spostava denaro fra i soci, in silenzio** (*8 agosto 2026*).
  Un membro con un ruolo non riconosciuto non entrava in nessuno dei due blocchi: restava
  con un esito vuoto e la sua quota veniva ripartita fra gli altri. Misurato: con
  `consumatori` al posto di `consumatore`, C2 riceveva `{}` e i suoi **1500 centesimi**
  finivano a C1. L'invariante di somma reggeva — il denaro non spariva, cambiava tasca —
  quindi nessuna guardia a valle se ne accorgeva. Stessa forma di difetto per i criteri di
  riparto: `criterio_produttori = "pro_capite"` non veniva rifiutato, cadeva nel ramo di
  default e ripartiva pro-quota energia, cioè dava una risposta plausibile a una domanda
  che nessuno aveva posto. Ruoli e criteri sono ora vocabolari chiusi, validati prima di
  qualunque conto.
- **Nomi che collidevano con le voci riservate del riparto** (*8 agosto 2026*). Un membro
  chiamato `_fondi` finiva dentro il dizionario dei fondi e compariva nel rendiconto come
  una voce di fondo che nessuno statuto aveva deliberato, mentre la sua riga spariva dalla
  tabella; un fondo statutario chiamato `finalita_sociali` si fondeva con l'importo
  eccedentario in una riga sola. In entrambi i casi il totale tornava, ed è questo che
  rendeva il difetto invisibile. Il fondo riservato è ora rifiutato anche da `regole.py`,
  cioè mentre si ha aperto il file dello statuto: è lì che il conflitto capiterà, perché
  nessun nome è più naturale, per uno statuto italiano, di `finalita_sociali`.
- **Tre commenti di calcolo che dicevano il falso** (*8 agosto 2026*). In un progetto in cui
  il commento *è* la dimostrazione, un caso "risolto a mano" con i numeri sbagliati è
  peggio di nessun commento, perché sembra una prova. I numeri erano stati misurati su
  configurazioni a due membri e incollati sopra test che ne usano tre (1125/2250/1125, non
  1500/3000), e due commenti attribuivano a `NaN` un comportamento che è di `Infinity`:
  `Decimal("NaN") < 0` solleva `InvalidOperation`, non restituisce `False`. Le asserzioni
  erano giuste, le spiegazioni no.
- **Importo eccedentario: frazione invece di differenza in punti percentuali**
  (*7 agosto 2026*). È la correzione più importante fatta finora, ed è un errore che spostava
  denaro reale fra categorie di membri. `scomponi_eccedentario` calcolava
  `(rapporto − soglia) / rapporto`, mentre le Regole Operative pag. 42 prescrivono
  `max(0; rapporto − soglia)` applicato direttamente al contributo economico:

  ```
  % E_ACI,ecc,j,n = max[0 ; (E_ACI,j,n / E_immessa,j,n * 100)% − valore soglia]
  ```

  Con rapporto 0,60 e soglia 0,55 la norma dà il 5% del contributo, la vecchia formula ne
  dava l'8,33%. **La sovrastima raggiungeva il +79% a rapporto 0,56** — appena sopra la
  soglia, dove cadono le configurazioni realistiche — e restava dell'11% a rapporto 0,90.
  L'errore non faceva fallire nulla e non violava alcun invariante contabile: la somma delle
  quote restava esatta, cambiava solo chi le riceveva. **Tre casi risolti a mano ne pinnavano
  i valori sbagliati**, perché derivati dalla stessa lettura errata della formula, e sono
  stati ricalcolati insieme al codice.
- **Guardie assenti sulla strada che tutti percorrevano** (*8 agosto 2026*). Una verifica
  avversariale ha trovato che tutte le validazioni stavano su `InsiemeIncentivato`, mentre la
  demo chiamava la primitiva `scomponi_eccedentario`, scoperta. Cinque attacchi passavano:
  argomenti scambiati (`EC > EI`) che dichiaravano eccedentario l'88% invece del 15%, base
  negativa, soglia negativa con eccedentario maggiore del contributo, contributo negativo e
  — il peggiore — **soglia scritta `55` invece di `0.55`, che azzerava l'importo eccedentario
  in silenzio**, senza eccezioni e senza numeri assurdi: semplicemente non pagava i
  consumatori non-imprese. Più un generatore passato al posto della lista, che faceva
  restituire `(0, 0)` a `scomponi_eccedentario_insiemi` annullando l'intero contributo TIP,
  con l'`assert` finale complice perché iterava anch'esso sul generatore ormai esaurito.
  Tutto chiuso, inchiodato da test di regressione, e le guardie sono ora in una funzione
  sola condivisa dalle due strade.
- **Arrotondamenti incoerenti nel rendiconto** (*7 agosto 2026, esteso l'8*). L'intestazione
  non arrotondava affatto in centesimi: formattava i `Decimal` in euro, e il formato `Decimal`
  usa `ROUND_HALF_EVEN` mentre `in_centesimi` usa `ROUND_HALF_UP`. Con TIP 1,005 € e ARERA
  2,005 € stampava "1,00 · 2,00 · totale 3,01" sopra una tabella che sommava 3,02: tre numeri
  incoerenti fra loro e con la tabella. Ha ragione la tabella, perché è la ripartizione a
  muovere il denaro e riceve `in_centesimi(tip) + in_centesimi(arera)`, quindi l'intestazione
  è ora costruita su quelle stesse quantità in centesimi e il rendiconto solleva `ValueError`
  se gli importi ripartiti non ci chiudono sopra. **Estensione dell'8 agosto**: quella
  guardia riderivava i centesimi dai `Decimal`, dando per scontato che il TIP fosse stato
  arrotondato una volta sola — falso nel flusso per insiemi, dove ogni insieme porta il
  proprio contributo già in centesimi interi. Con due insiemi da 1,005 € la ripartizione ne
  distribuiva 202 e il rendiconto ne pretendeva 201, su dati legittimi. Le chiavi `tip_cent`
  e `arera_cent` sono ora autorevoli: se ci sono, il rendiconto le usa.
- **Invariante dichiarato ma non posseduto** in `contributo_prelievo_coincidente`
  (*7 agosto 2026*). Il docstring prometteva che la somma dei contributi fosse esattamente la
  somma dell'energia condivisa, ma la funzione usava la divisione semplice: con tre
  consumatori uguali ed EC = 10 kWh la somma valeva 9,999999999999999999999999999. Non
  arrivava mai sui soldi — i contributi servono da pesi e `ripartisci_centesimi` li
  rinormalizza — ma era un'affermazione falsa in un modulo che sull'esattezza fa il proprio
  punto d'onore. Riportata sulla base del resto maggiore di `alloca_oraria`.
- **Guardie difettose di `ripartisci()`** (*7-8 agosto 2026*): quote negative che sommavano a
  1 (`quota_produttori = 1,5` con `quota_consumatori = −0,5` passava e assegnava ai
  consumatori una quota negativa, con l'invariante di somma comunque soddisfatto — un membro
  pagava per gli altri), fondi con percentuale negativa, fondi che assorbono più dell'importo
  base, fondi arrotondati che sfondano il totale.

### Modificato

- **Parte variabile della tariffa premio riportata alla forma normativa** (*7 agosto 2026*).
  Verifica verbatim sulle Regole Operative pag. 40 e Appendice B §1 pag. 160, confermata dal
  DM CACER 414/2023 All. 1 §1: la parte variabile è `max(0; 180 − Pz)` con Pz prezzo zonale
  **orario**, e il tetto normativo è il CAP sulla somma, `min[CAP; TP_base + max(0; 180 − Pz)]`.
  Il motore usava `max(0, min(40, 180 − Pz))`, che dà gli stessi numeri **solo** perché
  `CAP − TP_base = 40` in tutti e tre gli scaglioni, e avrebbe sbagliato in silenzio il
  giorno in cui un aggiornamento avesse mosso i due parametri in modo non parallelo.
- **Valori soglia del vincolo eccedentario confermati e resi costanti nominate**
  (*7 agosto 2026*): **55%** per gli impianti a sola tariffa premio, **45%** per quelli in
  cumulo con contributo in conto capitale, rapporto EC / energia immessa, verifica annuale a
  conguaglio (Regole Operative pag. 41 e Appendice B §4 pag. 161). Erano un punto aperto con
  un default provvisorio.
- La demo `python -m cer_motore` elabora **due** scenari invece di uno, ne stampa il
  confronto e il rendiconto completo di quello che fa scattare il vincolo. Tutto l'output su
  disco è raccolto sotto un'unica cartella usa-e-getta `data/`, già ignorata da git.

### Rimosso

- Costante `VAR_MAX = 40` da `tariffe.py` (*7 agosto 2026*). Non esiste un tetto normativo
  sulla parte variabile: in tutte le 171 pagine delle Regole Operative il valore "40 €/MWh"
  compare una sola volta, a pag. 39, come campo di variazione del parametro `Z` usato per
  l'acconto. Vedi "Modificato".

### Note sulla verifica delle fonti

Le formule sono verificate verbatim sul PDF ufficiale delle Regole Operative CACER
(171 pagine, agg. DD 16/7/2025, approvate con DM MASE 228/2025) e sul DM CACER 414/2023
Allegato 1, due fonti primarie indipendenti. Il PDF GSE è pubblico, senza login e
interamente estraibile: il "troncamento" annotato in vecchie note del progetto era un limite
dello strumento usato allora. Link e hash sha256 in fondo a
[`docs/FORMULE.md`](docs/FORMULE.md), che riporta per ogni regola la citazione, la pagina e
lo stato: `[verificato]`, `[assunto]` o `[modellazione]`.

I numeri di pagina citati nel codice e nella documentazione sono quelli **stampati a piè di
pagina**, sfasati di 1 rispetto all'indice del lettore PDF (Appendice B: pag. stampata 160 =
pag. 161 del lettore).

### Ancora aperto

Non è ancora stato osservato un export GSE reale dall'area clienti: i dati in ingresso sono
mock documentati, ed è l'unica voce di roadmap ancora aperta. Restano aperti, dentro voci
già chiuse, due punti che non spostano denaro oggi: il criterio con cui si attribuisce
l'energia esente dal fattore F ai punti di prelievo, che è nostro e non prescritto, e la
fonte da cui prendere la classificazione dei POD nelle cinque categorie esenti, che non sta
nelle misure. Elenco aggiornato in [`docs/ROADMAP.md`](docs/ROADMAP.md).

[Non rilasciato]: https://github.com/nqwrc/cer-motore/commits/main
