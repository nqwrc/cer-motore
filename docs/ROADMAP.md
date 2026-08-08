# Roadmap verso la v0.1

In ordine di priorità. Il gate della v0.1 (Fase 3 della roadmap open source personale, repo
privato `personal-archive`): un estraneo installa e ottiene un risultato utile in meno di 15 minuti.

## Fatti

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
   **136 oggi**, di cui una buona metà sono casi a mano veri (calcolo passo per passo nel
   commento) e il resto guardie di contratto. Coperti prosumer, impianti misti FV/non-FV, giorni da 23/25 ore,
   periodo interamente senza immissioni, arrotondamenti cattivi al centesimo, bordi del cap.

## Da fare

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
   sull'importo destinato ai non-imprese. La demo ci passa davvero, con un insieme solo
   (nessuno scenario mock ha impianti in cumulo), perché una funzione che nessun percorso
   reale attraversa è una funzione di cui non si sa se è cablata bene.
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
9. **Adapter export GSE reale**: quando una CER fornirà un export dall'area clienti,
   scrivere il parser e declassare il mock a fixture di test. Dipende da un contatto CER (nota
   di verifica del mercato nel repo privato `personal-archive`,
   `piano-lavorativo-nicola/opensource-impatto/06-verifica-cancello-cer.md`).
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

    Resta dentro questo punto, da decidere: **nessun tag semver** è stato creato, e la
    versione `0.0.1` vive in `pyproject.toml` e in `__init__.py` senza essere dichiarata nel
    CHANGELOG. E la **segnalazione privata di GitHub è disattivata** su questo repository:
    `SECURITY.md` oggi lo dice esplicitamente, ma se la si abilita (Settings > Code
    security) il documento va rimesso a indicarla.
11. **Uno scenario mock nella fascia critica 0,55–0,70.** I due scenari attuali stanno a
    0,272 e 0,976, cioè lontanissimi dalla soglia da entrambi i lati. Il bug più costoso
    che il progetto abbia trovato — la frazione al posto della differenza in punti
    percentuali — sbagliava del +79% proprio a rapporto 0,56, e quella fascia oggi la
    presidiano solo i test unitari. Basterebbe il `concentrata` con l'impianto raddoppiato.
12. **Robustezza residua, trovata in verifica avversariale e non ancora chiusa** (nessuna
    di queste sposta denaro oggi, tutte lo farebbero il giorno in cui qualcuno ci passa):
    - un membro chiamato `_fondi` finisce dentro il dizionario dei fondi e il rendiconto
      mente, con l'invariante di somma che regge lo stesso; simmetricamente un fondo
      statutario chiamato `finalita_sociali` si fonde con l'eccedentario;
    - un blocco con quota > 0 e nessun membro (o membri a energia nulla) muore con
      `ValueError: pesi tutti nulli`, che non dice quale blocco né quale criterio. Va
      deciso se è un errore o un caso legittimo col ripiego a quote uguali, come già fa
      il ramo eccedentario: oggi non è deciso, è capitato;
    - `NaN` passato a mano a `ripartisci` sfugge alle guardie e dà `InvalidOperation`, che
      è `ArithmeticError` e non `ValueError`. `regole.py` lo intercetta, ma il docstring di
      `ripartisci` promette una validazione che sul tipo e su `NaN` non ha;
    - le guardie di `ripartisci()` verificano solo il tipo di eccezione, mentre quelle di
      `regole.py` verificano il messaggio: è l'asimmetria che aveva lasciato invisibile una
      guardia morta (la somma dei fondi > 1, che sopravviveva al mutation testing);
    - la somma delle quote usa il contesto `Decimal` globale: dentro un `localcontext`
      a precisione bassa passano quote che non chiudono. Un modulo che si dichiara puro
      non dovrebbe dipendere da stato globale mutabile.
13. **Cumulo conto capitale (PNRR)**: la formula c'è ed è verificata — `TIP × (1 − F)`, F da
    0 a 0,50, esposta come parametro di `tip_unitaria`. Manca la parte difficile:
    l'energia afferente a punti di prelievo di enti territoriali, enti religiosi, enti del
    terzo settore, protezione ambientale e persone fisiche è **esente** dal fattore F, il
    che impone di partizionare l'energia condivisa in esente e non esente prima del calcolo.
14. Rendiconto: export CSV oltre al Markdown, campi utili al commercialista (Risoluzione AE
    33/2024). La dichiarazione che il vincolo eccedentario è calcolato sul periodo mentre
    il GSE lo verifica a conguaglio annuale c'è già, in fondo al rendiconto, ma solo quando
    l'eccedentario è diverso da zero. **Attenzione scrivendo l'export CSV**: la chiave
    `totale` di `incentivo_periodo` è `tip + arera` in euro e NON va portata in centesimi
    da sola, altrimenti reintroduce l'incoerenza chiusa al punto 15. Le due componenti si
    convertono separatamente — c'è un avviso in testa alla docstring della funzione.
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
