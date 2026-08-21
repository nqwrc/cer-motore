# Roadmap verso la v0.1

In ordine di priorità. Il gate della v0.1: un estraneo installa e ottiene un risultato
utile in meno di 15 minuti.

## Cosa resta aperto

Quindici voci su sedici sono chiuse. Resta la sola che non dipende da noi:

- **9 — adapter per l'export GSE reale**. Finché nessuna CER passa un export vero
  dall'area clienti, il formato di `mock.py` resta un'assunzione documentata e il motore
  non può essere usato su dati veri. Il contratto verso il motore, però, non dipende da
  come il GSE scrive i propri CSV ed è ora scritto per intero in
  [`ADAPTER-GSE.md`](ADAPTER-GSE.md), insieme alle domande a cui solo un file vero può
  rispondere: la voce resta aperta, ma è pronta da chiudere in una sessione.

Il gate d'installazione, invece, è **verificato il 20 agosto 2026** su un clone pubblico
fresco (Windows, con Python 3.13 già installato e cache pip calda: chi parte davvero da
zero aggiunge i propri download), percorso del README eseguito alla lettera: clone 1,4 s,
venv 8,7 s, install 17,5 s, suite 184 test verdi in 3,9 s, demo 0,4 s con i dodici file
attesi sotto `data/`. Trentadue secondi contro i quindici minuti del gate: a tenere aperta
la v0.1 resta la voce 9, non l'esperienza di installazione.

L'elenco numerato qui sotto è cronologico e le voci sono citate per numero dal codice e
dai commenti: le voci chiuse restano al loro posto, barrate, con quello che si è imparato.

## Le voci, in ordine

1. **Appendice B confermata** — *fatto 7 agosto 2026*. Il PDF ufficiale GSE (171 pagine) è
   interamente estraibile: il "troncamento" era un limite dello strumento usato allora, non
   del documento. Entrambi i parametri assunti sono risolti, su due fonti primarie
   indipendenti (Regole Operative GSE + DM CACER 414/2023 All. 1):
   - **parte variabile**: `max(0; 180 − Pz)` con Pz prezzo zonale orario. Il tetto di
     40 €/MWh **non esiste**: il cap normativo è sul totale (`min[CAP; TP_base + …]`) e i
     due modi coincidono solo perché `CAP − TP_base = 40` in tutti gli scaglioni. Il motore
     ora usa la forma normativa; `VAR_MAX` è stata rimossa;
   - **valore soglia eccedentario**: **55%** (sola tariffa premio) e **45%** (cumulo con
     conto capitale), rapporto EC/energia immessa, verifica **annuale a conguaglio**.
   Il tutto ha fatto emergere il bug del punto successivo. Dettagli e citazioni verbatim in
   [`FORMULE.md`](FORMULE.md).
2. **Bug da denaro corretto** — *fatto 7 agosto 2026*. `scomponi_eccedentario` calcolava
   `(rapporto − soglia)/rapporto`, mentre la norma vuole la differenza in punti percentuali
   `max(0; rapporto − soglia)` applicata al contributo. Sovrastimava l'importo eccedentario
   fino al +79% vicino alla soglia, spostando denaro fra categorie di membri. Corretto, con
   i tre casi a mano che ne pinnavano i valori sbagliati ricalcolati.
3. **Attribuzione EC per impianto** — *fatto 7 agosto 2026*. Era inline nella demo
   `__main__.py`, ora è `condivisione.alloca_oraria`: attribuisce l'EC oraria pro-quota
   delle immissioni, con invariante esatto `somma(quote) == EC_h` garantito dal metodo del
   resto maggiore su unità da 1e-6 kWh (la sola divisione `Decimal` non lo conserva). Ore a
   immissione nulla gestite. Rendiconto della demo invariato byte per byte.
   `contributo_prelievo_coincidente` è stata riportata sulla stessa base: aveva lo stesso
   difetto e un docstring che dichiarava un invariante che non aveva.
4. **20 casi risolti a mano** — *fatto 7 agosto 2026*, obiettivo superato: 51 test allora,
   **188 oggi** (21 agosto 2026), di cui una buona metà sono casi a mano veri (calcolo passo
   per passo nel commento) e il resto guardie di contratto. Coperti prosumer, impianti misti
   FV/non-FV, giorni da 23/25 ore, periodo interamente senza immissioni, arrotondamenti
   cattivi al centesimo, bordi del cap, cumulo con contributo in conto capitale (voce 16).

