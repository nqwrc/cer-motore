"""Casi risolti a mano per il calcolo dell'energia condivisa."""
from decimal import Decimal as D

import pytest

from cer_motore.condivisione import (
    alloca_oraria,
    contributo_prelievo_coincidente,
    energia_condivisa,
    partiziona_esente_fattore_f,
)


def test_energia_condivisa_caso_a_mano():
    # Ora 1: immissioni 5+1=6, prelievi 3+1=4 → EC=4 (limita il prelievo)
    # Ora 2: immissioni 2+0=2, prelievi 4+1=5 → EC=2 (limita l'immissione)
    immissioni = {"A": [D(5), D(2)], "B": [D(1), D(0)]}
    prelievi = {"X": [D(3), D(4)], "Y": [D(1), D(1)]}
    assert energia_condivisa(immissioni, prelievi) == [D(4), D(2)]


def test_energia_condivisa_serie_disallineate():
    with pytest.raises(ValueError):
        energia_condivisa({"A": [D(1)]}, {"X": [D(1), D(2)]})


def test_contributo_prelievo_coincidente_caso_a_mano():
    # EC=[4,2]. Ora 1: X preleva 3 su 4 → 3; Y → 1 (EC=prelievi, attribuzione piena).
    # Ora 2: prelievi X=4,Y=1 (tot 5), EC=2 → X: 2*4/5=1.6; Y: 2*1/5=0.4.
    prelievi = {"X": [D(3), D(4)], "Y": [D(1), D(1)]}
    ec = [D(4), D(2)]
    contributi = contributo_prelievo_coincidente(prelievi, ec)
    assert contributi["X"] == D("4.6")
    assert contributi["Y"] == D("1.4")
    # invariante: la somma dei contributi è la somma dell'energia condivisa
    assert sum(contributi.values()) == sum(ec)


def test_contributo_ora_senza_prelievi():
    prelievi = {"X": [D(0)], "Y": [D(0)]}
    contributi = contributo_prelievo_coincidente(prelievi, [D(0)])
    assert sum(contributi.values()) == 0


def test_contributo_prelievo_coincidente_invariante_esatto():
    # Il caso che la divisione semplice non chiude, gemello di quello di alloca_oraria.
    # Tre consumatori che prelevano 4 kWh ciascuno in un'ora sola, EC = 10 kWh:
    #   10 * 4/12 = 3,333... periodico. Con Decimal a 28 cifre la somma dei tre
    #   quozienti vale 9,999999999999999999999999999, cioè NON 10.
    # Ripartendo in unità intere da 1e-6 kWh: 10.000.000 unità, quota esatta
    #   3.333.333,33 ciascuno → troncate 3.333.333, somma 9.999.999, resta 1 unità,
    #   assegnata al resto maggiore (resti pari → chiave decrescente, quindi "C").
    prelievi = {"A": [D(4)], "B": [D(4)], "C": [D(4)]}
    contributi = contributo_prelievo_coincidente(prelievi, [D(10)])
    assert contributi == {"A": D("3.333333"), "B": D("3.333333"), "C": D("3.333334")}
    assert sum(contributi.values()) == D(10)      # esatto, non a meno di tolleranza
    # controprova: la divisione semplice non ci arriva
    assert sum(D(10) * D(4) / D(12) for _ in range(3)) != D(10)


def test_contributo_prelievo_coincidente_serie_disallineate():
    # Quarta e ultima guardia di allineamento del motore (le altre tre sono su
    # energia_condivisa, alloca_oraria e incentivo_periodo): 2 ore di prelievi contro
    # 1 sola ora di EC. Nessun conto viene tentato.
    with pytest.raises(ValueError):
        contributo_prelievo_coincidente({"X": [D(1), D(2)]}, [D(1)])


# --- alloca_oraria: attribuzione dell'EC agli impianti -----------------------------


def test_alloca_oraria_caso_a_mano():
    # Ora 1: immissioni A=3, B=1, C=0 → totale 4. EC=2, quindi ogni impianto prende
    #   la sua frazione oraria: A = 2*3/4 = 1.5 ; B = 2*1/4 = 0.5 ; C = 0.
    #   Somma 1.5+0.5+0 = 2 = EC. Divisione esatta, nessun resto da assegnare.
    # Ora 2: immissioni A=B=C=4 → totale 12. EC=10, quindi 10*4/12 = 3.333... periodico:
    #   la divisione non basta a garantire l'invariante. Si riparte in unità da 1e-6 kWh:
    #   10 kWh = 10_000_000 unità; quota esatta 10_000_000*4/12 = 3_333_333,33 ciascuno;
    #   troncate a 3_333_333 danno 9_999_999, resta 1 unità. Metodo del resto maggiore:
    #   i tre resti sono identici (0,33), il pareggio si rompe sull'ordine della chiave
    #   (decrescente, come in ripartisci_centesimi) → l'unità va a C.
    #   → A = 3.333333 ; B = 3.333333 ; C = 3.333334 ; somma = 10.000000 = EC esatta.
    immissioni = {"A": [D(3), D(4)], "B": [D(1), D(4)], "C": [D(0), D(4)]}
    ec = [D(2), D(10)]
    quote = alloca_oraria(immissioni, ec)
    assert quote["A"] == [D("1.5"), D("3.333333")]
    assert quote["B"] == [D("0.5"), D("3.333333")]
    assert quote["C"] == [D(0), D("3.333334")]
    # invariante orario: la somma delle attribuzioni è esattamente l'EC dell'ora
    for h, atteso in enumerate(ec):
        assert sum(q[h] for q in quote.values()) == atteso
    # e quindi anche sul totale del periodo
    assert sum(sum(q) for q in quote.values()) == sum(ec)


