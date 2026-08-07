"""Casi risolti a mano per la ripartizione. L'invariante al centesimo è sacro."""
from decimal import Decimal as D

import pytest

from cer_motore.ripartizione import (
    InsiemeIncentivato,
    ripartisci,
    ripartisci_centesimi,
    scomponi_eccedentario,
    scomponi_eccedentario_insiemi,
)
from cer_motore.tariffe import (
    SOGLIA_ECCEDENTARIO_CUMULO_CONTO_CAPITALE,
    SOGLIA_ECCEDENTARIO_SOLA_TARIFFA,
)


def test_ripartisci_centesimi_terzi():
    # 100.00 € in 3 parti uguali: 33.34 + 33.33 + 33.33, mai un cent perso
    quote = ripartisci_centesimi(10000, {"a": D(1), "b": D(1), "c": D(1)})
    assert sum(quote.values()) == 10000
    assert sorted(quote.values()) == [3333, 3333, 3334]


def test_ripartisci_centesimi_pesi_zero():
    with pytest.raises(ValueError):
        ripartisci_centesimi(100, {"a": D(0)})


# Il determinismo di ripartisci_centesimi non ha un test dedicato che confronti la
# funzione con se stessa: sarebbe tautologico. Lo dimostrano, con attesi letterali,
# test_ripartisci_centesimi_pesi_irregolari_caso_a_mano (i valori risolti a mano) e
# test_ripartisci_centesimi_indipendente_dall_ordine_di_inserimento (l'ordine del dict).


def test_scomponi_eccedentario_caso_a_mano():
    # Regole Operative pag. 42: %ecc = max[0; (EC/EI * 100)% − valore soglia], cioè la
    # differenza in PUNTI PERCENTUALI, applicata direttamente al contributo economico.
    # TIP = 100.00 €, EC=60 kWh, EI=100 kWh, soglia 55%:
    #   rapporto = 60/100 = 0,60 ; %ecc = max(0; 0,60 − 0,55) = 0,05
    #   ecc = arrotonda(10000 * 0,05) = 500 cent = 5.00 € ; base = 9500 = 95.00 €
    # Da non confondere con la frazione di energia oltre soglia, (0,60−0,55)/0,60 = 1/12,
    # che darebbe 833 cent: è la formula sbagliata che il motore usava fino al 7/8/2026.
    base, ecc = scomponi_eccedentario(10000, D(60), D(100))
    assert (base, ecc) == (9500, 500)
    assert base + ecc == 10000


def test_scomponi_eccedentario_sotto_soglia():
    assert scomponi_eccedentario(10000, D(50), D(100)) == (10000, 0)


MEMBRI = {
    "P1": {"ruolo": "produttore", "impresa": True},
    "C1": {"ruolo": "consumatore", "impresa": False},
    "C2": {"ruolo": "consumatore", "impresa": True},  # impresa: esclusa dall'eccedentario
}
REGOLE = {
    "fondi": {"gestione": D("0.10")},
    "quota_produttori": D("0.50"),
    "quota_consumatori": D("0.50"),
    "criterio_produttori": "energia_immessa",
    "criterio_consumatori": "prelievo_coincidente",
}


def test_ripartisci_caso_a_mano():
    # base 100.00 €: fondo gestione 10.00; residuo 90.00 → 45.00 produttori, 45.00 consumatori
    # P1 unico produttore → 45.00. Consumatori pro-quota contributi 2:1 → 30.00 e 15.00.
    # eccedentario 12.00 € → solo C1 (C2 è impresa) → 12.00.
    esito = ripartisci(
        REGOLE, 10000, 1200,
        energia_immessa_kwh={"P1": D(500)},
        contributi_consumo_kwh={"C1": D(200), "C2": D(100)},
        membri=MEMBRI,
    )
    assert esito["_fondi"]["gestione"] == 1000
    assert esito["P1"]["quota_produttore"] == 4500
    assert esito["C1"]["quota_consumatore"] == 3000
    assert esito["C2"]["quota_consumatore"] == 1500
    assert esito["C1"]["quota_eccedentaria"] == 1200
    assert "quota_eccedentaria" not in esito["C2"]
    totale = sum(v for d in esito.values() for v in d.values())
    assert totale == 11200  # invariante: nulla si crea, nulla si perde


def test_eccedentario_senza_idonei_va_a_finalita_sociali():
    membri = {
        "P1": {"ruolo": "produttore", "impresa": True},
        "C2": {"ruolo": "consumatore", "impresa": True},
    }
    esito = ripartisci(
        REGOLE, 10000, 500,
        energia_immessa_kwh={"P1": D(500)},
        contributi_consumo_kwh={"C2": D(100)},
        membri=membri,
    )
    assert esito["_fondi"]["finalita_sociali"] == 500
    assert sum(v for d in esito.values() for v in d.values()) == 10500


# --- arrotondamento al centesimo: casi costruiti apposta per non dividersi ---------


def test_ripartisci_centesimi_un_centesimo_tra_tre_membri():
    # Il caso più cattivo possibile: 0.01 € in tre parti uguali.
    #   quota esatta = 1 * 1/3 = 0,333... per ciascuno; troncate a 0 danno 0,
    #   residuo = 1 - 0 = 1 centesimo da assegnare.
    #   I tre resti sono identici (0,333...): il pareggio si rompe sull'ordine della
    #   chiave in senso decrescente (sorted(..., reverse=True)), quindi "c" > "b" > "a"
    #   e l'unico centesimo va a "c".
    quote = ripartisci_centesimi(1, {"a": D(1), "b": D(1), "c": D(1)})
    assert quote == {"a": 0, "b": 0, "c": 1}
    assert sum(quote.values()) == 1  # nessun centesimo creato dal nulla