5. ~~**Un secondo scenario mock sopra soglia**~~ — *fatto 7 agosto 2026*. `mock.py` non
   genera più una sola CER: espone uno `Scenario` (impianti, utenze, anagrafica, zone) e
   ne definisce due, con lo stesso formato di file e lo stesso statuto. `equilibrata` è la
   configurazione storica, invariata al decimale (rapporto EC/EI 0,272); `concentrata` è una
   CER artigianale con un FV da 30 kW davanti a un'officina, un supermercato e una palestra
   comunale, dove il prelievo eccede quasi sempre l'immissione e il rapporto arriva a 0,976.
   Lì il vincolo scatta e 241,72 € dei 567,16 € di tariffa premio vanno ai soli consumatori
   diversi dalle imprese. La demo elabora entrambi, stampa il confronto e il rendiconto
   completo del secondo. Nuovo `tests/test_scenari.py`; lo scenario `concentrata` esercita
   anche il ruolo "prosumer", che prima nessun percorso end-to-end toccava.
6. ~~**Aggregazione in due insiemi**~~ — *fatto 7-8 agosto 2026*. `InsiemeIncentivato`
   (dataclass congelata) e `scomponi_eccedentario_insiemi`: ogni insieme ha il proprio
   rapporto EC/EI, la propria soglia e il proprio contributo, e solo alla fine gli importi
   eccedentari si sommano. La soglia è un campo obbligatorio senza default, e i costruttori
   `sola_tariffa` / `cumulo_conto_capitale` la pescano dalle costanti di `tariffe.py`. Un
   test misura quanto si sbaglierebbe aggregando tutto in un insieme solo: −37%
   sull'importo destinato ai non-imprese. Alla chiusura di questa voce la demo ci passava
   con un insieme solo, perché nessuno scenario mock aveva impianti in cumulo con
   contributo in conto capitale: l'insieme a soglia 45% restava scritto ma mai popolato
   da un percorso reale. **Chiuso il 21 agosto 2026, voce 16**: lo scenario mock `cumulo`
   fa sì che l'insieme passato a `scomponi_eccedentario_insiemi` sia, per la prima volta,
   quello `cumulo_conto_capitale` invece di `sola_tariffa` — resta UNO alla volta, non
   due insieme: `elabora` rifiuta esplicitamente uno scenario che ne popolasse due
   contemporaneamente, perché la colonna "Soglia" del confronto non saprebbe quale
   mostrare. L'aggregazione di due insiemi SIMULTANEI resta quindi testata solo in
   isolamento, non dalla demo: non è quello che questa voce chiudeva.
7. ~~**Regole dichiarative da file**~~ — *fatto 7-8 agosto 2026*. `regole.py` legge lo
   statuto da TOML con `tomllib` (stdlib da 3.11, nessuna dipendenza nuova), separando
   l'adapter che tocca il disco (`leggi`) dalle funzioni pure che validano (`valida`,
   `da_testo`). I decimali non quotati sono **rifiutati**, non convertiti: TOML ha i float
   nativi e `Decimal(0.1)` non è `Decimal("0.1")`, quindi il messaggio mostra il valore
   binario che arriverebbe al motore e come riscrivere la riga. Ogni errore dice quale
   chiave, che valore ha trovato, cosa si aspettava e come si corregge, con suggerimento
   sui refusi. Schema in [`REGOLE.md`](REGOLE.md), esempio commentato in
   `regole-esempio.toml`, che un test tiene allineato allo statuto della demo. Chiuse anche
   le guardie difettose di `ripartisci()`: quote negative che sommavano a 1, fondi negativi,
   fondi che assorbono più del totale.
