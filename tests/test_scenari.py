"""Scenari mock e coerenza del rendiconto (roadmap 5 e 12).

Due gruppi di casi:

- gli SCENARI mock: formato dei file, determinismo, e il fatto che i due scenari stiano
  ai lati opposti della soglia del vincolo eccedentario, così che la demo eserciti anche
  il ramo eccedentario del motore invece di lasciarlo a zero per sempre;
- gli ARROTONDAMENTI del rendiconto: l'intestazione e la tabella devono chiudere sullo
  stesso numero anche quando i due modi di portare gli euro in centesimi divergono.

Come negli altri file, ogni caso non banale è risolto a mano nel commento.
Fonti delle formule in docs/FORMULE.md.
"""
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

import pytest

from cer_motore import mock, regole
from cer_motore.__main__ import REGOLE as REGOLE_DEMO
from cer_motore.__main__ import STATUTO_TOML, elabora
from cer_motore.condivisione import energia_condivisa
from cer_motore.rendiconto import rendiconto_markdown
from cer_motore.ripartizione import (
    InsiemeIncentivato,
    in_centesimi,
    ripartisci,
    scomponi_eccedentario_insiemi,
)
from cer_motore.tariffe import SOGLIA_ECCEDENTARIO_SOLA_TARIFFA

ORE_GIUGNO = 720  # 30 giorni * 24 ore, il mese generato per default


def _totali(scenario: mock.Scenario, cartella: Path) -> tuple[D, D, D]:
    """(energia immessa, energia condivisa, rapporto EC/EI) dello scenario."""
    f_mis, f_pz = mock.genera(cartella, scenario=scenario)
    immissioni, prelievi, _prezzi = mock.carica(f_mis, f_pz)
    ec = sum(energia_condivisa(immissioni, prelievi), D(0))
    immesse = sum((sum(s, D(0)) for s in immissioni.values()), D(0))
    return immesse, ec, ec / immesse


# --- formato e determinismo del mock ----------------------------------------------


def test_il_formato_dei_file_non_dipende_dallo_scenario(tmp_path):
    # docs/MOCK-GSE.md fissa il formato: separatore ";", intestazioni note, una riga per
    # (timestamp, POD), kWh a 3 decimali. Uno scenario nuovo può cambiare quanti POD ci
    # sono, non come sono scritti: un adapter futuro deve poter leggere entrambi.
    for scenario in (mock.EQUILIBRATA, mock.CONCENTRATA):
        f_mis, f_pz = mock.genera(tmp_path / scenario.nome, scenario=scenario)
        righe_mis = f_mis.read_text(encoding="utf-8").splitlines()
        righe_pz = f_pz.read_text(encoding="utf-8").splitlines()
        assert righe_mis[0] == "data_ora;pod;tipo;energia_kwh"
        assert righe_pz[0] == "data_ora;zona;prezzo_eur_mwh"

        # Righe attese: intestazione + un'ora per ogni POD, di produzione o di prelievo.
        #   equilibrata: 1 + 720 * (2 impianti + 8 utenze) = 7201
        #   concentrata: 1 + 720 * (1 impianto  + 5 utenze) = 4321
        n_pod = len(scenario.impianti) + len(scenario.utenze)
        assert len(righe_mis) == 1 + ORE_GIUGNO * n_pod
        assert len(righe_pz) == 1 + ORE_GIUGNO

        campi = righe_mis[1].split(";")
        assert campi[2] in ("IMMISSIONE", "PRELIEVO")
        assert len(campi[3].split(".")[1]) == 3  # kWh a 3 decimali
        assert righe_pz[1].split(";")[1] == scenario.zona_mercato


def test_la_generazione_e_deterministica(tmp_path):
    # Seed fisso per scenario: due generazioni successive devono dare file identici byte
    # per byte, altrimenti confrontare l'output della demo prima e dopo un refactor —
    # che è il test di non-regressione gratuito raccomandato in CLAUDE.md — non funziona.
    for scenario in (mock.EQUILIBRATA, mock.CONCENTRATA):
        a = mock.genera(tmp_path / f"a-{scenario.nome}", scenario=scenario)
        b = mock.genera(tmp_path / f"b-{scenario.nome}", scenario=scenario)
        for fa, fb in zip(a, b):
            assert fa.read_bytes() == fb.read_bytes()


def test_lo_scenario_equilibrata_non_e_cambiato(tmp_path):
    # Valori di riferimento dello scenario storico, quello descritto nel README: se
    # cambiano, cambia anche l'output della demo e il confronto prima/dopo va rifatto.
    immesse, ec, rapporto = _totali(mock.EQUILIBRATA, tmp_path)
    assert immesse == D("11856.752")
    assert ec == D("3222.269")
    assert rapporto < SOGLIA_ECCEDENTARIO_SOLA_TARIFFA  # 0,2718 contro 0,55


