"""cer-motore: motore di calcolo aperto per le comunità energetiche italiane (CER).

Dati GSE in ingresso → regole di ripartizione dichiarative → rendiconti per membro.
"""
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
