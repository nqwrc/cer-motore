"""Generatore di dati mock fedeli all'export GSE (assunzioni in docs/MOCK-GSE.md).

Deterministico (seed fisso per scenario): una CER fittizia romagnola, un mese di misure
orarie. Unico modulo (con __main__) autorizzato a fare I/O.

Gli scenari sono tre, con lo STESSO formato di file e le stesse assunzioni di
docs/MOCK-GSE.md: cambia solo la composizione fisica della configurazione, cioè quanti
impianti, quanto grandi e chi consuma. Servono perché il rapporto fra energia condivisa
ed energia immessa — che governa il vincolo dell'importo eccedentario (docs/FORMULE.md
§4) — dipende proprio da quella composizione:

- `EQUILIBRATA`: CER di quartiere, 2 impianti FV e 8 utenze miste. Rapporto EC/EI ≈ 0,27,
  molto sotto la soglia del 55%: il vincolo eccedentario NON scatta.
- `PAESE`: CER di paese, produzione di poco superiore ai consumi diurni. Rapporto
  EC/EI ≈ 0,60, appena sopra la soglia: il vincolo scatta ma morde poco, il 5,6% della
  tariffa premio.
- `CONCENTRATA`: CER artigianale, un solo impianto FV piccolo e pochi grandi consumatori
  diurni. Rapporto EC/EI oltre il 90%: il vincolo eccedentario scatta in pieno, il 42,6%.

`CONCENTRATA` non è un caso di scuola: una configurazione con l'impianto sottodimensionato
rispetto ai prelievi condivide quasi tutto ciò che immette, ed è esattamente la situazione
che il vincolo dell'importo eccedentario intende intercettare.

`PAESE` presidia la FASCIA CRITICA 0,55–0,70, cioè dove sta l'errore più costoso che il
progetto abbia trovato: fino al 7 ago 2026 l'importo eccedentario era calcolato come
`(rapporto − soglia)/rapporto` invece che come differenza in punti percentuali, e quella
forma sbaglia tanto più quanto più il rapporto è vicino alla soglia (+65% al rapporto di
questo scenario, +11% a rapporto 0,90). Con i soli scenari a 0,27 e 0,98 quella fascia
non era attraversata da nessun percorso end-to-end.
"""
import csv
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from .tariffe import CORRETTIVO_FV  # zone del correttivo geografico: sud, centro, nord

SEED = 42

# Zone di mercato elettrico italiane, scritte nella colonna `zona` del file dei prezzi.
# Sono cosa diversa dalle zone del correttivo FC_zonale (CORRETTIVO_FV): quelle sono
# tre macro-aree tariffarie, queste sono le zone del mercato elettrico dopo la riforma
# del 2021. Servono qui solo a validare lo scenario prima che il motore ci inciampi.
ZONE_MERCATO = frozenset({"NORD", "CNOR", "CSUD", "SUD", "CALA", "SICI", "SARD"})

