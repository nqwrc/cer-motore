"""Rendiconto per membro: dal risultato della ripartizione a un testo leggibile."""
from decimal import Decimal

from .ripartizione import in_centesimi


def _euro(cent: int) -> str:
    return f"{Decimal(cent) / 100:.2f} €"


def _perc(frazione: Decimal) -> str:
    return f"{frazione * 100:.1f}%"


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
    centesimi che la ripartizione ha distribuito: `in_centesimi(tip)` e
    `in_centesimi(arera)` presi separatamente, e il totale come loro SOMMA. Non si
    arrotonda mai la somma in euro, perché `in_centesimi(tip + arera)` e
    `in_centesimi(tip) + in_centesimi(arera)` possono differire di un centesimo — con
    tip = 1,005 € e arera = 2,005 € il primo dà 301 e il secondo 302 — e la tabella,
    che riparte i centesimi con l'invariante somma == totale, chiude sul secondo.
    Fino al 7 ago 2026 l'intestazione formattava i Decimal in euro (per giunta con
    l'arrotondamento ROUND_HALF_EVEN del formato, diverso dal ROUND_HALF_UP di
    `in_centesimi`): sullo stesso esempio stampava "TIP 1,00 · ARERA 2,00 · totale 3,01"
    sopra una tabella che sommava 3,02, tre numeri incoerenti fra loro.

    Se gli importi ripartiti non chiudono sui centesimi delle due componenti la
    funzione solleva `ValueError` invece di stampare un rendiconto che non torna.

    CHI DECIDE I CENTESIMI. Le chiavi facoltative `tip_cent` e `arera_cent` sono
    autorevoli: se ci sono, il rendiconto le usa cosi' come sono. Servono
    l'arrotondamento è già avvenuto a monte, e non una volta sola. È il caso del
    vincolo eccedentario sui due insiemi (`ripartizione.scomponi_eccedentario_insiemi`,
    Regole Operative pag. 42): lì ogni insieme porta il proprio contributo già in
    centesimi interi, e la loro somma può differire di un centesimo da
    `in_centesimi(somma dei Decimal)`. Riderivare dai Decimal in quel flusso faceva
    sollevare `ValueError` su dati perfettamente legittimi — verificato con due insiemi
    da 1,005 € di TIP: la ripartizione ne distribuiva 202, il rendiconto ne pretendeva
    201. Senza quelle chiavi si ricade sul comportamento storico, che resta corretto
    finché il chiamante arrotonda una volta sola.
    """
    tip_cent = incentivo.get("tip_cent")
    if tip_cent is None:
        tip_cent = in_centesimi(incentivo["tip"])
    arera_cent = incentivo.get("arera_cent")
    if arera_cent is None:
        arera_cent = in_centesimi(incentivo["arera"])
    totale_cent = tip_cent + arera_cent
    ripartito_cent = sum(v for voci in esito.values() for v in voci.values())
    if ripartito_cent != totale_cent:
        raise ValueError(
            f"rendiconto incoerente: la ripartizione distribuisce {ripartito_cent} "
            f"centesimi, ma TIP ({tip_cent}) + ARERA ({arera_cent}) fanno {totale_cent}. "
            "Il chiamante deve portare in centesimi le due componenti SEPARATAMENTE "
            "prima di ripartirle — in_centesimi(tip) + in_centesimi(arera) — e non "
            "arrotondare la somma in euro: i due valori differiscono di un centesimo "
            "quando entrambe le componenti cadono su mezzo centesimo. Se invece "
            "l'arrotondamento è già avvenuto a monte, per esempio per insieme "
            "incentivato, passa i totali autorevoli nelle chiavi 'tip_cent' e "
            "'arera_cent' invece di farli riderivare da qui."
        )

    righe = [
        f"# Rendiconto CER — {periodo}",
        "",
        f"Energia condivisa: **{incentivo['ec_tot_kwh']:.0f} kWh** · "
        f"TIP: **{_euro(tip_cent)}** · valorizzazione ARERA: **{_euro(arera_cent)}** · "
        f"totale: **{_euro(totale_cent)}**",
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
        if m == "_fondi":
            continue
        qp, qc, qe = voci.get("quota_produttore", 0), voci.get("quota_consumatore", 0), voci.get("quota_eccedentaria", 0)
        righe.append(
            f"| {m} | {membri[m]['ruolo']} | {_euro(qp)} | {_euro(qc)} | {_euro(qe)} | {_euro(qp + qc + qe)} |"
        )
    if esito.get("_fondi"):
        righe += ["", "**Fondi statutari:** " + " · ".join(
            f"{nome}: {_euro(cent)}" for nome, cent in esito["_fondi"].items())]

    eccedentario_cent = sum(
        voci.get("quota_eccedentaria", 0) for m, voci in esito.items() if m != "_fondi"
    ) + esito.get("_fondi", {}).get("finalita_sociali", 0)
    if eccedentario_cent:
        righe += ["", "*Il vincolo dell'importo eccedentario è qui applicato al singolo "
                  "periodo di calcolo; il GSE lo verifica a conguaglio su base annuale "
                  "(Regole Operative pag. 41). Su un mese è un'approssimazione.*"]

    righe += ["", "*Calcolo su dati mock — non usare per riparti reali. "
              "Formule e fonti: docs/FORMULE.md.*"]
    return "\n".join(righe)