def test_ripartisci_centesimi_due_centesimi_tra_tre_membri():
    # 0.02 € in tre: esatte 2/3 = 0,666... ciascuna, troncate a 0, residuo 2.
    # Resti tutti pari, ordine di chiave decrescente → i due centesimi vanno a "c" e "b".
    quote = ripartisci_centesimi(2, {"a": D(1), "b": D(1), "c": D(1)})
    assert quote == {"a": 0, "b": 1, "c": 1}
    assert sum(quote.values()) == 2


def test_ripartisci_centesimi_pesi_irregolari_caso_a_mano():
    # 100.01 € con pesi 3:2:2 (somma pesi 7), niente si divide:
    #   x = 10001 * 3/7 = 30003/7 = 4286,142857...  → troncata 4286, resto 0,142857...
    #   y = 10001 * 2/7 = 20002/7 = 2857,428571...  → troncata 2857, resto 0,428571...
    #   z = 10001 * 2/7 = 20002/7 = 2857,428571...  → troncata 2857, resto 0,428571...
    #   somma delle troncate = 4286 + 2857 + 2857 = 10000, residuo 1 centesimo.
    #   Resto maggiore: y e z pareggiano a 0,428571 (più alto di x); il pareggio si
    #   rompe sulla chiave decrescente, "z" > "y", quindi il centesimo va a z.
    quote = ripartisci_centesimi(10001, {"x": D(3), "y": D(2), "z": D(2)})
    assert quote == {"x": 4286, "y": 2857, "z": 2858}
    assert sum(quote.values()) == 10001


def test_ripartisci_centesimi_sette_quote_uguali():
    # 10.00 € tra sette membri: 1000 * 1/7 = 142,857... ciascuno → troncate 142,
    # somma 994, residuo 6 centesimi. Tutti i resti pari (0,857...), ordine di chiave
    # decrescente: m7, m6, m5, m4, m3, m2 prendono un centesimo in più; m1 resta a 142.
    #   verifica: 6 * 143 + 142 = 858 + 142 = 1000.
    quote = ripartisci_centesimi(1000, {f"m{i}": D(1) for i in range(1, 8)})
    assert quote["m1"] == 142
    assert all(quote[f"m{i}"] == 143 for i in range(2, 8))
    assert sum(quote.values()) == 1000


def test_ripartisci_centesimi_indipendente_dall_ordine_di_inserimento():
    # Il resto maggiore ordina per (resto, nome): l'ordine di inserimento nel dict dei
    # pesi non deve cambiare nulla, altrimenti due esecuzioni della stessa CER con
    # l'anagrafica letta in ordine diverso pagherebbero importi diversi.
    # Stesso caso 3:2:2 del test precedente, chiavi inserite al contrario.
    diretto = ripartisci_centesimi(10001, {"x": D(3), "y": D(2), "z": D(2)})
    inverso = ripartisci_centesimi(10001, {"z": D(2), "y": D(2), "x": D(3)})
    assert diretto == inverso == {"x": 4286, "y": 2857, "z": 2858}


def test_ripartisci_centesimi_totale_zero():
    # Niente da ripartire: quote tutte a zero, nessun residuo inventato.
    # (I pesi non sono nulli: il caso "pesi tutti nulli" resta un errore, vedi sopra.)
    quote = ripartisci_centesimi(0, {"a": D(1), "b": D(1)})
    assert quote == {"a": 0, "b": 0}


def test_ripartisci_centesimi_invariante_su_tutti_i_totali_fino_a_cento():
    # L'invariante somma(quote) == totale non deve dipendere dal totale: lo si verifica
    # su tutti i valori da 0 a 99 centesimi con tre pesi disuguali (1:2:4, somma 7).
    # Due punti controllati a mano dentro il ciclo:
    #   totale 7  → esatte 1, 2, 4 → divisione esatta, nessun resto.
    #   totale 10 → esatte 10/7 = 1,428... ; 20/7 = 2,857... ; 40/7 = 5,714...
    #               troncate 1 + 2 + 5 = 8, residuo 2 → ai due resti maggiori,
    #               b (0,857) e c (0,714) → a=1, b=3, c=6, somma 10.
    for totale in range(100):
        quote = ripartisci_centesimi(totale, {"a": D(1), "b": D(2), "c": D(4)})
        assert sum(quote.values()) == totale
        if totale == 7:
            assert quote == {"a": 1, "b": 2, "c": 4}
        if totale == 10:
            assert quote == {"a": 1, "b": 3, "c": 6}


# --- prosumer: lo stesso membro produce e consuma ---------------------------------

# PS è prosumer e non impresa: compare sia tra i produttori sia tra i consumatori, ed è
# idoneo all'importo eccedentario. P1 produce e basta, C1 consuma e basta.
MEMBRI_PROSUMER = {
    "PS": {"ruolo": "prosumer", "impresa": False},
    "P1": {"ruolo": "produttore", "impresa": True},
    "C1": {"ruolo": "consumatore", "impresa": False},
}


