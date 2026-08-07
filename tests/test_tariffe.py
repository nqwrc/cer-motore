"""Casi risolti a mano per TIP e incentivo. Fonti in docs/FORMULE.md §2-3."""
from decimal import Decimal as D

import pytest

from cer_motore.tariffe import (
    cap_tariffa,
    incentivo_periodo,
    parte_fissa,
    parte_variabile,
    tip_unitaria,
)


def test_parte_fissa_scaglioni_e_bordi():
    assert parte_fissa(D(100)) == 80
    assert parte_fissa(D(200)) == 80   # bordo: ≤200
    assert parte_fissa(D(201)) == 70
    assert parte_fissa(D(600)) == 70   # bordo: ≤600
    assert parte_fissa(D(601)) == 60


def test_parte_variabile():
    # Forma normativa max(0; 180 − Pz), Regole Operative pag. 40 e App. B §1 pag. 160.
    # NON e' troncata a 40: il limite normativo e' il CAP sulla tariffa totale.
    assert parte_variabile(D(200)) == 0         # 180-200 = -20 → max(0, -20) = 0
    assert parte_variabile(D(150)) == 30        # 180-150 = 30
    assert parte_variabile(D(100)) == 80        # 180-100 = 80, non troncato a 40
    assert parte_variabile(D(180)) == 0         # bordo esatto


def test_tip_unitaria_cap_e_correttivo():
    # Forma normativa: TIP = min[CAP; TP_base + max(0; 180 − Pz)] + FC_zonale.
    # P=100 kW, Pz=150: 80 + 30 = 110 ≤ cap 120 → 110; nord FV +10 → 120
    assert tip_unitaria(D(100), D(150), zona="nord") == 120
    # P=100 kW, Pz=100: 80 + 80 = 160 → min(120; 160) = 120; nord +10 → 130 (max nord)
    assert tip_unitaria(D(100), D(100), zona="nord") == 130
    # P=700 kW, Pz=100: 60 + 80 = 140 → min(100; 140) = 100; sud +0 → 100
    assert tip_unitaria(D(700), D(100), zona="sud") == 100
    # non fotovoltaico: nessun correttivo
    assert tip_unitaria(D(100), D(150), zona="nord", fotovoltaico=False) == 110


def test_tip_unitaria_il_cap_morde_solo_sul_totale():
    # Il caso che distingue la forma normativa dalla vecchia scorciatoia con VAR_MAX=40.
    # Pz = 0 (prezzo zonale nullo, ora di fortissima immissione): la parte variabile
    # vale 180, non 40. Il risultato coincide comunque, perche' il cap la riporta giu':
    #   P = 300 kW → TP_base 70, CAP 110. 70 + 180 = 250 → min(110; 250) = 110.
    #   Non fotovoltaico, nessun correttivo → 110 €/MWh, cioe' esattamente il cap.
    assert parte_variabile(D(0)) == 180
    assert tip_unitaria(D(300), D(0), zona="sud", fotovoltaico=False) == 110
    # Che i due modi coincidano dipende da CAP − TP_base = 40 in tutti gli scaglioni:
    # e' una coincidenza aritmetica, non una regola. Qui si verifica che valga oggi.
    assert all(cap_tariffa(p) - parte_fissa(p) == 40 for p in (D(100), D(300), D(800)))


def test_tip_unitaria_cumulo_conto_capitale():
    # Fattore F, Appendice B §3 pag. 161: TIP_conto_capitale = TIP * (1 − F), con F = 0,50
    # nel caso di contributo in conto capitale pari al 40% dell'investimento.
    #   P = 100 kW, Pz = 150, nord FV: TIP piena = min(120; 80+30) + 10 = 120 €/MWh
    #   con F = 0,50 → 120 * 0,50 = 60 €/MWh
    assert tip_unitaria(D(100), D(150), zona="nord", fattore_conto_capitale=D("0.50")) == 60
    # F = 0 e' il default e non cambia nulla.
    assert tip_unitaria(D(100), D(150), zona="nord", fattore_conto_capitale=D(0)) == 120
    # Fuori dall'intervallo 0–0,50 e' un errore, non una tariffa negativa o gonfiata.
    with pytest.raises(ValueError):
        tip_unitaria(D(100), D(150), fattore_conto_capitale=D("0.60"))