def test_i_due_scenari_stanno_ai_lati_opposti_della_soglia(tmp_path):
    # Il punto di tutto l'esercizio (roadmap 5). Il rapporto EC/EI è il solo parametro
    # che decide se il vincolo dell'importo eccedentario scatta (docs/FORMULE.md §4), e
    # dipende dalla composizione fisica della configurazione:
    #
    #   equilibrata: 80 kW di FV per 8 utenze piccole → si immette molto più di quanto
    #                si riesca a consumare nell'ora, EC/EI = 3222,269 / 11856,752 = 27,2%
    #   concentrata: 30 kW di FV per un'officina, un supermercato e una palestra → il
    #                prelievo eccede quasi sempre l'immissione, quindi EC_h = min(...)
    #                coincide quasi sempre con l'immissione stessa,
    #                EC/EI = 4367,190 / 4473,698 = 97,6%
    #
    # 97,6% non è un consumo assurdo, è un impianto sottodimensionato: 4474 kWh immessi
    # a fronte di 11229 kWh prelevati nel mese. È esattamente la configurazione che il
    # vincolo eccedentario intende intercettare.
    _, _, eq = _totali(mock.EQUILIBRATA, tmp_path / "eq")
    immesse, ec, co = _totali(mock.CONCENTRATA, tmp_path / "co")
    assert eq < SOGLIA_ECCEDENTARIO_SOLA_TARIFFA < co
    assert (immesse, ec) == (D("4473.698"), D("4367.190"))
    assert round(co, 4) == D("0.9762")


def test_lo_scenario_concentrata_ha_un_prosumer_e_consumatori_non_imprese():
    # Due proprietà strutturali di cui il resto del riparto ha bisogno:
    #  - l'impianto sta sul tetto dell'officina, che è anche la maggiore utenza: il suo
    #    proprietario è un "prosumer", ruolo che lo scenario equilibrata non esercita;
    #  - l'importo eccedentario spetta ai soli consumatori diversi dalle imprese (Regole
    #    Operative pag. 41): se fossero tutte imprese finirebbe nel fondo finalità
    #    sociali e la colonna del rendiconto resterebbe a zero anche sopra soglia.
    membri = mock.CONCENTRATA.membri()
    assert membri["M01-officina"]["ruolo"] == "prosumer"
    idonei = [m for m, d in membri.items()
              if d["ruolo"] in ("consumatore", "prosumer") and not d["impresa"]]
    assert idonei == ["M03-palestra", "M04", "M05"]


def test_uno_scenario_incoerente_e_rifiutato_alla_costruzione():
    with pytest.raises(ValueError, match="profilo"):
        mock.Scenario(
            nome="x", titolo="x", zona_mercato="NORD", zona_tariffa="nord",
            impianti=(mock.Impianto("P1", "M1", D(10)),),
            utenze=(mock.Utenza("C1", "M2", "acciaieria"),),  # profilo inesistente
        )
    with pytest.raises(ValueError, match="POD duplicati"):
        mock.Scenario(
            nome="x", titolo="x", zona_mercato="NORD", zona_tariffa="nord",
            impianti=(mock.Impianto("P1", "M1", D(10)),),
            utenze=(mock.Utenza("P1", "M2", "residenziale"),),
        )


# --- il vincolo eccedentario percorso davvero end-to-end ---------------------------


