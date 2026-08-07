"""Regole statutarie dichiarative da file TOML.

Due famiglie di test:
  - i casi numerici risolti a mano, che dimostrano il giro completo
    file TOML -> regole.py -> ripartizione.ripartisci e la scelta di far passare il
    denaro dalle stringhe e mai dai float;
  - un caso per ogni messaggio d'errore. Qui il messaggio E' il prodotto: lo legge un
    socio che deve correggere lo statuto, non uno stack trace. Se il testo cambia in
    peggio, questi test devono accorgersene.
"""
from decimal import ROUND_HALF_UP
from decimal import Decimal as D
from pathlib import Path

import pytest

from cer_motore.regole import ErroreRegole, da_testo, leggi, valida
from cer_motore.ripartizione import ripartisci

ESEMPIO = Path(__file__).resolve().parent.parent / "regole-esempio.toml"

# Le stesse regole dell'esempio, scritte a mano come nel dict di __main__.py: è il
# termine di paragone di tutto il file.
REGOLE_A_MANO = {
    "fondi": {"gestione": D("0.10")},
    "quota_produttori": D("0.50"),
    "quota_consumatori": D("0.50"),
    "criterio_produttori": "energia_immessa",
    "criterio_consumatori": "prelievo_coincidente",
}

# Anagrafica minima, identica a quella dei casi a mano di test_ripartizione.py.
MEMBRI = {
    "P1": {"ruolo": "produttore", "impresa": True},
    "C1": {"ruolo": "consumatore", "impresa": False},
    "C2": {"ruolo": "consumatore", "impresa": True},  # impresa: fuori dall'eccedentario
}
IMMESSA = {"P1": D(500)}
CONSUMO = {"C1": D(200), "C2": D(100)}

BASE = """\
[quote]
produttori = "0.50"
consumatori = "0.50"

[criteri]
produttori = "energia_immessa"
consumatori = "prelievo_coincidente"
"""


def messaggio(testo_toml: str) -> str:
    """Valida un TOML che deve fallire e ritorna il messaggio d'errore."""
    with pytest.raises(ErroreRegole) as errore:
        da_testo(testo_toml)
    return str(errore.value)


# --- il giro completo: file -> regole -> riparto ----------------------------------


def test_esempio_uguale_al_dict_scritto_a_mano():
    # Il file di esempio deve produrre esattamente le regole che la demo ha nel codice.
    # Decimal("0.10") e Decimal("0.1") sono numericamente uguali: il confronto fra dict
    # non distingue la scala, ed è giusto così (è lo stesso 10%).
    assert leggi(ESEMPIO) == REGOLE_A_MANO


def test_giro_completo_toml_stesso_riparto_del_dict_a_mano():
    # Caso a mano, base 100,00 € (10000 cent) ed eccedentario 12,00 € (1200 cent):
    #   fondo gestione = arrotonda(10000 × 0,10) = 1000 cent = 10,00 €
    #   residuo = 10000 − 1000 = 9000, diviso 0,50/0,50:
    #     blocco produttori 4500 ; blocco consumatori 4500 (divisione esatta)
    #   produttori, criterio energia_immessa: P1 è l'unico, prende tutti i 4500.
    #   consumatori, criterio prelievo_coincidente, pesi C1=200 e C2=100 (totale 300):
    #     C1 = 4500 × 200/300 = 3000 cent = 30,00 €
    #     C2 = 4500 × 100/300 = 1500 cent = 15,00 €
    #   eccedentario 1200 cent: solo consumatori non imprese → C1 da solo → 1200.
    #   Totale: 1000 + 4500 + 3000 + 1500 + 1200 = 11200 = 10000 + 1200.
    regole = leggi(ESEMPIO)
    esito = ripartisci(regole, 10000, 1200, IMMESSA, CONSUMO, MEMBRI)

    assert esito["_fondi"]["gestione"] == 1000
    assert esito["P1"]["quota_produttore"] == 4500
    assert esito["C1"]["quota_consumatore"] == 3000
    assert esito["C2"]["quota_consumatore"] == 1500
    assert esito["C1"]["quota_eccedentaria"] == 1200
    assert sum(v for d in esito.values() for v in d.values()) == 11200

    # e soprattutto: identico al riparto fatto con le regole scritte a mano.
    assert esito == ripartisci(REGOLE_A_MANO, 10000, 1200, IMMESSA, CONSUMO, MEMBRI)


