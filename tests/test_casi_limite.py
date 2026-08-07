"""Casi limite che attraversano piu' moduli: parco misto, giorni anomali, periodo fermo.

Ogni caso e' risolto a mano nei commenti, dalla misura oraria fino al centesimo
ripartito. Fonti delle formule in docs/FORMULE.md.
"""
from decimal import Decimal as D

import pytest

from cer_motore.condivisione import (
    alloca_oraria,
    contributo_prelievo_coincidente,
    energia_condivisa,
)
from cer_motore.ripartizione import (
    in_centesimi,
    ripartisci,
    ripartisci_centesimi,
    scomponi_eccedentario,
)
from cer_motore.tariffe import incentivo_periodo, tip_unitaria

REGOLE = {
    "fondi": {"gestione": D("0.10")},
    "quota_produttori": D("0.50"),
    "quota_consumatori": D("0.50"),
    "criterio_produttori": "energia_immessa",
    "criterio_consumatori": "prelievo_coincidente",
}


# --- parco misto fotovoltaico / non fotovoltaico ----------------------------------


def test_parco_misto_fv_e_non_fv_gli_incentivi_si_sommano():
    # Due impianti nella stessa configurazione, con parametri tariffari diversi:
    #   FV : fotovoltaico da 100 kW in Emilia-Romagna (zona "nord")
    #   H  : idroelettrico da 300 kW, stessa zona ma NON fotovoltaico
    # Il correttivo geografico si applica solo al fotovoltaico e sta FUORI dal cap
    # (docs/FORMULE.md §2): e' l'unico motivo per cui i due incentivi non si possono
    # calcolare sull'EC di configurazione, ma vanno attribuiti impianto per impianto.
    #
    # Misure, 2 ore:
    #   immissioni FV = [4, 6] kWh ; H = [4, 2] kWh  → totali orari 8 e 8
    #   prelievi   X  = [6, 10] kWh
    #   EC ora 1 = min(8, 6) = 6 (limita il prelievo)
    #   EC ora 2 = min(8, 10) = 8 (limita l'immissione)
    immissioni = {"FV": [D(4), D(6)], "H": [D(4), D(2)]}
    prelievi = {"X": [D(6), D(10)]}
    ec = energia_condivisa(immissioni, prelievi)
    assert ec == [D(6), D(8)]

    # Attribuzione pro-quota immissioni, entrambe le ore a divisione esatta:
    #   ora 1: FV = 6 * 4/8 = 3 ; H = 6 * 4/8 = 3
    #   ora 2: FV = 8 * 6/8 = 6 ; H = 8 * 2/8 = 2
    #   totali di periodo: FV = 9 kWh, H = 5 kWh, somma 14 = 6 + 8 = somma EC.
    quote = alloca_oraria(immissioni, ec)
    assert quote["FV"] == [D(3), D(6)]
    assert quote["H"] == [D(3), D(2)]
    assert sum(quote["FV"]) + sum(quote["H"]) == sum(ec)

    # Tariffe unitarie, prezzi zonali Pz = [100, 200] €/MWh. Forma normativa
    # min[CAP; TP_base + max(0; 180 − Pz)] + FC_zonale:
    #   variabile ora 1 = max(0; 180 − 100) = 80
    #   variabile ora 2 = max(0; 180 − 200) = 0
    #   FV (P=100 kW → TP_base 80, CAP 120):
    #     ora 1: min(120; 80 + 80 = 160) = 120, piu' correttivo nord +10 = 130 €/MWh
    #     ora 2: min(120; 80 +  0 =  80) =  80, piu' correttivo nord +10 =  90 €/MWh
    #   H (P=300 kW → TP_base 70, CAP 110; non fotovoltaico, nessun correttivo):
    #     ora 1: min(110; 70 + 80 = 150) = 110
    #     ora 2: min(110; 70 +  0 =  70) =  70
    # Il 130 dell'ora 1 dimostra che il correttivo sta fuori dal cap: 130 > 120.
    prezzi = [D(100), D(200)]
    assert tip_unitaria(D(100), D(100), zona="nord", fotovoltaico=True) == 130
    assert tip_unitaria(D(300), D(100), zona="nord", fotovoltaico=False) == 110

    # Incentivo FV:
    #   TIP   = 3 kWh * 130/1000 + 6 kWh * 90/1000 = 0.39 + 0.54 = 0.93 €
    #   ARERA = 9 kWh * 8.22/1000 = 0.07398 €
    #   totale = 1.00398 €
    inc_fv = incentivo_periodo(quote["FV"], prezzi, D(100), zona="nord", fotovoltaico=True)
    assert inc_fv["tip"] == D("0.93")
    assert inc_fv["arera"] == D("0.07398")
    assert inc_fv["totale"] == D("1.00398")

    # Incentivo H:
    #   TIP   = 3 kWh * 110/1000 + 2 kWh * 70/1000 = 0.33 + 0.14 = 0.47 €
    #   ARERA = 5 kWh * 8.22/1000 = 0.0411 €
    #   totale = 0.5111 €
    inc_h = incentivo_periodo(quote["H"], prezzi, D(300), zona="nord", fotovoltaico=False)
    assert inc_h["tip"] == D("0.47")
    assert inc_h["arera"] == D("0.0411")
    assert inc_h["totale"] == D("0.5111")

    # Somma di configurazione: TIP 0.93 + 0.47 = 1.40 € ; ARERA 0.07398 + 0.0411 =
    # 0.11508 € ; totale 1.51508 €. L'energia condivisa non si duplica: 9 + 5 = 14 kWh.
    assert inc_fv["tip"] + inc_h["tip"] == D("1.40")
    assert inc_fv["arera"] + inc_h["arera"] == D("0.11508")
    assert inc_fv["totale"] + inc_h["totale"] == D("1.51508")
    assert inc_fv["ec_tot_kwh"] + inc_h["ec_tot_kwh"] == sum(ec) == 14