def test_end_to_end_lo_scenario_concentrata_fa_scattare_leccedentario(tmp_path):
    # Caso a mano sui totali di periodo dello scenario "concentrata", verificando la
    # formula delle Regole Operative pag. 42:
    #
    #   % E_ACI,ecc = max[0; (E_ACI / E_immessa * 100)% − valore soglia]
    #   C_ACI,ecc   = % E_ACI,ecc * C_ACI
    #
    # Numeri del periodo (giugno 2026, seed 42):
    #   E_ACI      = 4367,190 kWh      E_immessa = 4473,698 kWh
    #   rapporto   = 4367,190 / 4473,698 = 0,9761924027951819724979200652
    #   soglia     = 0,55 (sola tariffa premio, nessun contributo in conto capitale)
    #   scarto     = 0,9761924027… − 0,55 = 0,4261924027951819724979200652
    #   C_ACI      = 567,16266428 € → 56716 centesimi (ROUND_HALF_UP)
    #   C_ACI,ecc  = 56716 * 0,4261924027… = 24171,928… → 24172 centesimi = 241,72 €
    #   base TIP   = 56716 − 24172 = 32544 centesimi
    #
    # La valorizzazione ARERA non è tariffa premio e non concorre al vincolo
    # (docs/FORMULE.md §3): 35,89830180 € → 3590 centesimi, tutti in quota base.
    totale, esito = elabora(mock.CONCENTRATA, tmp_path)
    assert in_centesimi(totale["tip"]) == 56716
    assert in_centesimi(totale["arera"]) == 3590
    assert totale["eccedentario_cent"] == 24172

    # L'eccedentario va SOLO ai consumatori diversi dalle imprese, e per intero:
    #   palestra comunale 200,23 € + due famiglie 20,67 € e 20,82 € = 241,72 €
    # L'officina (impresa, prosumer) e il supermercato (impresa) non ne prendono nulla.
    quote_ecc = {m: v["quota_eccedentaria"] for m, v in esito.items()
                 if m != "_fondi" and v.get("quota_eccedentaria")}
    assert quote_ecc == {"M03-palestra": 20023, "M04": 2067, "M05": 2082}
    assert sum(quote_ecc.values()) == 24172

    # Invariante sacro: tutto ciò che si distribuisce è esattamente TIP + ARERA in
    # centesimi, 56716 + 3590 = 60306, fondi statutari inclusi.
    assert sum(v for voci in esito.values() for v in voci.values()) == 60306


def test_la_demo_produce_entrambi_i_rendiconti(tmp_path, monkeypatch, capsys):
    # La demo è il gate dichiarato della v0.1 ("un estraneo ottiene un risultato utile in
    # meno di 15 minuti"): deve girare, scrivere i due rendiconti e mostrare a video il
    # confronto più il rendiconto dello scenario in cui il vincolo scatta.
    monkeypatch.chdir(tmp_path)
    from cer_motore.__main__ import main

    main()
    dati = tmp_path / "data"
    equilibrata = (dati / "rendiconto-equilibrata.md").read_text(encoding="utf-8")
    concentrata = (dati / "rendiconto-concentrata.md").read_text(encoding="utf-8")
    assert "vincolo eccedentario **non attivo**" in equilibrata
    assert "vincolo eccedentario **attivo**" in concentrata
    assert "200.23 €" in concentrata  # la quota eccedentaria della palestra
    # Tutto l'output della demo sta sotto ./data/, che è già ignorata da git: lanciarla
    # non deve lasciare file generati in mezzo ai sorgenti.
    assert (dati / "concentrata" / "misure.csv").exists()
    assert list(tmp_path.iterdir()) == [dati]

    stampato = capsys.readouterr().out
    assert "non scatta" in stampato and "scatta: 241.72 €" in stampato


# --- coerenza degli arrotondamenti nel rendiconto (roadmap 12) ---------------------


REGOLE_META = {
    "quota_produttori": D("0.50"),
    "quota_consumatori": D("0.50"),
    "criterio_produttori": "energia_immessa",
    "criterio_consumatori": "prelievo_coincidente",
}
MEMBRI_MINIMI = {
    "P": {"ruolo": "produttore", "impresa": False},
    "C": {"ruolo": "consumatore", "impresa": False},
}


def _esito_da(totale_cent: int) -> dict[str, dict]:
    return ripartisci(REGOLE_META, totale_cent, 0, {"P": D(10)}, {"C": D(10)}, MEMBRI_MINIMI)


