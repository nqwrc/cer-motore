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
    prelievo della configurazione, non un sottoinsieme. La completezza in sé non è
    verificabile da qui — il motore non conosce l'anagrafica — ma la sua CONSEGUENZA
    misurabile sì, ed è una disuguaglianza che viene dalla norma: EC è
    min(immissioni; prelievi) sulla configurazione intera (FORMULE.md §1), quindi
    `ec[h]` non può eccedere il prelievo totale dell'ora. Se lo eccede, `prelievi` è
    troncato, e la funzione solleva ValueError nominando l'ora e i due valori.

    Il confronto è a SENSO UNICO — la serie in ingresso è al più l'EC di configurazione,
    e di norma la quota di un solo impianto, che ne è una frazione — e i due lati si
    confrontano sulla stessa griglia di `decimali` (vedi il commento alla guardia: senza
    quantizzare anche il prelievo, l'arrotondamento in su di `alloca_oraria` accusava
    perimetri completi). Verificato sui quattro scenari mock, ogni impianto, tutti e
    dodici i mesi, a sei risoluzioni (`decimali` 0, 1, 2, 3, 6, 12) e su ENTRAMBE le
    serie che questa docstring dichiara ammissibili — la quota per impianto e l'EC di
    configurazione: **zero falsi positivi su 720 combinazioni**. La seconda serie non è
    un di più: è su quella che una verifica avversariale ha trovato il difetto speculare
    descritto alla guardia, che il solo sweep per impianto non vedeva.

    Uguaglianza esatta là dove è il prelievo a vincolare EC: 316 ore su 720 in `cumulo`,
    36 in `concentrata`, nessuna nei due scenari a due impianti. Quest'ultimo fatto è
    dei mock e non delle configurazioni a più impianti in generale: `mock._produzione_fv`
    dà a ogni impianto la stessa curva solare e la stessa nuvolosità oraria, quindi i due
    immettono sempre insieme e la quota di ciascuno resta una frazione dell'EC. Con
    tecnologie miste, o un impianto fermo, l'unico che immette in quell'ora prende il
    100% dell'EC e il margine si chiude come nel caso mono-impianto.

    Quanto vale, misurato su `cumulo` (F = 0,30, tre POD esenti su cinque): togliendo
    dal perimetro il bar — un POD NON esente, quindi il verso che gonfia la quota
    esente — l'energia esente passa da 1.966,142 a 2.468,219 kWh e la tariffa premio
    da 387,17 a 406,71 €, cioè **+19,54 € (+5,05%) mai decurtati**; togliendo lo
    studio, +21,22 € (+5,48%). La guardia precedente, che cercava solo le ore con
    prelievi TUTTI nulli, taceva in entrambi i casi (0 ore su 720); questa scatta in
    346 e 340 ore. Nell'altro verso — tolto un POD esente, con `pod_esenti` troncato
    coerentemente perché la guardia sui POD ignoti non scatti — l'esenzione sparisce e
    il TIP scende: −2,82 € e −2,85 € per le due famiglie (330 ore), **−50,19 € cioè
    −12,96% per la palestra** (378 ore), che è il punto di prelievo più grosso dei tre
    ed è il caso peggiore misurato in assoluto, in entrambi i versi.

    Quel che resta scoperto, ed è la ragione per cui questa resta una PRECONDIZIONE e
    non diventa una verifica: un troncamento che non morda in nessuna ora — POD la cui
    energia sta sempre sopra la linea di EC — passa ancora in silenzio. La guardia
    trasforma "sempre muto" in "muto solo se il troncamento non tocca mai il vincolo",
    non in "impossibile". FORMULE.md §2-bis, "il perimetro".
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
    # EC = min(immissioni; prelievi) sulla configurazione intera (FORMULE.md §1), quindi
    # EC[h] non può eccedere il prelievo totale dell'ora. La serie in ingresso è al più
    # quella EC (di norma la quota di UN impianto, che ne è una frazione), quindi il
    # confronto è a senso unico: su un perimetro completo non scatta, e se scatta il
    # perimetro è troncato.
    #
    # I DUE LATI VANNO PORTATI SULLA STESSA GRIGLIA prima di confrontarli, ed è il
    # motivo per cui questa funzione prende `decimali`. La serie in ingresso è di norma
    # prodotta da `alloca_oraria`, che quantizza EC a `decimali` con ROUND_HALF_UP:
    # arrotonda dunque IN SU, fino a mezza unità. Confrontare quel valore quantizzato
    # con la somma grezza dei prelievi accusa un perimetro completo di essere troncato
    # ogni volta che l'arrotondamento morde su un'ora dove EC eguaglia il prelievo — e
    # sono il 43,9% delle ore in `cumulo`. Misurato: con prelievi 0,6000005 + 0,4 e
    # un impianto solo, la quota esce 1,000001 contro un prelievo di 1,0000005, e la
    # guardia scattava su dati perfettamente legittimi. Quantizzando anche il prelievo
    # con lo stesso passo e lo stesso arrotondamento il confronto torna a misurare il
    # perimetro invece della griglia. Il margine così concesso è mezza unità di
    # `decimali`, e SCALA CON ESSO: 5e-7 kWh con il default, quattro ordini di grandezza
    # sotto i 3 decimali di kWh delle misure dei distributori; ma 0,005 kWh a
    # `decimali = 2` e mezzo kWh a `decimali = 0`. La detezione non sparisce mai — un
    # POD da 0,010 kWh/ora tolto da `cumulo` resta visto in 316 ore su 720 a `decimali`
    # 3 e 6 — ma la SENSIBILITÀ cala con la risoluzione: lo stesso POD si vede in 38 ore
    # a `decimali = 1` e in 4 a `decimali = 0`, dove mezzo kWh è il prelievo orario di
    # una famiglia. Alla risoluzione di default e fino a `decimali = 3` nessun
    # troncamento reale ci si nasconde; sotto, abbassare `decimali` abbassa con sé
    # questa guardia, ed è un'altra ragione per non farlo su dati veri.
    passo_confronto = Decimal(1).scaleb(-decimali)
    incoerenti = []
    for h in range(len(ec)):
        totale = sum((serie[h] for serie in prelievi.values()), Decimal(0))
        # ENTRAMBI i lati, non uno solo: quantizzare il solo prelievo non toglie il
        # difetto, lo specchia. Con ROUND_HALF_UP un totale che ha sotto la griglia una
        # frazione inferiore a mezza unità viene arrotondato IN GIÙ, e allora è l'EC
        # grezza a sfondarlo — misurato con prelievi 0,6000004 + 0,4, dove EC eguaglia
        # esattamente il prelievo e la guardia accusava lo stesso.
        if (
            ec[h].quantize(passo_confronto, rounding=ROUND_HALF_UP)
            > totale.quantize(passo_confronto, rounding=ROUND_HALF_UP)
        ):
            incoerenti.append((h, totale))
    if incoerenti:
        h, totale = incoerenti[0]
        quante = (
            "in 1 ora" if len(incoerenti) == 1 else f"in {len(incoerenti)} ore"
        )
        raise ValueError(
            f"Energia condivisa maggiore del prelievo totale {quante} "
            f"(prima: ora {h}, EC {ec[h]} kWh > prelievi {totale} kWh). EC è "
            "min(immissioni; prelievi) sulla configurazione intera, quindi non può "
            "eccedere il prelievo: un'ora così può esistere solo se `prelievi` non è "
            "l'insieme completo dei punti di prelievo (docstring, PRECONDIZIONE SUL "
            f"PERIMETRO). Punti di prelievo ricevuti: {sorted(prelievi)}."
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