8. ~~**Guardie della primitiva del vincolo eccedentario**~~ — *fatto 8 agosto 2026*, non
   era previsto. Una verifica avversariale ha trovato che tutte le guardie stavano su
   `InsiemeIncentivato`, cioè sulla strada che nessuno percorreva: la demo chiamava la
   primitiva `scomponi_eccedentario`, scoperta. Cinque attacchi passavano — argomenti
   scambiati (`EC > EI`) che dichiaravano eccedentario l'88% invece del 15%, base negativa,
   soglia negativa con eccedentario maggiore del contributo, contributo negativo, e il
   peggiore: **soglia scritta 55 invece di 0,55, che azzerava l'importo eccedentario in
   silenzio**, senza eccezioni e senza numeri assurdi. Più un generatore al posto della
   lista, che faceva restituire `(0, 0)` a `scomponi_eccedentario_insiemi` annullando
   l'intero contributo TIP, con l'assert finale complice. Tutto chiuso e inchiodato da test
   di regressione; le guardie ora sono in una funzione sola, condivisa dalle due strade.

   Il difetto comune a questa voce e alla 6 — una funzione scritta e testata a sé, ma
   scoperta perché nessun percorso reale la chiamava — si è ripresentato una terza volta
   con `condivisione.partiziona_esente_fattore_f` (voce 13) fino al 20 agosto 2026: la
   partizione esisteva, era testata, ma `__main__.elabora` non la chiamava mai, esattamente
   come `scomponi_eccedentario_insiemi` prima di questa voce. **Chiuso il 21 agosto 2026,
   voce 16.**
9. **Adapter export GSE reale**: quando una CER fornirà un export dall'area clienti,
   scrivere il parser e declassare il mock a fixture di test. Dipende da un contatto CER.

   *20 agosto 2026, resta aperta ma è specificata*: [`ADAPTER-GSE.md`](ADAPTER-GSE.md)
   scrive il contratto verso il motore — le tre strutture, le unità, l'allineamento
   posizionale, il fuso, la granularità — che è la parte indipendente da come il GSE
   scrive i propri file, più le quattro cose che un parser reale deve fare e il mock no
   (validare la griglia temporale in testa a tutto) e le dieci domande a cui solo un
   export vero può rispondere. Quel che manca è il file, non il progetto.
10. ~~**Pubblicazione e infrastruttura di progetto**~~ — *fatto 8 agosto 2026*, dopo lo
    spostamento del progetto in un repository proprio su
    <https://github.com/nqwrc/cer-motore>.
    - **Licenza MIT.** Il repo era pubblico dichiarando MIT in README e `pyproject.toml`
      ma senza il file: senza `LICENSE` il default legale è "tutti i diritti riservati" e
      nessuno può usare il codice. Ora GitHub riconosce `MIT`, e la licenza è nei metadati
      del pacchetto in forma PEP 639 (`license = "MIT"` + `license-files`), che richiede
      `setuptools >= 77`.
    - **CI GitHub Actions**, 6 job: Ubuntu e Windows per Python 3.11, 3.12 e 3.13, con
      install, suite e smoke test della demo su ognuno. Verde al primo giro. Windows non è
      simmetria: è l'unico sistema dove viene eseguito il ramo che riconfigura `sys.stdout`,
      senza il quale la demo morirebbe con `UnicodeEncodeError` su una console cp850 o
      cp437. Nessun passo di lint: il progetto non ha un formattatore concordato, e una CI
      che boccia su regole mai decise scoraggia i contributi.
    - **Badge** nel README, `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`, classifier e
      `[project.urls]` in `pyproject.toml`, description e topics del repo.
    - `CLAUDE.md` **non è più tracciato**: conteneva il contesto strategico del progetto e
      resta locale. Le regole vincolanti per chi contribuisce sono in `CONTRIBUTING.md`, i
      punti normativi aperti in `FORMULE.md`.

    *Aggiornamento del 20 agosto 2026*: i due punti che restavano da decidere qui erano
    già chiusi dall'8 agosto 2026 (commit `a1bc6fa`); questa nota allinea il documento.
    La versione è a fonte unica (`cer_motore.__version__`, che `pyproject.toml`
    legge come `dynamic`) e il CHANGELOG ne dichiara la politica: `0.0.1` è un marcatore
    di spike, nessun tag esiste per scelta, e il passaggio a `0.1.0` è legato all'adapter
    della voce 9, non al tempo. La **segnalazione privata di GitHub è stata attivata** e
    `SECURITY.md` la indica come canale riservato.