def test_ripartisci_prosumer_prende_entrambe_le_quote():
    # base 100.00 €: fondo gestione 10% = 10.00; residuo 90.00 → 45.00 al blocco
    # produttori e 45.00 al blocco consumatori (divisione esatta, nessun resto).
    # Blocco produttori, pro-quota energia immessa PS=300, P1=100 kWh (totale 400):
    #   PS = 4500 * 300/400 = 3375 cent = 33.75 € ; P1 = 4500 * 100/400 = 1125 = 11.25 €.
    # Blocco consumatori, pro-quota contributi PS=50, C1=150 kWh (totale 200):
    #   PS = 4500 * 50/200 = 1125 = 11.25 € ; C1 = 4500 * 150/200 = 3375 = 33.75 €.
    # PS incassa quindi 3375 + 1125 = 4500 cent = 45.00 €, su due voci distinte.
    # Totale: 1000 + 3375 + 1125 + 1125 + 3375 = 10000.
    esito = ripartisci(
        REGOLE, 10000, 0,
        energia_immessa_kwh={"PS": D(300), "P1": D(100)},
        contributi_consumo_kwh={"PS": D(50), "C1": D(150)},
        membri=MEMBRI_PROSUMER,
    )
    assert esito["PS"]["quota_produttore"] == 3375
    assert esito["PS"]["quota_consumatore"] == 1125
    assert sum(esito["PS"].values()) == 4500  # la doppia veste non si perde per strada
    assert esito["P1"]["quota_produttore"] == 1125
    assert esito["C1"]["quota_consumatore"] == 3375
    assert "quota_consumatore" not in esito["P1"]  # il produttore puro non consuma
    assert "quota_produttore" not in esito["C1"]
    assert sum(v for d in esito.values() for v in d.values()) == 10000


def test_ripartisci_prosumer_non_impresa_prende_anche_l_eccedentario():
    # Stesso riparto base del test precedente, più 10.00 € di importo eccedentario.
    # Idonei all'eccedentario = consumatori non imprese: PS e C1 (P1 non è consumatore).
    # Pro-quota contributi PS=50, C1=150 (totale 200):
    #   PS = 1000 * 50/200 = 250 cent = 2.50 € ; C1 = 1000 * 150/200 = 750 = 7.50 €.
    # PS incassa in tutto 3375 + 1125 + 250 = 4750 cent = 47.50 €.
    # Totale: 1000 + 3375 + 1125 + 1125 + 3375 + 250 + 750 = 11000 = 10000 + 1000.
    esito = ripartisci(
        REGOLE, 10000, 1000,
        energia_immessa_kwh={"PS": D(300), "P1": D(100)},
        contributi_consumo_kwh={"PS": D(50), "C1": D(150)},
        membri=MEMBRI_PROSUMER,
    )
    assert esito["PS"]["quota_eccedentaria"] == 250
    assert esito["C1"]["quota_eccedentaria"] == 750
    assert sum(esito["PS"].values()) == 4750
    assert "quota_eccedentaria" not in esito["P1"]
    assert sum(v for d in esito.values() for v in d.values()) == 11000


def test_ripartisci_prosumer_impresa_escluso_dall_eccedentario():
    # Stesso caso, ma PS è un'impresa (es. il capannone che autoconsuma): resta prosumer
    # e prende entrambe le quote ordinarie (3375 + 1125), ma il vincolo delle Regole
    # Operative (docs/FORMULE.md §4) lo esclude dall'eccedentario. L'unico idoneo è C1,
    # che incassa da solo tutti i 1000 centesimi invece dei 750 del test precedente.
    membri = dict(MEMBRI_PROSUMER, PS={"ruolo": "prosumer", "impresa": True})
    esito = ripartisci(
        REGOLE, 10000, 1000,
        energia_immessa_kwh={"PS": D(300), "P1": D(100)},
        contributi_consumo_kwh={"PS": D(50), "C1": D(150)},
        membri=membri,
    )
    assert "quota_eccedentaria" not in esito["PS"]
    assert esito["C1"]["quota_eccedentaria"] == 1000
    assert sum(esito["PS"].values()) == 4500
    assert sum(v for d in esito.values() for v in d.values()) == 11000


def test_ripartisci_quote_uguali_con_prosumer_e_centesimi_dispari():
    # Criterio "quote_uguali" su entrambi i blocchi (le energie non vengono nemmeno
    # lette) e un totale scelto per non dividersi: 100.01 € di base.
    #   fondo gestione = arrotonda(10001 * 0.10) = arrotonda(1000,1) = 1000 cent.
    #   residuo = 10001 - 1000 = 9001, da spezzare 50/50:
    #     esatte 4500,5 e 4500,5 → troncate 4500 + 4500 = 9000, residuo 1 centesimo;
    #     resti pari, chiave decrescente "prod" > "cons" → prod = 4501, cons = 4500.
    #   Produttori (PS, P1, P2) a quote uguali: 4501/3 = 1500,333... → troncate 1500
    #     ciascuno = 4500, residuo 1; resti pari, chiave decrescente "PS" > "P2" > "P1"
    #     ("S" viene dopo "2" e "1" in ASCII) → PS = 1501, P1 = P2 = 1500.
    #   Consumatori (PS, C1) a quote uguali: 4500/2 = 2250 esatti ciascuno.
    #   Totale: 1000 + 1501 + 1500 + 1500 + 2250 + 2250 = 10001.
    regole = dict(REGOLE, criterio_produttori="quote_uguali", criterio_consumatori="quote_uguali")
    membri = {
        "PS": {"ruolo": "prosumer", "impresa": False},
        "P1": {"ruolo": "produttore", "impresa": False},
        "P2": {"ruolo": "produttore", "impresa": False},
        "C1": {"ruolo": "consumatore", "impresa": False},
    }
    esito = ripartisci(regole, 10001, 0, {}, {}, membri)
    assert esito["PS"]["quota_produttore"] == 1501
    assert esito["P1"]["quota_produttore"] == 1500
    assert esito["P2"]["quota_produttore"] == 1500
    assert esito["PS"]["quota_consumatore"] == 2250
    assert esito["C1"]["quota_consumatore"] == 2250
    assert esito["_fondi"]["gestione"] == 1000
    assert sum(v for d in esito.values() for v in d.values()) == 10001


