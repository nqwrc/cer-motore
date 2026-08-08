# Mappa delle regole di calcolo — fonti e stato di verifica

Aggiornata al 7 agosto 2026. Stato di ogni regola: **[verificato]** = letto verbatim sul
documento ufficiale · **[assunto]** = da confermare · **[modellazione]** = scelta di
implementazione, non imposta dalla norma.

**Convenzione sui numeri di pagina, valida per tutto il repository** — documenti, docstring
del codice e commenti dei test. Ogni "pag. N" delle Regole Operative è il numero **stampato a
piè di pagina** del PDF ufficiale (171 pagine, agg. DD 16/7/2025, approvate con DM MASE
228/2025), mai quello dell'indice del lettore PDF, che è sfasato di 1. L'unica eccezione è
dove sta scritto "PDF" per esteso.

Esempio, perché lo sfasamento crea confusione proprio qui: l'Appendice B comincia a
**pag. stampata 160**, che il lettore PDF numera 161; i suoi paragrafi §3 e §4 stanno a
**pag. stampata 161**. Quando altrove si legge "Appendice B §4 pag. 161" è la pagina
stampata, non la 161 del lettore.

## 1. Energia condivisa (autoconsumata virtualmente) — [verificato]

Per **ciascuna ora**, verbatim dalle Regole Operative pag. 40:

> L'energia elettrica condivisa incentivabile per l'ora h è determinata sulla base del
> seguente algoritmo: `E_ACI,h = min(E_immessa,h ; E_prelevata,h)`

dove immissioni e prelievi sono le somme su tutti i punti di connessione della
configurazione, sottesi alla **stessa cabina primaria**. Il calcolo ufficiale lo fa il
**GSE** sulle misure dei distributori; il motore lo replica per trasparenza, verifica e
ripartizione interna.

## 1-bis. Attribuzione dell'energia condivisa ai singoli impianti — [modellazione]

L'energia condivisa è una grandezza della *configurazione*, ma la tariffa premio si calcola
*per impianto* (scaglione di potenza, cap e correttivo geografico dipendono dal singolo POD
di produzione). Serve quindi una regola di attribuzione, e le Regole Operative non ne
prescrivono una: `condivisione.alloca_oraria` usa il criterio pro-quota oraria delle
immissioni, `quota[i][h] = EC[h] × immissioni[i][h] / Σ immissioni[h]`.