# --- Profili di consumo ------------------------------------------------------------
# kWh medi per ora del giorno (giorno feriale), 24 valori. Sono profili di forma, non
# misure: il generatore li perturba con rumore pseudo-casuale. Assunti (docs/MOCK-GSE.md),
# non presi da un campione reale.
PROFILI_CONSUMO = {
    "residenziale": [0.2, 0.15, 0.15, 0.15, 0.2, 0.3, 0.5, 0.6, 0.4, 0.3, 0.3, 0.4,
                     0.6, 0.5, 0.3, 0.3, 0.4, 0.6, 0.9, 1.1, 1.0, 0.8, 0.5, 0.3],
    "ufficio":      [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.5, 1.5, 2.5, 2.8, 2.8, 2.6,
                     2.2, 2.6, 2.8, 2.7, 2.4, 1.5, 0.7, 0.4, 0.3, 0.3, 0.3, 0.3],
    "bar":          [0.4, 0.3, 0.3, 0.3, 0.5, 1.2, 2.0, 2.5, 2.2, 1.8, 1.8, 2.4,
                     2.6, 2.0, 1.4, 1.4, 1.8, 2.2, 2.4, 2.0, 1.4, 1.0, 0.7, 0.5],
    # Officina/carpenteria: due turni con pausa pranzo, spenta la notte (~147 kWh/giorno).
    "artigianale":  [0.6, 0.6, 0.6, 0.6, 0.6, 0.8, 3.0, 9.0, 13.0, 14.0, 14.0, 13.5,
                     8.0, 12.0, 14.0, 14.0, 13.0, 9.0, 3.5, 1.0, 0.8, 0.6, 0.6, 0.6],
    # Supermercato di vicinato: banchi frigo sempre accesi più l'apertura (~178 kWh/giorno).
    "supermercato": [3.0, 2.8, 2.8, 2.8, 3.0, 3.5, 5.0, 7.0, 9.5, 10.5, 11.0, 11.5,
                     12.0, 12.0, 11.5, 11.0, 11.0, 11.5, 11.0, 9.0, 6.0, 4.0, 3.5, 3.2],
    # Palestra comunale: apertura 9-22, punta serale (~83 kWh/giorno).
    "palestra":     [0.4, 0.4, 0.4, 0.4, 0.4, 0.5, 1.0, 2.0, 3.5, 5.0, 5.5, 5.0,
                     4.0, 4.0, 4.5, 5.0, 5.5, 6.5, 7.5, 7.5, 6.5, 4.5, 2.0, 0.8],
}

# Fattore applicato al profilo nei giorni non feriali. Il valore predefinito 0,75 è
# quello storico del generatore e resta per i profili originari, così lo scenario
# EQUILIBRATA non cambia di un decimale. I profili nuovi lo dichiarano: un'officina nel
# fine settimana è chiusa (solo standby), un supermercato quasi no.
FATTORE_FESTIVO_PREDEFINITO = 0.75
FATTORE_FESTIVO = {
    "artigianale": 0.15,
    "supermercato": 0.80,
    "palestra": 0.60,
}


# --- Descrizione di uno scenario ---------------------------------------------------


@dataclass(frozen=True)
class Impianto:
    """Un impianto di produzione della configurazione mock.

    `potenza_kw` determina scaglione e cap della tariffa premio, `fotovoltaico` se spetta
    il correttivo geografico FC_zonale (docs/FORMULE.md §2). `membro` è l'id nell'anagrafica
    della CER: non fa parte dell'export GSE (che conosce i POD), ma sta qui perché deve
    restare in sincronia con la lista dei POD, e tenerlo altrove è come si sfasano.
    """

    pod: str
    membro: str
    potenza_kw: Decimal
    fotovoltaico: bool = True


@dataclass(frozen=True)
class Utenza:
    """Un punto di prelievo della configurazione mock. `profilo` è una chiave di PROFILI_CONSUMO."""

    pod: str
    membro: str
    profilo: str