def test_tip_unitaria_oltre_il_megawatt_non_e_incentivabile():
    # DM CACER 414/2023: la tariffa premio spetta agli impianti fino a 1 MW
    # (POTENZA_MAX_INCENTIVABILE_KW). Un impianto piu' grande deve far fallire il
    # calcolo, non ricevere in silenzio la tariffa dello scaglione ">600 kW".
    assert tip_unitaria(D(1000), D(150), zona="sud", fotovoltaico=False) == 90  # 60+30
    with pytest.raises(ValueError):
        tip_unitaria(D(1001), D(150))


def test_incentivo_periodo_caso_a_mano():
    # 2 ore, 500 kWh condivisi l'una, P=100 kW, sud, non-cap:
    #   ora 1 Pz=200 → TIP 80 €/MWh → 0.5 MWh * 80 = 40 €
    #   ora 2 Pz=100 → TIP 120 €/MWh → 0.5 MWh * 120 = 60 €
    #   ARERA: 1 MWh * 8.22 = 8.22 € → totale 108.22 €
    inc = incentivo_periodo(
        [D(500), D(500)], [D(200), D(100)], D(100),
        zona="sud", valorizzazione_arera=D("8.22"),
    )
    assert inc["tip"] == D(100)
    assert inc["arera"] == D("8.22")
    assert inc["totale"] == D("108.22")
    assert inc["ec_tot_kwh"] == 1000


def test_cap_tariffa_scaglioni_e_bordi():
    # Gemello di test_parte_fissa_scaglioni_e_bordi sul cap fissa+variabile
    # (DM CACER 414/2023, All. 1 — tabella in docs/FORMULE.md §2):
    #   P ≤ 200 → 120 ; 200 < P ≤ 600 → 110 ; P > 600 → 100.
    assert cap_tariffa(D(100)) == 120
    assert cap_tariffa(D(200)) == 120   # bordo: ≤200
    assert cap_tariffa(D(201)) == 110
    assert cap_tariffa(D(600)) == 110   # bordo: ≤600
    assert cap_tariffa(D(601)) == 100


def test_parte_variabile_prezzo_zonale_negativo():
    # Pz negativo non è teorico: con molto fotovoltaico in rete il prezzo zonale orario
    # va sotto zero. Forma normativa max(0; 180 − Pz):
    #   Pz = −10 → 180 − (−10) = 190. La parte variabile non ha un tetto proprio.
    assert parte_variabile(D(-10)) == 190
    # È il cap sul totale a impedire che la tariffa "sfondi" verso l'alto:
    #   P=100 kW → min(120; 80 + 190 = 270) = 120; nord FV +10 fuori cap → 130 €/MWh,
    #   lo stesso massimo di Pz=100. Nessun prezzo zonale, per quanto negativo, va oltre.
    assert tip_unitaria(D(100), D(-10), zona="nord") == 130
    assert tip_unitaria(D(100), D(-99999), zona="nord") == 130


def test_incentivo_periodo_impianto_fermo_tutto_il_periodo():
    # Impianto fermo (guasto, manutenzione, o semplicemente periodo notturno):
    # EC = 0 in tutte e 4 le ore. La tariffa unitaria qui è 120 €/MWh (P=50 kW → 80,
    # Pz=150 → variabile 30, min(120; 110) = 110, nord FV +10 → 120), ma non conta:
    # TIP = 4 * (0 kWh * 120 €/MWh / 1000) = 0 €; ARERA = 0 MWh * 8.22 = 0 €.
    # Nessuna divisione per zero: prezzo zonale e potenza moltiplicano un'energia nulla.
    assert tip_unitaria(D(50), D(150), zona="nord") == 120  # la tariffa che non si applica
    inc = incentivo_periodo([D(0)] * 4, [D(150)] * 4, D(50), zona="nord")
    assert inc["ec_tot_kwh"] == 0
    assert inc["tip"] == 0
    assert inc["arera"] == 0
    assert inc["totale"] == 0


def test_incentivo_periodo_serie_disallineate():
    # 2 ore di EC contro 1 sola ora di prezzi zonali: incoerenza strutturale, nessun
    # conto viene tentato. Coerente con energia_condivisa e alloca_oraria.
    with pytest.raises(ValueError):
        incentivo_periodo([D(1), D(2)], [D(100)], D(50))


def test_tip_unitaria_zona_sconosciuta_fallisce():
    # Il correttivo geografico è un parametro normativo (CORRETTIVO_FV in tariffe.py):
    # una zona non prevista deve far fallire il calcolo, non applicare zitta un +0
    # che sottostimerebbe l'incentivo di 10 €/MWh. Qui "Nord" maiuscolo non è "nord".
    with pytest.raises(KeyError):
        tip_unitaria(D(100), D(150), zona="Nord")