11. ~~**Uno scenario mock nella fascia critica 0,55-0,70**~~ — *fatto 8 agosto 2026*.
    Terzo scenario `paese`: una CER di paese con 90 kW di fotovoltaico (50 sul tetto del
    supermercato, 40 su quello della palestra comunale) davanti a otto utenze. Rapporto
    EC/EI **0,606**, con il vincolo che scatta ma prende solo il **5,6%** della tariffa
    premio, contro il 42,6% del `concentrata`. È il regime in cui l'errore corretto il
    7 agosto sbagliava di più e passava più inosservato: lì avrebbe assegnato 97,46 €
    invece di 59,09 €, cioè **+65%**, su un importo abbastanza piccolo da non insospettire
    nessuno.

    Il suggerimento che questa voce conteneva — "basterebbe il `concentrata` con
    l'impianto raddoppiato" — **era sbagliato**, ed è stato misurato invece che seguito:
    dà 0,81-0,83, ancora fuori fascia. Per portare quel mix dentro la fascia servirebbe un
    impianto triplo davanti a un'officina, che non è una CER che qualcuno costruirebbe.
    La configurazione è stata quindi dimensionata, non azzeccata.

    La posizione nella fascia è **strutturale, non fortunata**: verificata su tutti e
    dodici i mesi del 2026, dove il rapporto resta fra 0,596 e 0,606 — un punto
    percentuale di escursione contro cinque di margine dalla soglia. Lo scenario copre
    anche una combinazione che gli altri due non esercitavano: un prosumer che **non** è
    un'impresa (il comune), quindi prende insieme quota da produttore e quota
    eccedentaria.
12. ~~**Robustezza residua trovata in verifica avversariale**~~ — *fatto 8 agosto 2026*.
    Tutti e sei i punti chiusi, ciascuno prima riprodotto eseguendo il codice:
    - `VOCE_FONDI` e `FONDO_ECCEDENTARIO` sono ora **nomi riservati**, rifiutati sia da
      `ripartisci` sia — per il fondo — da `regole.py`, che è dove il conflitto capiterà
      davvero: nessun nome è più naturale, per uno statuto italiano, di
      `finalita_sociali` per il fondo delle finalità sociali;
    - i tre blocchi si comportano allo stesso modo davanti ai pesi nulli, in
      `_ripartisci_blocco`: errore che nomina blocco, importo e criterio se non c'è
      nessun membro, ripiego a quote uguali se i membri ci sono ma pesano zero — la
      scelta che il solo ramo eccedentario già applicava;
    - `NaN` e `Infinity` sono fermati prima dei confronti, e per ragioni opposte:
      `Infinity < 0` è `False` e scivola oltre la guardia, `Decimal("NaN") < 0` solleva
      `InvalidOperation`, che è `ArithmeticError` e non `ValueError`;
    - tutte le guardie sono ora verificate **sul messaggio** e non sul solo tipo di
      eccezione: era l'asimmetria che aveva lasciato viva una guardia morta;
    - le funzioni pubbliche girano in una copia di `CONTESTO = Context(prec=28)` e non
      dipendono più dal contesto `Decimal` del chiamante.

    Aggiunto in corsa, non previsto: **ruoli e criteri sono vocabolari chiusi**. Un ruolo
    scritto male non sollevava nulla — il socio non entrava in nessun blocco, restava con
    un esito vuoto e la sua quota andava agli altri. Misurato: con `consumatori` al posto
    di `consumatore`, 1500 centesimi cambiavano tasca in silenzio, con l'invariante di
    somma che reggeva. Un criterio inesistente cadeva nel ramo di default e ripartiva
    pro-quota energia, cioè dava una risposta plausibile a una domanda mai posta.
