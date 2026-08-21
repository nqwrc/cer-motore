"""Demo end-to-end su dati mock: python -m cer_motore

Elabora QUATTRO scenari mock (docs/MOCK-GSE.md) con lo stesso statuto, per mostrare il
comportamento del vincolo dell'importo eccedentario al variare del solo dato fisico:

- `equilibrata`: rapporto energia condivisa / energia immessa 0,27, sotto la soglia del
  55% (sola tariffa premio), il vincolo non scatta e la colonna "Quota eccedentaria" è
  a zero;
- `cumulo`: rapporto 0,49, sopra la soglia del 45% che si applica agli impianti in
  cumulo con un contributo in conto capitale ma SOTTO quella del 55% della sola
  tariffa premio — il vincolo scatta qui perché la soglia dell'insieme è quella più
  bassa, non perché il rapporto sia alto: prende il 3,8% della tariffa premio;
- `paese`: rapporto 0,61, appena sopra la soglia del 55%; il vincolo scatta ma prende
  il 5,6% della tariffa premio, non di più;
- `concentrata`: rapporto 0,98, il vincolo scatta in pieno e si porta via il 42,6% del
  TIP a favore dei soli consumatori diversi dalle imprese (Regole Operative pag. 41).

Cosa stampa, e perché non tutto: la TABELLA di confronto dei quattro — che è dove la
progressione si legge in poche righe — e UN SOLO rendiconto per esteso, quello di
`concentrata`, dove la parte più delicata del motore si vede girare con i numeri più
grandi. Quattro rendiconti a video sarebbero un muro di testo, e chi ha quindici minuti
smette di leggere prima della fine; i quattro file completi restano su disco.

Tutto ciò che la demo scrive sta sotto ./data/, che è la sua cartella usa-e-getta: i CSV
di misura in data/<scenario>/, i rendiconti completi di tutti e quattro gli scenari in
data/rendiconto-<scenario>.md e, degli stessi quattro, l'export per il commercialista in
data/rendiconto-<scenario>.csv. Una sola cartella da cancellare, e già ignorata da git.
"""
import sys
from decimal import Decimal
from pathlib import Path

from . import mock, regole as mod_regole
from .comune import in_euro
from .condivisione import (
    alloca_oraria,
    contributo_prelievo_coincidente,
    energia_condivisa,
    partiziona_esente_fattore_f,
)
from .mock import Scenario
from .rendiconto import rendiconto_csv, rendiconto_markdown
from .ripartizione import (
    InsiemeIncentivato,
    in_centesimi,
    ripartisci,
    scomponi_eccedentario_insiemi,
)
from .tariffe import incentivo_periodo

MESE = "giugno 2026"
PERIODO = f"{MESE} (dati mock)"

# Statuto identico nei quattro scenari: così l'unica differenza fra i quattro rendiconti
# viene dal dato fisico (chi produce, chi consuma, quando, e — solo per `cumulo` — chi
# ha preso un contributo in conto capitale), non dalle regole di riparto.
#
# È scritto in TOML e passa dalla stessa validazione di un file vero (`regole.da_testo`,
# che è pura e non tocca il disco): la demo percorre così la strada che percorrerà una
# CER reale, invece di costruire a mano un dict che nessuna validazione ha visto. La
# versione commentata e leggibile in assemblea è `regole-esempio.toml`, e un test
# verifica che le due non divergano.
STATUTO_TOML = """
[fondi]
gestione = "0.10"

[quote]
produttori = "0.50"
consumatori = "0.50"

[criteri]
produttori = "energia_immessa"
consumatori = "prelievo_coincidente"
"""
REGOLE = mod_regole.da_testo(STATUTO_TOML)


