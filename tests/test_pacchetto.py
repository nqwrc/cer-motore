"""Contratto di impacchettamento: versione, licenza e metadati dichiarati.

Non verificano il calcolo ma le promesse che il pacchetto fa a chi lo installa, ed è
il genere di cose che si rompe in silenzio: un pyproject sbagliato non fa fallire
nessun test di dominio, si vede solo il giorno della pubblicazione.
"""
from importlib.metadata import metadata, version

import cer_motore


def test_la_versione_ha_una_fonte_sola():
    # `pyproject.toml` dichiara `dynamic = ["version"]` e la legge da
    # `cer_motore.__version__`. Se qualcuno reintroducesse un `version = "..."` statico
    # nel pyproject, i due numeri divergerebbero al primo aggiornamento dimenticato:
    # qui si romperebbe subito invece che sul pacchetto pubblicato.
    assert version("cer-motore") == cer_motore.__version__


def test_il_progetto_e_ancora_uno_spike_e_lo_dichiara():
    # Coerenza fra la versione e ciò che il progetto dice di sé. Finché il motore
    # lavora solo su dati mock (roadmap 9) resta su 0.0.x, e il classificatore deve
    # dire la stessa cosa: promettere "Alpha" o più sarebbe una promessa che il README
    # smentisce due righe dopo con "Non usare per riparti reali".
    assert cer_motore.__version__.startswith("0.0.")
    classifiers = metadata("cer-motore").get_all("Classifier") or []
    assert "Development Status :: 2 - Pre-Alpha" in classifiers
    # Nessun classificatore di licenza: con l'espressione SPDX di PEP 639 setuptools li
    # considera deprecati, e la licenza sta già nei metadati come License-Expression.
    assert not [c for c in classifiers if c.startswith("License ::")]


def test_la_licenza_dichiarata_e_quella_del_file():
    # Il repo è pubblico: una licenza dichiarata nei metadati ma assente dal pacchetto
    # è esattamente il buco che il progetto aveva prima dell'8 agosto 2026.
    assert metadata("cer-motore")["License-Expression"] == "MIT"


def test_il_motore_non_ha_dipendenze_di_runtime():
    # Regola vincolante: solo stdlib nel motore. `pytest` sta nell'extra "dev" e non
    # deve mai diventare una dipendenza di runtime.
    richieste = metadata("cer-motore").get_all("Requires-Dist") or []
    obbligatorie = [r for r in richieste if "extra ==" not in r]
    assert obbligatorie == [], f"dipendenze di runtime comparse: {obbligatorie}"
