"""Tariffa incentivante premio (TIP) e valorizzazione ARERA.

Fonti: DM CACER 414/2023, Allegato 1; Regole Operative GSE (agg. DD 16/7/2025,
approvate con DM MASE 228/2025). Vedi docs/FORMULE.md §2-3.
I parametri normativi sono costanti nominate: cambiano con gli aggiornamenti normativi,
non vanno mai inlined nel codice chiamante.

I numeri di pagina citati qui sotto sono quelli STAMPATI a piè di pagina sul PDF
ufficiale delle Regole Operative (171 pagine), non quelli dell'indice del lettore PDF,
che è sfasato di 1.
"""
from decimal import Decimal

# Il contesto decimale del motore sta in comune.py, che non importa nulla dal
# pacchetto: questo modulo e' il piu' in basso di tutti e non puo' dipendere da altri.
from .comune import nel_contesto_del_motore

# --- Parametri normativi (€/MWh salvo indicazione) --------------------------------

# Valore base della tariffa (TP_base nella norma) e valore soglia della tariffa (CAP),
# per scaglione di potenza. Fonte: Regole Operative pag. 41 e Appendice B §1 pag. 160;
# DM CACER 414/2023 All. 1 §1 — verificati verbatim sui due PDF ufficiali, 7 ago 2026.
SCAGLIONI = (  # (potenza_max_kw, tp_base, cap)
    (Decimal(200), Decimal(80), Decimal(120)),
    (Decimal(600), Decimal(70), Decimal(110)),
    (None, Decimal(60), Decimal(100)),
)

# Parte variabile della tariffa: max(0; 180 − Pz), con Pz prezzo zonale ORARIO.
# Fonte: Regole Operative pag. 40 e Appendice B §1 pag. 160 — verificata verbatim.
#
# NON esiste un tetto normativo sulla parte variabile. Il tetto è il CAP e si applica
# alla somma TP_base + parte variabile. Che la parte variabile risulti *di fatto*
# compresa fra 0 e 40 €/MWh è una conseguenza aritmetica di CAP − TP_base = 40 in tutti
# e tre gli scaglioni, non un parametro a sé: le Regole Operative usano quell'intervallo
# solo per descrivere il parametro Z dell'acconto (pag. 39). Una precedente versione di
# questo modulo aveva una costante VAR_MAX = 40 che troncava la parte variabile prima
# del cap: dà gli stessi numeri oggi, ma sbaglierebbe in silenzio se un aggiornamento
# normativo muovesse TP_base e CAP in modo non parallelo.
VAR_RIF = Decimal(180)

# Correttivo geografico per impianti fotovoltaici (FC_zonale). Si somma FUORI dal cap.
# Fonte: Regole Operative pag. 41 e Appendice B §2 pag. 160 — verificato verbatim.
CORRETTIVO_FV = {"sud": Decimal(0), "centro": Decimal(4), "nord": Decimal(10)}

# Decurtazione per cumulo con contributo in conto capitale: TIP × (1 − F), con F che
# varia linearmente fra 0 (nessun contributo) e 0,50 (contributo pari al 40%
# dell'investimento). Fonte: Regole Operative pag. 41 e Appendice B §3 pag. 161.
FATTORE_CONTO_CAPITALE_MAX = Decimal("0.50")

# Valori soglia dell'energia condivisa incentivabile per il vincolo dell'importo
# eccedentario (art. 3 c. 2 lett. g del Decreto CACER). Fonte: Regole Operative
# §2.2.2.1.3 pag. 41 e Appendice B §4 pag. 161 — verificati verbatim.
# La verifica del superamento è fatta dal GSE A CONGUAGLIO, SU BASE ANNUALE, aggregando
# gli impianti incentivati in due insiemi distinti (uno per soglia).
SOGLIA_ECCEDENTARIO_SOLA_TARIFFA = Decimal("0.55")
SOGLIA_ECCEDENTARIO_CUMULO_CONTO_CAPITALE = Decimal("0.45")

# Corrispettivo di valorizzazione ARERA per le CER (TIAD): valore 2024 — verificato
# come ordine di grandezza; varia ogni anno, passarlo esplicitamente nei conti annuali.
VALORIZZAZIONE_ARERA_2024 = Decimal("8.22")

ANNI_INCENTIVO = 20
POTENZA_MAX_INCENTIVABILE_KW = Decimal(1000)

# ----------------------------------------------------------------------------------


def parte_fissa(potenza_kw: Decimal) -> Decimal:
    """Parte fissa della TIP per la potenza dell'impianto (€/MWh). Norma: TP_base."""
    for soglia, fissa, _cap in SCAGLIONI:
        if soglia is None or potenza_kw <= soglia:
            return fissa
    raise AssertionError("scaglioni mal definiti")


def cap_tariffa(potenza_kw: Decimal) -> Decimal:
    """Valore soglia della tariffa per la potenza dell'impianto (€/MWh). Norma: CAP."""
    for soglia, _fissa, cap in SCAGLIONI:
        if soglia is None or potenza_kw <= soglia:
            return cap
    raise AssertionError("scaglioni mal definiti")


def parte_variabile(prezzo_zonale: Decimal) -> Decimal:
    """Parte variabile della TIP dato il prezzo zonale orario Pz (€/MWh).

    max(0; 180 − Pz). Fonte: Regole Operative pag. 40, Appendice B §1 pag. 160.
    Non è troncata a 40 €/MWh: il limite normativo è il CAP sulla tariffa totale e lo
    applica `tip_unitaria`. Vedi la nota su VAR_RIF per il perché la distinzione conta.
    """
    return max(Decimal(0), VAR_RIF - prezzo_zonale)