def test_alloca_oraria_ore_a_immissione_nulla():
    # Tre ore, con l'impianto B fermo per tutto il periodo tranne l'ultima ora.
    # Ora 1 (notte): immissioni A=0, B=0 → totale 0. EC=0 perché EC = min(imm, prel)
    #   e l'immissione è nulla: entrambe le quote sono 0, nessuna divisione per zero.
    # Ora 2: immissioni A=2, B=0 → totale 2. EC=1.5 → A = 1.5*2/2 = 1.5 ; B = 1.5*0/2 = 0.
    # Ora 3: immissioni A=1, B=3 → totale 4. EC=1 → A = 1*1/4 = 0.25 ; B = 1*3/4 = 0.75.
    # Totali di periodo: A = 0+1.5+0.25 = 1.75 ; B = 0+0+0.75 = 0.75 ;
    #   somma 2.50 = somma EC = 0+1.5+1 = 2.5.
    immissioni = {"A": [D(0), D(2), D(1)], "B": [D(0), D(0), D(3)]}
    ec = [D(0), D("1.5"), D(1)]
    quote = alloca_oraria(immissioni, ec)
    assert quote["A"] == [D(0), D("1.5"), D("0.25")]
    assert quote["B"] == [D(0), D(0), D("0.75")]
    assert sum(quote["A"]) == D("1.75")
    assert sum(quote["B"]) == D("0.75")
    assert sum(sum(q) for q in quote.values()) == sum(ec)


def test_alloca_oraria_invariante_esatto_dove_la_divisione_fallisce():
    # Perché serve il metodo del resto maggiore e non basta dividere: con tre impianti
    # uguali e EC=10 la divisione Decimal dà 3,333...3 (28 cifre) e la somma dei tre
    # quozienti vale 9,999999999999999999999999999 ≠ 10. alloca_oraria invece chiude.
    immissioni = {"A": [D(4)], "B": [D(4)], "C": [D(4)]}
    ec = [D(10)]
    quozienti = [ec[0] * D(4) / D(12) for _ in immissioni]
    assert sum(quozienti) != ec[0]  # la divisione pura non conserva l'energia
    quote = alloca_oraria(immissioni, ec)
    assert sum(q[0] for q in quote.values()) == ec[0]  # il riparto sì, esattamente


def test_alloca_oraria_ec_piu_fine_della_risoluzione():
    # L'invariante è esatto rispetto a EC quantizzato a 6 decimali (1e-6 kWh). Con un EC
    # più fine della risoluzione lo scarto è al più mezza unità, cioè 5e-7 kWh per ora.
    # Qui EC = 1.0000005 kWh → 1_000_000,5 unità → arrotondato a 1_000_001 unità;
    # due impianti pari: 500_000 ciascuno + 1 unità di resto → somma 1.000001 kWh.
    # Scarto |1.000001 − 1.0000005| = 5e-7 kWh, quattro ordini di grandezza sotto i
    # 3 decimali di kWh con cui i distributori misurano l'energia.
    immissioni = {"A": [D(1)], "B": [D(1)]}
    ec = [D("1.0000005")]
    quote = alloca_oraria(immissioni, ec)
    somma = sum(q[0] for q in quote.values())
    assert somma == D("1.000001")
    assert abs(somma - ec[0]) == D("5E-7")


def test_alloca_oraria_serie_disallineate():
    with pytest.raises(ValueError):
        alloca_oraria({"A": [D(1), D(2)]}, [D(1)])


# --- partizione esente / non esente dal fattore F (roadmap 13) ---------------------
#
# Regole Operative pag. 41: l'energia condivisa afferente a punti di prelievo di enti
# territoriali, enti religiosi, enti del terzo settore, enti di protezione ambientale e
# persone fisiche e' ESENTE dal fattore F, cioe' dalla decurtazione TIP * (1 - F) che
# spetta agli impianti in cumulo con un contributo in conto capitale. La norma dice
# quale energia e' esente, non come misurarla: il criterio pro-quota oraria dei prelievi
# e' una scelta di modellazione dichiarata (docs/FORMULE.md §2-bis), la stessa gia' usata
# per attribuire l'EC agli impianti.


