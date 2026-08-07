"""Ripartizione dichiarativa dell'incentivo tra i membri.

La ripartizione interna è materia statutaria (Regole Operative: serve un "soggetto
delegato responsabile del riparto"). Qui è modellata con regole dichiarative.
Tutti gli importi viaggiano in CENTESIMI (int); l'invariante somma == totale è
garantito dal metodo del resto maggiore. Vedi docs/FORMULE.md §4-5.
"""
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

# I valori soglia del vincolo eccedentario sono parametri normativi e stanno con gli
# altri in tariffe.py (CLAUDE.md, regola 4), non qui.
from .tariffe import (
    SOGLIA_ECCEDENTARIO_CUMULO_CONTO_CAPITALE,
    SOGLIA_ECCEDENTARIO_SOLA_TARIFFA,
)


def in_centesimi(euro: Decimal) -> int:
    return int((euro * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def ripartisci_centesimi(totale_cent: int, pesi: dict[str, Decimal]) -> dict[str, int]:
    """Ripartisce un importo in centesimi in proporzione ai pesi, senza perdere un cent.

    Metodo del resto maggiore: quote troncate, poi i centesimi residui assegnati alle
    frazioni più alte. A parità di resto il pareggio si rompe sull'ordine alfabetico
    DECRESCENTE della chiave: è una pura convenzione di determinismo (nessuna regola
    GSE la impone), ma è stabile e riproducibile, e i test la documentano.

    L'aritmetica è su interi e non sa nulla di valuta: `condivisione.alloca_oraria`
    riusa questa funzione con unità da 1e-6 kWh invece che centesimi.

    Un totale nullo si ripartisce in quote nulle anche se i pesi sono tutti nulli (è il
    caso del periodo senza immissioni); pesi tutti nulli con un totale da distribuire
    sono invece un errore, perché non esiste un criterio per ripartirlo.
    """
    tot_pesi = sum(pesi.values())
    if tot_pesi == 0:
        if totale_cent == 0:
            return {k: 0 for k in pesi}
        raise ValueError("pesi tutti nulli")
    esatte = {k: Decimal(totale_cent) * p / tot_pesi for k, p in pesi.items()}
    quote = {k: int(v) for k, v in esatte.items()}  # troncamento verso zero
    residuo = totale_cent - sum(quote.values())
    resti = sorted(pesi, key=lambda k: (esatte[k] - quote[k], k), reverse=True)
    for k in resti[:residuo]:
        quote[k] += 1
    assert sum(quote.values()) == totale_cent
    return quote


def _valida_eccedentario(
    importo_tip_cent: int,
    ec_kwh: Decimal,
    immissioni_kwh: Decimal,
    soglia: Decimal,
    dove: str = "",
) -> None:
    """Guardie comuni a `scomponi_eccedentario` e a `InsiemeIncentivato`.

    Stanno qui, e non nella sola dataclass, perché la primitiva è pubblica e viene
    chiamata direttamente: lasciarla scoperta significava che l'unica cosa a impedire
    argomenti scambiati era una proprietà del chiamante, non un contratto. Ciascuno
    di questi casi è stato misurato sul codice senza guardie, e nessuno era teorico:

        (20000, EC=1000, EI=700)      -> (2429, 17571): 88% dichiarato eccedentario
        (10000, EC=10000, EI=100)     -> (-984500, 994500): base NEGATIVA
        (10000, 60, 100, soglia=-0.5) -> (-1000, 11000): eccedentario > contributo
        (10000, 60, 100, soglia=55)   -> (10000, 0): azzera l'eccedentario IN SILENZIO
        (-10000, 70, 100)             -> (-8500, -1500)

    Il caso `soglia=55` è il più insidioso: non solleva nulla e non produce numeri
    assurdi, semplicemente non paga i consumatori non-imprese.
    """
    p = f"{dove}: " if dove else ""
    if not isinstance(importo_tip_cent, int) or isinstance(importo_tip_cent, bool):
        raise ValueError(
            f"{p}il contributo dev'essere un numero intero di centesimi, non "
            f"{importo_tip_cent!r}: il denaro viaggia in centesimi interi, altrimenti "
            "escono centesimi frazionari da una funzione che promette interi"
        )
    if importo_tip_cent < 0:
        raise ValueError(f"{p}contributo negativo: {importo_tip_cent} centesimi")
    for etichetta, valore in (
        ("energia condivisa", ec_kwh),
        ("energia immessa", immissioni_kwh),
        ("soglia", soglia),
    ):
        if isinstance(valore, Decimal) and not valore.is_finite():
            # NaN e Infinity vanno fermati PRIMA dei confronti: Decimal("NaN") < 0
            # solleva InvalidOperation, che è ArithmeticError e non ValueError.
            raise ValueError(f"{p}{etichetta} non è un numero finito: {valore}")
    if ec_kwh < 0 or immissioni_kwh < 0:
        raise ValueError(
            f"{p}energie negative: condivisa {ec_kwh} kWh, immessa {immissioni_kwh} kWh"
        )
    if not Decimal(0) <= soglia <= Decimal(1):
        raise ValueError(
            f"{p}soglia {soglia} fuori dall'intervallo 0–1. I valori normativi sono "
            "0,55 (sola tariffa premio) e 0,45 (cumulo con conto capitale), espressi "
            "come frazione: 55 al posto di 0,55 azzererebbe l'importo eccedentario "
            "senza che nulla protesti (Regole Operative pag. 41)"
        )
    if ec_kwh > immissioni_kwh:
        raise ValueError(
            f"{p}energia condivisa {ec_kwh} kWh maggiore dell'energia immessa "
            f"{immissioni_kwh} kWh: impossibile, perché E_ACI,h = min(E_immessa,h; "
            "E_prelevata,h) per ogni ora (Regole Operative pag. 40). Argomenti "
            "scambiati, o insieme composto male?"
        )


def scomponi_eccedentario(
    importo_tip_cent: int,
    ec_tot_kwh: Decimal,
    immissioni_tot_kwh: Decimal,
    soglia: Decimal = SOGLIA_ECCEDENTARIO_SOLA_TARIFFA,
) -> tuple[int, int]:
    """Divide l'importo della tariffa premio in (base, eccedentario).

    Forma normativa, verbatim dalle Regole Operative pag. 42 (verificata sul PDF
    ufficiale il 7 ago 2026):

        % E_ACI,ecc,j,n = max[0; (E_ACI,j,n / E_immessa,j,n * 100)% − valore soglia]
        C_ACI,ecc = Σ_j (% E_ACI,ecc,j,n * C_ACI,j,n)

    La quota eccedentaria è dunque la DIFFERENZA IN PUNTI PERCENTUALI fra il rapporto
    energia condivisa incentivabile / energia immessa e il valore soglia, applicata
    direttamente al contributo economico. Non è la frazione di energia condivisa che
    eccede la soglia: fino al 7 ago 2026 questo modulo calcolava (rapporto − soglia)
    / rapporto, che sovrastima l'eccedentario tanto più quanto più il rapporto è
    vicino alla soglia (+79% a rapporto 0,56) e spostava denaro reale fra categorie
    di membri. Con rapporto 0,60 e soglia 0,55: la norma dà 5% del contributo, la
    vecchia formula ne dava 8,33%.

    L'importo eccedentario va destinato ai soli consumatori diversi dalle imprese e/o
    a finalità sociali sui territori degli impianti (docs/FORMULE.md §4).

    Questa è la PRIMITIVA PER UN SINGOLO INSIEME "j". Le Regole Operative pag. 42
    vogliono che gli impianti incentivati siano aggregati in DUE insiemi (soglia 55%
    per la sola tariffa premio, 45% per il cumulo con conto capitale) e che gli
    importi eccedentari dei due insiemi si sommino: per farlo si usa
    `scomponi_eccedentario_insiemi`, che lega ogni insieme alla sua soglia.

    AVVERTENZA SUL PERIMETRO, che questa funzione non può imporre al chiamante: la
    verifica del superamento è fatta dal GSE a CONGUAGLIO, SU BASE ANNUALE (Regole
    Operative pag. 41). Applicarla a un singolo mese, come fa la demo, è
    un'approssimazione da dichiarare nel rendiconto.
    """
    _valida_eccedentario(importo_tip_cent, ec_tot_kwh, immissioni_tot_kwh, soglia)
    if immissioni_tot_kwh <= 0 or ec_tot_kwh <= 0:
        return importo_tip_cent, 0
    rapporto = ec_tot_kwh / immissioni_tot_kwh
    quota_ecc = max(Decimal(0), rapporto - soglia)  # differenza in punti percentuali
    if quota_ecc == 0:
        return importo_tip_cent, 0
    ecc = int((Decimal(importo_tip_cent) * quota_ecc).quantize(Decimal(1), ROUND_HALF_UP))
    return importo_tip_cent - ecc, ecc


@dataclass(frozen=True)
class InsiemeIncentivato:
    """Un insieme "j" di impianti incentivati, con la SUA soglia eccedentaria.

    Regole Operative pag. 42, verbatim: *"La quota percentuale di energia elettrica
    eccedentaria annuale è calcolata aggregando gli impianti di produzione incentivati
    in due insiemi"*. L'indice "j" della formula è l'INSIEME, non il singolo impianto;
    l'indice "n" è l'anno.

    I due insiemi previsti dalla norma (pag. 41, Appendice B §4 pag. 161) sono:
    impianti che accedono alla SOLA tariffa premio (soglia 55%) e impianti che la
    CUMULANO con un contributo in conto capitale (soglia 45%). Un impianto sta in uno
    e un solo insieme, e ogni grandezza (energia condivisa incentivabile, energia
    immessa, contributo economico) è la somma sugli impianti dell'insieme.

    `soglia` è un campo OBBLIGATORIO e senza default proprio perché associarla
    all'insieme sbagliato — o dimenticarla e prendere quella della sola tariffa —
    sposta denaro reale fra categorie di membri. I due costruttori nominati
    `sola_tariffa` e `cumulo_conto_capitale` la pescano dalle costanti di tariffe.py:
    sono la via consigliata, così la soglia non si scrive mai a mano.

    Campi: `nome` è un'etichetta libera che serve solo ai messaggi d'errore e alla
    tracciabilità; `contributo_tip_cent` è C_ACI,j,n in CENTESIMI (solo tariffa
    premio: la valorizzazione ARERA non concorre al vincolo, docs/FORMULE.md §3).
    """

    nome: str
    ec_kwh: Decimal
    immissioni_kwh: Decimal
    contributo_tip_cent: int
    soglia: Decimal

    def __post_init__(self) -> None:
        if not self.nome:
            raise ValueError("l'insieme incentivato deve avere un nome")
        # Le guardie sulle grandezze sono le STESSE della primitiva: stanno in una
        # funzione sola perché avere due strade con due livelli di controllo diversi
        # significa che una delle due è scoperta, e sarà quella che qualcuno userà.
        _valida_eccedentario(
            self.contributo_tip_cent,
            self.ec_kwh,
            self.immissioni_kwh,
            self.soglia,
            dove=f"insieme {self.nome!r}",
        )

    @classmethod
    def sola_tariffa(
        cls,
        ec_kwh: Decimal,
        immissioni_kwh: Decimal,
        contributo_tip_cent: int,
        nome: str = "sola_tariffa",
    ) -> "InsiemeIncentivato":
        """Insieme degli impianti a sola tariffa premio: soglia 55% (pag. 41)."""
        return cls(nome, ec_kwh, immissioni_kwh, contributo_tip_cent,
                   SOGLIA_ECCEDENTARIO_SOLA_TARIFFA)

    @classmethod
    def cumulo_conto_capitale(
        cls,
        ec_kwh: Decimal,
        immissioni_kwh: Decimal,
        contributo_tip_cent: int,
        nome: str = "cumulo_conto_capitale",
    ) -> "InsiemeIncentivato":
        """Insieme degli impianti in cumulo con conto capitale: soglia 45% (pag. 41)."""
        return cls(nome, ec_kwh, immissioni_kwh, contributo_tip_cent,
                   SOGLIA_ECCEDENTARIO_CUMULO_CONTO_CAPITALE)


def scomponi_eccedentario_insiemi(
    insiemi: Sequence[InsiemeIncentivato],
) -> tuple[int, int]:
    """Vincolo eccedentario aggregato sui DUE insiemi. Ritorna (base, ecc) in centesimi.

    Forma normativa, verbatim dalle Regole Operative pag. 42 (verificata sul PDF
    ufficiale il 7 ago 2026):

        % E_ACI,ecc,j,n = max[0; (E_ACI,j,n / E_immessa,j,n * 100)% − valore soglia]
        C_ACI,ecc = Σ_j (% E_ACI,ecc,j,n * C_ACI,j,n)

    La sommatoria su "j" è proprio questa funzione: ogni insieme ha il PROPRIO
    rapporto energia condivisa / energia immessa, la PROPRIA soglia e il PROPRIO
    contributo economico, si scompone da solo con `scomponi_eccedentario`, e solo alla
    fine i due importi eccedentari si sommano. Aggregare invece i due insiemi in uno
    darebbe un numero diverso e sbagliato: il rapporto medio non è la media dei
    rapporti, e le soglie sono due (55% e 45%, pag. 41).

    Non impone di ricevere esattamente due insiemi — una configurazione può non avere
    impianti in cumulo — ma i nomi devono essere distinti, così un insieme passato due
    volte per errore non conta doppio. Una sequenza vuota dà (0, 0).

    INVARIANTE: base + ecc == Σ_j contributo_tip_cent,j, esatto al centesimo. Regge
    anche quando i singoli insiemi arrotondano male, perché `scomponi_eccedentario`
    arrotonda una volta sola l'importo eccedentario e ricava la base per differenza
    (base_j = C_j − ecc_j): ogni addendo chiude per costruzione, e una somma di
    uguaglianze esatte è esatta. Nessun centesimo si crea e nessuno si perde.

    LA VERIFICA È ANNUALE, A CONGUAGLIO: *"La verifica del superamento del valore
    soglia è effettuata dal GSE, a conguaglio, su base annuale"* (Regole Operative
    pag. 41), e l'indice "n" della formula di pag. 42 è appunto l'ANNO. Applicare
    questa funzione a un singolo mese — come fa la demo — è un'APPROSSIMAZIONE: un
    mese di gennaio sopra soglia e un mese di luglio sotto soglia non si compensano
    come farebbero nel conguaglio annuale, dove conta solo il rapporto sui dodici
    mesi. Il rendiconto deve dichiararlo.
    """
    # La firma dichiara Sequence, ma un generatore la soddisfa abbastanza da entrare e
    # si esaurisce al primo giro: la funzione itera due volte (i nomi, poi il calcolo).
    # Misurato prima di questa riga: passando un generatore al posto della lista, la
    # funzione restituiva (0, 0) e annullava in silenzio l'INTERO contributo TIP, con
    # l'assert finale complice perché iterava anche lui sul generatore ormai vuoto.
    insiemi = list(insiemi)
    nomi = [i.nome for i in insiemi]
    if len(set(nomi)) != len(nomi):
        raise ValueError(f"nomi di insieme duplicati: {sorted(nomi)}")
    totale_atteso = sum(i.contributo_tip_cent for i in insiemi)

    base_tot = 0
    ecc_tot = 0
    for insieme in insiemi:
        base, ecc = scomponi_eccedentario(
            insieme.contributo_tip_cent,
            insieme.ec_kwh,
            insieme.immissioni_kwh,
            insieme.soglia,
        )
        base_tot += base
        ecc_tot += ecc

    assert base_tot + ecc_tot == totale_atteso
    return base_tot, ecc_tot


def ripartisci(
    regole: dict,
    importo_base_cent: int,
    importo_eccedentario_cent: int,
    energia_immessa_kwh: dict[str, Decimal],
    contributi_consumo_kwh: dict[str, Decimal],
    membri: dict[str, dict],
) -> dict[str, dict]:
    """Applica le regole statutarie dichiarative. Ritorna {membro: {voce: centesimi}}.

    `regole` esempio:
        {"fondi": {"gestione": Decimal("0.10")},          # % sul totale base
         "quota_produttori": Decimal("0.50"),             # % del residuo dopo i fondi
         "quota_consumatori": Decimal("0.50"),
         "criterio_produttori": "energia_immessa",        # o "quote_uguali"
         "criterio_consumatori": "prelievo_coincidente"}  # o "quote_uguali"

    `membri`: {id: {"ruolo": "produttore"|"consumatore"|"prosumer", "impresa": bool}}.
    L'eccedentario va solo ai consumatori con impresa=False (vincolo Regole Operative);
    se non ce ne sono, resta in un fondo "finalita_sociali".

    Le regole statutarie sono validate prima di qualunque conto: percentuali dei fondi
    non negative e di somma ≤ 1, quote dei blocchi non negative e di somma esattamente
    1, importi non negativi. Fino al 7 ago 2026 si controllava solo `qp + qc == 1`, e
    quindi `quota_produttori=1,5` con `quota_consumatori=−0,5` passava e assegnava ai
    consumatori una quota NEGATIVA (con l'invariante finale, che è una somma, comunque
    soddisfatto: un membro pagava per gli altri).
    """
    if importo_base_cent < 0 or importo_eccedentario_cent < 0:
        raise ValueError("gli importi da ripartire non possono essere negativi")

    esito: dict[str, dict] = {m: {} for m in membri}
    esito["_fondi"] = {}

    # 1. fondi statutari sul totale base
    fondi = regole.get("fondi", {})
    for nome, perc in fondi.items():
        if perc < 0:
            raise ValueError(f"la percentuale del fondo {nome!r} è negativa ({perc})")
    if sum(fondi.values(), Decimal(0)) > 1:
        raise ValueError(
            f"le percentuali dei fondi sommano a {sum(fondi.values(), Decimal(0))}: "
            "oltre 1 lascerebbero ai membri un residuo negativo"
        )
    residuo = importo_base_cent
    for nome, perc in fondi.items():
        q = int((Decimal(importo_base_cent) * perc).quantize(Decimal(1), ROUND_HALF_UP))
        esito["_fondi"][nome] = q
        residuo -= q
    if residuo < 0:
        # Le percentuali passano la guardia ma i singoli arrotondamenti al centesimo
        # sfondano il totale: succede solo con percentuali che sommano quasi a 1 e
        # importi di pochi centesimi (0.01 € diviso in due fondi da 0,5 dà 1 + 1 = 2).
        raise ValueError(
            f"i fondi arrotondati superano l'importo base di {-residuo} centesimi"
        )

    # 2. residuo diviso tra blocco produttori e blocco consumatori
    qp = regole.get("quota_produttori", Decimal("0.5"))
    qc = regole.get("quota_consumatori", Decimal("0.5"))
    if qp < 0 or qc < 0:
        raise ValueError(
            f"quota_produttori ({qp}) e quota_consumatori ({qc}) non possono essere "
            "negative: sommerebbero comunque a 1 ma darebbero quote negative ai membri"
        )
    if qp + qc != 1:
        raise ValueError("quota_produttori + quota_consumatori deve fare 1")
    blocco = ripartisci_centesimi(residuo, {"prod": qp, "cons": qc})

    produttori = [m for m, d in membri.items() if d["ruolo"] in ("produttore", "prosumer")]
    consumatori = [m for m, d in membri.items() if d["ruolo"] in ("consumatore", "prosumer")]

    def pesi(ids: list[str], criterio: str, energie: dict[str, Decimal]) -> dict[str, Decimal]:
        if criterio == "quote_uguali":
            return {m: Decimal(1) for m in ids}
        return {m: energie.get(m, Decimal(0)) for m in ids}

    for m, cent in ripartisci_centesimi(
        blocco["prod"], pesi(produttori, regole.get("criterio_produttori", "energia_immessa"), energia_immessa_kwh)
    ).items():
        esito[m]["quota_produttore"] = cent
    for m, cent in ripartisci_centesimi(
        blocco["cons"], pesi(consumatori, regole.get("criterio_consumatori", "prelievo_coincidente"), contributi_consumo_kwh)
    ).items():
        esito[m]["quota_consumatore"] = cent

    # 3. eccedentario: solo consumatori non-imprese, altrimenti fondo finalità sociali
    if importo_eccedentario_cent:
        idonei = [m for m in consumatori if not membri[m].get("impresa")]
        if idonei:
            p = pesi(idonei, regole.get("criterio_consumatori", "prelievo_coincidente"), contributi_consumo_kwh)
            if sum(p.values()) == 0:
                p = {m: Decimal(1) for m in idonei}
            for m, cent in ripartisci_centesimi(importo_eccedentario_cent, p).items():
                esito[m]["quota_eccedentaria"] = cent
        else:
            esito["_fondi"]["finalita_sociali"] = (
                esito["_fondi"].get("finalita_sociali", 0) + importo_eccedentario_cent
            )

    totale = importo_base_cent + importo_eccedentario_cent
    assert sum(v for d in esito.values() for v in d.values()) == totale
    return esito