def test_ripartisci_quote_dei_blocchi_devono_fare_uno():
    # Regola statutaria incoerente: 0.6 ai produttori e 0.5 ai consumatori farebbe
    # ripartire il 110% del residuo. Deve fallire prima di qualunque conto.
    regole = dict(REGOLE, quota_produttori=D("0.6"), quota_consumatori=D("0.5"))
    with pytest.raises(ValueError):
        ripartisci(regole, 10000, 0, {"P1": D(1)}, {"C1": D(1)}, MEMBRI)


# --- vincolo dell'importo eccedentario: bordi -------------------------------------


def test_scomponi_eccedentario_alla_soglia_esatta():
    # Bordo: EC=55 kWh su EI=100 kWh → rapporto esattamente 0,55 = soglia, quindi
    # %ecc = max(0; 0,55 − 0,55) = 0 e il bordo NON genera eccedentario.
    assert scomponi_eccedentario(10000, D(55), D(100)) == (10000, 0)
    # Un punto percentuale sopra: %ecc = 0,56 − 0,55 = 0,01 → 100 cent = 1.00 €.
    # (La vecchia formula sbagliata ne dava 1786: l'errore esplodeva proprio qui,
    # vicino alla soglia, che è il caso più frequente.)
    assert scomponi_eccedentario(10000, D(56), D(100)) == (9900, 100)


def test_scomponi_eccedentario_tutta_l_energia_condivisa():
    # Estremo opposto: EC = EI = 100 kWh → rapporto 1 (tutto ciò che si immette si
    # condivide). %ecc = max(0; 1 − 0,55) = 0,45 →
    #   ecc = arrotonda(10000 * 0,45) = 4500 cent = 45.00 € ; base = 5500 = 55.00 €.
    # È il massimo eccedentario possibile con la soglia al 55%, ed è anche il solo
    # punto in cui la vecchia formula (1 − 0,55)/1 coincideva con quella giusta.
    base, ecc = scomponi_eccedentario(10000, D(100), D(100))
    assert (base, ecc) == (5500, 4500)
    assert base + ecc == 10000


def test_scomponi_eccedentario_soglia_del_cumulo_conto_capitale():
    # Seconda soglia, 45%, per gli impianti che cumulano la tariffa premio con un
    # contributo in conto capitale (Regole Operative pag. 41, Appendice B §4 pag. 161).
    # Gli impianti vanno aggregati in due insiemi e scomposti separatamente.
    #   EC=60, EI=100 → rapporto 0,60 ; %ecc = max(0; 0,60 − 0,45) = 0,15
    #   ecc = arrotonda(10000 * 0,15) = 1500 cent ; base = 8500
    base, ecc = scomponi_eccedentario(
        10000, D(60), D(100), soglia=SOGLIA_ECCEDENTARIO_CUMULO_CONTO_CAPITALE
    )
    assert (base, ecc) == (8500, 1500)
    # Lo stesso rapporto con la soglia della sola tariffa premio dà molto meno:
    # la soglia più bassa rende eccedentaria una fetta più grande del contributo.
    assert scomponi_eccedentario(10000, D(60), D(100)) == (9500, 500)


def test_scomponi_eccedentario_senza_immissioni():
    # Impianto fermo per tutto il periodo: EI = 0 e EC = 0. Il rapporto EC/EI non è
    # definito, quindi non si calcola: l'importo (comunque nullo, in pratica) resta
    # tutto base e non si tenta alcuna divisione per zero.
    assert scomponi_eccedentario(0, D(0), D(0)) == (0, 0)
    assert scomponi_eccedentario(10000, D(0), D(0)) == (10000, 0)


# --- vincolo eccedentario aggregato sui DUE insiemi -------------------------------
#
# Regole Operative pag. 42: "La quota percentuale di energia elettrica eccedentaria
# annuale è calcolata aggregando gli impianti di produzione incentivati in due insiemi".
# L'indice "j" della formula è l'insieme; le soglie sono 55% (sola tariffa premio) e
# 45% (cumulo con conto capitale), pag. 41.


def test_scomponi_eccedentario_insiemi_caso_a_mano():
    # Due insiemi, ciascuno col proprio rapporto, la propria soglia e il proprio
    # contributo; gli importi eccedentari si sommano (C_ACI,ecc = Σ_j ...).
    #
    # Insieme A — sola tariffa premio, soglia 0,55:
    #   EC = 700 kWh, EI = 1000 kWh, C = 200,00 € = 20000 cent
    #   rapporto = 700/1000 = 0,70
    #   %ecc = max(0; 0,70 − 0,55) = 0,15
    #   ecc_A = arrotonda(20000 × 0,15) = 3000 cent = 30,00 €
    #   base_A = 20000 − 3000 = 17000 cent = 170,00 €
    #
    # Insieme B — cumulo con conto capitale, soglia 0,45:
    #   EC = 300 kWh, EI = 600 kWh, C = 90,00 € = 9000 cent
    #   rapporto = 300/600 = 0,50
    #   %ecc = max(0; 0,50 − 0,45) = 0,05
    #   ecc_B = arrotonda(9000 × 0,05) = 450 cent = 4,50 €
    #   base_B = 9000 − 450 = 8550 cent = 85,50 €
    #
    # Totali: base = 17000 + 8550 = 25550 ; ecc = 3000 + 450 = 3450
    #         somma = 29000 = 20000 + 9000, il totale dei contributi in ingresso.
    insiemi = [
        InsiemeIncentivato.sola_tariffa(D(700), D(1000), 20000),
        InsiemeIncentivato.cumulo_conto_capitale(D(300), D(600), 9000),
    ]
    base, ecc = scomponi_eccedentario_insiemi(insiemi)
    assert (base, ecc) == (25550, 3450)
    assert base + ecc == 29000  # invariante: nulla si crea, nulla si perde