def elabora(scenario: Scenario, cartella_dati: Path) -> tuple[dict, dict]:
    """Genera i CSV dello scenario e percorre la catena fino alla ripartizione.

    Ritorna (incentivo, esito): il dizionario dei totali di periodo arricchito con
    l'energia immessa e la soglia usata, e il riparto per membro in centesimi.

    Il vincolo eccedentario passa dalla forma aggregata per insiemi delle Regole
    Operative pag. 42, in DUE secchi — `sola_tariffa` (soglia 55%) e
    `cumulo_conto_capitale` (soglia 45%) — a seconda che il singolo impianto abbia o
    no un fattore F: uno scenario mock (`mock.CUMULO`) popola davvero il secondo, non
    solo il primo come accadeva fino al 20 agosto 2026, quando l'insieme a soglia 45%
    era raggiungibile solo dai test. Un impianto in cumulo (F > 0) attraversa anche
    `condivisione.partiziona_esente_fattore_f` PRIMA di tariffare: la sua energia
    condivisa si divide in esente e non esente dal fattore F (Regole Operative
    pag. 41), le due parti si tariffano separatamente — F = 0 sulla prima, F sulla
    seconda — e i contributi si sommano (`docs/FORMULE.md` §2-bis).
    """
    f_mis, f_pz = mock.genera(cartella_dati, scenario=scenario)
    immissioni, prelievi, prezzi = mock.carica(f_mis, f_pz)

    ec = energia_condivisa(immissioni, prelievi)

    # attribuzione oraria dell'EC agli impianti pro-quota immissioni → incentivo per impianto
    potenze, fotovoltaici = scenario.potenze_kw(), scenario.fotovoltaici()
    fattori_f = scenario.fattori_conto_capitale()
    totale = {"tip": Decimal(0), "arera": Decimal(0), "totale": Decimal(0), "ec_tot_kwh": Decimal(0)}
    # Un secchio per insieme "j": accumula l'energia condivisa, l'energia immessa e il
    # TIP (Decimal, non ancora in centesimi) degli impianti che gli appartengono. Un
    # impianto sta nel secchio "cumulo" se e solo se F > 0 — la STESSA condizione che
    # decide se la sua energia condivisa va partizionata prima di essere tariffata.
    dati_sola = {"ec": Decimal(0), "imm": Decimal(0), "tip": Decimal(0)}
    dati_cumulo = {"ec": Decimal(0), "imm": Decimal(0), "tip": Decimal(0)}
    for pod, ec_pod in alloca_oraria(immissioni, ec).items():
        kw, fv, f = potenze[pod], fotovoltaici[pod], fattori_f[pod]
        imm_pod = sum(immissioni[pod], Decimal(0))
        if f > 0:
            # `partiziona_esente_fattore_f` vuole il perimetro COMPLETO dei punti di
            # prelievo (PRECONDIZIONE SUL PERIMETRO nel suo docstring): `prelievi` qui è
            # già quello, non un sottoinsieme filtrato per impianto.
            esente, non_esente = partiziona_esente_fattore_f(
                prelievi, ec_pod, scenario.pod_esenti_fattore_f
            )
            a = incentivo_periodo(esente, prezzi, kw, zona=scenario.zona_tariffa,
                                  fotovoltaico=fv, fattore_conto_capitale=Decimal(0))
            b = incentivo_periodo(non_esente, prezzi, kw, zona=scenario.zona_tariffa,
                                  fotovoltaico=fv, fattore_conto_capitale=f)
            inc = {k: a[k] + b[k] for k in a}
            dati = dati_cumulo
        else:
            inc = incentivo_periodo(ec_pod, prezzi, kw, zona=scenario.zona_tariffa,
                                    fotovoltaico=fv)
            dati = dati_sola
        for k in totale:
            totale[k] += inc[k]
        dati["ec"] += inc["ec_tot_kwh"]
        dati["imm"] += imm_pod
        dati["tip"] += inc["tip"]

    # ripartizione. Ogni insieme porta i PROPRI centesimi, arrotondati dal proprio
    # Decimal: sommare prima e arrotondare dopo è la stessa strada già chiusa in
    # roadmap 15 per TIP e ARERA, e per lo stesso motivo — `in_centesimi(a) +
    # in_centesimi(b)` e `in_centesimi(a + b)` divergono quando entrambe cadono su
    # mezzo centesimo.
    imm_tot = sum(sum(s) for s in immissioni.values())
    arera_cent = in_centesimi(totale["arera"])
    insiemi = []
    tip_cent_sola = tip_cent_cumulo = 0
    if dati_sola["imm"] > 0:
        tip_cent_sola = in_centesimi(dati_sola["tip"])
        insiemi.append(
            InsiemeIncentivato.sola_tariffa(dati_sola["ec"], dati_sola["imm"], tip_cent_sola)
        )
    if dati_cumulo["imm"] > 0:
        tip_cent_cumulo = in_centesimi(dati_cumulo["tip"])
        insiemi.append(
            InsiemeIncentivato.cumulo_conto_capitale(
                dati_cumulo["ec"], dati_cumulo["imm"], tip_cent_cumulo
            )
        )
    base, ecc = scomponi_eccedentario_insiemi(insiemi)
    base += arera_cent  # la valorizzazione ARERA non è "eccedentaria"

    totale["immissioni_tot_kwh"] = imm_tot
    totale["eccedentario_cent"] = ecc
    # Centesimi autorevoli per il rendiconto: li ha decisi qui la scomposizione per
    # insieme, e il rendiconto non deve riottenerli dai Decimal (vedi rendiconto.py).
    totale["tip_cent"], totale["arera_cent"] = tip_cent_sola + tip_cent_cumulo, arera_cent
    # La colonna "Soglia" del confronto ha UN valore per scenario: vale finché ogni
    # scenario mock ha impianti di un solo insieme, come i quattro attuali. Uno
    # scenario che mescolasse sola tariffa e cumulo avrebbe due soglie contemporanee,
    # e questa riga smetterebbe di avere una risposta univoca: si ferma piuttosto che
    # sceglierne una a caso.
    if len(insiemi) != 1:
        raise NotImplementedError(
            f"scenario {scenario.nome!r}: {len(insiemi)} insiemi incentivati non vuoti "
            "(ne serve esattamente 1: impianti a sola tariffa OPPURE impianti in cumulo "
            "con conto capitale, mai zero — con almeno un impianto valido l'energia "
            "immessa non può essere nulla sull'intero periodo — e mai entrambi insieme). "
            "La colonna 'Soglia' del confronto e l'intestazione del rendiconto assumono "
            "un insieme solo per scenario: nessuno dei quattro scenari mock lo viola, e "
            "la demo non è ancora pronta a uno che lo faccia."
        )
    totale["soglia_eccedentario"] = insiemi[0].soglia

    # I pesi si aggregano per MEMBRO, non per POD: un membro può avere più punti di
    # connessione (l'officina dello scenario "concentrata" ne ha due, uno di immissione
    # e uno di prelievo) e sommare è l'unica operazione corretta — una comprehension
    # POD → membro sovrascriverebbe in silenzio.
    membro_di, membri = scenario.membro_di(), scenario.membri()
    energia_per_membro: dict[str, Decimal] = {}
    for pod, serie in immissioni.items():
        m = membro_di[pod]
        energia_per_membro[m] = energia_per_membro.get(m, Decimal(0)) + sum(serie, Decimal(0))
    contributi: dict[str, Decimal] = {}
    for pod, kwh in contributo_prelievo_coincidente(prelievi, ec).items():
        m = membro_di[pod]
        contributi[m] = contributi.get(m, Decimal(0)) + kwh
    esito = ripartisci(REGOLE, base, ecc, energia_per_membro, contributi, membri)
    return totale, esito


