"""Rendiconto per membro: dal risultato della ripartizione a un testo leggibile.

Due scritture della stessa sostanza: `rendiconto_markdown` per le persone (totali,
contesto del vincolo eccedentario, note), `rendiconto_csv` per chi deve rielaborare i
numeri — il commercialista in testa (Risoluzione AE 33/2024: il trattamento fiscale del
riparto è fuori perimetro del motore, ma i dati per farlo devono uscire da qui).
Entrambe sono pure: ritornano testo, l'I/O resta al chiamante.
"""
import csv
import io
from decimal import Decimal

from .comune import in_euro
from .ripartizione import FONDO_ECCEDENTARIO, VOCE_FONDI, in_centesimi


def _perc(frazione: Decimal) -> str:
    return f"{frazione * 100:.1f}%"


def _componenti_cent(incentivo: dict, esito: dict[str, dict]) -> tuple[int, int]:
    """Centesimi autorevoli di TIP e ARERA, con la guardia di coerenza sul ripartito.

    È la logica condivisa dai due rendiconti, e la ragione per cui sta in una funzione
    sola è la stessa di `ripartizione._valida_eccedentario`: due scritture con due
    livelli di controllo diversi significano che una delle due è scoperta.

    COERENZA DEGLI ARROTONDAMENTI. I totali si costruiscono sulle STESSE quantità in
    centesimi che la ripartizione ha distribuito: `in_centesimi(tip)` e
    `in_centesimi(arera)` presi separatamente, e il totale come loro SOMMA. Non si
    arrotonda mai la somma in euro, perché `in_centesimi(tip + arera)` e
    `in_centesimi(tip) + in_centesimi(arera)` possono differire di un centesimo — con
    tip = 1,005 € e arera = 2,005 € il primo dà 301 e il secondo 302 — e la tabella,
    che riparte i centesimi con l'invariante somma == totale, chiude sul secondo.

    CHI DECIDE I CENTESIMI. Le chiavi facoltative `tip_cent` e `arera_cent` di
    `incentivo` sono autorevoli: se ci sono, si usano così come sono. Servono quando
    l'arrotondamento è già avvenuto a monte, e non una volta sola — è il caso del
    vincolo eccedentario sui due insiemi (`ripartizione.scomponi_eccedentario_insiemi`,
    Regole Operative pag. 42), dove ogni insieme porta il proprio contributo già in
    centesimi interi e la loro somma può differire di un centesimo da
    `in_centesimi(somma dei Decimal)`. Senza quelle chiavi si ricade sul comportamento
    storico, corretto finché il chiamante arrotonda una volta sola.

    Se gli importi ripartiti non chiudono sui centesimi delle due componenti si
    solleva `ValueError` invece di produrre un rendiconto che non torna.
    """
    tip_cent = incentivo.get("tip_cent")
    if tip_cent is None:
        tip_cent = in_centesimi(incentivo["tip"])
    arera_cent = incentivo.get("arera_cent")
    if arera_cent is None:
        arera_cent = in_centesimi(incentivo["arera"])
    ripartito_cent = sum(v for voci in esito.values() for v in voci.values())
    if ripartito_cent != tip_cent + arera_cent:
        raise ValueError(
            f"rendiconto incoerente: la ripartizione distribuisce {ripartito_cent} "
            f"centesimi, ma TIP ({tip_cent}) + ARERA ({arera_cent}) fanno "
            f"{tip_cent + arera_cent}. "
            "Il chiamante deve portare in centesimi le due componenti SEPARATAMENTE "
            "prima di ripartirle — in_centesimi(tip) + in_centesimi(arera) — e non "
            "arrotondare la somma in euro: i due valori differiscono di un centesimo "
            "quando entrambe le componenti cadono su mezzo centesimo. Se invece "
            "l'arrotondamento è già avvenuto a monte, per esempio per insieme "
            "incentivato, passa i totali autorevoli nelle chiavi 'tip_cent' e "
            "'arera_cent' invece di farli riderivare da qui."
        )
    return tip_cent, arera_cent