def test_scomponi_eccedentario_insiemi_non_e_l_insieme_unico():
    # Perché l'aggregazione in due insiemi non è un dettaglio formale: sugli stessi
    # impianti del test precedente, trattarli come UN insieme solo dà un altro numero.
    #   EC totale = 700 + 300 = 1000 kWh ; EI totale = 1000 + 600 = 1600 kWh
    #   rapporto medio = 1000/1600 = 0,625 (NON è la media di 0,70 e 0,50)
    #   con l'unica soglia 0,55: %ecc = 0,625 − 0,55 = 0,075
    #   ecc = arrotonda(29000 × 0,075) = arrotonda(2175,0) = 2175 cent = 21,75 €
    # contro i 3450 cent = 34,50 € del calcolo per insiemi: 1275 centesimi in meno,
    # il 37% dell'importo che deve andare ai consumatori non-impresa e alle finalità
    # sociali (Regole Operative pag. 41). Due errori si sommano: il rapporto medio
    # annacqua l'insieme sopra soglia, e la soglia 0,55 viene applicata anche agli
    # impianti in cumulo, che ne hanno una più bassa (0,45).
    unico = scomponi_eccedentario(29000, D(1000), D(1600))
    assert unico == (26825, 2175)
    per_insiemi = scomponi_eccedentario_insiemi([
        InsiemeIncentivato.sola_tariffa(D(700), D(1000), 20000),
        InsiemeIncentivato.cumulo_conto_capitale(D(300), D(600), 9000),
    ])
    assert per_insiemi == (25550, 3450)
    assert unico[1] != per_insiemi[1]
    # In entrambi i casi l'invariante regge: cambia la ripartizione, non il totale.
    assert sum(unico) == sum(per_insiemi) == 29000


def test_scomponi_eccedentario_insiemi_stesso_rapporto_soglie_diverse():
    # Stesse identiche energie nei due insiemi (EC 500 su EI 1000, rapporto 0,50) e
    # stesso contributo (100,00 € = 10000 cent): a decidere è solo la soglia.
    #   A, sola tariffa (0,55): 0,50 < 0,55 → %ecc = 0 → base 10000, ecc 0
    #   B, cumulo       (0,45): %ecc = max(0; 0,50 − 0,45) = 0,05
    #                           ecc = arrotonda(10000 × 0,05) = 500 cent = 5,00 €
    #                           base = 10000 − 500 = 9500
    # Totali: base = 10000 + 9500 = 19500 ; ecc = 0 + 500 = 500 ; somma = 20000.
    base, ecc = scomponi_eccedentario_insiemi([
        InsiemeIncentivato.sola_tariffa(D(500), D(1000), 10000),
        InsiemeIncentivato.cumulo_conto_capitale(D(500), D(1000), 10000),
    ])
    assert (base, ecc) == (19500, 500)
    assert base + ecc == 20000


def test_scomponi_eccedentario_insiemi_arrotondamenti_che_non_chiudono():
    # Il caso che il metodo deve reggere: entrambi gli insiemi cadono esattamente su
    # mezzo centesimo, dove l'arrotondamento è costretto a scegliere.
    #   A, sola tariffa (0,55): EC = 56, EI = 100 → rapporto 0,56 → %ecc = 0,01
    #      50,50 € = 5050 cent → ecc = arrotonda(5050 × 0,01) = arrotonda(50,50)
    #      = 51 cent (ROUND_HALF_UP: mezzo centesimo va per eccesso)
    #      base_A = 5050 − 51 = 4999
    #   B, cumulo (0,45): EC = 46, EI = 100 → rapporto 0,46 → %ecc = 0,01
    #      10,50 € = 1050 cent → ecc = arrotonda(10,50) = 11 cent
    #      base_B = 1050 − 11 = 1039
    # Totali: base = 4999 + 1039 = 6038 ; ecc = 51 + 11 = 62 ; somma = 6100.
    # Entrambi gli insiemi hanno arrotondato PER ECCESSO l'eccedentario (mezzo
    # centesimo ciascuno, un centesimo intero in tutto), eppure il totale chiude: è
    # la base a essere ricavata per differenza, non arrotondata a sua volta.
    base, ecc = scomponi_eccedentario_insiemi([
        InsiemeIncentivato.sola_tariffa(D(56), D(100), 5050),
        InsiemeIncentivato.cumulo_conto_capitale(D(46), D(100), 1050),
    ])
    assert (base, ecc) == (6038, 62)
    assert base + ecc == 5050 + 1050