# --- giorni anomali: cambio dell'ora legale ---------------------------------------
#
# Il motore NON ha nozione di tempo: lavora su liste di serie orarie allineate, senza
# fusi, date o timestamp. Questi test verificano quindi l'unica cosa realmente
# verificabile, che e' anche l'unica che serve: una serie di lunghezza diversa da 24
# attraversa tutta la catena senza rompersi e i totali tornano sulle ore che ci sono
# davvero. Un giorno da 23 o 25 ore e' semplicemente una lista di 23 o 25 elementi;
# l'ora ripetuta di ottobre e' un elemento in piu', non un duplicato da deduplicare.


def _catena_giornaliera(n_ore: int) -> dict:
    """Catena completa su un giorno di `n_ore` ore, misure costanti (helper dei 2 test).

    Impianto idroelettrico H da 300 kW che immette 3 kWh ogni ora (produce anche di
    notte, quindi anche nell'ora ripetuta di fine ottobre), unico prelievo X da 1 kWh
    ogni ora, prezzo zonale costante a 180 €/MWh.
    """
    immissioni = {"H": [D(3)] * n_ore}
    prelievi = {"X": [D(1)] * n_ore}
    ec = energia_condivisa(immissioni, prelievi)
    quote = alloca_oraria(immissioni, ec)
    inc = incentivo_periodo(
        quote["H"], [D(180)] * n_ore, D(300), zona="nord", fotovoltaico=False
    )
    return {"ec": ec, "quote": quote, "inc": inc}


def test_giorno_da_23_ore_cambio_ora_legale_di_marzo():
    # Ultima domenica di marzo (29 marzo 2026): alle 02:00 le lancette vanno a 03:00,
    # quel giorno ha 23 ore e la serie oraria del distributore ha 23 elementi.
    #
    # Ogni ora: EC = min(3 immessi, 1 prelevato) = 1 kWh → EC = 1 per 23 ore = 23 kWh.
    # Unico impianto, quindi alloca_oraria gli attribuisce tutto: 1 kWh * 23 ore.
    # Tariffa: Pz = 180 → variabile max(0; 180 − 180) = 0 ; TP_base 70 (300 kW);
    #   min(110; 70 + 0) = 70 ; non fotovoltaico → nessun correttivo → 70 €/MWh.
    #   TIP = 23 * (1 kWh * 70/1000) = 23 * 0.07 = 1.61 €
    #   ARERA = 23 kWh * 8.22/1000 = 0.18906 € → totale 1.79906 €
    r = _catena_giornaliera(23)
    assert len(r["ec"]) == 23
    assert sum(r["ec"]) == 23
    assert len(r["quote"]["H"]) == 23
    assert r["inc"]["ec_tot_kwh"] == 23
    assert r["inc"]["tip"] == D("1.61")
    assert r["inc"]["arera"] == D("0.18906")
    assert r["inc"]["totale"] == D("1.79906")
    # Un giorno canonico da 24 ore varrebbe 24 * 0.07 = 1.68 €: l'ora mancante vale
    # esattamente un'ora di incentivo, 0.07 €, ne' piu' ne' meno.
    assert D("1.68") - r["inc"]["tip"] == D("0.07")


