"""Calcolo dell'energia condivisa (autoconsumata virtualmente).

Fonte: DM CACER 414/2023; Regole Operative GSE (agg. DD 16/7/2025).
Per ciascuna ora: EC_h = min(somma immissioni, somma prelievi) tra i POD della
configurazione sottesi alla stessa cabina primaria. Vedi docs/FORMULE.md §1.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping, Sequence

from .ripartizione import ripartisci_centesimi

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
        riparto = ripartisci_centesimi(ec_unita, pesi)  # unità = 1e-6 kWh, non centesimi
        for pod, u in riparto.items():
            quote[pod].append(Decimal(u) * passo)
    return quote
