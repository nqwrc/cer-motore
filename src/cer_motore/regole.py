"""Regole statutarie di ripartizione, dichiarate in un file TOML.

La ripartizione interna è materia STATUTARIA, non normativa: le Regole Operative GSE
(agg. DD 16/7/2025) impongono che esista un soggetto delegato responsabile del riparto
e vincolano la destinazione dell'importo eccedentario (pag. 41-42), ma su come i soci
si dividono il denaro decide lo statuto. Vedi docs/FORMULE.md §5.

Questo modulo esiste perché quello statuto — un documento umano, negoziato fra soci —
possa stare in un file che un socio non programmatore legge, rilegge e contesta, invece
che in un dict Python dentro `__main__.py`. Lo schema è documentato in docs/REGOLE.md,
con un esempio commentato in regole-esempio.toml.

I PARAMETRI NORMATIVI NON STANNO QUI. Soglie dell'eccedentario, tariffe premio,
correttivi zonali sono legge, non statuto: vivono in tariffe.py come costanti nominate
con fonte e data (CLAUDE.md, regola 4). Un file di regole non può ridefinirli, ed è una
delle ragioni per cui ogni chiave fuori schema è un errore invece che un valore ignorato.

DIVISIONE DEL LAVORO (CLAUDE.md, regola 1)
    `valida`   PURA: prende una struttura già caricata, non tocca il disco, non ha
               stato, ritorna il dict che `ripartizione.ripartisci` si aspetta.
    `da_testo` PURA: analizza una stringa TOML (`tomllib.loads` non fa I/O) e valida.
    `leggi`    ADAPTER: l'unica funzione del modulo che apre un file.

DENARO E STRINGHE — la scelta che vincola tutto il resto
    Le percentuali statutarie si scrivono FRA VIRGOLETTE: `gestione = "0.10"`.
    Il TOML ha i float nativi, e un float è un binario: `0.10` non esiste in binario e
    arriva come 0,1000000000000000055511151231257827…, `0.35` come
    0,34999999999999997779… Convertire quel float in `Decimal` propagherebbe l'errore
    nel denaro; convertirlo passando da `str()` lo nasconderebbe (in CPython `str(0.1)`
    dà "0.1" per la regola del repr più corto), ma affiderebbe l'esattezza degli
    importi a un dettaglio di formattazione dell'interprete, non alla norma.
    Quindi: un decimale non quotato è un ERRORE con un messaggio che dice come
    riscriverlo. Conseguenze accettate, in ordine di fastidio:
      - il file è meno "naturale" da scrivere per chi conosce il TOML;
      - un socio che copia un numero da un foglio di calcolo prende un errore, non un
        risultato leggermente sbagliato — ed è esattamente l'ordine di preferenza
        giusto quando il numero decide chi incassa quanto;
      - gli interi restano ammessi senza virgolette (`produttori = 1`), perché in TOML
        sono esatti: non c'è nulla da nascondere.
    Si accetta anche la virgola come separatore decimale ("0,10"): è come un socio
    italiano scrive una percentuale, e la conversione a Decimal resta esatta perché
    avviene su testo.

ERRORI
    Tutti gli errori sono `ErroreRegole`, sottoclasse di `ValueError`. Ognuno dice
    QUALE chiave, CHE valore ha trovato e COSA si aspettava; dove serve, come si
    riscrive la riga. La validazione si ferma al primo problema: chi legge il messaggio
    è un socio, non un compilatore, e una lista di dieci errori a cascata generati da un
    refuso di battitura sarebbe meno utile di uno solo, giusto.
"""
import difflib
import tomllib
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from os import PathLike
from pathlib import Path

__all__ = [
    "ErroreRegole",
    "valida",
    "da_testo",
    "leggi",
    "CRITERI_PRODUTTORI",
    "CRITERI_CONSUMATORI",
    "SEZIONI",
]

# Criteri di riparto supportati. NON sono parametri normativi (quelli stanno in
# tariffe.py): sono il vocabolario del motore, cioè le funzioni-peso che
# `ripartizione.ripartisci` sa applicare. Aggiungerne uno qui senza implementarlo là
# significherebbe accettare un file che poi ripartisce in un altro modo, in silenzio.
CRITERI_PRODUTTORI = ("energia_immessa", "quote_uguali")
CRITERI_CONSUMATORI = ("prelievo_coincidente", "quote_uguali")

