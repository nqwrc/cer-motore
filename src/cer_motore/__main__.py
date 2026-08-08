"""Demo end-to-end su dati mock: python -m cer_motore

Elabora TRE scenari mock (docs/MOCK-GSE.md) con lo stesso statuto, per mostrare il
comportamento del vincolo dell'importo eccedentario al variare del solo dato fisico:

- `equilibrata`: rapporto energia condivisa / energia immessa 0,27, sotto la soglia del
  55%, il vincolo non scatta e la colonna "Quota eccedentaria" è a zero;
- `paese`: rapporto 0,61, appena sopra la soglia; il vincolo scatta ma prende il 5,6%
  della tariffa premio, non di più;
- `concentrata`: rapporto 0,98, il vincolo scatta in pieno e si porta via il 42,6% del
  TIP a favore dei soli consumatori diversi dalle imprese (Regole Operative pag. 41).

Cosa stampa, e perché non tutto: la TABELLA di confronto dei tre — che è dove la
progressione si legge in tre righe — e UN SOLO rendiconto per esteso, quello di
`concentrata`, dove la parte più delicata del motore si vede girare con i numeri più
grandi. Tre rendiconti a video sarebbero un muro di testo, e chi ha quindici minuti
smette di leggere prima della fine; i tre file completi restano su disco.

Tutto ciò che la demo scrive sta sotto ./data/, che è la sua cartella usa-e-getta: i CSV
in data/<scenario>/, i rendiconti completi di tutti e tre gli scenari in
data/rendiconto-<scenario>.md. Una sola cartella da cancellare, e già ignorata da git.
"""
import sys
from decimal import Decimal
from pathlib import Path

from . import mock, regole as mod_regole
from .comune import in_euro
from .condivisione import alloca_oraria, contributo_prelievo_coincidente, energia_condivisa
from .mock import Scenario
from .rendiconto import rendiconto_markdown
from .ripartizione import (
    InsiemeIncentivato,
    in_centesimi,
    ripartisci,
    scomponi_eccedentario_insiemi,
)
from .tariffe import SOGLIA_ECCEDENTARIO_SOLA_TARIFFA, incentivo_periodo

MESE = "giugno 2026"
PERIODO = f"{MESE} (dati mock)"

# Statuto identico nei tre scenari: così l'unica differenza fra i tre rendiconti viene
# dal dato fisico (chi produce, chi consuma e quando), non dalle regole di riparto.
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
    Operative pag. 42, anche se qui l'insieme è UNO SOLO: nessuno degli scenari mock
    ha impianti in cumulo con contributo in conto capitale, quindi l'insieme a soglia
    45% sarebbe vuoto. Ci passa lo stesso di proposito — una funzione che nessun
    percorso reale attraversa è una funzione di cui non si sa se è cablata bene.
    """
    f_mis, f_pz = mock.genera(cartella_dati, scenario=scenario)
    immissioni, prelievi, prezzi = mock.carica(f_mis, f_pz)

    ec = energia_condivisa(immissioni, prelievi)

    # attribuzione oraria dell'EC agli impianti pro-quota immissioni → incentivo per impianto
    potenze, fotovoltaici = scenario.potenze_kw(), scenario.fotovoltaici()
    totale = {"tip": Decimal(0), "arera": Decimal(0), "totale": Decimal(0), "ec_tot_kwh": Decimal(0)}
    for pod, ec_pod in alloca_oraria(immissioni, ec).items():
        inc = incentivo_periodo(ec_pod, prezzi, potenze[pod],
                                zona=scenario.zona_tariffa, fotovoltaico=fotovoltaici[pod])
        for k in totale:
            totale[k] += inc[k]

    # ripartizione. Le due componenti vanno portate in centesimi SEPARATAMENTE e prima di
    # ripartirle: è la stessa quantità su cui il rendiconto costruisce l'intestazione.
    imm_tot = sum(sum(s) for s in immissioni.values())
    tip_cent, arera_cent = in_centesimi(totale["tip"]), in_centesimi(totale["arera"])
    base, ecc = scomponi_eccedentario_insiemi([
        InsiemeIncentivato.sola_tariffa(totale["ec_tot_kwh"], imm_tot, tip_cent),
    ])
    base += arera_cent  # la valorizzazione ARERA non è "eccedentaria"
    totale["immissioni_tot_kwh"] = imm_tot
    totale["soglia_eccedentario"] = SOGLIA_ECCEDENTARIO_SOLA_TARIFFA
    totale["eccedentario_cent"] = ecc
    # Centesimi autorevoli per il rendiconto: li ha decisi qui la scomposizione per
    # insieme, e il rendiconto non deve riottenerli dai Decimal (vedi rendiconto.py).
    totale["tip_cent"], totale["arera_cent"] = tip_cent, arera_cent

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
        testo = rendiconto_markdown(f"{PERIODO} — {scenario.titolo}", totale, esito,
                                    scenario.membri())
        (dati / f"rendiconto-{scenario.nome}.md").write_text(testo, encoding="utf-8")
        risultati.append((scenario, totale, esito))
        rendiconti[scenario.nome] = testo

    # Un solo rendiconto a video, e i tre file su disco: vedi il docstring del modulo.
    # Un nome solo per lo scenario da stampare per esteso: cablarlo in due punti
    # significa che prima o poi la frase di chiusura annuncia uno scenario e la demo ne
    # stampa un altro, e che togliere quello scenario da SCENARI da' un KeyError.
    print(confronto(risultati, per_esteso))
    print()
    print(rendiconti[per_esteso.nome])


if __name__ == "__main__":
    main()