def test_percentuale_dalla_stringa_e_non_dal_float():
    # Il caso che giustifica l'obbligo delle virgolette, risolto a mano su un importo
    # minuscolo perché la differenza si veda in un centesimo intero.
    # Fondo al 35% su un incentivo di 0,10 € (10 centesimi):
    #   dalla stringa: Decimal("0.35") × 10 = 3,50 → ROUND_HALF_UP → 4 centesimi
    #   dal float:     Decimal(0.35) = 0,34999999999999997779553950749686919…
    #                  × 10 = 3,4999999999999997779… → ROUND_HALF_UP → 3 centesimi
    # Un centesimo di differenza sul fondo, e a cascata sul residuo dei soci:
    #   residuo = 10 − 4 = 6 → 3 al blocco produttori e 3 ai consumatori
    #   P1 unico produttore → 3 ; consumatori pesi 200:100 → C1 = 2, C2 = 1
    #   Totale: 4 + 3 + 2 + 1 = 10 centesimi.
    regole = da_testo('[fondi]\ngestione = "0.35"\n\n' + BASE)
    assert regole["fondi"]["gestione"] == D("0.35")

    esito = ripartisci(regole, 10, 0, IMMESSA, CONSUMO, MEMBRI)
    assert esito["_fondi"]["gestione"] == 4
    assert esito["P1"]["quota_produttore"] == 3
    assert esito["C1"]["quota_consumatore"] == 2
    assert esito["C2"]["quota_consumatore"] == 1
    assert sum(v for d in esito.values() for v in d.values()) == 10

    # La strada scartata, verificata qui perché non resti un'affermazione teorica:
    # passando dal float lo stesso statuto tratterrebbe 3 centesimi invece di 4.
    dal_float = (D(0.35) * 10).quantize(D(1), rounding=ROUND_HALF_UP)
    assert dal_float == 3 != esito["_fondi"]["gestione"]


def test_quote_sessanta_quaranta_caso_a_mano():
    # Statuto che premia chi ha investito nell'impianto: 60% ai produttori.
    # Base 100,00 €: fondo gestione 1000 cent, residuo 9000, quote 0,60/0,40:
    #   blocco produttori = 9000 × 0,60 = 5400 cent = 54,00 €
    #   blocco consumatori = 9000 × 0,40 = 3600 cent = 36,00 € (divisioni esatte)
    #   P1 unico produttore → 5400.
    #   consumatori pro-quota 200:100 → C1 = 3600 × 2/3 = 2400 ; C2 = 1200.
    #   Totale: 1000 + 5400 + 2400 + 1200 = 10000.
    regole = da_testo(
        '[fondi]\ngestione = "0.10"\n\n'
        '[quote]\nproduttori = "0.60"\nconsumatori = "0.40"\n\n'
        '[criteri]\nproduttori = "energia_immessa"\n'
        'consumatori = "prelievo_coincidente"\n'
    )
    esito = ripartisci(regole, 10000, 0, IMMESSA, CONSUMO, MEMBRI)
    assert esito["P1"]["quota_produttore"] == 5400
    assert esito["C1"]["quota_consumatore"] == 2400
    assert esito["C2"]["quota_consumatore"] == 1200
    assert sum(v for d in esito.values() for v in d.values()) == 10000


def test_virgola_come_separatore_decimale():
    # Un socio italiano scrive "0,55", non "0.55": la conversione avviene su testo,
    # quindi resta esatta. 0,55 + 0,45 = 1,00 e le quote chiudono.
    regole = da_testo(
        '[quote]\nproduttori = "0,55"\nconsumatori = "0,45"\n\n'
        '[criteri]\nproduttori = "quote_uguali"\nconsumatori = "quote_uguali"\n'
    )
    assert regole["quota_produttori"] == D("0.55")
    assert regole["quota_consumatori"] == D("0.45")