def test_giorno_da_25_ore_con_ora_ripetuta_di_ottobre():
    # Ultima domenica di ottobre (25 ottobre 2026): l'ora 02:00–03:00 si ripete, quel
    # giorno ha 25 ore e la serie ha 25 elementi, con due slot distinti per le 02:00.
    # Il secondo passaggio delle 02:00 e' energia vera, misurata e condivisa: non va
    # deduplicato. Qui l'impianto e' idroelettrico proprio perche' di notte produce.
    #
    # Ogni ora: EC = min(3, 1) = 1 kWh → 25 ore = 25 kWh (uno in piu' di un giorno
    # normale, non uno in meno).
    #   TIP = 25 * 0.07 = 1.75 € ; ARERA = 25 * 8.22/1000 = 0.2055 € ; totale 1.9555 €
    r = _catena_giornaliera(25)
    assert len(r["ec"]) == 25
    assert sum(r["ec"]) == 25
    assert r["inc"]["ec_tot_kwh"] == 25
    assert r["inc"]["tip"] == D("1.75")
    assert r["inc"]["arera"] == D("0.2055")
    assert r["inc"]["totale"] == D("1.9555")
    # Rispetto alle 24 ore canoniche (1.68 €) l'ora ripetuta aggiunge 0.07 €.
    assert r["inc"]["tip"] - D("1.68") == D("0.07")
    # I due slot delle 02:00 (indici 2 e 3) sono elementi distinti e valgono uguale.
    assert r["quote"]["H"][2] == r["quote"]["H"][3] == D(1)


def test_giorni_dst_disallineati_sollevano_errore():
    # Il rischio vero del cambio d'ora non e' il conto, e' il disallineamento: una
    # serie generata su 24 ore fisse incrociata con una misura reale da 23 o 25 ore.
    # Il motore non sa che giorno sia, ma si accorge che le liste non combaciano e si
    # ferma, invece di calcolare su un'ora sbagliata.
    with pytest.raises(ValueError):  # 23 ore di immissioni contro 24 di prelievi
        energia_condivisa({"H": [D(3)] * 23}, {"X": [D(1)] * 24})
    with pytest.raises(ValueError):  # 25 ore di immissioni contro 24 di EC
        alloca_oraria({"H": [D(3)] * 25}, [D(1)] * 24)
    with pytest.raises(ValueError):  # 25 ore di EC contro 24 prezzi zonali
        incentivo_periodo([D(1)] * 25, [D(180)] * 24, D(300))


# --- periodo interamente senza immissioni -----------------------------------------