def test_intestazione_e_tabella_chiudono_sullo_stesso_numero(tmp_path):
    # IL CASO CHE SUI DATI MOCK NON SI VEDE (roadmap 12). Due componenti che cadono
    # entrambe su mezzo centesimo:
    #
    #   TIP = 1,005 €   ARERA = 2,005 €
    #
    #   (a) arrotondando le COMPONENTI, ROUND_HALF_UP, come fa in_centesimi:
    #         1,005 * 100 = 100,5 → 101 centesimi
    #         2,005 * 100 = 200,5 → 201 centesimi
    #         totale = 101 + 201 = 302 centesimi = 3,02 €
    #   (b) arrotondando la SOMMA:
    #         1,005 + 2,005 = 3,010 → 301,0 → 301 centesimi = 3,01 €
    #
    # I due modi differiscono di UN centesimo. Quello giusto è (a): è la ripartizione a
    # muovere il denaro, e riceve 302 centesimi — la scomposizione dell'eccedentario e i
    # riparti lavorano su interi, l'invariante somma(quote) == totale li distribuisce
    # tutti. Un'intestazione costruita su (b) annuncerebbe 3,01 € sopra una tabella che
    # somma 3,02 €.
    #
    # Riparto: nessun fondo, 50/50 fra i due blocchi, un membro per blocco.
    #   302 * 0,5 = 151 esatti a testa → P 1,51 € e C 1,51 €, somma 3,02 €.
    tip, arera = D("1.005"), D("2.005")
    assert in_centesimi(tip) + in_centesimi(arera) == 302
    assert in_centesimi(tip + arera) == 301

    esito = _esito_da(302)
    assert esito["P"]["quota_produttore"] == 151
    assert esito["C"]["quota_consumatore"] == 151

    testo = rendiconto_markdown(
        "test", {"tip": tip, "arera": arera, "totale": tip + arera, "ec_tot_kwh": D(0)},
        esito, MEMBRI_MINIMI,
    )
    intestazione = [r for r in testo.splitlines() if r.startswith("Energia condivisa")][0]
    assert "TIP: **1.01 €**" in intestazione
    assert "valorizzazione ARERA: **2.01 €**" in intestazione
    assert "totale: **3.02 €**" in intestazione

    # Le tre cifre dell'intestazione sono coerenti anche fra loro: 1,01 + 2,01 = 3,02.
    # La versione fino al 7 ago 2026 formattava i Decimal in euro, e il formato Decimal
    # arrotonda ROUND_HALF_EVEN (diverso da in_centesimi): stampava "1.00", "2.00" e
    # "3.01", tre numeri che non tornano né fra loro né con la tabella.
    assert (f"{tip:.2f}", f"{arera:.2f}", f"{tip + arera:.2f}") == ("1.00", "2.00", "3.01")

    # E la somma della colonna "Totale" della tabella fa davvero 3,02 €.
    totali_riga = [r.rsplit("|", 2)[1].strip() for r in testo.splitlines()
                   if r.startswith("| P |") or r.startswith("| C |")]
    assert totali_riga == ["1.51 €", "1.51 €"]


def test_il_rendiconto_rifiuta_un_esito_che_non_chiude(tmp_path):
    # Guardia del contratto: se il chiamante arrotonda nel punto sbagliato — cioè
    # ripartisce in_centesimi(tip + arera) = 301 mentre l'intestazione vale
    # in_centesimi(tip) + in_centesimi(arera) = 302 — il rendiconto non stampa un
    # documento che non torna, si ferma.
    esito = _esito_da(301)
    assert sum(v for voci in esito.values() for v in voci.values()) == 301
    with pytest.raises(ValueError, match="rendiconto incoerente"):
        rendiconto_markdown(
            "test",
            {"tip": D("1.005"), "arera": D("2.005"), "ec_tot_kwh": D(0)},
            esito, MEMBRI_MINIMI,
        )


def test_la_riga_del_rapporto_e_omessa_se_mancano_i_dati():
    # `immissioni_tot_kwh` e `soglia_eccedentario` sono facoltativi: un chiamante che non
    # li passa ottiene il rendiconto senza la riga sul vincolo, non un KeyError.
    testo = rendiconto_markdown(
        "test", {"tip": D("1.00"), "arera": D("0.00"), "ec_tot_kwh": D(0)},
        _esito_da(100), MEMBRI_MINIMI,
    )
    assert "rapporto EC/EI" not in testo
    assert "totale: **1.00 €**" in testo


# --- il flusso a due insiemi non deve far esplodere il rendiconto ------------------
#
# Regressione trovata in verifica avversariale l'8/8/2026: la guardia di coerenza del
# rendiconto riderivava i centesimi dai Decimal, e quindi dava per scontato che il TIP
# fosse stato arrotondato UNA volta sola. Nel flusso del vincolo eccedentario sui due
# insiemi (Regole Operative pag. 42) non è vero: ogni insieme porta il proprio
# contributo già in centesimi interi.