def test_interi_ammessi_senza_virgolette():
    # Gli interi in TOML sono esatti: niente da nascondere, si accettano nudi.
    # Statuto che dà tutto ai produttori (quota consumatori zero), base 100,00 €
    # senza fondi: blocco produttori 10000, blocco consumatori 0.
    #   P1 unico produttore → 10000 cent = 100,00 € ; C1 e C2 → 0 ciascuno.
    regole = da_testo(
        "[quote]\nproduttori = 1\nconsumatori = 0\n\n"
        '[criteri]\nproduttori = "energia_immessa"\n'
        'consumatori = "prelievo_coincidente"\n'
    )
    assert regole["quota_produttori"] == D(1)
    assert regole["quota_consumatori"] == D(0)
    esito = ripartisci(regole, 10000, 0, IMMESSA, CONSUMO, MEMBRI)
    assert esito["P1"]["quota_produttore"] == 10000
    assert esito["C1"]["quota_consumatore"] == 0
    assert esito["C2"]["quota_consumatore"] == 0
    assert sum(v for d in esito.values() for v in d.values()) == 10000


def test_sezione_fondi_facoltativa_ma_chiave_sempre_presente():
    # Senza [fondi] non si trattiene nulla, e la chiave in uscita c'è lo stesso: il
    # chiamante non deve distinguere "nessun fondo" da "regole scritte a metà".
    regole = da_testo(BASE)
    assert regole["fondi"] == {}
    esito = ripartisci(regole, 10000, 0, IMMESSA, CONSUMO, MEMBRI)
    assert esito["_fondi"] == {}
    assert esito["P1"]["quota_produttore"] == 5000  # niente fondi: metà piena
    assert sum(v for d in esito.values() for v in d.values()) == 10000


def test_piu_fondi_con_nomi_liberi():
    # I nomi dei fondi sono liberi (finiscono così come sono nel rendiconto) e la
    # somma può arrivare fino a 1. Qui 0,10 + 0,05 = 0,15, ben sotto.
    regole = da_testo('[fondi]\ngestione = "0.10"\nsolidarieta = "0.05"\n\n' + BASE)
    assert regole["fondi"] == {"gestione": D("0.10"), "solidarieta": D("0.05")}


def test_leggi_e_da_testo_danno_lo_stesso_risultato(tmp_path):
    # L'adapter non aggiunge aritmetica propria: apre il file e delega alla parte pura.
    f = tmp_path / "statuto.toml"
    f.write_text(BASE, encoding="utf-8")
    assert leggi(f) == da_testo(BASE)


def test_valida_non_modifica_la_struttura_in_ingresso():
    # `valida` è pura: niente stato, niente effetti sull'input (che il chiamante
    # potrebbe voler ristampare o riusare).
    dati = {
        "quote": {"produttori": "0.5", "consumatori": "0.5"},
        "criteri": {"produttori": "quote_uguali", "consumatori": "quote_uguali"},
    }
    copia = {k: dict(v) for k, v in dati.items()}
    valida(dati)
    assert dati == copia


# --- errori: struttura del file ---------------------------------------------------


def test_errore_sezione_sconosciuta_con_suggerimento():
    # Il refuso più probabile: [fondo] invece di [fondi]. Senza la guardia, il fondo
    # non verrebbe trattenuto e nessuno se ne accorgerebbe fino al rendiconto.
    testo = messaggio(BASE + '\n[fondo]\ngestione = "0.10"\n')
    assert "sezione sconosciuta 'fondo'" in testo
    assert "forse intendevi 'fondi'" in testo
    assert "Ammesse: quote, criteri, fondi" in testo


def test_errore_chiavi_del_dict_python_al_primo_livello():
    # Chi conosce il dict di __main__.py prova a ricopiarlo piatto: va detto che le
    # regole stanno dentro le sezioni, mostrando la struttura attesa.
    testo = messaggio('quota_produttori = "0.5"\n\n' + BASE)
    assert "sezione sconosciuta 'quota_produttori'" in testo
    assert "[quote]" in testo  # il messaggio contiene l'esempio di struttura


def test_errore_chiave_sconosciuta_dentro_quote():
    # IL caso del compito: un refuso in "produttori" non deve passare in silenzio e
    # far ripartire tutto ai consumatori.
    testo = messaggio(
        '[quote]\nproduttri = "0.50"\nconsumatori = "0.50"\n\n'
        '[criteri]\nproduttori = "energia_immessa"\n'
        'consumatori = "prelievo_coincidente"\n'
    )
    assert "sezione [quote]: chiave sconosciuta 'produttri'" in testo
    assert "forse intendevi 'produttori'" in testo


def test_errore_sezione_quote_mancante():
    testo = messaggio(
        '[criteri]\nproduttori = "energia_immessa"\n'
        'consumatori = "prelievo_coincidente"\n'
    )
    assert "manca la sezione [quote]" in testo
    assert "obbligatoria" in testo