def test_partiziona_esente_fattore_f_caso_a_mano():
    # Tre punti di prelievo: la palestra comunale (ente territoriale, quindi ESENTE dal
    # fattore F) e due imprese, che esenti non sono. L'EC oraria si attribuisce
    # pro-quota prelievi, esattamente come alloca_oraria fa con le immissioni.
    # Ora 1: prelievi COMUNE=3, A=1, B=0 → totale 4. EC=2 →
    #   COMUNE = 2*3/4 = 1.5 (esente) ; A = 2*1/4 = 0.5 ; B = 0 → non esente 0.5
    # Ora 2: prelievi COMUNE=1, A=1, B=2 → totale 4. EC=4, cioe' tutto il prelievo →
    #   COMUNE = 1 (esente) ; A = 1, B = 2 → non esente 3
    # Totali di periodo: esente 2.5 kWh, non esente 3.5 kWh, somma 6 = somma EC.
    prelievi = {"COMUNE": [D(3), D(1)], "A": [D(1), D(1)], "B": [D(0), D(2)]}
    ec = [D(2), D(4)]
    esente, non_esente = partiziona_esente_fattore_f(prelievi, ec, ["COMUNE"])
    assert esente == [D("1.5"), D(1)]
    assert non_esente == [D("0.5"), D(3)]
    assert sum(esente) == D("2.5") and sum(non_esente) == D("3.5")
    # invariante orario: le due parti ricompongono esattamente l'EC dell'ora
    for h, atteso in enumerate(ec):
        assert esente[h] + non_esente[h] == atteso


def test_partiziona_esente_fattore_f_ai_due_estremi():
    # Nessun POD esente: tutta l'energia e' non esente e prende il fattore F per intero.
    # Tutti esenti (una CER di sole persone fisiche e enti territoriali, che e' la
    # configurazione tipica delle CER di paese): il fattore F non morde su nulla, e
    # l'impianto in cumulo incassa la tariffa piena pur avendo preso il contributo.
    prelievi = {"X": [D(2), D(1)], "Y": [D(1), D(1)]}
    ec = [D(3), D(2)]
    niente, tutto = partiziona_esente_fattore_f(prelievi, ec, [])
    assert niente == [D(0), D(0)] and tutto == [D(3), D(2)]
    tutto_esente, niente2 = partiziona_esente_fattore_f(prelievi, ec, ["X", "Y"])
    assert tutto_esente == [D(3), D(2)] and niente2 == [D(0), D(0)]


def test_partiziona_esente_fattore_f_invariante_dove_la_divisione_non_chiude():
    # Lo stesso caso periodico degli altri due riparti: tre consumatori da 4 kWh in
    # un'ora ed EC = 10 kWh. 10*4/12 = 3,333... e la somma dei tre quozienti non fa 10.
    # Col resto maggiore su unita' da 1e-6 kWh: 3.333333 + 3.333333 + 3.333334 = 10.
    # Un solo consumatore esente → esente 3.333333 (o 3.333334, secondo la chiave) e
    # la somma delle due parti resta esattamente 10, che e' cio' che conta: nessun
    # millesimo di kWh sfugge alla tariffazione ne' viene tariffato due volte.
    prelievi = {"A": [D(4)], "B": [D(4)], "C": [D(4)]}
    ec = [D(10)]
    esente, non_esente = partiziona_esente_fattore_f(prelievi, ec, ["C"])
    assert esente == [D("3.333334")]      # C prende l'unita' di resto (chiave decrescente)
    assert non_esente == [D("6.666666")]
    assert esente[0] + non_esente[0] == D(10)


def test_partiziona_esente_fattore_f_rifiuta_un_pod_sconosciuto():
    # Un POD esente scritto male non e' un prelievo nullo: e' energia esente trattata
    # come non esente, cioe' tariffa premio decurtata a chi la norma esentava, in
    # silenzio e senza che nessun invariante se ne accorga (la somma delle due parti
    # resterebbe esatta). Stessa specie del ruolo scritto male in ripartisci, stesso
    # trattamento: errore al confine, con l'elenco dei POD noti nel messaggio.
    prelievi = {"COMUNE": [D(3)], "A": [D(1)]}
    with pytest.raises(ValueError, match="assenti dai prelievi"):
        partiziona_esente_fattore_f(prelievi, [D(2)], ["COMUME"])  # refuso su COMUNE
    # Il messaggio nomina il POD sbagliato e quelli buoni, non solo il fatto che manca.
    with pytest.raises(ValueError, match=r"\['COMUME'\].*'A', 'COMUNE'"):
        partiziona_esente_fattore_f(prelievi, [D(2)], ["COMUME"])


def test_partiziona_esente_fattore_f_serie_disallineate():
    # Eredita la guardia di allineamento di alloca_oraria, che e' la funzione da cui
    # passa: 2 ore di prelievi contro 1 sola di EC non producono una partizione monca.
    with pytest.raises(ValueError):
        partiziona_esente_fattore_f({"X": [D(1), D(2)]}, [D(1)], ["X"])