SEZIONI = ("quote", "criteri", "fondi")
SEZIONI_OBBLIGATORIE = ("quote", "criteri")
RUOLI = ("produttori", "consumatori")

ESEMPIO = """\
[quote]
produttori = "0.50"
consumatori = "0.50"

[criteri]
produttori = "energia_immessa"
consumatori = "prelievo_coincidente"

[fondi]
gestione = "0.10"
"""

_ESEMPIO_IN_ERRORE = "Struttura attesa del file:\n\n" + ESEMPIO


class ErroreRegole(ValueError):
    """Regole statutarie non valide: il file non descrive un riparto eseguibile.

    Sottoclasse di `ValueError` perché è quello che il resto del motore solleva per gli
    input incoerenti (`ripartizione.ripartisci`), così un chiamante che già cattura
    `ValueError` non deve cambiare nulla; ma è un tipo proprio, perché "il tuo file di
    statuto ha un problema alla riga X" e "questo calcolo è impossibile" meritano di
    essere distinti da chi scrive una interfaccia sopra il motore.
    """


# --- funzioni pure: validazione e conversione -------------------------------------


def valida(dati: Mapping[str, object]) -> dict:
    """Valida una struttura già caricata e la converte in regole per `ripartisci`.

    PURA: nessun I/O, nessuno stato, nessun default nascosto. `dati` è tipicamente il
    dict che `tomllib` restituisce, ma va bene qualunque mapping con la stessa forma
    (per esempio uno costruito a mano da un test o da una futura interfaccia web).

    Ritorna esattamente il dict che `ripartizione.ripartisci` si aspetta:

        {"fondi": {nome: Decimal},          # frazioni del totale base, somma ≤ 1
         "quota_produttori": Decimal,       # frazione del residuo dopo i fondi
         "quota_consumatori": Decimal,      # le due quote sommano esattamente a 1
         "criterio_produttori": str,        # uno di CRITERI_PRODUTTORI
         "criterio_consumatori": str}       # uno di CRITERI_CONSUMATORI

    `fondi` è sempre presente, eventualmente vuoto: la sezione [fondi] è facoltativa
    (nessun fondo trattenuto), ma la chiave in uscita no, così il chiamante non deve
    distinguere "nessun fondo" da "regole scritte a metà".

    Solleva `ErroreRegole` per: sezioni o chiavi sconosciute (un refuso in
    `produttori` non deve passare in silenzio e mandare tutto ai consumatori), sezioni
    obbligatorie o campi mancanti, decimali non quotati, valori non numerici, quote
    fuori dall'intervallo 0-1, quote che non sommano a 1, fondi negativi o che
    assorbono più del totale, criteri non supportati.
    """
    if not isinstance(dati, Mapping):
        raise ErroreRegole(
            f"le regole devono essere una tabella di sezioni, non {_tipo(dati)}.\n"
            + _ESEMPIO_IN_ERRORE
        )

    _chiavi_ammesse(dati, SEZIONI, dove=None, cosa="sezione", con_esempio=True)
    for sezione in SEZIONI_OBBLIGATORIE:
        if sezione not in dati:
            raise ErroreRegole(
                f"manca la sezione [{sezione}], che è obbligatoria: senza, il motore "
                "dovrebbe indovinare come si divide il denaro fra i soci.\n"
                + _ESEMPIO_IN_ERRORE
            )

    quote = _sezione(dati, "quote")
    criteri = _sezione(dati, "criteri")
    fondi = _sezione(dati, "fondi") if "fondi" in dati else {}

    return {
        "fondi": _valida_fondi(fondi),
        **_valida_quote(quote),
        **_valida_criteri(criteri),
    }


def da_testo(testo: str) -> dict:
    """Analizza una stringa TOML e la valida. PURA: `tomllib.loads` non fa I/O.

    È la via per validare regole che non arrivano da un file — un campo di testo, una
    stringa di test — e il cuore di `leggi`, che si limita ad aggiungerci l'apertura
    del file e il nome del file nei messaggi d'errore.
    """
    try:
        dati = tomllib.loads(testo)
    except tomllib.TOMLDecodeError as errore:
        raise ErroreRegole(
            f"il testo non è TOML valido: {errore}.\n" + _ESEMPIO_IN_ERRORE
        ) from errore
    return valida(dati)