13. ~~**Cumulo conto capitale (PNRR)**~~ — *fatto 20 agosto 2026*. La formula `TIP × (1 − F)`
    c'era già, verificata ed esposta come parametro di `tip_unitaria`; mancava la parte
    difficile, cioè la partizione. `condivisione.partiziona_esente_fattore_f` divide la
    serie oraria dell'energia condivisa in quota esente e quota non esente: l'energia
    afferente a punti di prelievo di enti territoriali, enti religiosi, enti del terzo
    settore, protezione ambientale e persone fisiche è **esente** dal fattore F (Regole
    Operative pag. 41). Le due serie si tariffano separatamente — F = 0 sulla prima, F
    sull'altra — e non sui totali di periodo, perché `TIP_h` dipende dal prezzo zonale
    dell'ora. Misurato sul caso a mano: applicare F a tutta l'energia dell'impianto
    toglie il **29%** del contributo a un impianto che la norma non decurtava per intero.

    **L'esenzione è verificata, il criterio di attribuzione no**, e la differenza è
    dichiarata: le Regole Operative dicono *quale* energia è esente ma non *come*
    misurarla, come già per l'attribuzione dell'EC ai singoli impianti. Si adotta lo
    stesso criterio pro-quota oraria, applicato ai prelievi invece che alle immissioni,
    ed è marcato `[modellazione]` nel nuovo §2-bis di [`FORMULE.md`](FORMULE.md), con lo
    stesso riparto in unità da 1e-6 kWh e quindi lo stesso invariante esatto.

    Due cose che è facile confondere e che ora sono scritte: la partizione **non crea un
    secondo insieme incentivato** (gli insiemi "j" si formano per impianto, e un impianto
    in cumulo sta tutto in quello a soglia 45%); e la **classificazione dei POD** nelle
    cinque categorie esenti è un fatto giuridico sul titolare, non deducibile dalle
    misure — resta l'unico punto aperto della voce, insieme al criterio. Aggiunti anche i
    tre bordi della soglia del 45%, che erano coperti solo di sopra: 0,44, 0,45 esatto
    (non genera eccedentario) e 0,46.
14. ~~**Rendiconto in CSV**~~ — *fatto 20 agosto 2026*. `rendiconto.rendiconto_csv`, stessa
    sostanza del Markdown per un altro pubblico: una riga per destinatario e l'importo
    scomposto per titolo — quota da produttore, da consumatore, eccedentaria, fondo — più
    ruolo e qualità di impresa del percettore, che sono i due campi da cui dipende il
    trattamento fiscale del riparto (Risoluzione AE 33/2024, fuori perimetro motore).
    Separatore `;` e punto decimale come i CSV di misura del mock, ordine delle colonne
    fisso e dichiarato in `INTESTAZIONE_CSV`, fine riga `\n` esplicito perché il `\r\n` di
    default di `csv.writer` diventa `\r\r\n` passando da `write_text` su Windows.

    Niente riga di totali e niente commenti: il file resta rettangolare, così
    `SOMMA(totale_eur)` è il totale ripartito e non il doppio. Il fondo `finalita_sociali`
    sta nella colonna dell'eccedentario e non in quella dei fondi statutari, perché le
    Regole Operative pag. 41 danno all'importo eccedentario una sola destinazione con due
    forme, e sommare quella colonna deve dare l'importo del periodo comunque sia stato
    destinato. La dichiarazione che il vincolo è calcolato sul periodo mentre il GSE lo
    verifica a conguaglio annuale resta nel Markdown, dove c'era: in un CSV una riga di
    nota sarebbe una riga che non è un pagamento.

    L'avvertenza che questa voce conteneva — la chiave `totale` di `incentivo_periodo` è
    `tip + arera` in euro e non va portata in centesimi da sola — **non è stata seguita a
    mano**: la guardia di coerenza è ora in `rendiconto._componenti_cent`, una sola
    funzione condivisa dalle due scritture. Due guardie separate per la stessa regola
    significano che una delle due è scoperta, e l'export è quella che qualcuno importa in
    un foglio senza rileggerla.
15. ~~Coerenza degli arrotondamenti nel rendiconto~~ — *fatto 7 agosto 2026, esteso l'8*.
    La divergenza
    c'era ed era peggio del previsto: l'intestazione non arrotondava affatto in centesimi, ma
    formattava i `Decimal` in euro, e il formato `Decimal` usa ROUND_HALF_EVEN mentre
    `in_centesimi` usa ROUND_HALF_UP. Con TIP 1,005 € e ARERA 2,005 € stampava
    "1,00 · 2,00 · totale 3,01" sopra una tabella che sommava 3,02: tre numeri incoerenti fra
    loro e con la tabella. Ha ragione la tabella — è la ripartizione a muovere il denaro e
    riceve `in_centesimi(tip) + in_centesimi(arera)` — quindi ora il rendiconto costruisce
    l'intestazione da quelle stesse quantità in centesimi, e solleva `ValueError` se gli
    importi ripartiti non ci chiudono sopra. Sui dati mock il delta resta zero in entrambi
    gli scenari, come previsto: il caso che diverge davvero è in `tests/test_scenari.py`.
    **Estensione dell'8 agosto**: quella guardia, così com'era, avrebbe bloccato il punto 6.
    Riderivava i centesimi dai `Decimal`, dando per scontato che il TIP fosse stato
    arrotondato una volta sola — falso nel flusso per insiemi, dove ogni insieme porta il
    proprio contributo già in centesimi interi. Con due insiemi da 1,005 € la ripartizione
    ne distribuiva 202 e il rendiconto ne pretendeva 201, su dati legittimi. Ora le chiavi
    `tip_cent` e `arera_cent` sono autorevoli: se ci sono, il rendiconto le usa.
