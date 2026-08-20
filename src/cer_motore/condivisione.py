"""Calcolo dell'energia condivisa (autoconsumata virtualmente).

Fonte: DM CACER 414/2023; Regole Operative GSE (agg. DD 16/7/2025).
Per ciascuna ora: EC_h = min(somma immissioni, somma prelievi) tra i POD della
configurazione sottesi alla stessa cabina primaria. Vedi docs/FORMULE.md §1.

Qui stanno anche le due partizioni di quella grandezza che la tariffa richiede e la
norma non prescrive — l'attribuzione agli impianti (§1-bis) e quella fra energia esente
e non esente dal fattore F del cumulo con conto capitale (§2-bis) — perché sono la
stessa operazione pro-quota oraria applicata due volte, una alle immissioni e una ai
prelievi, ed entrambe sono scelte di modellazione dichiarate.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Collection, Mapping, Sequence

from .comune import nel_contesto_del_motore
from .ripartizione import riparto_per_pesi

Serie = Sequence[Decimal]  # kWh per ora, un elemento per ora del periodo

# Risoluzione dell'allocazione oraria per impianto: 1e-6 kWh (1 mWh). Le misure dei
# distributori arrivano con 3 decimali di kWh, quindi la quantizzazione a 6 decimali
# non tocca i dati in ingresso e lascia tre cifre di margine alle frazioni di riparto.
DECIMALI_KWH = 6


def _lunghezza(serie: Mapping[str, Serie]) -> int:
    lunghezze = {len(s) for s in serie.values()}
    if len(lunghezze) > 1:
        raise ValueError(f"serie orarie di lunghezza diversa: {sorted(lunghezze)}")
    return lunghezze.pop() if lunghezze else 0


@nel_contesto_del_motore
def energia_condivisa(
    immissioni: Mapping[str, Serie],
    prelievi: Mapping[str, Serie],
) -> list[Decimal]:
    """Serie oraria dell'energia condivisa della configurazione (kWh).

    `immissioni`: POD produttore -> serie oraria kWh immessi.
    `prelievi`:   POD consumatore -> serie oraria kWh prelevati.
    """
    n_i, n_p = _lunghezza(immissioni), _lunghezza(prelievi)
    if immissioni and prelievi and n_i != n_p:
        raise ValueError(f"immissioni ({n_i} ore) e prelievi ({n_p} ore) non allineati")
    n = max(n_i, n_p)
    out: list[Decimal] = []
    for h in range(n):
        imm = sum((s[h] for s in immissioni.values()), Decimal(0))
        pre = sum((s[h] for s in prelievi.values()), Decimal(0))
        out.append(min(imm, pre))
    return out


@nel_contesto_del_motore
def contributo_prelievo_coincidente(
    prelievi: Mapping[str, Serie],
    ec: Serie,
    decimali: int = DECIMALI_KWH,
) -> dict[str, Decimal]:
    """Contributo di ogni consumatore alla condivisione (kWh, allocazione oraria).

    Per ogni ora l'energia condivisa EC_h viene attribuita ai consumatori in
    proporzione al loro prelievo in quell'ora. È il criterio "chi consuma quando
    il sole produce" usato dalle regole statutarie più comuni.

    È la stessa attribuzione oraria pro-quota di `alloca_oraria` — là sugli impianti
    a partire dalle immissioni, qui sui consumatori a partire dai prelievi — sommata
    sul periodo, e ne eredita l'invariante ESATTO: somma dei contributi == somma di EC.
    Fino al 7 ago 2026 questa funzione usava la divisione semplice e il suo docstring
    dichiarava un invariante che non aveva: con tre consumatori uguali ed EC=10 la
    somma dei contributi valeva 9,999999999999999999999999999. Non arrivava mai sui
    soldi (i contributi servono da pesi e `ripartisci_centesimi` li rinormalizza), ma
    era un'affermazione falsa in un modulo che ne fa il proprio punto d'onore.
    """
    n = _lunghezza(prelievi)
    if n != len(ec):
        raise ValueError(f"serie EC ({len(ec)} ore) non allineata ai prelievi ({n} ore)")
    return {pod: sum(serie, Decimal(0))
            for pod, serie in alloca_oraria(prelievi, ec, decimali).items()}


@nel_contesto_del_motore
def alloca_oraria(
    immissioni: Mapping[str, Serie],
    ec: Serie,
    decimali: int = DECIMALI_KWH,
) -> dict[str, list[Decimal]]:
    """Attribuisce l'energia condivisa oraria agli impianti, pro-quota immissioni.

    Fonte: DM CACER 414/2023 e Regole Operative GSE (agg. DD 16/7/2025). L'energia
    condivisa è una grandezza della *configurazione* (docs/FORMULE.md §1), ma la
    tariffa premio si calcola *per impianto*: scaglione di potenza, cap e correttivo
    geografico dipendono dal singolo POD di produzione (§2). Serve quindi una regola
    di attribuzione, e il criterio è pro-quota oraria delle immissioni:

        quota[i][h] = EC[h] * immissioni[i][h] / somma_i(immissioni[i][h])

    Ore con immissione totale nulla: tutte le quote sono zero, nessuna divisione per
    zero. Non si perde energia, perché EC[h] = min(immissioni, prelievi) ≤ immissioni:
    se l'immissione totale è nulla lo è anche EC[h]. (La funzione è pura e non lo
    verifica: se si passa un EC[h] > 0 su un'ora senza immissioni, quell'energia non
    è attribuibile ad alcun impianto e viene lasciata a zero.)

    INVARIANTE: per ogni ora, somma delle quote == EC[h] (zero sulle ore senza
    immissioni). L'uguaglianza è **esatta**, non a meno di arrotondamento, ma non è
    ottenibile con la sola divisione: EC[h] * imm / tot è in generale un decimale
    periodico troncato dal contesto Decimal (28 cifre significative), e la somma dei
    quozienti non ritorna EC[h]. Si applica perciò lo stesso metodo del resto maggiore
    già usato per il denaro (`ripartizione.ripartisci_centesimi`), che è indipendente
    dall'unità: qui l'unità intera non è il centesimo ma 1e-6 kWh (`decimali`).

    Precisazione onesta sull'invariante: l'uguaglianza esatta vale rispetto a EC[h]
    *quantizzato* a `decimali` decimali. Sulle misure dei distributori (3 decimali di
    kWh) la quantizzazione è l'identità, quindi somma quote == EC[h] senza riserve.
    Se si passa un EC con più di `decimali` decimali, l'invariante vale sul valore
    quantizzato e lo scarto rispetto all'originale è al più 5 * 10^-(decimali+1) kWh
    per ora — quattro ordini di grandezza sotto la risoluzione di misura.
    """
    n = _lunghezza(immissioni)
    if n != len(ec):
        raise ValueError(f"serie EC ({len(ec)} ore) non allineata alle immissioni ({n} ore)")
    passo = Decimal(1).scaleb(-decimali)  # 1e-6 kWh: l'unità intera del riparto
    quote: dict[str, list[Decimal]] = {pod: [] for pod in immissioni}
    for h in range(n):
        pesi = {pod: s[h] for pod, s in immissioni.items()}
        tot = sum(pesi.values(), Decimal(0))
        ec_unita = int((ec[h] / passo).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        if tot <= 0 or ec_unita == 0:
            for pod in quote:
                quote[pod].append(Decimal(0))
            continue
        # `riparto_per_pesi` e non `ripartisci_centesimi`: siamo gia' dentro il
        # contesto del motore, e questa riga gira una volta per ora.
        riparto = riparto_per_pesi(ec_unita, pesi)  # unità = 1e-6 kWh, non centesimi
        for pod, u in riparto.items():
            quote[pod].append(Decimal(u) * passo)
    return quote


@nel_contesto_del_motore
def partiziona_esente_fattore_f(
    prelievi: Mapping[str, Serie],
    ec: Serie,
    pod_esenti: Collection[str],
    decimali: int = DECIMALI_KWH,
) -> tuple[list[Decimal], list[Decimal]]:
    """Divide l'energia condivisa oraria in (esente, non esente) dal fattore F.

    Fonte dell'ESENZIONE, Regole Operative pag. 41: l'energia condivisa afferente a
    punti di prelievo di **enti territoriali, enti religiosi, enti del terzo settore,
    enti di protezione ambientale e persone fisiche** è esente dal fattore F, cioè dalla
    decurtazione `TIP × (1 − F)` che si applica agli impianti che cumulano la tariffa
    premio con un contributo in conto capitale (Appendice B §3 pag. 161, `tariffe.py`).
    L'esenzione è al PRELIEVO, non alla produzione: lo stesso impianto in cumulo produce
    energia in parte decurtata e in parte no, a seconda di chi l'ha consumata nell'ora.

    Il CRITERIO DI ATTRIBUZIONE, invece, è nostro — **[modellazione]**, docs/FORMULE.md
    §2-bis. Le Regole Operative dicono quale energia è esente ma non come misurarla, per
    la stessa ragione per cui non prescrivono come attribuire l'EC ai singoli impianti
    (§1-bis): l'energia condivisa oraria è `min(immissioni, prelievi)` sulla
    configurazione intera e non nasce già intestata a un POD. Qui si usa lo stesso
    criterio già adottato là, applicato ai prelievi — pro-quota oraria, via
    `alloca_oraria` — e ne eredita l'invariante esatto:

        esente[h] + non_esente[h] == EC[h]   (quantizzato a `decimali`, per ogni ora)

    Va sostituito se i tracciati GSE ne prescriveranno uno diverso.

    LA PARTIZIONE NON CREA UN SECONDO INSIEME INCENTIVATO. Gli insiemi "j" del vincolo
    eccedentario (Regole Operative pag. 42, `ripartizione.InsiemeIncentivato`) si
    formano per IMPIANTO — un impianto in cumulo sta tutto nell'insieme a soglia 45% —
    mentre questa partizione riguarda l'energia e decide solo a quale metà si applica F.
    Le due cose si sommano, non si intrecciano.

    COME SI COMPONE. La serie in ingresso è tipicamente l'EC già attribuita a un singolo
    impianto in cumulo (`alloca_oraria(immissioni, ec)[pod]`), perché la tariffa premio
    si calcola per impianto. Le due serie che escono vanno tariffate separatamente e i
    contributi si sommano:

        esente, non_esente = partiziona_esente_fattore_f(prelievi, ec_pod, esenti)
        a = incentivo_periodo(esente, prezzi, kw, fattore_conto_capitale=Decimal(0))
        b = incentivo_periodo(non_esente, prezzi, kw, fattore_conto_capitale=f)

    Serie ORARIE e non totali di periodo, perché `TIP_h` dipende dal prezzo zonale
    dell'ora: un totale di periodo non è più tariffabile.

    `pod_esenti` sono i POD DI PRELIEVO esenti, e devono esistere fra i `prelievi`: un
    POD scritto male non è un caso di zero energia, è energia esente trattata come non
    esente, cioè tariffa premio decurtata a chi non doveva esserlo, in silenzio e senza
    che nessun invariante se ne accorga. È la stessa specie di errore del ruolo scritto
    male in `ripartizione.ripartisci`, e riceve lo stesso trattamento. La classificazione
    dei POD resta al chiamante: è un fatto giuridico sul titolare del punto di prelievo,
    non una grandezza che il motore possa dedurre dalle misure.

    PRECONDIZIONE SUL PERIMETRO: `prelievi` deve essere l'insieme COMPLETO dei punti di
    prelievo della configurazione, non un sottoinsieme. La completezza non è verificabile
    da qui — il motore non conosce l'anagrafica — ma il suo caso estremo sì: un'ora con
    EC > 0 e prelievi tutti nulli è impossibile (EC è min(immissioni; prelievi) sulla
    configurazione intera) e solleva ValueError. Con una mappa troncata ma non nulla
    l'errore è silenzioso e va nella direzione del troncamento: tolti POD non esenti,
    la quota esente si gonfia e la decurtazione non viene mai applicata; tolti POD
    esenti (con `pod_esenti` troncato coerentemente, così la guardia sui POD ignoti
    non può scattare), l'esenzione sparisce e la decurtazione colpisce chi la norma
    risparmiava. FORMULE.md §2-bis, "il perimetro".
    """
    ignoti = sorted(set(pod_esenti) - set(prelievi))
    if ignoti:
        raise ValueError(
            f"POD dichiarati esenti dal fattore F ma assenti dai prelievi: {ignoti}. "
            "Non è un prelievo nullo: l'energia di quei punti resterebbe nella quota "
            "NON esente e prenderebbe la decurtazione TIP × (1 − F) che la norma le "
            "risparmia (Regole Operative pag. 41), senza che nulla lo segnali. "
            f"Punti di prelievo noti: {sorted(prelievi)}."
        )
    esenti = set(pod_esenti)
    # Prima l'allocazione: sono le sue guardie a diagnosticare serie disallineate e
    # valori non trattabili, con i loro messaggi. La guardia sul perimetro legge le
    # serie per indice e sarebbe un IndexError nudo se corresse per prima.
    quote = alloca_oraria(prelievi, ec, decimali)
    ore_incoerenti = [
        h
        for h in range(len(ec))
        if ec[h] > 0 and all(serie[h] == 0 for serie in prelievi.values())
    ]
    if ore_incoerenti:
        raise ValueError(
            f"Energia condivisa positiva in ore senza alcun prelievo: ore {ore_incoerenti}. "
            "EC è min(immissioni; prelievi) sulla configurazione intera: un'ora così può "
            "esistere solo se `prelievi` non è l'insieme completo dei punti di prelievo "
            "(docstring, PRECONDIZIONE SUL PERIMETRO)."
        )
    esente, non_esente = [], []
    for h in range(len(ec)):
        # Entrambe le serie si costruiscono SOMMANDO le quote, nessuna delle due per
        # differenza da EC[h]: così l'invariante è quello di `alloca_oraria` — la somma
        # delle quote è esattamente EC[h] quantizzato — invece di un'uguaglianza
        # imposta a una delle due parti e da verificare sull'altra.
        esente.append(sum((q[h] for pod, q in quote.items() if pod in esenti), Decimal(0)))
        non_esente.append(
            sum((q[h] for pod, q in quote.items() if pod not in esenti), Decimal(0))
        )
    return esente, non_esente