# --- adapter: la sola funzione che tocca il disco ---------------------------------


def leggi(percorso: str | PathLike[str]) -> dict:
    """Legge le regole statutarie da un file TOML. Ritorna quello che ritorna `valida`.

    ADAPTER (CLAUDE.md, regola 1): è l'unica funzione del modulo che fa I/O, e non fa
    altro che questo. Ogni messaggio d'errore viene prefissato col nome del file,
    perché chi corregge lo statuto spesso ha più file aperti (uno per esercizio, uno
    per la delibera in discussione) e "quote.produttori: …" senza il file non basta.
    """
    p = Path(percorso)
    try:
        with p.open("rb") as f:  # tomllib vuole binario: decide lui l'encoding (UTF-8)
            dati = tomllib.load(f)
    except FileNotFoundError:
        raise ErroreRegole(f"file delle regole non trovato: {p}") from None
    except tomllib.TOMLDecodeError as errore:
        raise ErroreRegole(
            f"{p}: il file non è TOML valido: {errore}.\n" + _ESEMPIO_IN_ERRORE
        ) from errore
    try:
        return valida(dati)
    except ErroreRegole as errore:
        raise ErroreRegole(f"{p}: {errore}") from None


# --- validazione delle singole sezioni --------------------------------------------


def _valida_quote(quote: Mapping[str, object]) -> dict:
    """Quote dei due blocchi: non negative, non oltre 1, di somma esattamente 1."""
    _chiavi_ammesse(quote, RUOLI, dove="sezione [quote]", cosa="chiave")
    for ruolo in RUOLI:
        if ruolo not in quote:
            raise ErroreRegole(
                f"sezione [quote]: manca {ruolo}. Vanno indicate entrambe le quote, "
                'anche quando una è zero (per esempio produttori = "1" e '
                'consumatori = "0"): il residuo dopo i fondi si ripartisce tutto.'
            )
    valori = {r: _decimale(quote[r], f"quote.{r}") for r in RUOLI}

    for ruolo, q in valori.items():
        if q < 0:
            raise ErroreRegole(
                f"quote.{ruolo}: {_it(q)} è negativa. Una quota negativa non toglie "
                "denaro a quel blocco: lo fa PAGARE, perché la quota dell'altro blocco "
                "supera il residuo. Le quote stanno fra 0 e 1."
            )
        if q > 1:
            raise ErroreRegole(
                f"quote.{ruolo}: {_it(q)} è maggiore di 1, cioè più del residuo "
                "disponibile. Le quote sono frazioni di 1: il 60% si scrive \"0.60\"."
            )

    somma = valori["produttori"] + valori["consumatori"]
    if somma != 1:
        raise ErroreRegole(
            f"le quote non chiudono: produttori ({_it(valori['produttori'])}) + "
            f"consumatori ({_it(valori['consumatori'])}) fanno {_it(somma)}, "
            "devono fare esattamente 1. Tutto il residuo dopo i fondi va ripartito: "
            "per trattenerne una parte si aggiunge un fondo in [fondi], non si "
            "abbassano le quote."
        )
    return {
        "quota_produttori": valori["produttori"],
        "quota_consumatori": valori["consumatori"],
    }