@dataclass(frozen=True)
class Scenario:
    """Una configurazione CER fittizia completa, da cui `genera` produce i CSV.

    `zona_mercato` è la zona di mercato elettrico scritta nel file dei prezzi (NORD, CNOR,
    CSUD, SUD, SICI, CALA, SARD). `zona_tariffa` è l'area geografica del correttivo
    FC_zonale (sud/centro/nord, Regole Operative Appendice B §2 pag. 160). Sono due
    partizioni DIVERSE dell'Italia e il motore non deve dedurre l'una dall'altra: qui
    coincidono solo perché la CER è in Emilia-Romagna, che è "nord" in entrambe.

    `imprese` elenca gli id dei membri che sono imprese: serve al vincolo dell'importo
    eccedentario, che va ai soli consumatori diversi dalle imprese (docs/FORMULE.md §4).
    """

    nome: str
    titolo: str
    zona_mercato: str
    zona_tariffa: str
    impianti: tuple[Impianto, ...]
    utenze: tuple[Utenza, ...]
    imprese: frozenset[str] = frozenset()
    seed: int = SEED

    def __post_init__(self) -> None:
        pod = [i.pod for i in self.impianti] + [u.pod for u in self.utenze]
        if len(set(pod)) != len(pod):
            raise ValueError(f"scenario {self.nome!r}: POD duplicati")
        if not self.impianti or not self.utenze:
            raise ValueError(f"scenario {self.nome!r}: servono almeno un impianto e un'utenza")
        for i in self.impianti:
            if i.potenza_kw <= 0:
                raise ValueError(f"scenario {self.nome!r}: potenza non positiva su {i.pod}")
        for u in self.utenze:
            if u.profilo not in PROFILI_CONSUMO:
                raise ValueError(
                    f"scenario {self.nome!r}: profilo {u.profilo!r} sconosciuto su {u.pod}; "
                    f"noti: {sorted(PROFILI_CONSUMO)}"
                )
        # `zona_tariffa` indicizza CORRETTIVO_FV dentro il motore: se è sbagliata, senza
        # questa guardia lo scenario si costruisce senza un fiato e muore molto più
        # tardi con un KeyError in tariffe.py, cioè dentro il calcolo invece che al
        # confine. Stessa natura del profilo qui sopra, stesso trattamento.
        if self.zona_tariffa not in CORRETTIVO_FV:
            raise ValueError(
                f"scenario {self.nome!r}: zona_tariffa {self.zona_tariffa!r} sconosciuta; "
                f"note: {sorted(CORRETTIVO_FV)} (correttivo FC_zonale, Regole Operative "
                "Appendice B §2 pag. 160)"
            )
        if self.zona_mercato not in ZONE_MERCATO:
            raise ValueError(
                f"scenario {self.nome!r}: zona_mercato {self.zona_mercato!r} sconosciuta; "
                f"note: {sorted(ZONE_MERCATO)}"
            )
        ignoti = self.imprese - set(self.membri())
        if ignoti:
            raise ValueError(f"scenario {self.nome!r}: imprese non fra i membri: {sorted(ignoti)}")

    def potenze_kw(self) -> dict[str, Decimal]:
        """POD di produzione -> potenza in kW."""
        return {i.pod: i.potenza_kw for i in self.impianti}

    def fotovoltaici(self) -> dict[str, bool]:
        """POD di produzione -> se l'impianto è fotovoltaico (correttivo FC_zonale)."""
        return {i.pod: i.fotovoltaico for i in self.impianti}

    def membro_di(self) -> dict[str, str]:
        """POD (di produzione o di prelievo) -> id del membro che lo possiede."""
        return {**{i.pod: i.membro for i in self.impianti},
                **{u.pod: u.membro for u in self.utenze}}

    def membri(self) -> dict[str, dict]:
        """Anagrafica per `ripartizione.ripartisci`: id -> {"ruolo", "impresa"}.

        Il ruolo è dedotto: chi ha sia un impianto sia un'utenza è "prosumer".
        """
        produttori = {i.membro for i in self.impianti}
        consumatori = {u.membro for u in self.utenze}
        out: dict[str, dict] = {}
        for m in [i.membro for i in self.impianti] + [u.membro for u in self.utenze]:
            if m in out:
                continue
            if m in produttori and m in consumatori:
                ruolo = "prosumer"
            elif m in produttori:
                ruolo = "produttore"
            else:
                ruolo = "consumatore"
            out[m] = {"ruolo": ruolo, "impresa": m in self.imprese}
        return out


# --- I tre scenari -----------------------------------------------------------------

EQUILIBRATA = Scenario(
    nome="equilibrata",
    titolo="CER di quartiere: 2 impianti FV (60 e 20 kW), 8 utenze fra case, uffici e un bar",
    zona_mercato="NORD",
    zona_tariffa="nord",
    impianti=(
        Impianto("IT001E0000001A", "M01-capannone", Decimal("60")),
        Impianto("IT001E0000002B", "M02-scuola", Decimal("20")),
    ),
    utenze=(
        Utenza("IT001E0000101C", "M03", "residenziale"),
        Utenza("IT001E0000102D", "M04", "residenziale"),
        Utenza("IT001E0000103E", "M05", "residenziale"),
        Utenza("IT001E0000104F", "M06", "residenziale"),
        Utenza("IT001E0000105G", "M07", "ufficio"),
        Utenza("IT001E0000106H", "M08", "ufficio"),
        Utenza("IT001E0000107I", "M09-bar", "bar"),
        Utenza("IT001E0000108L", "M10", "residenziale"),
    ),
    imprese=frozenset({"M01-capannone", "M09-bar"}),
)