Stessa regola, applicata ai prelievi invece che alle immissioni, per il contributo dei
consumatori (`contributo_prelievo_coincidente`, criterio "chi consuma quando il sole
produce", il più comune negli statuti).

Il riparto avviene in unità intere da **1e-6 kWh** col metodo del resto maggiore, così che
la somma delle quote sia *esattamente* EC (la sola divisione non chiude: `10 × 4/12` tre
volte non fa 10). Anche la risoluzione è una scelta: le misure dei distributori hanno 3
decimali di kWh, il margine è di tre cifre. Se i tracciati GSE prescrivessero un
arrotondamento, va sostituita — è il parametro `decimali`.

## 2. Tariffa premio (TIP) — [verificato]

Forma normativa, verbatim dalle Regole Operative pag. 40:

> `TIP_h = {min[CAP ; TP_base + max(0; 180 − Pz)] + FC_zonale} * (1 − F)`

e il contributo del mese è `C_ACI = Σ_h (TIP_h × E_ACI,h)`. Riconosciuta per **20 anni**
dall'entrata in esercizio, sugli impianti fino a 1 MW.

| Potenza impianto | TP_base | CAP |
|---|---|---|
| P ≤ 200 kW | 80 €/MWh | 120 €/MWh |
| 200 < P ≤ 600 kW | 70 €/MWh | 110 €/MWh |
| P > 600 kW | 60 €/MWh | 100 €/MWh |

Fonte della tabella e della formula: Appendice B §1 pag. 160, che riporta ad esempio
*"per impianti di potenza ≤ 200 kW — TIP: 80 + max (0; 180 − Pz) [...] La tariffa premio
non può eccedere il valore di 120 €/MWh"*. Identica, parola per parola, nel DM CACER
414/2023 All. 1 §1 (pag. 23 del PDF MASE): due fonti primarie indipendenti.

**Pz è il prezzo zonale ORARIO** (Appendice A pag. 156: prezzo di cui alla Sezione
2-13.3.8 del TIDE; il PUN Index GME vale solo per impianti su reti non interconnesse).

**Non esiste un tetto di 40 €/MWh sulla parte variabile.** Il tetto è il CAP e agisce sulla
somma. In tutte le 171 pagine il "40 €/MWh" compare una volta sola, a pag. 39, come campo
di variazione del parametro `Z` usato per l'*acconto*. Che la parte variabile risulti di
fatto fra 0 e 40 è una conseguenza di `CAP − TP_base = 40` in tutti e tre gli scaglioni.
Il motore ha usato fino al 7/8/2026 la forma `max(0, min(40, 180 − Pz))`: dà gli stessi
numeri oggi, ma sbaglierebbe in silenzio se un aggiornamento muovesse TP_base e CAP in
modo non parallelo.

**Correttivo geografico FC_zonale (solo fotovoltaico), FUORI dal cap:** +4 €/MWh centro
(Lazio, Marche, Toscana, Umbria, Abruzzo); **+10 €/MWh nord (inclusa Emilia-Romagna)**.
Sta dentro la graffa ma fuori dal `min`, quindi il massimo al nord per un impianto
≤ 200 kW è 130 €/MWh. Appendice B §2 pag. 160.

**Fattore F**, decurtazione per cumulo con contributo in conto capitale: varia linearmente
fra 0 (nessun contributo) e 0,50 (contributo pari al 40% dell'investimento). Appendice B §3
pag. 161. *Punto aperto*: l'energia afferente a punti di prelievo di enti territoriali,
enti religiosi, enti del terzo settore, protezione ambientale e persone fisiche è **esente**
dal fattore F (pag. 41), il che richiede di partizionare l'energia condivisa in esente e
non esente. Il motore espone il parametro ma non fa la partizione.

## 3. Corrispettivo di valorizzazione ARERA (TIAD) — [verificato] struttura

Su ogni MWh condiviso: restituzione componenti tariffarie ≈ **8,22 €/MWh** (trasmissione,
valore 2024; 8,48 nel 2023 — varia ogni anno, parametro configurabile). Per le CER **non**
si applica la quota distribuzione (+0,65) né perdite evitate, riservate ai gruppi di
autoconsumatori. Non è tariffa premio: non entra nel vincolo del §4.

## 4. Vincolo dell'importo eccedentario — [verificato]

Verbatim dalle Regole Operative pag. 42:

> `% E_ACI,ecc,j,n = max[0 ; (E_ACI,j,n / E_immessa,j,n * 100)% − valore soglia]`
> `C_ACI,ecc = Σ_j (% E_ACI,ecc,j,n * C_ACI,j,n)`

La quota eccedentaria è la **differenza in punti percentuali** fra il rapporto energia
condivisa incentivabile / energia immessa e il valore soglia, applicata direttamente al
contributo economico. **Non** è la frazione di energia condivisa che eccede la soglia: il
motore calcolava `(rapporto − soglia)/rapporto` fino al 7/8/2026, sovrastimando
l'eccedentario del 79% a rapporto 0,56 e dell'11% a rapporto 0,90.

**Valori soglia** (pag. 41 e Appendice B §4 pag. 161): **55%** per gli impianti che accedono
alla sola tariffa premio, **45%** per quelli che la cumulano con un contributo in conto
capitale. Gli impianti incentivati vanno aggregati nei **due insiemi "j"** e la
scomposizione fatta per insieme, poi sommata.

**La verifica è annuale, a conguaglio**, fatta dal GSE (pag. 41). Applicarla a un singolo
mese — come fa la demo — è un'approssimazione, da dichiarare nel rendiconto.

L'importo eccedentario va destinato *"ai soli consumatori diversi dalle imprese e\o
utilizzato per finalità sociali aventi ricadute sui territori ove sono ubicati gli impianti
per la condivisione"* (pag. 41). Le Regole elencano a pag. 42 esempi non esaustivi di
finalità sociali (ambiente, rigenerazione urbana, inclusione di soggetti vulnerabili).

## 5. Ripartizione interna — libera ma vincolata

La ripartizione tra membri è materia **statutaria** (il GSE paga il referente; le Regole
impongono un "soggetto delegato responsabile del riparto"). Il motore la modella con regole
dichiarative: fondi a percentuale, quote produttori/consumatori, criteri pro-quota (energia
immessa; prelievo coincidente con la condivisione oraria; quote uguali), più il vincolo del
§4. Fiscalità del riparto: Risoluzione AE 33/2024 (fuori perimetro motore).

## Punti ancora aperti

- **Esenzione dal fattore F**: partizione dell'energia condivisa in esente e non esente
  (§2). Serve prima di modellare seriamente il cumulo con conto capitale.
- **Valore TIAD per anno**: 8,22 è il 2024. Serve la serie storica e la fonte ARERA puntuale.
- **Formato reale export GSE** dall'area clienti: il mock è un'assunzione documentata
  (`MOCK-GSE.md`). Non dipende da noi, dipende da una CER che ci passi un export vero.
- **Risoluzione di arrotondamento** dell'attribuzione per impianto (§1-bis): scelta nostra,
  da allineare se i tracciati GSE ne impongono una.

## Riferimenti

- [Regole Operative CACER (GSE, PDF ufficiale)](https://www.gse.it/documenti_site/Documenti%20GSE/Servizi%20per%20te/AUTOCONSUMO/Gruppi%20di%20autoconsumatori%20e%20comunita%20di%20energia%20rinnovabile/Regole%20e%20procedure/ALLEGATO%201%20Regole%20Operative%20CACER.pdf)
  — agg. DD 16/7/2025, 171 pagine, sha256 `bb0efe22316e81d48f0df40dde3ac1afcce2cb5ff1953b7820df9e55562d8641`
  (scaricato e verificato il 7/8/2026). Nessun login, il PDF è interamente estraibile.
- [DM CACER 7 dicembre 2023 n. 414, Allegato 1 (MASE)](https://www.mase.gov.it/portale/documents/d/guest/decreto-cer-pdf) — seconda fonte primaria, testo identico
- [GSE — mappa cabine primarie](https://www.gse.it/servizi-per-te/autoconsumo/mappa-interattiva-delle-cabine-primarie)
- TIAD: ARERA, delibera 727/2022/R/eel e s.m.i.