def test_periodo_senza_immissioni_attraversa_il_motore_a_zero():
    # Impianto fermo per tutto il periodo (guasto, o distacco per manutenzione), con i
    # membri che pero' continuano a prelevare dalla rete. Quattro ore:
    #   immissioni A = [0, 0, 0, 0] ; prelievi X = [2, 2, 2, 2], Y = [1, 1, 1, 1]
    #   EC_h = min(0, 3) = 0 per ogni ora → EC = 0 kWh sul periodo.
    immissioni = {"A": [D(0)] * 4}
    prelievi = {"X": [D(2)] * 4, "Y": [D(1)] * 4}
    ec = energia_condivisa(immissioni, prelievi)
    assert ec == [D(0)] * 4

    # alloca_oraria: immissione totale nulla in ogni ora → tutte le quote a zero e
    # nessuna divisione per zero (il caso e' gestito esplicitamente in condivisione.py).
    quote = alloca_oraria(immissioni, ec)
    assert quote["A"] == [D(0)] * 4
    assert sum(quote["A"]) == 0

    # I contributi dei consumatori pesano il prelievo per l'EC dell'ora: prelievi non
    # nulli ma EC nulla → ogni contributo e' 2 * 0/3 = 0 e 1 * 0/3 = 0.
    contributi = contributo_prelievo_coincidente(prelievi, ec)
    assert contributi == {"X": D(0), "Y": D(0)}

    # Incentivo: 0 kWh * qualunque tariffa = 0 €, per TIP e per ARERA.
    inc = incentivo_periodo(quote["A"], [D(150)] * 4, D(50), zona="nord")
    assert inc["tip"] == 0 and inc["arera"] == 0 and inc["totale"] == 0

    # Vincolo eccedentario: EI = 0, rapporto EC/EI indefinito → non si calcola.
    assert in_centesimi(inc["tip"]) == 0
    assert scomponi_eccedentario(in_centesimi(inc["tip"]), inc["ec_tot_kwh"], D(0)) == (0, 0)

    # La catena arriva fino in fondo: 0 centesimi da ripartire e pesi tutti nulli danno
    # un rendiconto a zero, non un ValueError. (Fino al 7/8/2026 `ripartisci_centesimi`
    # sollevava "pesi tutti nulli" anche con totale nullo: un mese di impianto fermo
    # faceva esplodere il riparto invece di produrre un rendiconto vuoto.)
    #   fondo gestione = arrotonda(0 * 0,10) = 0 ; residuo 0 → blocchi prod/cons a 0
    #   pesi produttori {A: 0} e consumatori {X: 0, Y: 0}: tutti nulli, ma il totale da
    #   distribuire è 0, quindi ogni quota è 0 e l'invariante somma == totale regge.
    membri = {
        "A": {"ruolo": "produttore", "impresa": False},
        "X": {"ruolo": "consumatore", "impresa": False},
        "Y": {"ruolo": "consumatore", "impresa": True},
    }
    esito = ripartisci(
        REGOLE, 0, 0,
        energia_immessa_kwh={"A": D(0)},
        contributi_consumo_kwh=contributi,
        membri=membri,
    )
    assert esito["A"]["quota_produttore"] == 0
    assert esito["X"]["quota_consumatore"] == 0
    assert esito["Y"]["quota_consumatore"] == 0
    assert sum(v for d in esito.values() for v in d.values()) == 0

    # Ma un importo da distribuire su pesi tutti nulli resta un errore: non esiste un
    # criterio per ripartirlo, e inventarne uno silenziosamente sposterebbe denaro.
    with pytest.raises(ValueError):
        ripartisci_centesimi(100, {"X": D(0), "Y": D(0)})


# --- caso integrato: mini-CER con un prosumer, dalla misura al centesimo -----------