def test_scomponi_eccedentario_insiemi_invariante_su_molti_contributi():
    # L'invariante somma == totale dei contributi non deve dipendere dagli importi:
    # lo si verifica su contributi che non si dividono, con rapporti scelti perché
    # le percentuali eccedentarie siano periodiche (0,70 − 0,55 = 0,15 su A;
    # 2/3 − 0,45 = 0,21666... su B, con 2/3 = 0,666... non rappresentabile esatto).
    for c_a in range(0, 1000, 7):
        for c_b in (0, 1, 99, 12345):
            base, ecc = scomponi_eccedentario_insiemi([
                InsiemeIncentivato.sola_tariffa(D(70), D(100), c_a),
                InsiemeIncentivato.cumulo_conto_capitale(D(2), D(3), c_b),
            ])
            assert base + ecc == c_a + c_b
            assert base >= 0 and ecc >= 0


def test_scomponi_eccedentario_insiemi_uno_solo_coincide_con_la_primitiva():
    # Un insieme solo deve dare esattamente quello che dà la primitiva: la funzione
    # aggregata non aggiunge aritmetica propria, somma soltanto.
    uno = scomponi_eccedentario_insiemi([
        InsiemeIncentivato.sola_tariffa(D(60), D(100), 10000)
    ])
    assert uno == scomponi_eccedentario(10000, D(60), D(100)) == (9500, 500)


def test_scomponi_eccedentario_insiemi_vuoto():
    # Configurazione senza impianti incentivati: la sommatoria su un insieme vuoto è
    # zero, e l'invariante (0 + 0 == 0) regge banalmente.
    assert scomponi_eccedentario_insiemi([]) == (0, 0)


def test_scomponi_eccedentario_insiemi_impianti_fermi():
    # Un insieme con gli impianti fermi (EI = 0, EC = 0) non ha rapporto definito:
    # il suo contributo — nullo in pratica, ma non lo si assume — resta tutto base e
    # non manda in errore l'altro insieme, che si scompone normalmente.
    #   A: EI = 0 → base 0, ecc 0
    #   B, cumulo: EC 60 su EI 100 → %ecc = 0,60 − 0,45 = 0,15 → ecc = 1500, base 8500
    base, ecc = scomponi_eccedentario_insiemi([
        InsiemeIncentivato.sola_tariffa(D(0), D(0), 0),
        InsiemeIncentivato.cumulo_conto_capitale(D(60), D(100), 10000),
    ])
    assert (base, ecc) == (8500, 1500)
    assert base + ecc == 10000


# --- l'insieme porta la sua soglia: guardie ---------------------------------------


def test_insieme_incentivato_soglie_dei_costruttori_nominati():
    # I due costruttori nominati pescano la soglia dalle costanti di tariffe.py: è il
    # modo per non scriverla mai a mano e non associarla all'insieme sbagliato.
    a = InsiemeIncentivato.sola_tariffa(D(10), D(100), 500)
    b = InsiemeIncentivato.cumulo_conto_capitale(D(10), D(100), 500)
    assert a.soglia == SOGLIA_ECCEDENTARIO_SOLA_TARIFFA == D("0.55")
    assert b.soglia == SOGLIA_ECCEDENTARIO_CUMULO_CONTO_CAPITALE == D("0.45")
    assert a.nome != b.nome  # nomi distinti di default: niente duplicati per sbaglio


def test_insieme_incentivato_la_soglia_non_si_puo_dimenticare():
    # Il costruttore grezzo non ha un default per la soglia: ometterla è un errore di
    # chiamata, non un calcolo silenziosamente sbagliato con la soglia della sola
    # tariffa premio applicata anche agli impianti in cumulo.
    with pytest.raises(TypeError):
        InsiemeIncentivato("A", D(10), D(100), 500)  # manca la soglia


def test_insieme_incentivato_soglia_fuori_intervallo():
    with pytest.raises(ValueError):
        InsiemeIncentivato("A", D(10), D(100), 500, D("1.5"))
    with pytest.raises(ValueError):
        InsiemeIncentivato("A", D(10), D(100), 500, D("-0.1"))


def test_insieme_incentivato_energia_condivisa_oltre_l_immessa():
    # E_ACI,h = min(E_immessa,h; E_prelevata,h) ≤ E_immessa,h ora per ora (Regole
    # Operative pag. 40), quindi anche sui totali dell'insieme: un rapporto > 1 non
    # esiste, e di solito significa che i due argomenti sono stati scambiati.
    with pytest.raises(ValueError):
        InsiemeIncentivato.sola_tariffa(D(1000), D(700), 20000)


def test_insieme_incentivato_valori_negativi():
    with pytest.raises(ValueError):
        InsiemeIncentivato.sola_tariffa(D(-1), D(100), 500)
    with pytest.raises(ValueError):
        InsiemeIncentivato.sola_tariffa(D(10), D(100), -500)
    with pytest.raises(ValueError):
        InsiemeIncentivato("", D(10), D(100), 500, D("0.55"))


def test_scomponi_eccedentario_insiemi_rifiuta_nomi_duplicati():
    # Lo stesso insieme passato due volte conterebbe doppio il suo contributo senza
    # che nulla protesti: l'invariante reggerebbe (la somma in ingresso raddoppia con
    # quella in uscita) e il rendiconto pagherebbe due volte gli stessi impianti.
    with pytest.raises(ValueError):
        scomponi_eccedentario_insiemi([
            InsiemeIncentivato.sola_tariffa(D(700), D(1000), 20000),
            InsiemeIncentivato.sola_tariffa(D(700), D(1000), 20000),
        ])
    # Due insiemi con la stessa soglia ma nomi distinti sono invece legittimi: la
    # norma ne prevede due, ma il motore non impone come si compongano.
    base, ecc = scomponi_eccedentario_insiemi([
        InsiemeIncentivato.sola_tariffa(D(700), D(1000), 20000, nome="fv_nord"),
        InsiemeIncentivato.sola_tariffa(D(700), D(1000), 20000, nome="fv_centro"),
    ])
    assert (base, ecc) == (34000, 6000)  # 2 × (17000, 3000)


