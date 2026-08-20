"""Scenari mock e coerenza del rendiconto (roadmap 5, 11 e 12).

Due gruppi di casi:

- gli SCENARI mock: formato dei file, determinismo, e il fatto che i tre scenari coprano
  i tre regimi del vincolo eccedentario — sotto soglia, appena sopra, molto sopra — così
  che la demo eserciti anche il ramo eccedentario del motore invece di lasciarlo a zero
  per sempre, e lo eserciti anche dove sbagliarlo costa di più;
- gli ARROTONDAMENTI del rendiconto: l'intestazione e la tabella devono chiudere sullo
  stesso numero anche quando i due modi di portare gli euro in centesimi divergono.

Come negli altri file, ogni caso non banale è risolto a mano nel commento.
Fonti delle formule in docs/FORMULE.md.
"""
import csv
import io
from dataclasses import replace
from decimal import ROUND_HALF_UP
from decimal import Decimal as D
from pathlib import Path

import pytest

from cer_motore import mock, regole
from cer_motore.__main__ import REGOLE as REGOLE_DEMO
from cer_motore.__main__ import STATUTO_TOML, elabora
from cer_motore.condivisione import energia_condivisa
from cer_motore.rendiconto import INTESTAZIONE_CSV, rendiconto_csv, rendiconto_markdown
from cer_motore.ripartizione import (
    FONDO_ECCEDENTARIO,
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
    for scenario in mock.SCENARI.values():
        f_mis, f_pz = mock.genera(tmp_path / scenario.nome, scenario=scenario)
        righe_mis = f_mis.read_text(encoding="utf-8").splitlines()
        righe_pz = f_pz.read_text(encoding="utf-8").splitlines()
        assert righe_mis[0] == "data_ora;pod;tipo;energia_kwh"
        assert righe_pz[0] == "data_ora;zona;prezzo_eur_mwh"

        # Righe attese: intestazione + un'ora per ogni POD, di produzione o di prelievo.
        #   equilibrata: 1 + 720 * (2 impianti + 8 utenze) = 7201
        #   paese:       1 + 720 * (2 impianti + 8 utenze) = 7201
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
    for scenario in mock.SCENARI.values():
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


def test_gli_scenari_estremi_stanno_ai_lati_opposti_della_soglia(tmp_path):
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
    # Fra i due sta `paese`, che presidia la fascia critica: vedi il test successivo.
    _, _, eq = _totali(mock.EQUILIBRATA, tmp_path / "eq")
    immesse, ec, co = _totali(mock.CONCENTRATA, tmp_path / "co")
    assert eq < SOGLIA_ECCEDENTARIO_SOLA_TARIFFA < co
    assert (immesse, ec) == (D("4473.698"), D("4367.190"))
    assert round(co, 4) == D("0.9762")


# Fascia critica: dove il rapporto EC/EI deve stare perché lo scenario `paese` faccia il
# lavoro per cui esiste. L'estremo inferiore è la soglia normativa stessa (55%, sola
# tariffa premio): sotto di essa il vincolo non scatta e lo scenario non prova nulla.
# L'estremo superiore, 70%, non è normativo: è il punto oltre il quale l'errore corretto
# il 7/8/2026 diventava piccolo abbastanza da poter passare inosservato in un rendiconto.
FASCIA_CRITICA = (SOGLIA_ECCEDENTARIO_SOLA_TARIFFA, D("0.70"))
MESI_2026 = range(1, 13)


def test_lo_scenario_paese_resta_nella_fascia_critica_in_ogni_mese(tmp_path):
    # LA PROPRIETÀ CHE CONTA È STRUTTURALE, NON FORTUNATA (roadmap 11). Uno scenario che
    # cade nella fascia solo a giugno col seed 42 sarebbe una fixture che si rompe alla
    # prima volta che qualcuno cambia mese: qui il rapporto è verificato su tutti e
    # dodici i mesi del 2026, che nel generatore differiscono per numero di giorni,
    # allineamento dei fine settimana (i profili sono scalati nei giorni non feriali) e
    # sequenza di numeri pseudo-casuali.
    #
    # Il margine è ampio da entrambi i lati, e non per caso: i 90 kW installati coprono
    # i consumi diurni della configurazione senza sovradimensionare, e la forma delle
    # curve — campana solare contro profili di supermercato, palestra, uffici e case —
    # non dipende dal mese in questo generatore. Misurato: min 0,5959 (maggio), max
    # 0,6063 (giugno), cioè un'escursione di un punto percentuale su dodici mesi, contro
    # i 5 punti di margine verso la soglia e i 9 verso l'estremo alto della fascia.
    rapporti = {}
    for mese in MESI_2026:
        f_mis, f_pz = mock.genera(tmp_path / f"m{mese:02d}", mese=mese, scenario=mock.PAESE)
        immissioni, prelievi, _prezzi = mock.carica(f_mis, f_pz)
        ec = sum(energia_condivisa(immissioni, prelievi), D(0))
        immesse = sum((sum(s, D(0)) for s in immissioni.values()), D(0))
        rapporti[mese] = ec / immesse

    basso, alto = FASCIA_CRITICA
    fuori = {m: round(r, 4) for m, r in rapporti.items() if not basso < r < alto}
    assert not fuori, f"rapporto EC/EI fuori dalla fascia critica nei mesi: {fuori}"
    assert round(min(rapporti.values()), 4) == D("0.5959")
    assert round(max(rapporti.values()), 4) == D("0.6063")
    # E giugno, il mese della demo, è il massimo: i valori inchiodati dal caso a mano
    # qui sotto sono quindi anche il caso peggiore dei dodici.
    assert rapporti[6] == max(rapporti.values())


def test_lo_scenario_paese_ha_un_prosumer_che_non_e_unimpresa():
    # Combinazione che né `equilibrata` né `concentrata` esercitano: il comune possiede
    # l'impianto sulla palestra ED è utente della palestra, quindi è un prosumer, ma non
    # è un'impresa. Prende perciò sia la quota da produttore sia una fetta dell'importo
    # eccedentario, che spetta ai soli consumatori diversi dalle imprese (Regole
    # Operative pag. 41). In `concentrata` il prosumer è l'officina, cioè un'impresa, e
    # questa strada restava non percorsa.
    membri = mock.PAESE.membri()
    assert membri["M02-comune"] == {"ruolo": "prosumer", "impresa": False}
    assert membri["M01-market"] == {"ruolo": "prosumer", "impresa": True}
    idonei = [m for m, d in membri.items()
              if d["ruolo"] in ("consumatore", "prosumer") and not d["impresa"]]
    # `sorted`: quali soci sono idonei e' la proprieta' che conta; l'ordine viene
    # dall'inserimento nelle tuple dello scenario e riordinarle non cambia nulla di
    # cio' che questo caso verifica.
    assert sorted(idonei) == ["M02-comune", "M06", "M07", "M08"]


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
    assert sorted(idonei) == ["M03-palestra", "M04", "M05"]


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


def test_end_to_end_lo_scenario_paese_fa_scattare_un_eccedentario_che_morde_poco(tmp_path):
    # IL CASO A MANO NELLA FASCIA CRITICA (roadmap 11), dalla misura oraria al centesimo
    # ripartito. Stessa formula del caso "concentrata" qui sopra, Regole Operative
    # pag. 42, ma a un rapporto vicino alla soglia:
    #
    #   % E_ACI,ecc = max[0; (E_ACI / E_immessa * 100)% − valore soglia]
    #   C_ACI,ecc   = % E_ACI,ecc * C_ACI
    #
    # Numeri del periodo (giugno 2026, seed 42):
    #   E_ACI      = 8086,838 kWh      E_immessa = 13338,844 kWh
    #   rapporto   = 8086,838 / 13338,844 = 0,6062622817989325011972551744
    #   soglia     = 0,55 (sola tariffa premio, nessun contributo in conto capitale)
    #   scarto     = 0,6062622817989… − 0,55 = 0,0562622817989325011972551744
    #   C_ACI      = 1050,18166322 € → 105018 centesimi (ROUND_HALF_UP)
    #   C_ACI,ecc  = 105018 * 0,0562622817989… = 5908,5523099… → 5909 cent = 59,09 €
    #   base TIP   = 105018 − 5909 = 99109 centesimi
    #
    # La valorizzazione ARERA si rifà a mano per intero da docs/FORMULE.md §3, 8,22 €
    # per MWh condiviso, e non concorre al vincolo:
    #   8,086838 MWh * 8,22 = 66,47380836 € → 6647 centesimi, tutti in quota base.
    totale, esito = elabora(mock.PAESE, tmp_path)
    assert (totale["ec_tot_kwh"], totale["immissioni_tot_kwh"]) == (D("8086.838"), D("13338.844"))
    assert in_centesimi(totale["tip"]) == 105018
    assert totale["arera"] == D("8086.838") / 1000 * D("8.22") == D("66.47380836")
    assert in_centesimi(totale["arera"]) == 6647
    assert totale["eccedentario_cent"] == 5909

    # MORDE POCO, ed è questo il punto della fixture: 5909 / 105018 = 5,63% della tariffa
    # premio, contro il 42,62% dello scenario "concentrata" (24172 / 56716). Il vincolo
    # scatta davvero — percorre lo stesso ramo di codice — ma sposta una fetta piccola,
    # che è il regime in cui un errore di formula si nota meno e fa più danni relativi.
    quota = D(totale["eccedentario_cent"]) / totale["tip_cent"] * 100
    assert round(quota, 2) == D("5.63")

    # PERCHÉ QUESTO SCENARIO ESISTE. La forma sbagliata usata fino al 7/8/2026 —
    # (rapporto − soglia)/rapporto invece della differenza in punti percentuali — è
    # esattamente la forma giusta divisa per il rapporto, quindi gonfia l'importo di un
    # fattore 1/rapporto: +2,4% a 0,976 (dove sta "concentrata"), +65% qui, +79% a 0,56.
    #   0,0562622817989… / 0,6062622817989… = 0,0928018837523392950371950074
    #   105018 * 0,09280188375233929… = 9745,7… → 9746 cent = 97,46 €
    # cioè 38,37 € in più tolti agli altri membri. Nessuno dei due scenari precedenti
    # avrebbe reso visibile uno scarto del genere in un rendiconto.
    rapporto = totale["ec_tot_kwh"] / totale["immissioni_tot_kwh"]
    vecchia_formula = (rapporto - SOGLIA_ECCEDENTARIO_SOLA_TARIFFA) / rapporto
    gonfiato = int((D(totale["tip_cent"]) * vecchia_formula).quantize(D(1), ROUND_HALF_UP))
    assert gonfiato == 9746
    # 9746 / 5909 = 1,6493, cioè 1/0,60626 a meno degli arrotondamenti al centesimo.
    assert round(D(gonfiato) / totale["eccedentario_cent"], 3) == D("1.649")
    assert gonfiato - totale["eccedentario_cent"] == 3837  # 38,37 € di troppo

    # L'eccedentario va ai soli consumatori diversi dalle imprese, e per intero. Qui sono
    # il comune (prosumer NON impresa: palestra) e le tre famiglie; supermercato, bar e i
    # due uffici non ne prendono nulla. Il riparto è pro-quota del prelievo coincidente,
    # e la palestra consuma di giorno molto più di tre case:
    #   comune 45,10 € + 4,69 € + 4,67 € + 4,63 € = 59,09 €
    quote_ecc = {m: v["quota_eccedentaria"] for m, v in esito.items()
                 if m != "_fondi" and v.get("quota_eccedentaria")}
    assert quote_ecc == {"M02-comune": 4510, "M06": 469, "M07": 467, "M08": 463}
    assert sum(quote_ecc.values()) == 5909

    # Invariante sacro: si distribuisce esattamente TIP + ARERA in centesimi,
    # 105018 + 6647 = 111665, fondi statutari inclusi.
    assert sum(v for voci in esito.values() for v in voci.values()) == 111665


def test_la_demo_produce_tutti_i_rendiconti(tmp_path, monkeypatch, capsys):
    # La demo è il gate dichiarato della v0.1 ("un estraneo ottiene un risultato utile in
    # meno di 15 minuti"): deve girare, scrivere i TRE rendiconti e mostrare a video il
    # confronto più UN SOLO rendiconto per esteso — tre sarebbero un muro di testo.
    monkeypatch.chdir(tmp_path)
    from cer_motore.__main__ import main

    main()
    dati = tmp_path / "data"
    scritti = {n: (dati / f"rendiconto-{n}.md").read_text(encoding="utf-8")
               for n in mock.SCENARI}
    assert "vincolo eccedentario **non attivo**" in scritti["equilibrata"]
    assert "vincolo eccedentario **attivo**" in scritti["paese"]
    assert "vincolo eccedentario **attivo**" in scritti["concentrata"]
    assert "200.23 €" in scritti["concentrata"]  # la quota eccedentaria della palestra
    assert "45.10 €" in scritti["paese"]         # quella del comune, nella fascia critica
    # E i TRE export CSV accanto ai tre Markdown (roadmap 14): la demo è l'unico
    # percorso reale che li attraversa, e una funzione che nessun flusso percorre è una
    # funzione di cui non si sa se è cablata bene.
    esportati = {n: (dati / f"rendiconto-{n}.csv").read_text(encoding="utf-8")
                 for n in mock.SCENARI}
    for nome, csv_testo in esportati.items():
        assert csv_testo.startswith(";".join(INTESTAZIONE_CSV) + "\n"), nome
        # Fine riga LF anche su Windows: il testo li porta già e la demo scrive con
        # newline="". Senza, `write_text` tradurrebbe e uscirebbe \r\r\n.
        assert "\r" not in csv_testo, nome
    assert ";M03-palestra;membro;consumatore;no;0.00;30.50;200.23;" in esportati["concentrata"]
    # Tutto l'output della demo sta sotto ./data/, che è già ignorata da git: lanciarla
    # non deve lasciare file generati in mezzo ai sorgenti.
    assert (dati / "concentrata" / "misure.csv").exists()
    assert (dati / "paese" / "misure.csv").exists()
    assert list(tmp_path.iterdir()) == [dati]

    # A video: la tabella con tutti e tre i regimi, e solo il rendiconto di concentrata.
    stampato = capsys.readouterr().out
    assert "non scatta" in stampato
    assert "scatta: 59.09 €, il 5.6% del TIP" in stampato
    assert "scatta: 241.72 €, il 42.6% del TIP" in stampato
    assert stampato.count("| Membro | Ruolo |") == 1
    assert scritti["concentrata"] in stampato and scritti["paese"] not in stampato

    # La tabella deve STARE in una console: il titolo per esteso di uno scenario è di
    # 84 caratteri e da solo portava la riga a 200, cioè a capo su qualunque terminale.
    # I titoli sono ora in un elenco sotto, dove avvolgersi non fa danno.
    righe_tabella = [r for r in stampato.splitlines() if r.startswith("| `")]
    assert len(righe_tabella) == 3
    assert max(len(r) for r in righe_tabella) <= 100
    for nome in ("equilibrata", "paese", "concentrata"):
        assert f"- `{nome}` — " in stampato


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


# --- rendiconto in CSV (roadmap 14) ------------------------------------------------
#
# L'export per chi i numeri li deve rielaborare, il commercialista in testa (Risoluzione
# AE 33/2024: il trattamento fiscale del riparto è fuori dal perimetro del motore, ma i
# dati per deciderlo devono uscire da qui). I casi sono pinnati sui TRE scenari mock,
# cioè sugli stessi totali già risolti a mano sopra: il CSV non è un secondo calcolo, è
# una seconda scrittura dello stesso, e deve dire gli stessi centesimi del Markdown.


def _righe_csv(testo: str) -> list[dict[str, str]]:
    """Righe del rendiconto CSV come dizionari, senza passare dal disco."""
    return list(csv.DictReader(io.StringIO(testo, newline=""), delimiter=";"))


def _somma_colonna(righe: list[dict[str, str]], colonna: str) -> int:
    """Somma una colonna di importi in CENTESIMI: il confronto si fa su interi."""
    return sum(int((D(r[colonna]) * 100).quantize(D(1), ROUND_HALF_UP)) for r in righe)


def test_il_rendiconto_csv_chiude_sui_totali_dei_tre_scenari(tmp_path):
    # L'INVARIANTE SACRO, verificato sull'export invece che sull'esito: la somma della
    # colonna `totale_eur` è TIP + ARERA del periodo, fondi statutari compresi. I tre
    # totali sono quelli già risolti a mano nei casi end-to-end qui sopra:
    #
    #   equilibrata:  TIP 41827 + ARERA 2649 = 44476 cent = 444,76 €, eccedentario 0
    #   paese:        TIP 105018 + ARERA 6647 = 111665 cent, di cui 5909 eccedentari
    #   concentrata:  TIP 56716 + ARERA 3590 = 60306 cent, di cui 24172 eccedentari
    #
    # E la somma della colonna `quota_eccedentaria_eur` è l'importo eccedentario del
    # periodo: è la colonna che dice quanto denaro ha una destinazione OBBLIGATA
    # (Regole Operative pag. 41), e su cui si controlla che sia arrivato dove doveva.
    attesi = {
        "equilibrata": (41827, 2649, 0),
        "paese": (105018, 6647, 5909),
        "concentrata": (56716, 3590, 24172),
    }
    for nome, scenario in mock.SCENARI.items():
        totale, esito = elabora(scenario, tmp_path / nome)
        righe = _righe_csv(rendiconto_csv("giugno 2026", totale, esito, scenario.membri()))
        tip_atteso, arera_atteso, ecc_atteso = attesi[nome]
        totale_atteso = tip_atteso + arera_atteso
        assert (totale["tip_cent"], totale["arera_cent"]) == (tip_atteso, arera_atteso), nome
        assert _somma_colonna(righe, "totale_eur") == totale_atteso, nome
        assert _somma_colonna(righe, "quota_eccedentaria_eur") == ecc_atteso, nome
        assert totale["eccedentario_cent"] == ecc_atteso, nome
        # Ogni riga chiude su se stessa: le quattro colonne di scomposizione sommano al
        # totale di riga, altrimenti la scomposizione per titolo non è una scomposizione.
        for r in righe:
            per_titolo = sum(D(r[c]) for c in INTESTAZIONE_CSV[5:9])
            assert per_titolo == D(r["totale_eur"]), (nome, r["voce"])


def test_il_rendiconto_csv_ha_una_riga_per_destinatario_e_niente_altro(tmp_path):
    # Rettangolare dalla prima riga all'ultima: nessuna riga di totali, nessun commento,
    # nessuna riga vuota. È la ragione per cui SOMMA(totale_eur) è il totale ripartito e
    # non il doppio, e per cui il file si può filtrare senza inciampare in una riga che
    # non è un pagamento. Sullo scenario "concentrata": 5 membri + 1 fondo statutario.
    totale, esito = elabora(mock.CONCENTRATA, tmp_path / "concentrata")
    testo = rendiconto_csv("giugno 2026", totale, esito, mock.CONCENTRATA.membri())
    righe = _righe_csv(testo)
    assert len(righe) == len(testo.splitlines()) - 1 == 6
    assert [r["voce"] for r in righe] == [
        "M01-officina", "M02-market", "M03-palestra", "M04", "M05", "gestione"
    ]
    assert [r["tipo"] for r in righe] == ["membro"] * 5 + ["fondo_statutario"]
    # I membri sono in ordine di identificativo, come nella tabella del Markdown: due
    # esecuzioni sugli stessi dati devono dare lo stesso file byte per byte.
    assert testo == rendiconto_csv("giugno 2026", totale, esito, mock.CONCENTRATA.membri())

    # Le colonne sono quelle dichiarate, in quell'ordine, e l'ordine è contratto: chi
    # importa questo file lo rifà ogni mese per vent'anni con lo stesso foglio.
    assert testo.splitlines()[0] == ";".join(INTESTAZIONE_CSV)
    assert INTESTAZIONE_CSV[:5] == ("periodo", "voce", "tipo", "ruolo", "impresa")


def test_il_csv_e_il_markdown_dicono_gli_stessi_importi(tmp_path):
    # Due scritture della stessa sostanza. Se divergono, una delle due mente, e non si
    # sa quale: qui si confrontano riga per riga sullo scenario in cui il vincolo
    # eccedentario scatta in pieno, cioè dove ci sono tre colonne diverse da zero.
    totale, esito = elabora(mock.CONCENTRATA, tmp_path / "concentrata")
    membri = mock.CONCENTRATA.membri()
    righe = _righe_csv(rendiconto_csv("giugno 2026", totale, esito, membri))
    testo_md = rendiconto_markdown("giugno 2026", totale, esito, membri)
    for r in righe:
        if r["tipo"] != "membro":
            continue
        # Riga Markdown: | membro | ruolo | qp € | qc € | qe € | totale € |
        attesa = (f"| {r['voce']} | {r['ruolo']} | {r['quota_produttore_eur']} € | "
                  f"{r['quota_consumatore_eur']} € | {r['quota_eccedentaria_eur']} € | "
                  f"{r['totale_eur']} € |")
        assert attesa in testo_md
    # Il fondo statutario compare in entrambi, in forme diverse ma con lo stesso numero.
    fondo = [r for r in righe if r["tipo"] == "fondo_statutario"][0]
    assert f"gestione: {fondo['quota_fondo_eur']} €" in testo_md
    # La colonna `impresa` è invece SOLO del CSV, e serve al commercialista: l'officina e
    # il supermercato sono imprese, la palestra comunale e le due famiglie no. È anche
    # ciò che spiega la colonna dell'eccedentario, che a loro resta a zero.
    imprese = {r["voce"]: r["impresa"] for r in righe if r["tipo"] == "membro"}
    assert imprese == {"M01-officina": "si", "M02-market": "si",
                       "M03-palestra": "no", "M04": "no", "M05": "no"}
    assert all(D(r["quota_eccedentaria_eur"]) == 0
               for r in righe if r["tipo"] == "membro" and r["impresa"] == "si")


def test_il_fondo_delleccedentario_sta_nella_colonna_delleccedentario():
    # Le Regole Operative pag. 41 danno all'importo eccedentario UNA destinazione con due
    # forme: "ai soli consumatori diversi dalle imprese e\\o utilizzato per finalità
    # sociali". Quando nella CER non ci sono consumatori idonei — qui l'unico consumatore
    # è un'impresa — il riparto lo mette nel fondo riservato `finalita_sociali`, e
    # nell'export quei centesimi restano nella colonna dell'eccedentario, non in quella
    # dei fondi statutari: chi somma `quota_eccedentaria_eur` deve trovare l'importo
    # eccedentario del periodo comunque sia stato destinato.
    #   base 9000 + eccedentario 1000 = 10000 cent; nessun fondo di statuto, 50/50 fra i
    #   blocchi, un membro per blocco → P 4500, C 4500, finalita_sociali 1000.
    membri = {"P": {"ruolo": "produttore", "impresa": True},
              "C": {"ruolo": "consumatore", "impresa": True}}
    esito = ripartisci(REGOLE_META, 9000, 1000, {"P": D(10)}, {"C": D(10)}, membri)
    assert esito["_fondi"] == {FONDO_ECCEDENTARIO: 1000}
    righe = _righe_csv(rendiconto_csv(
        "test", {"tip": D(100), "arera": D(0), "ec_tot_kwh": D(0)}, esito, membri))
    fondo = [r for r in righe if r["voce"] == FONDO_ECCEDENTARIO][0]
    assert fondo["tipo"] == "fondo_eccedentario"
    assert (fondo["quota_eccedentaria_eur"], fondo["quota_fondo_eur"]) == ("10.00", "0.00")
    assert _somma_colonna(righe, "quota_eccedentaria_eur") == 1000
    assert _somma_colonna(righe, "quota_fondo_eur") == 0
    assert _somma_colonna(righe, "totale_eur") == 10000


def test_il_rendiconto_csv_rifiuta_un_esito_che_non_chiude():
    # Stessa guardia del Markdown, e non una copia: entrambi passano da
    # `_componenti_cent`. L'export è la scrittura che qualcuno importa in un foglio senza
    # rileggerla, quindi è quella in cui un riparto che non chiude farebbe più danno.
    # Caso identico a quello del Markdown: 301 centesimi ripartiti contro i 302 che
    # in_centesimi(1,005) + in_centesimi(2,005) pretende.
    esito = _esito_da(301)
    with pytest.raises(ValueError, match="rendiconto incoerente"):
        rendiconto_csv(
            "test", {"tip": D("1.005"), "arera": D("2.005"), "ec_tot_kwh": D(0)},
            esito, MEMBRI_MINIMI,
        )


def test_gli_importi_del_csv_sono_numeri_e_non_testo():
    # `comune.in_euro` produce "1.51 €", che a video va benissimo e in una colonna
    # numerica è testo: chi la somma in un foglio ottiene zero. Il CSV usa il punto
    # decimale, due decimali fissi e nessun simbolo di valuta, come i CSV di misura del
    # mock (`data_ora;pod;tipo;energia_kwh`), che è il solo dialetto già in uso.
    righe = _righe_csv(rendiconto_csv(
        "test", {"tip": D("1.005"), "arera": D("2.005"), "ec_tot_kwh": D(0)},
        _esito_da(302), MEMBRI_MINIMI,
    ))
    assert [r["totale_eur"] for r in righe] == ["1.51", "1.51"]
    assert all("€" not in v and "," not in v for r in righe for v in r.values())
    # E i decimali ci sono anche quando sono zero: una colonna con "0" e "0.00" mescolati
    # è una colonna che qualche importatore legge come testo.
    assert [r["quota_eccedentaria_eur"] for r in righe] == ["0.00", "0.00"]