def _valida_criteri(criteri: Mapping[str, object]) -> dict:
    """Criteri di riparto dentro ciascun blocco: solo quelli che il motore implementa."""
    _chiavi_ammesse(criteri, RUOLI, dove="sezione [criteri]", cosa="chiave")
    ammessi = {"produttori": CRITERI_PRODUTTORI, "consumatori": CRITERI_CONSUMATORI}
    scelti = {}
    for ruolo in RUOLI:
        if ruolo not in criteri:
            raise ErroreRegole(
                f"sezione [criteri]: manca {ruolo}. Va detto esplicitamente con quale "
                f"criterio si ripartisce dentro il blocco; quelli supportati sono: "
                f"{_elenco(ammessi[ruolo])}."
            )
        valore = criteri[ruolo]
        if not isinstance(valore, str):
            raise ErroreRegole(
                f"criteri.{ruolo}: {valore!r} non è un nome di criterio ma "
                f"{_tipo(valore)}. Si scrive fra virgolette, per esempio "
                f'{ruolo} = "{ammessi[ruolo][0]}".'
            )
        if valore not in ammessi[ruolo]:
            raise ErroreRegole(
                f"criteri.{ruolo}: {valore!r} non è un criterio supportato"
                f"{_suggerimento(valore, ammessi[ruolo])}. Per i {ruolo} il motore "
                f"conosce: {_elenco(ammessi[ruolo])}."
            )
        scelti[ruolo] = valore
    return {
        "criterio_produttori": scelti["produttori"],
        "criterio_consumatori": scelti["consumatori"],
    }


def _valida_fondi(fondi: Mapping[str, object]) -> dict[str, Decimal]:
    """Fondi statutari: percentuali del totale base, non negative e di somma ≤ 1."""
    valori: dict[str, Decimal] = {}
    for nome, valore in fondi.items():
        # In TOML le chiavi sono sempre testo; la guardia serve perché `valida` accetta
        # qualunque mapping, anche costruito a mano da una futura interfaccia.
        if not isinstance(nome, str):
            raise ErroreRegole(
                f"sezione [fondi]: {nome!r} non è un nome di fondo valido. I nomi sono "
                'testo, per esempio gestione = "0.10".'
            )
        if not nome.strip():
            raise ErroreRegole(
                "sezione [fondi]: c'è un fondo senza nome. Ogni fondo si chiama in "
                'qualche modo nel rendiconto, per esempio gestione = "0.10".'
            )
        percentuale = _decimale(valore, f"fondi.{nome}")
        if percentuale < 0:
            raise ErroreRegole(
                f"fondi.{nome}: {_it(percentuale)} è negativa. Un fondo negativo non "
                "restituisce denaro ai soci, lo crea dal nulla: il riparto "
                "distribuirebbe più di quanto la CER ha incassato."
            )
        if percentuale > 1:
            raise ErroreRegole(
                f"fondi.{nome}: {_it(percentuale)} è maggiore di 1, cioè più "
                "dell'intero incentivo. Le percentuali sono frazioni di 1: il 10% si "
                'scrive "0.10", non "10".'
            )
        valori[nome] = percentuale

    somma = sum(valori.values(), Decimal(0))
    if somma > 1:
        dettaglio = ", ".join(f"{n} {_it(v)}" for n, v in valori.items())
        raise ErroreRegole(
            f"i fondi sommano a {_it(somma)} ({dettaglio}): non possono superare 1. "
            "Assorbirebbero più dell'incentivo, e ai soci resterebbe un residuo "
            "negativo da ripartire."
        )
    return valori


# --- conversioni e messaggi -------------------------------------------------------