def test_errore_sezione_criteri_mancante():
    testo = messaggio('[quote]\nproduttori = "0.50"\nconsumatori = "0.50"\n')
    assert "manca la sezione [criteri]" in testo


def test_errore_chiave_mancante_in_quote():
    testo = messaggio(
        '[quote]\nproduttori = "1"\n\n'
        '[criteri]\nproduttori = "energia_immessa"\n'
        'consumatori = "prelievo_coincidente"\n'
    )
    assert "sezione [quote]: manca consumatori" in testo
    assert 'consumatori = "0"' in testo  # dice come scrivere il caso a quota zero


def test_errore_chiave_mancante_in_criteri():
    testo = messaggio(
        '[quote]\nproduttori = "0.50"\nconsumatori = "0.50"\n\n'
        '[criteri]\nproduttori = "energia_immessa"\n'
    )
    assert "sezione [criteri]: manca consumatori" in testo
    assert "prelievo_coincidente, quote_uguali" in testo  # elenca i supportati


def test_errore_sezione_che_non_e_una_tabella():
    testo = messaggio('quote = "meta e meta"\n\n[criteri]\nproduttori = "quote_uguali"\n'
                      'consumatori = "quote_uguali"\n')
    assert "[quote] deve essere una sezione" in testo
    assert "un testo" in testo


def test_errore_toml_malformato():
    testo = messaggio("[quote\nprodutt")
    assert "non è TOML valido" in testo


def test_errore_regole_non_sono_una_tabella():
    with pytest.raises(ErroreRegole) as errore:
        valida(["quote", "criteri"])
    assert "devono essere una tabella" in str(errore.value)


# --- errori: quote ----------------------------------------------------------------


def test_errore_quote_che_non_sommano_a_uno():
    # Il messaggio deve dire i due valori e la loro somma: è l'unico modo perché chi
    # legge capisca quale dei due ha sbagliato a scrivere.
    testo = messaggio(
        '[quote]\nproduttori = "0.6"\nconsumatori = "0.5"\n\n'
        '[criteri]\nproduttori = "energia_immessa"\n'
        'consumatori = "prelievo_coincidente"\n'
    )
    assert "produttori (0,6)" in testo
    assert "consumatori (0,5)" in testo
    assert "fanno 1,1" in testo
    assert "devono fare esattamente 1" in testo


def test_errore_quota_negativa():
    # Il bug storico del motore (roadmap punto 7): −0,5 e 1,5 sommano a 1 e passavano
    # la guardia di ripartisci, producendo una quota negativa. Qui non arriva nemmeno
    # al calcolo, e il messaggio spiega che il blocco "pagherebbe".
    testo = messaggio(
        '[quote]\nproduttori = "-0.5"\nconsumatori = "1.5"\n\n'
        '[criteri]\nproduttori = "energia_immessa"\n'
        'consumatori = "prelievo_coincidente"\n'
    )
    assert "quote.produttori: -0,5 è negativa" in testo
    assert "PAGARE" in testo


def test_errore_quota_maggiore_di_uno():
    testo = messaggio(
        '[quote]\nproduttori = "1.5"\nconsumatori = "-0.5"\n\n'
        '[criteri]\nproduttori = "energia_immessa"\n'
        'consumatori = "prelievo_coincidente"\n'
    )
    assert "quote.produttori: 1,5 è maggiore di 1" in testo


def test_errore_percentuale_scritta_come_numero_intero_di_punti():
    # "50" per dire il 50%: errore frequente, e il messaggio deve dire la regola.
    testo = messaggio(
        '[quote]\nproduttori = "50"\nconsumatori = "50"\n\n'
        '[criteri]\nproduttori = "energia_immessa"\n'
        'consumatori = "prelievo_coincidente"\n'
    )
    assert "quote.produttori: 50 è maggiore di 1" in testo
    assert 'il 60% si scrive "0.60"' in testo


# --- errori: fondi ----------------------------------------------------------------


def test_errore_fondo_con_percentuale_negativa():
    testo = messaggio('[fondi]\ngestione = "-0.10"\n\n' + BASE)
    assert "fondi.gestione: -0,10 è negativa" in testo
    assert "crea dal nulla" in testo