def test_rendiconto_accetta_i_centesimi_gia_decisi_dal_chiamante():
    # Due insiemi, ciascuno con 1,005 € di tariffa premio, entrambi sotto soglia
    # (rapporto 0,50 contro soglia 0,55 e 0,45 → nessun eccedentario qui, il punto è
    # solo l'arrotondamento):
    #   in_centesimi(1,005) = arrotonda(100,5) = 101 cent per insieme, ROUND_HALF_UP
    #   somma dei contributi per insieme  = 101 + 101 = 202 cent
    #   in_centesimi(1,005 + 1,005) = in_centesimi(2,010) = 201 cent
    # I due modi differiscono di un centesimo, e quello giusto è 202: è la cifra che
    # la ripartizione distribuisce davvero, perché la scomposizione per insieme lavora
    # su interi. Prima di questa correzione il rendiconto pretendeva 201 e sollevava
    # ValueError su dati perfettamente legittimi.
    per_insieme = in_centesimi(D("1.005")) + in_centesimi(D("1.005"))
    assert per_insieme == 202
    assert in_centesimi(D("1.005") + D("1.005")) == 201  # la strada sbagliata

    insiemi = [
        InsiemeIncentivato.sola_tariffa(D(50), D(100), in_centesimi(D("1.005"))),
        InsiemeIncentivato.cumulo_conto_capitale(
            D(45), D(100), in_centesimi(D("1.005"))
        ),
    ]
    base, ecc = scomponi_eccedentario_insiemi(insiemi)
    assert (base, ecc) == (202, 0)

    testo = rendiconto_markdown(
        "test",
        {"tip": D("1.005") + D("1.005"), "arera": D(0), "ec_tot_kwh": D(95),
         "tip_cent": base + ecc, "arera_cent": 0},
        _esito_da(base + ecc), MEMBRI_MINIMI,
    )
    assert "totale: **2.02 €**" in testo

    # Senza le chiavi autorevoli il rendiconto ricalcola 201 dai Decimal e si rifiuta
    # di stampare: è il comportamento che bloccava il flusso a due insiemi.
    with pytest.raises(ValueError, match="rendiconto incoerente"):
        rendiconto_markdown(
            "test",
            {"tip": D("1.005") + D("1.005"), "arera": D(0), "ec_tot_kwh": D(95)},
            _esito_da(base + ecc), MEMBRI_MINIMI,
        )


def test_scenario_con_zona_sconosciuta_fallisce_al_confine():
    # zona_tariffa indicizza CORRETTIVO_FV dentro tariffe.py: senza guardia lo scenario
    # si costruiva senza obiezioni e moriva molto più tardi con KeyError dentro il
    # motore, invece che al confine dove l'errore è comprensibile.
    base = mock.SCENARI["equilibrata"]
    with pytest.raises(ValueError, match="zona_tariffa"):
        replace(base, zona_tariffa="lunare")
    with pytest.raises(ValueError, match="zona_mercato"):
        replace(base, zona_mercato="ATLANTIDE")
    # Le zone valide restano tali: nessun falso positivo sulle tre macro-aree.
    for zona in ("sud", "centro", "nord"):
        assert replace(base, zona_tariffa=zona).zona_tariffa == zona


def test_lo_statuto_della_demo_e_il_file_di_esempio_non_divergono():
    # La demo tiene il proprio statuto come stringa TOML dentro __main__.py, mentre
    # `regole-esempio.toml` è la versione commentata, pensata per essere letta in
    # assemblea. Due copie della stessa cosa derivano: questo test le tiene allineate.
    # È anche l'unico caso che percorre `regole.leggi`, cioè l'adapter che tocca
    # davvero il disco — tutti gli altri usano `da_testo`, che è puro.
    esempio = Path(__file__).resolve().parent.parent / "regole-esempio.toml"
    assert esempio.is_file(), "regole-esempio.toml non trovato accanto al pyproject"
    assert regole.leggi(esempio) == regole.da_testo(STATUTO_TOML) == REGOLE_DEMO
    # E ciò che ne esce è denaro esatto, non float mascherati da Decimal.
    assert REGOLE_DEMO["fondi"]["gestione"] == D("0.10")
    assert REGOLE_DEMO["fondi"]["gestione"].as_tuple() == D("0.10").as_tuple()


def test_la_demo_passa_dalla_forma_aggregata_per_insiemi(tmp_path):
    # Regressione di cablaggio: fino all'8/8/2026 scomponi_eccedentario_insiemi esisteva
    # ma non era chiamata da nessun percorso reale, solo dai test. Una funzione che
    # nessun flusso attraversa è una funzione di cui non si sa se è collegata bene.
    # Qui si verifica che la demo produca lo stesso eccedentario della forma aggregata
    # calcolata a parte, sullo scenario in cui il vincolo scatta davvero.
    import inspect

    sorgente = inspect.getsource(elabora)
    assert "scomponi_eccedentario_insiemi" in sorgente
    totale, _esito = elabora(mock.CONCENTRATA, tmp_path / "concentrata")
    atteso = scomponi_eccedentario_insiemi([
        InsiemeIncentivato.sola_tariffa(
            totale["ec_tot_kwh"], totale["immissioni_tot_kwh"], totale["tip_cent"]
        )
    ])
    assert totale["eccedentario_cent"] == atteso[1] == 24172
    assert atteso[0] + atteso[1] == totale["tip_cent"]
