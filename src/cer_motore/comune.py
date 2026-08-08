"""Ciò che più moduli del motore condividono: contesto decimale e formattazione.

Questo modulo NON importa nulla dal pacchetto, ed è la ragione per cui esiste. Il
contesto decimale serve a `tariffe`, `condivisione` e `ripartizione`, ma `ripartizione`
importa già `tariffe`: tenerlo in uno dei tre avrebbe creato un ciclo alla prima volta
che il modulo più in basso ne avesse avuto bisogno. Stessa cosa per le due funzioni di
formattazione, che servivano a `ripartizione`, `rendiconto` e `__main__` ed erano
finite duplicate in tutti e tre.

Regola per chi lo modifica: qui dentro non entra logica di dominio, e non entra un
`from .` di nessun tipo.
"""
from collections.abc import Callable, Sequence
from decimal import Context, Decimal, localcontext
from functools import wraps

CONTESTO = Context(prec=28)
"""Contesto decimale del motore: 28 cifre significative e trap attive.

Il motore si dichiara puro e senza stato, ma l'aritmetica `Decimal` legge precisione,
arrotondamento e trap dal contesto del CHIAMANTE, che è stato globale e mutabile
(`decimal.localcontext`). Misurato l'8 ago 2026 sul codice senza questa costante,
dentro un `localcontext(Context(prec=5))`:

    quota_produttori 0,500001 + quota_consumatori 0,5 = 1,000001, ma la somma
    arrotondata a 5 cifre dà 1,0000: la guardia `qp + qc != 1` NON scatta e uno statuto
    malformato passa. Non si perde denaro — il resto maggiore normalizza sui pesi e
    distribuisce comunque il residuo esatto — ma la stessa CER, ripartita da due
    programmi con precisione diversa, ottiene dall'uno un errore e dall'altro un
    riparto;
    due fondi allo 0,999999 e allo 0,000002 sommano a 1,000001 e passano allo stesso
    modo la guardia `somma > 1`;
    `condivisione.alloca_oraria` muore con `InvalidOperation` invece di attribuire
    l'energia condivisa agli impianti.

E con le trap disattivate (`Context(traps=[])`, che un chiamante può benissimo
impostare) `Decimal("NaN") < 0` non solleva più nulla: restituisce False, quindi ogni
guardia scritta come confronto lascia passare NaN in silenzio.

Le funzioni pubbliche del motore si eseguono perciò in una COPIA di questo contesto,
non in quello ambientale. 28 cifre sono la precisione di default di CPython: il
comportamento storico non cambia di un centesimo (i rendiconti della demo restano
identici byte per byte), cambia che ora è una scelta dichiarata invece di un'eredità.
Il limite resta quello di qualunque precisione finita: due percentuali con più di 28
cifre significative possono ancora sommare a 1 per arrotondamento. Nessuno statuto
scrive una percentuale con 29 cifre.
"""


def nel_contesto_del_motore(funzione: Callable) -> Callable:
    """Esegue la funzione in una copia di `CONTESTO`, qualunque sia quello ambientale.

    `localcontext(ctx)` installa una COPIA di `ctx`: i flag alzati durante il calcolo
    non si accumulano sulla costante di modulo, e il contesto del chiamante viene
    ripristinato all'uscita. La purezza vale quindi in entrambi i versi — il motore non
    legge lo stato globale e non lo sporca.

    Va messo sulle FUNZIONI PUBBLICHE di ingresso, non su ogni funzione interna:
    entrare e uscire da un contesto costa (misurato: +24% su `ripartisci_centesimi`,
    che il motore chiama una volta per ora), e un chiamante interno è già dentro al
    contesto di chi lo ha invocato. Le funzioni interne che fanno solo aritmetica
    stanno nude e si affidano al proprio chiamante.
    """

    @wraps(funzione)
    def avvolta(*args, **kwargs):
        with localcontext(CONTESTO):
            return funzione(*args, **kwargs)

    return avvolta


def in_euro(cent: int) -> str:
    """Importo in centesimi reso in euro, per rendiconti e messaggi d'errore.

    Si chiama `in_euro` e non `euro` per simmetria con `ripartizione.in_centesimi`, e
    perche' quella funzione ha un parametro chiamato `euro` che ombreggerebbe questa.
    """
    return f"{Decimal(cent) / 100:.2f} €"


def elenco(voci: Sequence[str]) -> str:
    """Elenco di valori ammessi per i messaggi d'errore: `'a', 'b' o 'c'`.

    Uno solo per tutto il motore, e con gli apici: senza, un elenco di valori che
    contengono spazi o virgole diventa illeggibile, e il socio non distingue dove
    finisce un valore e comincia il successivo.
    """
    virgolette = [f"{v!r}" for v in voci]
    if len(virgolette) < 2:
        return "".join(virgolette)
    return ", ".join(virgolette[:-1]) + " o " + virgolette[-1]