def test_errore_fondi_che_assorbono_piu_del_totale():
    # Due fondi al 70%: 140% dell'incentivo, e ai soci un residuo negativo.
    testo = messaggio('[fondi]\ngestione = "0.7"\nriserva = "0.7"\n\n' + BASE)
    assert "i fondi sommano a 1,4" in testo
    assert "gestione 0,7" in testo and "riserva 0,7" in testo
    assert "non possono superare 1" in testo


def test_errore_singolo_fondo_oltre_uno():
    testo = messaggio('[fondi]\ngestione = "1.2"\n\n' + BASE)
    assert "fondi.gestione: 1,2 è maggiore di 1" in testo
    assert 'il 10% si scrive "0.10"' in testo


def test_errore_nome_di_fondo_non_testuale():
    # Non arriva mai da un file TOML (le chiavi sono sempre testo), ma `valida` accetta
    # qualunque mapping: una futura interfaccia potrebbe costruirlo male.
    with pytest.raises(ErroreRegole) as errore:
        valida({
            "fondi": {7: "0.10"},
            "quote": {"produttori": "0.5", "consumatori": "0.5"},
            "criteri": {"produttori": "quote_uguali", "consumatori": "quote_uguali"},
        })
    assert "non è un nome di fondo valido" in str(errore.value)


def test_errore_fondo_senza_nome():
    # In TOML "" = "0.10" è sintatticamente legale: un fondo anonimo comparirebbe nel
    # rendiconto come una riga senza etichetta.
    testo = messaggio('[fondi]\n"" = "0.10"\n\n' + BASE)
    assert "un fondo senza nome" in testo


def test_fondi_che_sommano_esattamente_a_uno_sono_leciti():
    # Bordo legittimo: un esercizio di sola capitalizzazione. Non è un errore, e il
    # riparto lo conferma: ai soci resta zero, l'invariante regge.
    regole = da_testo('[fondi]\ngestione = "0.6"\nriserva = "0.4"\n\n' + BASE)
    esito = ripartisci(regole, 10000, 0, IMMESSA, CONSUMO, MEMBRI)
    assert esito["_fondi"] == {"gestione": 6000, "riserva": 4000}
    assert esito["P1"]["quota_produttore"] == 0
    assert sum(v for d in esito.values() for v in d.values()) == 10000


# --- errori: criteri --------------------------------------------------------------


def test_errore_criterio_non_supportato():
    testo = messaggio(
        '[quote]\nproduttori = "0.50"\nconsumatori = "0.50"\n\n'
        '[criteri]\nproduttori = "energia_immesse"\n'
        'consumatori = "prelievo_coincidente"\n'
    )
    assert "criteri.produttori: 'energia_immesse' non è un criterio supportato" in testo
    assert "forse intendevi 'energia_immessa'" in testo
    assert "energia_immessa, quote_uguali" in testo


def test_errore_criterio_valido_ma_per_l_altro_blocco():
    # "energia_immessa" per i consumatori non è un sinonimo di niente: i consumatori
    # non immettono. L'elenco nel messaggio è quello giusto per il blocco.
    testo = messaggio(
        '[quote]\nproduttori = "0.50"\nconsumatori = "0.50"\n\n'
        '[criteri]\nproduttori = "energia_immessa"\n'
        'consumatori = "energia_immessa"\n'
    )
    assert "criteri.consumatori: 'energia_immessa' non è un criterio supportato" in testo
    assert "prelievo_coincidente, quote_uguali" in testo


def test_errore_criterio_non_e_un_testo():
    testo = messaggio(
        '[quote]\nproduttori = "0.50"\nconsumatori = "0.50"\n\n'
        "[criteri]\nproduttori = 3\n"
        'consumatori = "prelievo_coincidente"\n'
    )
    assert "criteri.produttori: 3 non è un nome di criterio" in testo
    assert 'produttori = "energia_immessa"' in testo


# --- errori: il denaro non passa dai float ----------------------------------------


def test_errore_decimale_non_quotato():
    # Il cuore della scelta di progetto: 0.5 senza virgolette è un float binario.
    testo = messaggio(
        "[quote]\nproduttori = 0.5\nconsumatori = 0.5\n\n"
        '[criteri]\nproduttori = "energia_immessa"\n'
        'consumatori = "prelievo_coincidente"\n'
    )
    assert "quote.produttori: 0.5 è scritto come numero decimale" in testo
    assert "float binari" in testo
    assert 'produttori = "0.5"' in testo  # dice esattamente come riscrivere la riga