@nel_contesto_del_motore
def tip_unitaria(
    potenza_kw: Decimal,
    prezzo_zonale: Decimal,
    zona: str = "sud",
    fotovoltaico: bool = True,
    fattore_conto_capitale: Decimal = Decimal(0),
) -> Decimal:
    """Tariffa premio oraria unitaria (€/MWh).

    Forma normativa, verbatim dalle Regole Operative pag. 40:

        TIP_h = {min[CAP; TP_base + max(0; 180 − Pz)] + FC_zonale} * (1 − F)

    Il correttivo geografico FC_zonale sta dentro la graffa ma FUORI dal min, quindi si
    somma dopo il cap: il massimo per un impianto ≤ 200 kW al nord è 120 + 10 = 130
    €/MWh (la pagina pubblica GSE "Corrispettivi e tariffa" espone gli stessi massimi).

    `fattore_conto_capitale` è F, la decurtazione per cumulo con contributo in conto
    capitale (0 ≤ F ≤ 0,50; Appendice B §3 pag. 161). Default 0, nessun cumulo.
    NOTA DI PERIMETRO: l'energia condivisa afferente a punti di prelievo di enti
    territoriali, enti religiosi, enti del terzo settore, protezione ambientale e
    persone fisiche è ESENTE dal fattore F (Regole Operative pag. 41). L'esenzione
    riguarda l'energia, non la tariffa: si partiziona l'energia condivisa con
    `condivisione.partiziona_esente_fattore_f` e si chiama questa funzione due volte,
    con F = 0 sulla parte esente e con F sull'altra (docs/FORMULE.md §2-bis).
    """
    if potenza_kw > POTENZA_MAX_INCENTIVABILE_KW:
        raise ValueError(
            f"impianto da {potenza_kw} kW: la tariffa premio spetta solo fino a "
            f"{POTENZA_MAX_INCENTIVABILE_KW} kW (DM CACER 414/2023)"
        )
    if not Decimal(0) <= fattore_conto_capitale <= FATTORE_CONTO_CAPITALE_MAX:
        raise ValueError(
            f"fattore conto capitale {fattore_conto_capitale} fuori dall'intervallo "
            f"0–{FATTORE_CONTO_CAPITALE_MAX} (Regole Operative pag. 41)"
        )
    return _tip_unitaria(potenza_kw, prezzo_zonale, zona, fotovoltaico,
                        fattore_conto_capitale)


def _tip_unitaria(
    potenza_kw: Decimal,
    prezzo_zonale: Decimal,
    zona: str,
    fotovoltaico: bool,
    fattore_conto_capitale: Decimal,
) -> Decimal:
    """Nucleo di `tip_unitaria`, senza gestione del contesto decimale.

    `incentivo_periodo` la chiama una volta per ora — 720 volte per impianto in un mese
    — ed e' gia' dentro al contesto del motore: entrare e uscire da un contesto
    identico a ogni ora sarebbe lavoro sprecato. Le guardie restano nell'involucro
    pubblico, che e' l'unico punto da cui arriva un chiamante esterno.
    """
    base = min(parte_fissa(potenza_kw) + parte_variabile(prezzo_zonale), cap_tariffa(potenza_kw))
    correttivo = CORRETTIVO_FV[zona] if fotovoltaico else Decimal(0)
    return (base + correttivo) * (Decimal(1) - fattore_conto_capitale)


@nel_contesto_del_motore
def incentivo_periodo(
    ec_kwh: list[Decimal],
    prezzi_zonali: list[Decimal],
    potenza_kw: Decimal,
    zona: str = "sud",
    fotovoltaico: bool = True,
    valorizzazione_arera: Decimal = VALORIZZAZIONE_ARERA_2024,
    fattore_conto_capitale: Decimal = Decimal(0),
) -> dict[str, Decimal]:
    """Incentivo del periodo (€): TIP ora per ora + valorizzazione ARERA sul totale EC.

    Corrisponde a C_ACI = Σ_h (TIP_h × E_ACI,h) delle Regole Operative pag. 40, più il
    corrispettivo di valorizzazione ARERA (§3 di docs/FORMULE.md), che non è tariffa
    premio e non concorre al vincolo eccedentario.

    `ec_kwh` e `prezzi_zonali` sono serie orarie allineate. Ritorna importi in €
    (Decimal, non arrotondati: l'arrotondamento avviene solo in ripartizione).

    ATTENZIONE ALLA CHIAVE `totale`. È `tip + arera` in euro, comoda per leggere e
    stampare, ma NON va convertita in centesimi: `in_centesimi(tip + arera)` e
    `in_centesimi(tip) + in_centesimi(arera)` differiscono di un centesimo quando
    entrambe le componenti cadono su mezzo centesimo (tip 1,005 € e arera 2,005 €
    danno 301 contro 302). È la ripartizione a muovere il denaro, e riceve le due
    componenti convertite SEPARATAMENTE: chi porta questi importi in centesimi — un
    export CSV, un rendiconto, un adapter — deve fare altrettanto, altrimenti
    reintroduce l'incoerenza chiusa il 7 ago 2026 (docs/ROADMAP.md punto 12).
    """
    if len(ec_kwh) != len(prezzi_zonali):
        raise ValueError("serie EC e prezzi zonali non allineate")
    mwh = Decimal(1000)
    tip = sum(
        (ec * _tip_unitaria(potenza_kw, pz, zona, fotovoltaico, fattore_conto_capitale) / mwh
         for ec, pz in zip(ec_kwh, prezzi_zonali)),
        Decimal(0),
    )
    ec_tot = sum(ec_kwh, Decimal(0))
    arera = ec_tot * valorizzazione_arera / mwh
    return {"tip": tip, "arera": arera, "totale": tip + arera, "ec_tot_kwh": ec_tot}