# --- guardie sulle regole statutarie ----------------------------------------------


def test_ripartisci_quote_negative_che_sommano_a_uno():
    # Il bug corretto il 7 ago 2026: la guardia controllava solo che le due quote
    # sommassero a 1, non il segno. Con quota_produttori = 1,5 e quota_consumatori
    # = −0,5 la somma fa 1, la guardia passava, e il riparto del residuo (9000 cent
    # dopo il fondo gestione) dava:
    #   prod = 9000 × 1,5/1 = 13500 cent = 135,00 €
    #   cons = 9000 × (−0,5)/1 = −4500 cent = −45,00 €
    # cioè il consumatore DOVEVA soldi alla CER per far incassare di più il
    # produttore. L'invariante finale non se ne accorgeva: è una somma, e
    # 13500 − 4500 + 1000 fa comunque 10000.
    regole = dict(REGOLE, quota_produttori=D("1.5"), quota_consumatori=D("-0.5"))
    with pytest.raises(ValueError):
        ripartisci(regole, 10000, 0, {"P1": D(500)}, {"C1": D(100)}, MEMBRI)


def test_ripartisci_fondo_con_percentuale_negativa():
    # Un fondo negativo non "restituisce" nulla: crea denaro dal nulla per i membri.
    # Prima della guardia, base 100,00 € con un fondo al −10% dava fondo = −1000 cent
    # e residuo = 10000 − (−1000) = 11000, cioè 110,00 € da ripartire su 100,00 €
    # incassati, con la voce di fondo a −10,00 € a pareggiare il bilancio.
    regole = dict(REGOLE, fondi={"gestione": D("-0.10")})
    with pytest.raises(ValueError):
        ripartisci(regole, 10000, 0, {"P1": D(500)}, {"C1": D(100)}, MEMBRI)


def test_ripartisci_fondi_che_sommano_a_piu_di_uno():
    # Due fondi al 70% ciascuno: 140% del totale ai fondi e residuo negativo ai
    # membri. Prima della guardia, base 100,00 € dava fondi a 7000 + 7000 = 14000 cent
    # e residuo −4000, spezzato in −2000 al blocco produttori e −2000 ai consumatori.
    regole = dict(REGOLE, fondi={"a": D("0.7"), "b": D("0.7")})
    with pytest.raises(ValueError):
        ripartisci(regole, 10000, 0, {"P1": D(500)}, {"C1": D(100)}, MEMBRI)


def test_ripartisci_fondi_che_sommano_esattamente_a_uno():
    # Bordo legittimo, e deve restare tale: uno statuto può destinare tutto il base ai
    # fondi (per esempio un anno di sola capitalizzazione). Base 100,00 €:
    #   fondo a = arrotonda(10000 × 0,6) = 6000 ; fondo b = arrotonda(10000 × 0,4) = 4000
    #   residuo = 10000 − 6000 − 4000 = 0 → tutte le quote dei membri sono 0.
    # Totale: 6000 + 4000 = 10000, invariante rispettato.
    regole = dict(REGOLE, fondi={"a": D("0.6"), "b": D("0.4")})
    esito = ripartisci(regole, 10000, 0, {"P1": D(500)}, {"C1": D(100)}, MEMBRI)
    assert esito["_fondi"] == {"a": 6000, "b": 4000}
    assert esito["P1"]["quota_produttore"] == 0
    assert esito["C1"]["quota_consumatore"] == 0
    assert sum(v for d in esito.values() for v in d.values()) == 10000


def test_ripartisci_fondi_arrotondati_che_sfondano_l_importo():
    # Le percentuali passano la guardia (0,5 + 0,5 = 1) ma su un importo di UN
    # centesimo i due arrotondamenti sfondano il totale:
    #   fondo a = arrotonda(1 × 0,5) = arrotonda(0,5) = 1 cent (ROUND_HALF_UP)
    #   fondo b = arrotonda(0,5) = 1 cent
    #   residuo = 1 − 1 − 1 = −1 centesimo
    # Senza guardia, ripartisci_centesimi(−1, ...) violerebbe il proprio invariante e
    # morirebbe con un AssertionError opaco. Meglio un ValueError che dice cosa è
    # successo.
    regole = dict(REGOLE, fondi={"a": D("0.5"), "b": D("0.5")})
    with pytest.raises(ValueError):
        ripartisci(regole, 1, 0, {"P1": D(500)}, {"C1": D(100)}, MEMBRI)


def test_ripartisci_importi_negativi():
    # Non esiste un incentivo negativo da ripartire: né sul base né sull'eccedentario.
    with pytest.raises(ValueError):
        ripartisci(REGOLE, -100, 0, {"P1": D(500)}, {"C1": D(100)}, MEMBRI)
    with pytest.raises(ValueError):
        ripartisci(REGOLE, 10000, -100, {"P1": D(500)}, {"C1": D(100)}, MEMBRI)


# --- guardie della primitiva: regressioni trovate in verifica avversariale l'8/8/2026 -
#
# Tutte le guardie stavano in InsiemeIncentivato.__post_init__, cioè sulla strada che
# nessuno percorreva: la demo chiama la primitiva. Ogni riga qui sotto è un attacco che
# passava e ora è chiuso; i valori nei commenti sono quelli che il codice restituiva.