def test_errore_decimale_non_quotato_mostra_il_valore_inesatto():
    # Con 0.10 l'inesattezza si vede: il messaggio riporta il numero che arriverebbe
    # davvero al motore, 0,1000000000000000055511151231257827…
    testo = messaggio('[fondi]\ngestione = 0.10\n\n' + BASE)
    assert "fondi.gestione: 0.1 è scritto come numero decimale" in testo
    assert "0,10000000000000000555" in testo


def test_errore_valore_vero_falso():
    # `bool` è sottoclasse di `int` in Python: senza un ramo apposta, `true` sarebbe
    # diventato 1 e lo statuto avrebbe dato tutto ai produttori.
    testo = messaggio(
        "[quote]\nproduttori = true\nconsumatori = false\n\n"
        '[criteri]\nproduttori = "energia_immessa"\n'
        'consumatori = "prelievo_coincidente"\n'
    )
    assert "quote.produttori: true è un valore vero/falso" in testo


def test_errore_stringa_non_numerica():
    testo = messaggio(
        '[quote]\nproduttori = "meta"\nconsumatori = "meta"\n\n'
        '[criteri]\nproduttori = "energia_immessa"\n'
        'consumatori = "prelievo_coincidente"\n'
    )
    assert "quote.produttori: 'meta' non è un numero" in testo
    assert '"0,10"' in testo  # ricorda che la virgola è ammessa


def test_errore_stringa_con_due_separatori():
    # "1,234.5" e "0,1,5" non si toccano: la virgola si converte solo quando è una
    # sola e non c'è già un punto, altrimenti sarebbe un indovinello.
    assert "non è un numero" in messaggio(
        '[fondi]\ngestione = "0,1,5"\n\n' + BASE
    )


def test_errore_valore_non_finito():
    # Decimal accetta "nan" e "Infinity": qui sarebbero denaro non calcolabile, e
    # passerebbero silenziosamente ogni confronto di intervallo (nan < 0 è falso).
    assert "non è un numero finito" in messaggio('[fondi]\ngestione = "nan"\n\n' + BASE)
    assert "non è un numero finito" in messaggio(
        '[fondi]\ngestione = "Infinity"\n\n' + BASE
    )


def test_errore_valore_di_tipo_inatteso():
    # Un elenco al posto di una percentuale (per esempio una quota "per fasce").
    testo = messaggio(
        '[quote]\nproduttori = ["0.5"]\nconsumatori = "0.5"\n\n'
        '[criteri]\nproduttori = "energia_immessa"\n'
        'consumatori = "prelievo_coincidente"\n'
    )
    assert "quote.produttori" in testo
    assert "un elenco" in testo


# --- errori dell'adapter ----------------------------------------------------------


def test_errore_file_non_trovato(tmp_path):
    with pytest.raises(ErroreRegole) as errore:
        leggi(tmp_path / "statuto-che-non-esiste.toml")
    assert "file delle regole non trovato" in str(errore.value)
    assert "statuto-che-non-esiste.toml" in str(errore.value)


def test_errore_di_validazione_prefissato_col_nome_del_file(tmp_path):
    # Chi corregge uno statuto ha spesso più file aperti: il messaggio deve dire quale.
    f = tmp_path / "statuto-2026.toml"
    f.write_text(
        '[quote]\nproduttori = "0.6"\nconsumatori = "0.5"\n\n'
        '[criteri]\nproduttori = "energia_immessa"\n'
        'consumatori = "prelievo_coincidente"\n',
        encoding="utf-8",
    )
    with pytest.raises(ErroreRegole) as errore:
        leggi(f)
    testo = str(errore.value)
    assert "statuto-2026.toml" in testo
    assert "fanno 1,1" in testo


def test_errore_toml_malformato_da_file(tmp_path):
    f = tmp_path / "rotto.toml"
    f.write_text("[quote\n", encoding="utf-8")
    with pytest.raises(ErroreRegole) as errore:
        leggi(f)
    assert "non è TOML valido" in str(errore.value)
    assert "rotto.toml" in str(errore.value)


def test_errore_regole_e_un_value_error():
    # Sottoclasse di ValueError: chi già cattura gli input incoerenti del motore
    # (ripartisci solleva ValueError) non deve cambiare nulla.
    assert issubclass(ErroreRegole, ValueError)
    with pytest.raises(ValueError):
        da_testo("")
