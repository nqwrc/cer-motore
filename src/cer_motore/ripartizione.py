"""Ripartizione dichiarativa dell'incentivo tra i membri.

La ripartizione interna è materia statutaria (Regole Operative: serve un "soggetto
delegato responsabile del riparto"). Qui è modellata con regole dichiarative.
Tutti gli importi viaggiano in CENTESIMI (int); l'invariante somma == totale è
garantito dal metodo del resto maggiore. Vedi docs/FORMULE.md §4-5.

Due cose che l'invariante di somma NON protegge, e che qui sono protette a parte:
il denaro può finire nella voce sbagliata senza che il totale se ne accorga (di qui i
nomi riservati `VOCE_FONDI` e `FONDO_ECCEDENTARIO`), e l'aritmetica `Decimal` dipende
dal contesto del chiamante, che è stato globale e mutabile (di qui il `CONTESTO` di
`comune.py`, che protegge allo stesso modo anche `tariffe` e `condivisione`).

L'invariante è difeso da `raise` e non da `assert`: un `assert` sparisce con
`python -O`, e sotto -O un riparto che non chiude tornerebbe in silenzio a chi paga.
"""
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

# Contesto decimale, decoratore e formattazione stanno in comune.py, che non importa
# nulla dal pacchetto: servono anche a `tariffe`, che questo modulo importa, e tenerli
# qui avrebbe creato un ciclo.
from .comune import CONTESTO, elenco, in_euro, nel_contesto_del_motore  # noqa: F401
# I valori soglia del vincolo eccedentario sono parametri normativi e stanno con gli
# altri in tariffe.py (CLAUDE.md, regola 4), non qui.
from .tariffe import (
    SOGLIA_ECCEDENTARIO_CUMULO_CONTO_CAPITALE,
    SOGLIA_ECCEDENTARIO_SOLA_TARIFFA,
)

# --- nomi riservati nel risultato della ripartizione -------------------------------

VOCE_FONDI = "_fondi"
"""Chiave del risultato di `ripartisci` che raccoglie i fondi: NON è un membro.

Nessun membro può chiamarsi così, e `ripartisci` lo rifiuta. Il risultato è un dict
piatto {nome: {voce: centesimi}} in cui i fondi occupano una chiave come tutti gli
altri: un socio con questo identificativo ci finiva dentro e il rendiconto diventava
falso senza che nulla protestasse (vedi la guardia in `ripartisci`).
"""

FONDO_ECCEDENTARIO = "finalita_sociali"
"""Voce di fondo in cui `ripartisci` deposita l'importo eccedentario senza idonei.

Regole Operative pag. 41: l'importo eccedentario va ai soli consumatori diversi dalle
imprese e/o a finalità sociali sui territori degli impianti. Nome riservato: un fondo
statutario omonimo si fonderebbe con questo importo in una riga sola.
"""

# --- vocabolario chiuso di ruoli e criteri -----------------------------------------
#
# Stanno qui, e non in regole.py, perché è questo modulo a consumarli: `regole.py` li
# importa per validare lo statuto al confine. Due elenchi che possono divergere sono
# un elenco solo scritto male.
#
# Sono vocabolari CHIUSI apposta. Un ruolo o un criterio non riconosciuto non solleva
# niente da sé — il socio semplicemente non entra in nessun blocco, il criterio ignoto
# cade nel ramo di default — e il denaro finisce a qualcun altro senza che l'invariante
# di somma se ne accorga.

RUOLI = ("produttore", "consumatore", "prosumer")
"""Ruoli ammessi in anagrafica. Il prosumer sta in ENTRAMBI i blocchi e prende due quote."""

CRITERI_PRODUTTORI = ("energia_immessa", "quote_uguali")
"""Criteri di riparto dentro il blocco produttori."""

CRITERI_CONSUMATORI = ("prelievo_coincidente", "quote_uguali")
"""Criteri di riparto dentro il blocco consumatori."""


def _criterio(regole: dict, chiave: str, default: str, ammessi: Sequence[str]) -> str:
    """Legge un criterio dalle regole statutarie e lo valida contro il vocabolario.

    Senza questo controllo un criterio inesistente non veniva rifiutato: cadeva nel
    ramo "non è quote_uguali" e ripartiva pro-quota energia, cioè dava una risposta
    plausibile a una domanda che nessuno aveva posto.
    """
    valore = regole.get(chiave, default)
    if valore not in ammessi:
        raise ValueError(
            f"{chiave}: {valore!r} non è un criterio supportato; il motore conosce "
            f"{elenco(ammessi)}. Un criterio non riconosciuto non verrebbe segnalato "
            "dal calcolo: ripartirebbe con quello di default, e il rendiconto "
            "sembrerebbe corretto."
        )
    return valore