def confronto(
    risultati: list[tuple[Scenario, dict, dict]], per_esteso: Scenario
) -> str:
    """Tabella di confronto fra scenari: dove sta il rapporto EC/EI e cosa ne segue.

    L'importo eccedentario è mostrato anche come PERCENTUALE DELLA TARIFFA PREMIO, non
    solo in euro: è quella la grandezza che il vincolo determina (differenza in punti
    percentuali fra rapporto e soglia, Regole Operative pag. 42), ed è l'unico modo per
    vedere in tabella che a rapporto 0,61 il vincolo morde per pochi punti mentre a
    0,98 si porta via quasi metà del contributo. In euro i due numeri non si possono
    confrontare, perché gli scenari hanno impianti di taglia diversa.

    `per_esteso` è lo scenario di cui la demo stampa il rendiconto completo subito
    dopo: passarlo evita che questa riga di chiusura menta il giorno in cui la demo
    cambia idea su quale stampare.
    """
    # La colonna "Scenario" porta il NOME breve, non il titolo. Il titolo dello
    # scenario più lungo è di 84 caratteri e da solo portava la riga a 200: una tabella
    # Markdown più larga della console va a capo, e una tabella andata a capo non è più
    # una tabella. I titoli per esteso stanno sotto, in righe che possono avvolgersi
    # senza far danno.
    righe = [
        f"# cer-motore — demo su dati mock, {MESE}",
        "",
        "| Scenario | Immesso | Condiviso | EC/EI | Soglia | Vincolo eccedentario |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for scenario, totale, _esito in risultati:
        rapporto = totale["ec_tot_kwh"] / totale["immissioni_tot_kwh"]
        soglia = totale["soglia_eccedentario"]
        ecc = totale["eccedentario_cent"]
        if ecc:
            # L'importo eccedentario in euro non si può confrontare fra scenari, che
            # hanno impianti di taglia diversa: la percentuale sul TIP sì, ed è la
            # grandezza che il vincolo determina davvero (Regole Operative pag. 42).
            quota = Decimal(ecc) / totale["tip_cent"] * 100
            stato = f"scatta: {in_euro(ecc)}, il {quota:.1f}% del TIP"
        else:
            stato = "non scatta"
        righe.append(
            f"| `{scenario.nome}` | {totale['immissioni_tot_kwh']:.0f} kWh | "
            f"{totale['ec_tot_kwh']:.0f} kWh | {rapporto * 100:.1f}% | "
            f"{soglia * 100:.1f}% | {stato} |"
        )
    righe.append("")
    for scenario, _totale, _esito in risultati:
        righe.append(f"- `{scenario.nome}` — {scenario.titolo}")
    righe += [
        "",
        "L'importo eccedentario va ai soli consumatori diversi dalle imprese "
        "(Regole Operative pag. 41).",
        "",
        "Rendiconti completi: "
        + " · ".join(f"`data/rendiconto-{s.nome}.md`" for s, _, _ in risultati)
        + f". Qui sotto, per esteso, solo quello di `{per_esteso.nome}`.",
    ]
    return "\n".join(righe)


def main() -> None:
    # Il rendiconto stampa quattro caratteri fuori dall'ASCII: "·" (U+00B7), "è",
    # "—" (U+2014) e "€" (U+20AC). Su una console Windows con code page 850 o 437 —
    # cioè le console vere, non cp1252, che regge tutti e quattro — l'em dash e il
    # simbolo dell'euro non sono codificabili, e la demo morirebbe con
    # UnicodeEncodeError invece di stampare. Stesso esito con una codifica ASCII, che
    # è ciò che Python sceglie quando la locale non dice niente di meglio.
    # I file su disco restano UTF-8 e completi: qui si degrada solo il video.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    dati = Path.cwd() / "data"
    per_esteso = mock.CONCENTRATA  # quello con i numeri più grandi: vedi il docstring
    risultati: list[tuple[Scenario, dict, dict]] = []
    rendiconti: dict[str, str] = {}
    # `SCENARI` è già in ordine di rapporto EC/EI crescente (mock.py): la tabella di
    # confronto si legge come una scala, da "non scatta" a "si porta via il 42,6%".
    for scenario in mock.SCENARI.values():
        totale, esito = elabora(scenario, dati / scenario.nome)
        intestazione = f"{PERIODO} — {scenario.titolo}"
        membri = scenario.membri()
        testo = rendiconto_markdown(intestazione, totale, esito, membri)
        (dati / f"rendiconto-{scenario.nome}.md").write_text(testo, encoding="utf-8")
        # L'export CSV passa dagli stessi quattro scenari, e non solo dai test: una
        # funzione che nessun percorso reale attraversa è una funzione di cui non si sa
        # se è cablata bene. `newline=""` perché il testo porta già i suoi fine riga.
        # Il periodo è quello breve e non l'intestazione del Markdown: nel CSV si ripete
        # su ogni riga, e il titolo dello scenario più lungo è di 84 caratteri.
        (dati / f"rendiconto-{scenario.nome}.csv").write_text(
            rendiconto_csv(PERIODO, totale, esito, membri), encoding="utf-8", newline=""
        )
        risultati.append((scenario, totale, esito))
        rendiconti[scenario.nome] = testo

    # Un solo rendiconto a video, e i quattro file su disco: vedi il docstring del modulo.
    # Un nome solo per lo scenario da stampare per esteso: cablarlo in due punti
    # significa che prima o poi la frase di chiusura annuncia uno scenario e la demo ne
    # stampa un altro, e che togliere quello scenario da SCENARI da' un KeyError.
    print(confronto(risultati, per_esteso))
    print()
    print(rendiconti[per_esteso.nome])


if __name__ == "__main__":
    main()
