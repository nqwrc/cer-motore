# cer-motore

[![Test](https://github.com/nqwrc/cer-motore/actions/workflows/test.yml/badge.svg)](https://github.com/nqwrc/cer-motore/actions/workflows/test.yml)

**Il motore di calcolo aperto per le comunità energetiche rinnovabili italiane.**

Ogni CER deve fare le stesse tre cose, ogni mese, per 20 anni: capire quanta energia è stata
condivisa, ripartire l'incentivo tra i membri secondo le regole del proprio statuto, produrre
rendiconti che un condomino capisca. Oggi si fa con Excel o con SaaS proprietari. Questo
progetto è la parte noiosa e critica, fatta bene una volta sola: **un motore puro e testato** —
niente piattaforma, niente gestionale.

```
misure orarie (GSE) ──▶ energia condivisa ──▶ incentivo (TIP + ARERA) ──▶ ripartizione statutaria ──▶ rendiconti per membro
```

## Stato: spike (pre-v0.1)

Lavora su **dati mock** (`docs/MOCK-GSE.md`): il formato reale dell'export GSE non è ancora
stato osservato. **Non usare per riparti reali.**

Le formule sono però verificate verbatim sui documenti ufficiali (Regole Operative GSE agg.
16/7/2025 e DM CACER 414/2023), pagina per pagina: `docs/FORMULE.md` riporta le citazioni e
lo stato di ogni regola. Quella verifica, fatta il 7 agosto 2026, ha fatto emergere un errore
nel calcolo dell'importo eccedentario — la norma vuole una differenza in punti percentuali,
il motore ne calcolava una frazione — che sovrastimava l'importo fino al 79%. È corretto.

## Prova subito

Serve **Python 3.11 o superiore** e nient'altro: il motore usa solo la libreria standard.
Il venv non è pignoleria — su Debian, Ubuntu e con Python da Homebrew installare fuori da un
ambiente virtuale si ferma con `externally-managed-environment` (PEP 668).

```bash
git clone https://github.com/nqwrc/cer-motore.git
cd cer-motore
python3 -m venv .venv                                  # su Windows: python -m venv .venv
./.venv/bin/python -m pip install -e ".[dev]"          # Windows: .\.venv\Scripts\python.exe
./.venv/bin/python -m pytest -q                        # i casi risolti a mano
./.venv/bin/python -m cer_motore                       # demo end-to-end su due CER mock
```

La demo genera un mese di misure orarie, calcola energia condivisa, TIP con cap e correttivo
geografico, valorizzazione ARERA, applica regole statutarie dichiarative (fondi, quote
produttori/consumatori) e scrive un rendiconto per membro.

Gli scenari mock sono **due, con lo stesso statuto**: cambia solo la configurazione fisica, e
con essa il rapporto fra energia condivisa ed energia immessa, che è ciò che decide se scatta
il vincolo dell'importo eccedentario (soglia 55%, `docs/FORMULE.md` §4).

| Scenario | Configurazione | EC/EI | Vincolo eccedentario |
|---|---|---:|---|
| `equilibrata` | CER di quartiere: 2 impianti FV (60 e 20 kW), 8 utenze fra case, uffici e un bar | 27,2% | non scatta |
| `concentrata` | CER artigianale: un FV da 30 kW, un'officina, un supermercato, una palestra comunale e 2 famiglie | 97,6% | scatta: 241,72 € dei 567,16 € di tariffa premio |

Il secondo non è un caso di scuola: con un impianto piccolo davanti a grandi consumatori diurni
il prelievo eccede quasi sempre l'immissione, quindi si condivide quasi tutto ciò che si immette
— la situazione che il vincolo eccedentario intende intercettare. Lì l'importo eccedentario va
ai **soli consumatori diversi dalle imprese**: nel rendiconto la colonna corrispondente si
popola per la palestra comunale e le due famiglie, non per l'officina né per il supermercato.

A video la demo stampa il confronto fra i due e il rendiconto completo di `concentrata`. Tutto
ciò che scrive sta sotto `data/`: i CSV in `data/<scenario>/`, i rendiconti completi di entrambi
in `data/rendiconto-<scenario>.md`. Una sola cartella usa-e-getta, da cancellare quando si vuole.

## Principi

Funzioni pure, denaro in `Decimal` e centesimi (invariante: la somma delle quote è il totale,
sempre), ogni formula cita la fonte normativa, ogni parametro che può cambiare è una costante
nominata. Fonti e stato di verifica: [`docs/FORMULE.md`](docs/FORMULE.md).

## Dove trovare il resto

| | |
|---|---|
| Le formule, con citazione verbatim e numero di pagina | [`docs/FORMULE.md`](docs/FORMULE.md) |
| Lo statuto in TOML: schema, campi, errori | [`docs/REGOLE.md`](docs/REGOLE.md) · [`regole-esempio.toml`](regole-esempio.toml) |
| Cosa assume il mock sul formato GSE | [`docs/MOCK-GSE.md`](docs/MOCK-GSE.md) |
| Cosa è fatto e cosa manca | [`docs/ROADMAP.md`](docs/ROADMAP.md) · [`CHANGELOG.md`](CHANGELOG.md) |
| Come contribuire senza rompere le cose che contano | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| Come segnalare un errore di calcolo | [`SECURITY.md`](SECURITY.md) |

## Licenza

[MIT](LICENSE).