def rendiconto_markdown(
    periodo: str,
    incentivo: dict,
    esito: dict[str, dict],
    membri: dict[str, dict],
) -> str:
    """Rendiconto della CER in Markdown: totali, fondi e riga per membro.

    `incentivo` è il dizionario di `tariffe.incentivo_periodo` sommato sugli impianti
    (chiavi `tip`, `arera`, `ec_tot_kwh` in Decimal). Le chiavi facoltative
    `immissioni_tot_kwh` e `soglia_eccedentario` fanno stampare la riga sul rapporto
    energia condivisa / energia immessa e sullo stato del vincolo eccedentario
    (docs/FORMULE.md §4); senza di esse la riga è omessa.

    COERENZA DEGLI ARROTONDAMENTI. L'intestazione è costruita sulle STESSE quantità in
    centesimi che la ripartizione ha distribuito, e la guardia che lo verifica sta in
    `_componenti_cent`, che è anche l'unico posto dove la regola è spiegata per esteso
    (comprese le chiavi autorevoli `tip_cent` e `arera_cent`): il rendiconto CSV la
    condivide, e due spiegazioni della stessa regola divergono al primo aggiornamento.
    Fino al 7 ago 2026 l'intestazione formattava i Decimal in euro (per giunta con
    l'arrotondamento ROUND_HALF_EVEN del formato, diverso dal ROUND_HALF_UP di
    `in_centesimi`): con tip = 1,005 € e arera = 2,005 € stampava "TIP 1,00 · ARERA
    2,00 · totale 3,01" sopra una tabella che sommava 3,02, tre numeri incoerenti.
    """
    tip_cent, arera_cent = _componenti_cent(incentivo, esito)
    totale_cent = tip_cent + arera_cent

    righe = [
        f"# Rendiconto CER — {periodo}",
        "",
        f"Energia condivisa: **{incentivo['ec_tot_kwh']:.0f} kWh** · "
        f"TIP: **{in_euro(tip_cent)}** · valorizzazione ARERA: **{in_euro(arera_cent)}** · "
        f"totale: **{in_euro(totale_cent)}**",
    ]

    immesse = incentivo.get("immissioni_tot_kwh")
    soglia = incentivo.get("soglia_eccedentario")
    if immesse is not None and soglia is not None and immesse > 0:
        rapporto = Decimal(incentivo["ec_tot_kwh"]) / Decimal(immesse)
        scarto = max(Decimal(0), rapporto - Decimal(soglia))
        stato = (
            f"**attivo**, {_perc(scarto)} del TIP in quota eccedentaria"
            if scarto > 0 else "**non attivo**"
        )
        righe.append(
            f"Energia immessa: **{immesse:.0f} kWh** · rapporto EC/EI: "
            f"**{_perc(rapporto)}** contro una soglia del **{_perc(Decimal(soglia))}**, "
            f"vincolo eccedentario {stato}"
        )

    righe += [
        "",
        "| Membro | Ruolo | Quota produttore | Quota consumatore | Quota eccedentaria | Totale |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for m, voci in sorted(esito.items()):
        if m == VOCE_FONDI:
            continue
        qp, qc, qe = voci.get("quota_produttore", 0), voci.get("quota_consumatore", 0), voci.get("quota_eccedentaria", 0)
        righe.append(
            f"| {m} | {membri[m]['ruolo']} | {in_euro(qp)} | {in_euro(qc)} | {in_euro(qe)} | {in_euro(qp + qc + qe)} |"
        )
    if esito.get(VOCE_FONDI):
        righe += ["", "**Fondi statutari:** " + " · ".join(
            f"{nome}: {in_euro(cent)}" for nome, cent in esito[VOCE_FONDI].items())]

    # `FONDO_ECCEDENTARIO` è un nome riservato (`ripartizione.ripartisci` rifiuta un
    # fondo statutario omonimo), quindi quello che si legge qui è tutto e solo importo
    # eccedentario: prima della riserva un fondo di statuto con quel nome ci si sommava
    # e faceva comparire la nota qui sotto anche su un periodo senza eccedentario.
    eccedentario_cent = sum(
        voci.get("quota_eccedentaria", 0) for m, voci in esito.items() if m != VOCE_FONDI
    ) + esito.get(VOCE_FONDI, {}).get(FONDO_ECCEDENTARIO, 0)
    if eccedentario_cent:
        righe += ["", "*Il vincolo dell'importo eccedentario è qui applicato al singolo "
                  "periodo di calcolo; il GSE lo verifica a conguaglio su base annuale "
                  "(Regole Operative pag. 41). Su un mese è un'approssimazione.*"]

    righe += ["", "*Calcolo su dati mock — non usare per riparti reali. "
              "Formule e fonti: docs/FORMULE.md.*"]
    return "\n".join(righe)


# --- rendiconto in CSV (roadmap 14) ------------------------------------------------

INTESTAZIONE_CSV = (
    "periodo",
    "voce",
    "tipo",
    "ruolo",
    "impresa",
    "quota_produttore_eur",
    "quota_consumatore_eur",
    "quota_eccedentaria_eur",
    "quota_fondo_eur",
    "totale_eur",
)
"""Ordine delle colonne del rendiconto CSV: fisso, e parte del contratto.

Chi importa questo file lo fa una volta e poi lo rifà ogni mese per vent'anni, con lo
stesso foglio o lo stesso script: cambiare l'ordine — o rinominare una colonna — sposta
i numeri in caselle diverse senza che nulla protesti. Le colonne si aggiungono in fondo.
"""


def _importo_csv(cent: int) -> str:
    """Importo in euro per il CSV: separatore decimale il PUNTO, nessun simbolo.

    Non usa `comune.in_euro`, che produce "241,72 €" (a video va benissimo) ma in una
    colonna numerica è testo: chi la somma ottiene zero. Stessa convenzione dei CSV di
    misura del mock (`mock.genera`, `energia_kwh` a 3 decimali col punto), che è il solo
    dialetto già in uso nel progetto.
    """
    return f"{Decimal(cent) / 100:.2f}"


def rendiconto_csv(
    periodo: str,
    incentivo: dict,
    esito: dict[str, dict],
    membri: dict[str, dict],
) -> str:
    """Rendiconto della CER in CSV: una riga per destinatario, importi in euro.

    Stessa sostanza di `rendiconto_markdown` e stessi argomenti, altro pubblico: il
    Markdown è per l'assemblea, questo è per chi i numeri li deve rielaborare — il
    commercialista in testa, perché il trattamento fiscale del riparto (Risoluzione AE
    33/2024) è fuori dal perimetro del motore ma i dati per deciderlo devono uscire da
    qui. Le colonne che servono a quella decisione sono `ruolo` e `impresa` (la natura
    del percettore) e la scomposizione dell'importo per titolo: quota da produttore,
    quota da consumatore, quota eccedentaria, fondo.

    FORMATO. Separatore `;` e punto decimale, come i CSV di misura del mock: è il
    dialetto che Excel italiano apre senza procedura di importazione. Fine riga `\\n`
    esplicito e non il `\\r\\n` di default di `csv.writer`, perché la funzione ritorna
    testo e l'I/O lo fa il chiamante: con `Path.write_text` su Windows un `\\r\\n` già
    scritto diventerebbe `\\r\\r\\n`. L'ordine delle colonne è `INTESTAZIONE_CSV` e non
    cambia; le righe sono ordinate per identificativo, prima i membri e poi i fondi,
    così due esecuzioni sugli stessi dati danno lo stesso file byte per byte.

    COSA NON C'È, di proposito. Nessuna riga di totali e nessuna riga di commento: il
    file è rettangolare dalla prima riga all'ultima, così `SOMMA(totale_eur)` è il
    totale ripartito e non il doppio, e ogni riga si può filtrare senza inciampare in
    una riga che non è un pagamento. L'intestazione con energia condivisa, TIP e
    valorizzazione ARERA sta nel rendiconto Markdown, che è il riepilogo; questo è
    l'elenco dei destinatari. Non c'è nemmeno la nota sul vincolo eccedentario che il
    Markdown stampa in fondo — vale identica anche qui: il vincolo è applicato al
    singolo periodo di calcolo, mentre il GSE lo verifica a conguaglio su base annuale
    (Regole Operative pag. 41), quindi su un mese è un'approssimazione.

    IL FONDO DELL'IMPORTO ECCEDENTARIO sta in `quota_eccedentaria_eur`, non in
    `quota_fondo_eur`, e si riconosce dal `tipo`. Non è una sottigliezza contabile: le
    Regole Operative pag. 41 danno all'importo eccedentario UNA destinazione con due
    forme — "ai soli consumatori diversi dalle imprese e\\o [...] per finalità sociali"
    — e `FONDO_ECCEDENTARIO` è la seconda, cioè quel che resta quando nella CER non ci
    sono consumatori idonei. Sommare quella colonna deve dare l'importo eccedentario del
    periodo comunque sia stato destinato. I fondi statutari, che sono un'altra cosa
    (deliberati dall'assemblea, non imposti dalla norma), stanno in `quota_fondo_eur`.

    INVARIANTE: la somma di `totale_eur` è TIP + ARERA del periodo, fondi compresi. La
    guardia è quella condivisa con il Markdown (`_componenti_cent`): se gli importi
    ripartiti non chiudono sui centesimi delle due componenti, la funzione solleva
    `ValueError` invece di esportare un file che non torna.
    """
    # Il valore di ritorno non serve qui — nel CSV non c'è riga di totali — ma la
    # chiamata sì: è la guardia di coerenza, e saltarla renderebbe l'export l'unica
    # uscita del motore capace di scrivere un riparto che non chiude.
    _componenti_cent(incentivo, esito)

    # `csv.writer` vuole un file, non una stringa: `StringIO(newline="")` è la forma
    # documentata per riceverne il testo senza passare dal disco (il motore è puro).
    buffer = io.StringIO(newline="")
    scrittore = csv.writer(buffer, delimiter=";", lineterminator="\n")
    scrittore.writerow(INTESTAZIONE_CSV)

    for m, voci in sorted(esito.items()):
        if m == VOCE_FONDI:
            continue
        qp = voci.get("quota_produttore", 0)
        qc = voci.get("quota_consumatore", 0)
        qe = voci.get("quota_eccedentaria", 0)
        scrittore.writerow([
            periodo, m, "membro", membri[m]["ruolo"],
            # `impresa` è facoltativa in `ripartizione.ripartisci`, che la legge con
            # .get(): assente vale "non impresa", ed è il caso in cui l'eccedentario
            # spetta. La colonna dice quindi "no", non lascia il vuoto da interpretare.
            "si" if membri[m].get("impresa") else "no",
            _importo_csv(qp), _importo_csv(qc), _importo_csv(qe),
            _importo_csv(0), _importo_csv(qp + qc + qe),
        ])

    for nome, cent in sorted(esito.get(VOCE_FONDI, {}).items()):
        eccedentario = nome == FONDO_ECCEDENTARIO
        scrittore.writerow([
            periodo, nome,
            "fondo_eccedentario" if eccedentario else "fondo_statutario",
            "", "",
            _importo_csv(0), _importo_csv(0),
            _importo_csv(cent if eccedentario else 0),
            _importo_csv(0 if eccedentario else cent),
            _importo_csv(cent),
        ])

    return buffer.getvalue()