def _decimale(valore: object, chiave: str) -> Decimal:
    """Converte in `Decimal` un valore che diventerà denaro. Mai passando da float.

    Ammette stringhe (anche con la virgola come separatore decimale) e interi. Rifiuta
    i decimali non quotati del TOML: vedi la nota "DENARO E STRINGHE" in cima al modulo
    per il perché e per le conseguenze della scelta.
    """
    # `bool` è sottoclasse di `int` in Python: senza questo ramo, `true` diventerebbe 1
    # e uno statuto con `produttori = true` ripartirebbe tutto ai produttori.
    if isinstance(valore, bool):
        raise ErroreRegole(
            f"{chiave}: {str(valore).lower()} è un valore vero/falso, non una "
            'percentuale. Si scrive fra virgolette, per esempio "0.10" per il 10%.'
        )
    if isinstance(valore, int):
        return Decimal(valore)  # in TOML gli interi sono esatti: nulla da nascondere
    if isinstance(valore, float):
        esatto = _it(Decimal(valore))
        if len(esatto) > 26:
            esatto = esatto[:26] + "..."
        raise ErroreRegole(
            f"{chiave}: {valore!r} è scritto come numero decimale, e i decimali del "
            f"TOML sono float binari: arriverebbe al motore come {esatto}, non come "
            f"{valore!r}. Sul denaro non è accettabile. Basta metterlo fra virgolette, "
            f'per esempio: {chiave.rsplit(".", 1)[-1]} = "{valore!r}".'
        )
    if not isinstance(valore, str):
        raise ErroreRegole(
            f"{chiave}: {valore!r} è {_tipo(valore)}, non una percentuale. Si scrive "
            'fra virgolette, per esempio "0.10" per il 10%.'
        )

    testo = valore.strip()
    # Un socio italiano scrive "0,10". La sostituzione è sicura solo se la virgola è
    # una sola e non c'è già un punto: "1,234.5" o "0,1,5" restano errori espliciti.
    if testo.count(",") == 1 and "." not in testo:
        testo = testo.replace(",", ".")
    try:
        numero = Decimal(testo)
    except InvalidOperation:
        raise ErroreRegole(
            f"{chiave}: {valore!r} non è un numero. Attesa una frazione di 1 fra "
            'virgolette: "0.10" per il 10%, "0.5" per la metà. Si accetta anche la '
            'virgola come separatore decimale, "0,10".'
        ) from None
    if not numero.is_finite():  # Decimal accetta "nan" e "Infinity": qui non hanno senso
        raise ErroreRegole(
            f"{chiave}: {valore!r} non è un numero finito. Attesa una frazione di 1, "
            'per esempio "0.10".'
        )
    return numero


def _sezione(dati: Mapping[str, object], nome: str) -> Mapping[str, object]:
    """Estrae una sezione, verificando che sia davvero una tabella TOML."""
    valore = dati[nome]
    if not isinstance(valore, Mapping):
        raise ErroreRegole(
            f"[{nome}] deve essere una sezione, ma è {_tipo(valore)} ({valore!r}). "
            f"Una sezione si apre con [{nome}] su una riga sua e continua con le "
            "chiavi sotto.\n" + _ESEMPIO_IN_ERRORE
        )
    return valore


def _chiavi_ammesse(
    tabella: Mapping[str, object],
    ammesse: tuple[str, ...],
    dove: str | None,
    cosa: str,
    con_esempio: bool = False,
) -> None:
    """Rifiuta le chiavi fuori schema, con suggerimento sulla più simile.

    È la guardia che rende il file affidabile: senza, un refuso in `produttori`
    lascerebbe la chiave a un default e ripartirebbe il denaro in un altro modo senza
    dire nulla — il tipo di errore che si scopre dal rendiconto sbagliato di un socio.
    """
    for chiave in tabella:
        if chiave in ammesse:
            continue
        # `dove` è None al primo livello del file: lì il prefisso sarebbe rumore,
        # perché `leggi` antepone già il nome del file.
        messaggio = (
            f"{dove + ': ' if dove else ''}{cosa} sconosciuta {chiave!r}"
            f"{_suggerimento(chiave, ammesse)}. Ammesse: {_elenco(ammesse)}."
        )
        if con_esempio:
            messaggio += "\n" + _ESEMPIO_IN_ERRORE
        raise ErroreRegole(messaggio)


def _suggerimento(chiave: object, ammesse: tuple[str, ...]) -> str:
    """"; forse intendevi 'x'" quando c'è un candidato simile, altrimenti stringa vuota."""
    if not isinstance(chiave, str):  # `valida` accetta mapping non prodotti da tomllib
        return ""
    vicine = difflib.get_close_matches(chiave, ammesse, n=1, cutoff=0.6)
    return f"; forse intendevi {vicine[0]!r}" if vicine else ""


def _elenco(voci: tuple[str, ...]) -> str:
    return ", ".join(voci)


def _it(valore: Decimal) -> str:
    """Numero in notazione italiana: la virgola separa i decimali."""
    return str(valore).replace(".", ",")


def _tipo(valore: object) -> str:
    """Nome del tipo in italiano, per i messaggi d'errore rivolti a chi non programma."""
    nomi = {
        str: "un testo",
        int: "un numero intero",
        float: "un numero decimale",
        bool: "un valore vero/falso",
        list: "un elenco",
        dict: "una sezione",
    }
    return nomi.get(type(valore), f"di tipo {type(valore).__name__}")
