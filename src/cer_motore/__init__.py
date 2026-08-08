"""cer-motore: motore di calcolo aperto per le comunità energetiche italiane (CER).

Dati GSE in ingresso → regole di ripartizione dichiarative → rendiconti per membro.
"""
# FONTE UNICA della versione: `pyproject.toml` la legge da qui
# (`[tool.setuptools.dynamic] version = {attr = "cer_motore.__version__"}`), invece di
# tenerne una copia propria. Due numeri di versione in due file divergono: è solo
# questione di quale dei due qualcuno si dimentica di aggiornare.
#
# 0.0.x è un MARCATORE DI SPIKE, non una release: non esiste alcun tag né alcuna
# pubblicazione, e il CHANGELOG tiene tutto sotto "Non rilasciato". Il progetto passerà
# a 0.1.0 quando il gate dichiarato nella roadmap sarà chiuso — cioè quando esisterà un
# adapter per un export GSE vero e il motore non lavorerà più solo su dati mock.
__version__ = "0.0.1"

from .condivisione import alloca_oraria, contributo_prelievo_coincidente, energia_condivisa
from .ripartizione import (
    InsiemeIncentivato,
    ripartisci,
    ripartisci_centesimi,
    scomponi_eccedentario,
    scomponi_eccedentario_insiemi,
)
from .tariffe import incentivo_periodo, tip_unitaria

__all__ = [
    "energia_condivisa",
    "contributo_prelievo_coincidente",
    "alloca_oraria",
    "tip_unitaria",
    "incentivo_periodo",
    "ripartisci",
    "ripartisci_centesimi",
    "scomponi_eccedentario",
    "scomponi_eccedentario_insiemi",
    "InsiemeIncentivato",
]