16. ~~**Quarto scenario mock `cumulo`: la partizione del fattore F cablata davvero**~~ —
    *fatto 21 agosto 2026*. Chiude un rilievo di revisione permanente: fino a questa
    voce `condivisione.partiziona_esente_fattore_f` e la soglia 45% di
    `InsiemeIncentivato.cumulo_conto_capitale` (voce 13) erano scritte e testate a sé, ma
    nessun percorso reale le chiamava — la STESSA specie di difetto già trovato due volte
    alle voci 6 e 8, dove cinque bug da denaro erano nati esattamente da funzioni scritte
    ma non cablate. `mock.CUMULO`: un impianto FV comunale da 47 kW con un contributo in
    conto capitale (F = 0,30, `Impianto.fattore_conto_capitale`, nuovo campo con default
    0 — i tre scenari precedenti non se ne accorgono) e cinque utenze, tre esenti dal
    fattore F (il comune stesso, ente territoriale, e due famiglie — `Scenario.
    pod_esenti_fattore_f`, nuovo campo) e due no (studio e bar, imprese).

    `__main__.elabora` ora smista ogni impianto in uno di DUE secchi possibili — sola
    tariffa o cumulo conto capitale — secondo il proprio fattore F: un impianto in
    cumulo passa prima da `partiziona_esente_fattore_f`, poi da `tariffe.
    incentivo_periodo` DUE volte (F = 0 sulla parte esente, F sull'altra), e il secchio
    non vuoto diventa l'`InsiemeIncentivato` che `scomponi_eccedentario_insiemi` scompone
    — per la prima volta quello `cumulo_conto_capitale`, non `sola_tariffa`. Resta UN
    insieme alla volta: `elabora` rifiuta esplicitamente uno scenario che li popolasse
    entrambi, perché la colonna "Soglia" del confronto e l'intestazione del rendiconto
    assumono un valore solo. L'aggregazione di due insiemi SIMULTANEI (quella che la
    voce 6 aveva introdotto) resta quindi verificata solo dai test, non da un percorso
    reale — non è quello che questa voce chiude. Misurato sul caso a mano (giugno 2026,
    seed 42): rapporto EC/EI 0,4881,
    **sopra la soglia del cumulo (45%) ma sotto quella della sola tariffa premio (55%)**
    — con questi stessi numeri e la sola tariffa premio il vincolo NON scatterebbe
    affatto: è la dimostrazione che le due soglie sono indipendenti, non un secondo
    numero ridondante. Il vincolo eccedentario scatta e prende 14,76 € del TIP (3,8%);
    l'identità esatta fra "l'esenzione preserva T_esente × F" e "applicare F a tutta
    l'energia costerebbe il 19,75% del contributo in più" è verificata in
    `tests/test_scenari.py` a livello di `Decimal`, non solo di centesimi arrotondati.

    I TRE scenari precedenti (`equilibrata`, `paese`, `concentrata`) restano identici
    byte per byte, verificato per confronto diretto con `HEAD` prima di questa voce:
    `elabora` per un impianto a F = 0 somma esattamente gli stessi termini nello stesso
    ordine di prima, in un secchio invece che nell'accumulatore unico di allora.

    La guardia sull'insieme unico (sopra) ha il proprio test: uno scenario con un
    impianto a sola tariffa E uno in cumulo, costruito per il solo test, alza
    `NotImplementedError` con il messaggio verificato, non un tipo di eccezione soltanto
    — la stessa disciplina della voce 12 ("tutte le guardie sono ora verificate sul
    messaggio e non sul solo tipo di eccezione").

    **Resta aperto quello che voce 13 aveva già dichiarato aperto**: il criterio di
    attribuzione dell'energia esente e la fonte della classificazione dei POD restano
    nostri e non prescritti — `Scenario.pod_esenti_fattore_f` è anagrafica del mock, non
    una risposta alla domanda. Cablare la partizione in un percorso reale non la risolve,
    la rende visibile.