@nel_contesto_del_motore
def in_centesimi(euro: Decimal) -> int:
    return int((euro * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


@nel_contesto_del_motore
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
    sono invece un errore, perché non esiste un criterio per ripartirlo. Questa
    primitiva non ripiega su nulla, e non potrebbe: non sa se i pesi siano energie di
    membri o quote orarie di impianti. Chi lo sa è `_ripartisci_blocco`, che davanti a
    un blocco di membri tutti a peso nullo sceglie le quote uguali.
    """
    return riparto_per_pesi(totale_cent, pesi)


def riparto_per_pesi(totale_cent: int, pesi: dict[str, Decimal]) -> dict[str, int]:
    """Nucleo del resto maggiore, SENZA gestione del contesto decimale.

    Identica a `ripartisci_centesimi`, ma per i chiamanti che sono gia' dentro il
    contesto del motore: `ripartisci` la invoca tre volte per riparto e
    `condivisione.alloca_oraria` una volta per ora, e reinstallare un contesto identico
    a quello corrente e' lavoro sprecato (misurato: +24% sulla sola gestione).
    Chi arriva da fuori usa `ripartisci_centesimi`, che il contesto lo installa.
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
    if sum(quote.values()) != totale_cent:
        # Invariante sul denaro: un `assert` sparirebbe con `python -O`, che e' una
        # configurazione di esercizio del tutto ordinaria, e restituirebbe in silenzio
        # un riparto che non chiude.
        raise AssertionError(
            f"riparto incoerente: le quote sommano a {sum(quote.values())} centesimi "
            f"invece di {totale_cent}"
        )
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


@nel_contesto_del_motore
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


@nel_contesto_del_motore
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


# --- validazione delle regole statutarie e dei pesi dei blocchi -------------------


def _descrivi(valore: object) -> str:
    """Tipo del valore in italiano: i messaggi li legge un socio, non un compilatore."""
    nomi = {
        str: "un testo",
        float: "un numero decimale binario (float)",
        bool: "un valore vero/falso",
        list: "un elenco",
        dict: "una tabella",
    }
    for tipo, nome in nomi.items():
        if isinstance(valore, tipo):
            return nome
    if valore is None:
        return "un valore assente"
    return f"un valore di tipo {type(valore).__name__}"


def _percentuale(valore: object, chiave: str) -> Decimal:
    """Percentuale statutaria: `Decimal` (o intero) e FINITA. Mai float, mai testo.

    `regole.valida` fa già questi controlli sul file TOML, ma `ripartisci` è pubblica e
    viene chiamata anche con dizionari costruiti a mano — dai test, e domani da un
    adapter o da un'interfaccia. Misurato l'8 ago 2026 senza questa funzione:

        fondi={"gestione": Decimal("NaN")}  -> decimal.InvalidOperation
        quota_produttori=Decimal("NaN")     -> decimal.InvalidOperation
        quota_produttori="0.5"              -> TypeError
        fondi={"gestione": 0.1}             -> TypeError

    Nessuno dei quattro è `ValueError`, che è il tipo su cui il resto del motore ha
    insegnato ai chiamanti a contare (`InvalidOperation` è `ArithmeticError`), e
    `Decimal("NaN") < 0` non fa scattare nessuna delle guardie scritte come confronto:
    NaN non è né minore né maggiore di niente. Il docstring di `ripartisci` prometteva
    una validazione "prima di qualunque conto" che su questi quattro casi non c'era.
    """
    if isinstance(valore, bool) or not isinstance(valore, (int, Decimal)):
        raise ValueError(
            f"{chiave}: {valore!r} non è una percentuale utilizzabile sul denaro, è "
            f"{_descrivi(valore)}. Le percentuali statutarie sono Decimal (o interi "
            'esatti): un float non rappresenta 0,10 — arriverebbe come '
            "0,1000000000000000055511151231257827… — e un testo non è un numero. Nel "
            'codice si scrivono Decimal("0.10"), nel file delle regole fra virgolette, '
            '`gestione = "0.10"` (docs/REGOLE.md).'
        )
    numero = Decimal(valore)
    if not numero.is_finite():
        raise ValueError(
            f"{chiave}: {numero} non è un numero finito. Attesa una frazione di 1, per "
            'esempio Decimal("0.10") per il 10%. NaN e Infinity vanno fermati qui, ma '
            "per ragioni opposte: Infinity supera i confronti delle guardie senza "
            "farli scattare (Infinity < 0 è False), mentre NaN li fa esplodere con "
            "InvalidOperation, che è ArithmeticError e non ValueError. Uno passa, "
            "l'altro esce dalla porta sbagliata, e nessuno dei due dice quale regola "
            "statutaria correggere."
        )
    return numero


def _energia(valore: object, membro: str, blocco: str, criterio: str) -> Decimal:
    """Peso di un membro dentro un blocco: `Decimal` (o intero), FINITO e non negativo.

    Gemella di `_percentuale`, e per la stessa ragione: `ripartisci` è pubblica e i pesi
    arrivano da un adapter tanto quanto le percentuali. Il controllo sul TIPO non è
    pedanteria — senza, un peso `float` supera ogni guardia e muore molto più in là.
    Misurato il 9 ago 2026 quando la guardia sulla finitezza era condizionata a
    `isinstance(peso, Decimal)`:

        energia_immessa_kwh={"P1": float("nan")}  -> TypeError da riparto_per_pesi
        energia_immessa_kwh={"P1": float("inf")}  -> TypeError da riparto_per_pesi
        energia_immessa_kwh={"P1": 0.5}           -> TypeError da riparto_per_pesi

    Tutti e tre `TypeError`, cioè non `ValueError`, e sollevati dalle viscere del
    riparto senza nominare né il membro né il blocco. Un `float` fra i pesi va fermato
    comunque, e non solo per il tipo dell'eccezione: mescolarlo ai `Decimal` è ciò che
    la regola 2 del CLAUDE.md vieta sul denaro.
    """
    if isinstance(valore, bool) or not isinstance(valore, (int, Decimal)):
        raise ValueError(
            f"blocco {blocco}: il peso di {membro!r} è {_descrivi(valore)}, non un "
            f"Decimal. Con il criterio {criterio!r} il peso è un'energia in kWh, e le "
            "energie viaggiano in Decimal come il denaro: un float non rappresenta "
            "esattamente i decimali di un contatore, e mescolato ai Decimal fa fallire "
            "il riparto con un errore che non nomina né il membro né il blocco."
        )
    numero = Decimal(valore)
    if not numero.is_finite():
        raise ValueError(
            f"blocco {blocco}: il peso di {membro!r} non è un numero finito ({numero}). "
            f"Con il criterio {criterio!r} il peso è un'energia in kWh: Infinity "
            "attraverserebbe la guardia sul segno senza farla scattare, e azzererebbe "
            "la quota di tutti gli altri membri del blocco; NaN la farebbe esplodere "
            "con InvalidOperation invece che con ValueError."
        )
    if numero < 0:
        raise ValueError(
            f"blocco {blocco}: {membro!r} ha un peso negativo ({numero} kWh) con il "
            f"criterio {criterio!r}. Riceverebbe una quota negativa, cioè pagherebbe "
            "per gli altri membri, e l'invariante somma == totale reggerebbe lo stesso "
            "perché è una somma. Le energie misurate non sono mai negative: "
            "probabilmente il segno arriva da un adapter."
        )
    return numero


def _ripartisci_blocco(
    blocco: str,
    totale_cent: int,
    ids: list[str],
    criterio: str,
    energie: dict[str, Decimal],
    rimedio: str,
) -> dict[str, int]:
    """Ripartisce la dotazione di un blocco fra i suoi membri. Decide i due casi limite.

    Le due situazioni in cui il criterio statutario non produce un riparto sono
    DIVERSE, e fino all'8 ago 2026 finivano nello stesso `ValueError("pesi tutti
    nulli")` sollevato dalle viscere di `ripartisci_centesimi`, che non nominava né il
    blocco né il criterio — mentre il ramo dell'importo eccedentario, davanti allo
    stesso problema, ripiegava in silenzio sulle quote uguali. Quell'asimmetria non era
    una decisione, era un caso: ora i tre blocchi passano tutti di qui.

    BLOCCO SENZA MEMBRI E CON DENARO DA DISTRIBUIRE: errore. Non è il criterio a
    mancare, sono i destinatari: nessun ripiego può inventare a chi pagare, e tacere
    significherebbe far sparire quel denaro dal rendiconto. Il messaggio dice quanto,
    quale blocco e come si corregge lo statuto.

    MEMBRI PRESENTI MA PESI TUTTI NULLI: quote uguali. Qui i destinatari ci sono, è il
    criterio a non saperli distinguere — un mese in cui nessun produttore ha immesso, o
    in cui l'energia condivisa è nulla e quindi lo sono tutti i contributi di prelievo
    coincidente. Dividere in parti uguali è la scelta meno arbitraria fra quelle
    possibili, ed è già il comportamento del ramo eccedentario. NON è una regola GSE:
    la ripartizione interna è materia statutaria (docs/FORMULE.md §5), e uno statuto che
    voglia un'altra risposta può dichiarare `quote_uguali` come criterio o azzerare la
    quota del blocco.

    Un blocco senza membri e senza denaro non è un problema: non ripartisce nulla.
    """
    if not ids:
        if totale_cent == 0:
            return {}
        raise ValueError(
            f"blocco {blocco}: ci sono {totale_cent} centesimi da ripartire "
            f"({in_euro(totale_cent)}) ma non c'è nessun membro con quel ruolo, quindi "
            f"quel denaro non ha destinatario e nessun criterio può inventarne uno "
            f"(criterio dichiarato: {criterio!r}). {rimedio}"
        )
    if criterio == "quote_uguali":
        return riparto_per_pesi(totale_cent, {m: Decimal(1) for m in ids})

    pesi = {
        m: _energia(energie.get(m, Decimal(0)), m, blocco, criterio) for m in ids
    }

    if all(peso == 0 for peso in pesi.values()):
        pesi = {m: Decimal(1) for m in ids}
    return riparto_per_pesi(totale_cent, pesi)


@nel_contesto_del_motore
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
    se non ce ne sono, resta nel fondo `FONDO_ECCEDENTARIO`.

    Le regole statutarie e i membri sono validati prima di qualunque conto: percentuali
    dei fondi e quote dei blocchi finite, non negative, di somma ≤ 1 le prime ed
    esattamente 1 le seconde; importi non negativi; nessun nome riservato. Fino al 7 ago
    2026 si controllava solo `qp + qc == 1`, e quindi `quota_produttori=1,5` con
    `quota_consumatori=−0,5` passava e assegnava ai consumatori una quota NEGATIVA (con
    l'invariante finale, che è una somma, comunque soddisfatto: un membro pagava per gli
    altri).

    DUE NOMI SONO RISERVATI, e vengono rifiutati invece che accettati in silenzio. Il
    risultato è un dict piatto in cui i fondi occupano una chiave accanto ai membri, e i
    fondi sono a loro volta un dict di nomi liberi: due collisioni erano possibili, e
    l'8 ago 2026 sono state misurate entrambe. Nessuna delle due viola l'invariante
    finale — è una somma, e una somma non si accorge di dove sono finiti gli addendi —
    quindi nessuna guardia se ne accorgeva: il rendiconto mentiva e basta.

        un membro chiamato `_fondi`: la sua quota (1500 centesimi nella misura)
        finiva dentro il dizionario dei fondi, stampata nel rendiconto come una voce di
        fondo, e la riga del socio spariva dalla tabella;
        un fondo statutario chiamato `finalita_sociali`: 1000 centesimi statutari e 500
        di importo eccedentario senza consumatori idonei diventavano una riga sola da
        1500, e la nota di fondo pagina sull'eccedentario ne contava 1500 invece di 500.

    Il fondo riservato è rifiutato SEMPRE, anche nei periodi in cui l'importo
    eccedentario è nullo e la collisione non si produrrebbe: uno statuto è valido o no
    di suo, e scoprire il conflitto al primo mese in cui il vincolo scatta significa
    scoprirlo mentre si sposta denaro.
    """
    if importo_base_cent < 0 or importo_eccedentario_cent < 0:
        raise ValueError(
            f"gli importi da ripartire non possono essere negativi: importo base "
            f"{importo_base_cent} centesimi, importo eccedentario "
            f"{importo_eccedentario_cent}. Un incentivo negativo non esiste, e "
            "ripartirlo farebbe pagare i soci."
        )

    if VOCE_FONDI in membri:
        raise ValueError(
            f"c'è un membro con identificativo {VOCE_FONDI!r}, che è un nome riservato: "
            "nel risultato della ripartizione è la voce che raccoglie i fondi "
            "statutari. La quota di quel socio finirebbe fra i fondi e il rendiconto la "
            "stamperebbe come un fondo invece che come la sua riga, senza che nulla "
            "protesti, perché il totale torna lo stesso. Dài al membro un altro "
            "identificativo, per esempio il suo codice POD."
        )

    esito: dict[str, dict] = {m: {} for m in membri}
    esito[VOCE_FONDI] = {}

    # 1. fondi statutari sul totale base
    # Il nome riservato si controlla PRIMA di convertire i valori: con l'ordine inverso
    # un fondo `finalita_sociali = 0.1` riceveva l'errore sul float, e chi correggeva le
    # virgolette scopriva solo al secondo tentativo che il nome andava cambiato.
    if FONDO_ECCEDENTARIO in regole.get("fondi", {}):
        raise ValueError(
            f"c'è un fondo statutario chiamato {FONDO_ECCEDENTARIO!r}, che è un nome "
            "riservato: è la voce in cui finisce l'importo eccedentario quando nella "
            "CER non ci sono consumatori diversi dalle imprese (Regole Operative "
            "pag. 41). I due importi si sommerebbero in una riga sola del rendiconto e "
            "non si distinguerebbe più quanto viene dallo statuto e quanto dal vincolo "
            "normativo, che ha una destinazione obbligata. Chiama il fondo statutario "
            "in un altro modo, per esempio 'sociale' o 'finalita_sociali_statutario'."
        )
    fondi = {
        nome: _percentuale(perc, f"fondi.{nome}")
        for nome, perc in regole.get("fondi", {}).items()
    }
    for nome, perc in fondi.items():
        if perc < 0:
            raise ValueError(
                f"la percentuale del fondo {nome!r} è negativa ({perc}): un fondo "
                "negativo non restituisce denaro ai soci, lo crea dal nulla, e il "
                "riparto distribuirebbe più di quanto la CER ha incassato."
            )
    somma_fondi = sum(fondi.values(), Decimal(0))
    if somma_fondi > 1:
        raise ValueError(
            f"le percentuali dei fondi sommano a {somma_fondi}, cioè a più del totale "
            "da ripartire: uno statuto che destina ai fondi più del 100% "
            "dell'incentivo non descrive un riparto eseguibile. (Non sempre il residuo "
            "risulta negativo: su importi di pochi centesimi ogni fondo può arrotondare "
            "a zero e il residuo restare positivo — vedi "
            "test_ripartisci_fondi_oltre_uno_anche_quando_arrotondano_tutti_a_zero. "
            "È la somma delle percentuali a essere malformata, non il suo effetto.)"
        )
    residuo = importo_base_cent
    for nome, perc in fondi.items():
        q = int((Decimal(importo_base_cent) * perc).quantize(Decimal(1), ROUND_HALF_UP))
        esito[VOCE_FONDI][nome] = q
        residuo -= q
    if residuo < 0:
        # Le percentuali passano la guardia ma i singoli arrotondamenti al centesimo
        # sfondano il totale: succede solo con percentuali che sommano quasi a 1 e
        # importi di pochi centesimi (0.01 € diviso in due fondi da 0,5 dà 1 + 1 = 2).
        raise ValueError(
            f"i fondi arrotondati superano l'importo base di {-residuo} centesimi: "
            f"su {importo_base_cent} centesimi da ripartire i fondi ne trattengono "
            f"{importo_base_cent - residuo} e ai membri resterebbe un residuo negativo. "
            "Le percentuali sommano a 1 o quasi, e su importi di pochi centesimi ogni "
            "arrotondamento vale più della differenza."
        )

    # 2. residuo diviso tra blocco produttori e blocco consumatori
    qp = _percentuale(regole.get("quota_produttori", Decimal("0.5")), "quota_produttori")
    qc = _percentuale(regole.get("quota_consumatori", Decimal("0.5")), "quota_consumatori")
    if qp < 0 or qc < 0:
        raise ValueError(
            f"quota_produttori ({qp}) e quota_consumatori ({qc}) non possono essere "
            "negative: sommerebbero comunque a 1 ma darebbero quote negative ai membri"
        )
    if qp + qc != 1:
        raise ValueError(
            f"le quote dei blocchi non chiudono: quota_produttori ({qp}) + "
            f"quota_consumatori ({qc}) fanno {qp + qc}, devono fare esattamente 1. "
            "Tutto il residuo dopo i fondi va ripartito: per trattenerne una parte si "
            "aggiunge un fondo in [fondi], non si abbassano le quote."
        )
    blocco = riparto_per_pesi(residuo, {"prod": qp, "cons": qc})

    # I ruoli si validano PRIMA di selezionare i blocchi. Un ruolo scritto male non
    # solleva niente da sé: il socio semplicemente non entra in nessuna delle due liste,
    # resta con un esito vuoto, e la sua quota viene ripartita fra gli altri. Misurato:
    # con "consumatori" al posto di "consumatore", C2 riceve {} e i suoi 4500 centesimi
    # finiscono a C1. L'invariante di somma regge — il denaro non sparisce, cambia solo
    # tasca — quindi nessuna guardia a valle se ne accorge. È un errore silenzioso che
    # sposta denaro fra i soci, la cosa peggiore che questo modulo possa fare.
    for m, d in membri.items():
        if "ruolo" not in d:
            raise ValueError(
                f"membro {m!r}: manca la chiave 'ruolo'. Attesa una fra "
                f"{elenco(RUOLI)}, insieme a 'impresa' (vero o falso)."
            )
        if d["ruolo"] not in RUOLI:
            raise ValueError(
                f"membro {m!r}: ruolo {d['ruolo']!r} sconosciuto; attesa una fra "
                f"{elenco(RUOLI)}. Un ruolo non riconosciuto non fa entrare il socio "
                "in nessun blocco: resterebbe senza quota, e la sua parte andrebbe "
                "agli altri senza che nulla lo segnali."
            )

    produttori = [m for m, d in membri.items() if d["ruolo"] in ("produttore", "prosumer")]
    consumatori = [m for m, d in membri.items() if d["ruolo"] in ("consumatore", "prosumer")]
    criterio_prod = _criterio(regole, "criterio_produttori", "energia_immessa", CRITERI_PRODUTTORI)
    criterio_cons = _criterio(regole, "criterio_consumatori", "prelievo_coincidente", CRITERI_CONSUMATORI)

    for m, cent in _ripartisci_blocco(
        "produttori", blocco["prod"], produttori, criterio_prod, energia_immessa_kwh,
        rimedio="Se la CER non ha membri che immettono energia, lo statuto deve dirlo: "
                'quote.produttori = "0" e quote.consumatori = "1" (docs/REGOLE.md). '
                "Altrimenti manca dall'anagrafica chi ha ruolo 'produttore' o 'prosumer'.",
    ).items():
        esito[m]["quota_produttore"] = cent
    for m, cent in _ripartisci_blocco(
        "consumatori", blocco["cons"], consumatori, criterio_cons, contributi_consumo_kwh,
        rimedio="Se la CER non ha membri che consumano, lo statuto deve dirlo: "
                'quote.consumatori = "0" e quote.produttori = "1" (docs/REGOLE.md). '
                "Altrimenti manca dall'anagrafica chi ha ruolo 'consumatore' o 'prosumer'.",
    ).items():
        esito[m]["quota_consumatore"] = cent

    # 3. eccedentario: solo consumatori non-imprese, altrimenti fondo finalità sociali
    if importo_eccedentario_cent:
        idonei = [m for m in consumatori if not membri[m].get("impresa")]
        if idonei:
            # Stesso percorso degli altri due blocchi, ripiego a quote uguali compreso:
            # era la sola strada che ci ripiegava, ed è da lì che la decisione è stata
            # presa per tutti (vedi `_ripartisci_blocco`).
            for m, cent in _ripartisci_blocco(
                "eccedentario", importo_eccedentario_cent, idonei, criterio_cons,
                contributi_consumo_kwh,
                # Il ramo "nessun destinatario" di `_ripartisci_blocco` qui non può
                # scattare: `if idonei` sopra garantisce la lista non vuota, e il caso
                # senza idonei è presidiato dal ramo `else`, che deposita nel fondo.
                rimedio="",
            ).items():
                esito[m]["quota_eccedentaria"] = cent
        else:
            # Nessun consumatore diverso dalle imprese: il nome del fondo è riservato,
            # quindi questa voce non può fondersi con un fondo statutario omonimo e nel
            # rendiconto la provenienza dell'importo resta leggibile.
            esito[VOCE_FONDI][FONDO_ECCEDENTARIO] = importo_eccedentario_cent

    totale = importo_base_cent + importo_eccedentario_cent
    ripartito = sum(v for d in esito.values() for v in d.values())
    if ripartito != totale:
        raise AssertionError(
            f"riparto incoerente: distribuiti {ripartito} centesimi invece di {totale}"
        )
    return esito