PAESE = Scenario(
    nome="paese",
    titolo="CER di paese: FV da 50 kW sul supermercato e 40 kW sulla palestra comunale, "
           "8 utenze",
    zona_mercato="NORD",
    zona_tariffa="nord",
    impianti=(
        # 90 kW su due tetti, contro ~390 kWh/giorno di consumi: la CER produce nel mese
        # poco più di quanto consuma (13.339 kWh contro 10.970), che è il dimensionamento
        # di una configurazione fatta bene. Non è una taglia scelta per centrare un
        # numero: è quella che serve a coprire i consumi diurni di un supermercato e di
        # una palestra senza sovradimensionare come fa EQUILIBRATA.
        Impianto("IT001E0000301A", "M01-market", Decimal("50")),
        Impianto("IT001E0000302B", "M02-comune", Decimal("40")),
    ),
    utenze=(
        Utenza("IT001E0000303C", "M01-market", "supermercato"),
        Utenza("IT001E0000304D", "M02-comune", "palestra"),
        Utenza("IT001E0000305E", "M03-bar", "bar"),
        Utenza("IT001E0000306F", "M04-studio", "ufficio"),
        Utenza("IT001E0000307G", "M05-agenzia", "ufficio"),
        Utenza("IT001E0000308H", "M06", "residenziale"),
        Utenza("IT001E0000309I", "M07", "residenziale"),
        Utenza("IT001E0000310L", "M08", "residenziale"),
    ),
    # Il comune possiede l'impianto sulla palestra ED è utente della palestra: è un
    # prosumer che NON è un'impresa, combinazione che nessuno degli altri due scenari
    # esercita (in CONCENTRATA il prosumer è l'officina, cioè un'impresa). Prende quindi
    # sia la quota da produttore sia una fetta dell'importo eccedentario, insieme alle
    # tre famiglie (Regole Operative pag. 41).
    imprese=frozenset({"M01-market", "M03-bar", "M04-studio", "M05-agenzia"}),
)

CONCENTRATA = Scenario(
    nome="concentrata",
    titolo="CER artigianale: un FV da 30 kW e pochi grandi consumatori diurni",
    zona_mercato="NORD",
    zona_tariffa="nord",
    impianti=(
        # L'impianto sta sul tetto dell'officina, che è anche la maggiore utenza: il suo
        # proprietario è quindi un prosumer, ruolo che lo scenario EQUILIBRATA non ha.
        Impianto("IT001E0000201M", "M01-officina", Decimal("30")),
    ),
    utenze=(
        Utenza("IT001E0000202N", "M01-officina", "artigianale"),
        Utenza("IT001E0000203O", "M02-market", "supermercato"),
        Utenza("IT001E0000204P", "M03-palestra", "palestra"),
        Utenza("IT001E0000205Q", "M04", "residenziale"),
        Utenza("IT001E0000206R", "M05", "residenziale"),
    ),
    # La palestra è comunale e le due utenze domestiche sono famiglie: sono loro i
    # destinatari dell'importo eccedentario (Regole Operative pag. 41).
    imprese=frozenset({"M01-officina", "M02-market"}),
)

# In ordine di rapporto EC/EI crescente: 0,27 · 0,60 · 0,98. La demo li elabora in
# quest'ordine, così la tabella di confronto si legge come una scala.
SCENARI = {s.nome: s for s in (EQUILIBRATA, PAESE, CONCENTRATA)}


# --- Generazione e lettura ---------------------------------------------------------