def test_scomponi_eccedentario_primitiva_rifiuta_argomenti_scambiati():
    # EC non può eccedere EI, perché EC_h = min(E_immessa,h; E_prelevata,h) ora per ora
    # (Regole Operative pag. 40) e la disuguaglianza passa ai totali. Un rapporto > 1
    # significa argomenti invertiti.
    #   Prima: SE(20000, EC=1000, EI=700) → (2429, 17571), cioè l'87,9% del contributo
    #   dichiarato eccedentario invece del 15% che gli spetterebbe con EC/EI = 0,70.
    with pytest.raises(ValueError, match="maggiore dell'energia immessa"):
        scomponi_eccedentario(20000, D(1000), D(700))
    #   Nel caso estremo la base diventava NEGATIVA: SE(10000, 10000, 100) dava
    #   (-984500, 994500), un eccedentario 99 volte il contributo.
    with pytest.raises(ValueError):
        scomponi_eccedentario(10000, D(10000), D(100))


def test_scomponi_eccedentario_soglia_in_percento_non_passa_in_silenzio():
    # Il difetto più insidioso dei cinque: scrivere 55 invece di 0,55 non produceva
    # numeri assurdi né eccezioni. Semplicemente max(0; 0,60 − 55) = 0, quindi
    # SE(10000, 60, 100, 55) restituiva (10000, 0): l'importo eccedentario azzerato,
    # e i consumatori non-imprese non pagati, senza che nulla protestasse.
    with pytest.raises(ValueError, match="0,55"):
        scomponi_eccedentario(10000, D(60), D(100), D(55))
    # Una soglia negativa dava invece un eccedentario MAGGIORE del contributo:
    #   SE(10000, 60, 100, soglia=−0,5) → (−1000, 11000).
    with pytest.raises(ValueError):
        scomponi_eccedentario(10000, D(60), D(100), D("-0.5"))
    # I due bordi legittimi 0 e 1 restano ammessi: non sono valori normativi, ma sono
    # matematicamente innocui (soglia 1 non produce mai eccedentario).
    assert scomponi_eccedentario(10000, D(60), D(100), D(1)) == (10000, 0)


def test_scomponi_eccedentario_rifiuta_contributo_non_intero_o_negativo():
    # Il denaro viaggia in centesimi interi. Un float attraversava tutte le guardie e
    # usciva come centesimo frazionario da una funzione che promette tuple[int, int]:
    #   SEI([sola_tariffa(700, 1000, 20000.5)]) → (17000.5, 3000).
    with pytest.raises(ValueError, match="intero di centesimi"):
        scomponi_eccedentario(20000.5, D(700), D(1000))
    #   SE(-10000, 70, 100) dava (-8500, -1500): un incentivo negativo ripartito.
    with pytest.raises(ValueError, match="contributo negativo"):
        scomponi_eccedentario(-10000, D(70), D(100))


def test_scomponi_eccedentario_rifiuta_valori_non_finiti():
    # NaN e Infinity vanno fermati prima dei confronti: Decimal("NaN") < 0 solleva
    # InvalidOperation, che è ArithmeticError e NON ValueError, quindi sfuggirebbe a
    # un chiamante che cattura ValueError come il resto del modulo gli insegna.
    with pytest.raises(ValueError, match="non è un numero finito"):
        scomponi_eccedentario(10000, D("NaN"), D(100))
    with pytest.raises(ValueError, match="non è un numero finito"):
        scomponi_eccedentario(10000, D(60), D(100), D("Infinity"))


def test_scomponi_eccedentario_insiemi_accetta_un_generatore():
    # La firma dichiara Sequence, ma un generatore entrava lo stesso e la funzione
    # itera due volte (prima i nomi, poi il calcolo): al secondo giro era vuoto.
    # Prima: (0, 0), cioè l'INTERO contributo TIP annullato in silenzio, con l'assert
    # finale complice perché confrontava 0 con 0 iterando anch'esso sul generatore.
    # Stesso caso a mano del test principale: 20000 e 9000 cent → (25550, 3450).
    def voci():
        yield InsiemeIncentivato.sola_tariffa(D(700), D(1000), 20000)
        yield InsiemeIncentivato.cumulo_conto_capitale(D(300), D(600), 9000)

    da_generatore = scomponi_eccedentario_insiemi(voci())
    da_lista = scomponi_eccedentario_insiemi(list(voci()))
    assert da_generatore == da_lista == (25550, 3450)
    assert sum(da_generatore) == 29000  # nessun centesimo evaporato


def test_ripartisci_fondi_oltre_uno_anche_quando_arrotondano_tutti_a_zero():
    # Caso che separa la guardia sulla somma delle percentuali da quella sul residuo:
    # senza la prima, questa configurazione passerebbe in silenzio.
    #   base = 1 centesimo, tre fondi allo 0,4 (somma 1,2 > 1).
    #   Ciascun fondo: arrotonda(1 * 0,4) = arrotonda(0,4) = 0 centesimi.
    #   residuo = 1 − 0 − 0 − 0 = 1, che è >= 0: la guardia sul residuo NON scatta.
    # Uno statuto che destina il 120% ai fondi è malformato e va rifiutato comunque.
    regole = dict(REGOLE, fondi={"a": D("0.4"), "b": D("0.4"), "c": D("0.4")})
    with pytest.raises(ValueError, match="sommano a"):
        ripartisci(regole, 1, 0, {"P1": D(500)}, {"C1": D(100)}, MEMBRI)