def test_integrato_mini_cer_con_prosumer():
    # Configurazione: un solo impianto FV da 50 kW in zona nord, intestato al prosumer
    # PS, che ha anche un POD di prelievo. C1 consuma e non e' impresa; C2 consuma ed
    # e' impresa (quindi esclusa dall'eccedentario). Due ore di misure.
    #
    # 1) Energia condivisa (docs/FORMULE.md §1)
    #   immissioni PS-P = [1000, 1000] kWh → totale immesso EI = 2000 kWh
    #   prelievi PS-C = [200, 400], C1 = [400, 200], C2 = [200, 200]
    #     → prelievo totale 800 kWh in entrambe le ore
    #   EC ora 1 = min(1000, 800) = 800 ; EC ora 2 = min(1000, 800) = 800 → EC = 1600 kWh
    immissioni = {"PS-P": [D(1000), D(1000)]}
    prelievi = {"PS-C": [D(200), D(400)], "C1": [D(400), D(200)], "C2": [D(200), D(200)]}
    ec = energia_condivisa(immissioni, prelievi)
    assert ec == [D(800), D(800)] and sum(ec) == 1600

    # 2) Attribuzione all'unico impianto: prende tutta l'EC, 800 + 800 = 1600 kWh.
    quote = alloca_oraria(immissioni, ec)
    assert sum(quote["PS-P"]) == 1600

    # 3) Incentivo (docs/FORMULE.md §2-3). Pz = 140 €/MWh in entrambe le ore. Forma
    #    normativa TIP_h = min[CAP; TP_base + max(0; 180 − Pz)] + FC_zonale:
    #      parte variabile = max(0; 180 − 140) = 40 ; TP_base 80 (P = 50 kW ≤ 200)
    #      min(120; 80 + 40) = 120 ; FC_zonale nord +10 fuori cap → 130 €/MWh
    #      TIP = 800 * 130/1000 + 800 * 130/1000 = 104 + 104 = 208.00 €
    #      ARERA = 1600 kWh * 8.22/1000 = 13.152 €
    inc = incentivo_periodo(quote["PS-P"], [D(140), D(140)], D(50), zona="nord", fotovoltaico=True)
    assert inc["tip"] == D(208)
    assert inc["arera"] == D("13.152")

    # 4) Vincolo eccedentario (docs/FORMULE.md §4), soglia 55% (sola tariffa premio).
    #    La quota eccedentaria e' la differenza in PUNTI PERCENTUALI, non la frazione
    #    di energia oltre soglia (Regole Operative pag. 42):
    #      rapporto EC/EI = 1600/2000 = 0,80
    #      quota eccedentaria = max(0; 0,80 − 0,55) = 0,25
    #      ecc  = arrotonda(20800 * 0,25) = 5200 cent = 52.00 €
    #      base = 20800 − 5200 = 15600 cent
    #    La valorizzazione ARERA non e' tariffa premio e non e' mai eccedentaria:
    #      arrotonda(1315,2) = 1315 cent, che si somma alla base → 15600 + 1315 = 16915.
    #    Totale da ripartire = 16915 + 5200 = 22115 cent = 221.15 €.
    base, ecc = scomponi_eccedentario(in_centesimi(inc["tip"]), inc["ec_tot_kwh"], D(2000))
    assert (base, ecc) == (15600, 5200)
    base += in_centesimi(inc["arera"])
    assert base == 16915

    # 5) Contributi di prelievo coincidente: in entrambe le ore EC = prelievo totale,
    #    quindi ciascuno si porta a casa esattamente il proprio prelievo.
    #      PS-C = 200 + 400 = 600 ; C1 = 400 + 200 = 600 ; C2 = 200 + 200 = 400
    #      somma 1600 = somma EC.
    contributi = contributo_prelievo_coincidente(prelievi, ec)
    assert contributi == {"PS-C": D(600), "C1": D(600), "C2": D(400)}

    # 6) Ripartizione statutaria.
    #    fondo gestione = arrotonda(16915 * 0,10) = arrotonda(1691,5) = 1692 cent
    #    residuo = 16915 − 1692 = 15223, da spezzare 50/50:
    #      esatte 7611,5 e 7611,5 → troncate 7611 + 7611 = 15222, residuo 1 centesimo;
    #      resti pari, chiave decrescente "prod" > "cons" → prod = 7612, cons = 7611.
    #    Blocco produttori: PS e' l'unico (ruolo prosumer) → 7612 cent = 76.12 €.
    #    Blocco consumatori, pro-quota contributi 600 : 600 : 400 (totale 1600):
    #      PS = 7611 * 600/1600 = 2854,125 → troncata 2854, resto 0,125
    #      C1 = 7611 * 600/1600 = 2854,125 → troncata 2854, resto 0,125
    #      C2 = 7611 * 400/1600 = 1902,75  → troncata 1902, resto 0,75
    #      somma troncate 7610, residuo 1 → al resto maggiore, che qui e' C2 da solo
    #      (0,75 > 0,125) → C2 = 1903 ; verifica 2854 + 2854 + 1903 = 7611.
    #    Eccedentario 5200 cent ai soli consumatori non imprese: PS e C1 (C2 e' impresa),
    #      pro-quota contributi 600 : 600 → 5200 * 600/1200 = 2600 esatti ciascuno.
    #    PS incassa 7612 + 2854 + 2600 = 13066 cent = 130.66 €.
    #    Totale: 1692 + 7612 + 2854 + 2854 + 1903 + 2600 + 2600 = 22115. Nulla si perde.
    membri = {
        "PS": {"ruolo": "prosumer", "impresa": False},
        "C1": {"ruolo": "consumatore", "impresa": False},
        "C2": {"ruolo": "consumatore", "impresa": True},
    }
    esito = ripartisci(
        REGOLE, base, ecc,
        energia_immessa_kwh={"PS": D(2000)},
        contributi_consumo_kwh={"PS": contributi["PS-C"], "C1": contributi["C1"],
                                "C2": contributi["C2"]},
        membri=membri,
    )
    assert esito["_fondi"]["gestione"] == 1692
    assert esito["PS"]["quota_produttore"] == 7612
    assert esito["PS"]["quota_consumatore"] == 2854
    assert esito["PS"]["quota_eccedentaria"] == 2600
    assert sum(esito["PS"].values()) == 13066
    assert esito["C1"]["quota_consumatore"] == 2854
    assert esito["C1"]["quota_eccedentaria"] == 2600
    assert esito["C2"]["quota_consumatore"] == 1903
    assert "quota_eccedentaria" not in esito["C2"]
    assert sum(v for d in esito.values() for v in d.values()) == 22115 == base + ecc