def _produzione_fv(kw: Decimal, ora: int, nuvolosita: float) -> Decimal:
    """Campana solare 6-20 con attenuazione per nuvolosità."""
    if not 6 <= ora <= 20:
        return Decimal(0)
    picco = float(kw) * 0.75  # rendimento al picco
    forma = max(0.0, 1 - ((ora - 13) / 7) ** 2)
    return Decimal(f"{picco * forma * (1 - nuvolosita):.3f}")


def genera(
    cartella: Path,
    anno: int = 2026,
    mese: int = 6,
    scenario: Scenario = EQUILIBRATA,
) -> tuple[Path, Path]:
    """Scrive misure.csv e prezzi_zonali.csv per il mese indicato. Ritorna i path.

    Il formato è quello descritto in docs/MOCK-GSE.md e non dipende dallo scenario: una
    riga per (timestamp, POD) con tipo IMMISSIONE/PRELIEVO, separatore `;`, kWh a 3
    decimali. Due scenari diversi vanno scritti in cartelle diverse.
    """
    rng = random.Random(scenario.seed)
    cartella.mkdir(parents=True, exist_ok=True)
    inizio = datetime(anno, mese, 1)
    fine = (inizio.replace(day=28) + timedelta(days=4)).replace(day=1)
    ore = int((fine - inizio).total_seconds() // 3600)

    f_mis = cartella / "misure.csv"
    f_pz = cartella / "prezzi_zonali.csv"
    with f_mis.open("w", newline="", encoding="utf-8") as m, \
         f_pz.open("w", newline="", encoding="utf-8") as p:
        wm = csv.writer(m, delimiter=";")
        wp = csv.writer(p, delimiter=";")
        wm.writerow(["data_ora", "pod", "tipo", "energia_kwh"])
        wp.writerow(["data_ora", "zona", "prezzo_eur_mwh"])
        for h in range(ore):
            ts = (inizio + timedelta(hours=h)).isoformat()
            ora = (inizio + timedelta(hours=h)).hour
            feriale = (inizio + timedelta(hours=h)).weekday() < 5
            nuvolosita = rng.betavariate(2, 5)  # per lo più sereno
            # prezzo zonale: base 110 €/MWh, picchi serali, rumore
            pz = 110 + (25 if ora in (19, 20, 21) else 0) - (30 if 11 <= ora <= 15 else 0)
            pz = max(5, pz + rng.gauss(0, 12))
            wp.writerow([ts, scenario.zona_mercato, f"{pz:.2f}"])
            for imp in scenario.impianti:
                e = _produzione_fv(imp.potenza_kw, ora, nuvolosita)
                wm.writerow([ts, imp.pod, "IMMISSIONE", f"{e:.3f}"])
            for ut in scenario.utenze:
                festivo = FATTORE_FESTIVO.get(ut.profilo, FATTORE_FESTIVO_PREDEFINITO)
                base = PROFILI_CONSUMO[ut.profilo][ora] * (1.0 if feriale else festivo)
                e = max(0.0, base * rng.uniform(0.7, 1.3))
                wm.writerow([ts, ut.pod, "PRELIEVO", f"{e:.3f}"])
    return f_mis, f_pz


def carica(f_misure: Path, f_prezzi: Path):
    """Legge i CSV mock e ritorna (immissioni, prelievi, prezzi) per il motore."""
    immissioni: dict[str, list[Decimal]] = {}
    prelievi: dict[str, list[Decimal]] = {}
    with f_misure.open(encoding="utf-8") as fh:
        for riga in csv.DictReader(fh, delimiter=";"):
            dest = immissioni if riga["tipo"] == "IMMISSIONE" else prelievi
            dest.setdefault(riga["pod"], []).append(Decimal(riga["energia_kwh"]))
    with f_prezzi.open(encoding="utf-8") as fh:
        prezzi = [Decimal(r["prezzo_eur_mwh"]) for r in csv.DictReader(fh, delimiter=";")]
    return immissioni, prelievi, prezzi
