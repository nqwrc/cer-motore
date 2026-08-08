"""Contratto di impacchettamento: versione, licenza e metadati dichiarati.

Non verificano il calcolo ma le promesse che il pacchetto fa a chi lo installa, ed è
il genere di cose che si rompe in silenzio: un pyproject sbagliato non fa fallire
nessun test di dominio, si vede solo il giorno della pubblicazione.
"""
from importlib.metadata import PackageNotFoundError, metadata, version
from pathlib import Path

import pytest

import cer_motore

# `pyproject.toml` imposta `pythonpath = ["src"]` proprio perche' la suite giri anche su
# un checkout non installato. Questi casi pero' interrogano i METADATI della
# distribuzione, che senza installazione non esistono: verificato su un checkout pulito
# col solo pytest, fallivano tutti e quattro con PackageNotFoundError, quattro rossi che
# non c'entravano nulla col lavoro di chi li vedeva. Verificano un contratto di
# impacchettamento: quando non c'e' un pacchetto, non c'e' contratto da verificare.
try:
    METADATI = metadata("cer-motore")
    VERSIONE_INSTALLATA = version("cer-motore")
except PackageNotFoundError:  # pragma: no cover - dipende dall'ambiente, non dal codice
    METADATI = VERSIONE_INSTALLATA = None

serve_installazione = pytest.mark.skipif(
    METADATI is None,
    reason='pacchetto non installato: esegui `pip install -e ".[dev]"` per questi casi',
)


@serve_installazione
def test_la_versione_ha_una_fonte_sola():
    # `pyproject.toml` dichiara `dynamic = ["version"]` e la legge da
    # `cer_motore.__version__`. Se qualcuno reintroducesse un `version = "..."` statico
    # nel pyproject, i due numeri divergerebbero al primo aggiornamento dimenticato:
    # qui si romperebbe subito invece che sul pacchetto pubblicato.
    assert VERSIONE_INSTALLATA == cer_motore.__version__


@serve_installazione
def test_il_progetto_e_ancora_uno_spike_e_lo_dichiara():
    # Coerenza fra la versione e ciò che il progetto dice di sé. Finché il motore
    # lavora solo su dati mock (roadmap 9) resta su 0.0.x, e il classificatore deve
    # dire la stessa cosa: promettere "Alpha" o più sarebbe una promessa che il README
    # smentisce due righe dopo con "Non usare per riparti reali".
    assert cer_motore.__version__.startswith("0.0.")
    classifiers = METADATI.get_all("Classifier") or []
    assert "Development Status :: 2 - Pre-Alpha" in classifiers
    # Nessun classificatore di licenza: con l'espressione SPDX di PEP 639 setuptools li
    # considera deprecati, e la licenza sta già nei metadati come License-Expression.
    assert not [c for c in classifiers if c.startswith("License ::")]


@serve_installazione
def test_la_licenza_dichiarata_e_quella_del_file():
    # Il repo è pubblico: una licenza dichiarata nei metadati ma assente dal pacchetto
    # è esattamente il buco che il progetto aveva prima dell'8 agosto 2026. Il nome del
    # test promette un confronto col FILE, quindi il file va davvero aperto: `MIT` nei
    # metadati con un LICENSE mancante o di un'altra licenza sarebbe la stessa bugia
    # con un'aria più rispettabile.
    assert METADATI["License-Expression"] == "MIT"
    licenza = Path(__file__).resolve().parent.parent / "LICENSE"
    assert licenza.is_file(), "LICENSE assente accanto al pyproject"
    testo = licenza.read_text(encoding="utf-8")
    assert testo.startswith("MIT License")
    assert "Nicola Pandolfi" in testo


@serve_installazione
def test_il_motore_non_ha_dipendenze_di_runtime():
    # Regola vincolante: solo stdlib nel motore. `pytest` sta nell'extra "dev" e non
    # deve mai diventare una dipendenza di runtime.
    richieste = METADATI.get_all("Requires-Dist") or []
    obbligatorie = [r for r in richieste if "extra ==" not in r]
    assert obbligatorie == [], f"dipendenze di runtime comparse: {obbligatorie}"
