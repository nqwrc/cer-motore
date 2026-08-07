# Le regole di ripartizione in un file

Aggiornata al 7 agosto 2026.

La ripartizione interna di una CER è materia **statutaria**: le Regole Operative GSE
impongono che esista un soggetto responsabile del riparto e vincolano la destinazione
dell'importo eccedentario (pag. 41-42), ma su come i soci si dividono il denaro decide
lo statuto. Vedi [`FORMULE.md`](FORMULE.md) §5.

Questo documento descrive il file in cui quello statuto si scrive. L'obiettivo è che un
socio non programmatore possa leggerlo, contestarlo in assemblea e correggerlo senza
toccare il codice. Esempio commentato pronto all'uso:
[`../regole-esempio.toml`](../regole-esempio.toml).

## In due righe

```python
from cer_motore.regole import leggi
regole = leggi("regole-esempio.toml")   # -> il dict che ripartizione.ripartisci si aspetta
```

Il formato è **TOML** ([toml.io](https://toml.io/it/)), letto con `tomllib`, che sta
nella libreria standard da Python 3.11: nessuna dipendenza in più. Le righe che iniziano
con `#` sono commenti e servono a citare l'articolo dello statuto o la delibera che ha
deciso il numero.

## Esempio completo

```toml
[fondi]
gestione = "0.10"

[quote]
produttori = "0.50"
consumatori = "0.50"

[criteri]
produttori = "energia_immessa"
consumatori = "prelievo_coincidente"
```

Si legge così: si trattiene il 10% per la gestione; il 90% che resta si divide a metà
fra il blocco di chi immette e il blocco di chi consuma; dentro il primo blocco si
ripartisce in proporzione ai kWh immessi, dentro il secondo in proporzione all'energia
prelevata nelle ore in cui la comunità ha condiviso energia.

## Come si scrivono le percentuali

**Fra virgolette, come frazione di 1**: il 10% è `"0.10"`, la metà `"0.50"`, il 100%
`"1"`. Si accetta anche la virgola italiana: `"0,10"`.

Le virgolette non sono un vezzo. Un numero decimale scritto senza (`gestione = 0.10`) è
per il TOML un *float binario*, e in binario 0,10 non esiste: arriva al motore come
0,1000000000000000055511151231257827…, e 0,35 come 0,34999999999999997779… Su un
incentivo di 0,10 € un fondo del 35% vale 4 centesimi calcolato sul numero scritto e 3
centesimi calcolato sul float — il test
`test_percentuale_dalla_stringa_e_non_dal_float` in `tests/test_regole.py` lo mostra con
i numeri. Il motore quindi **rifiuta** i decimali non quotati, con un errore che dice
come riscrivere la riga.

Conseguenze accettate: il file è un po' meno naturale da scrivere per chi conosce il
TOML, e chi incolla un numero da un foglio di calcolo prende un errore. In cambio, non
esiste il caso in cui il rendiconto sbaglia di qualche centesimo senza che nessuno se ne
accorga. Gli **interi** restano ammessi senza virgolette (`produttori = 1`): in TOML
sono esatti, non c'è niente da nascondere.

## I campi, uno per uno

### `[fondi]` — facoltativa

Percentuali trattenute sull'incentivo **prima** di ogni altro riparto, sulla sola quota
non eccedentaria. I nomi dei fondi sono liberi e compaiono così come sono scritti nel
rendiconto.

| | |
|---|---|
| Valori ammessi | percentuali fra `"0"` e `"1"`, somma dei fondi ≤ 1 |
| Se manca la sezione | nessun fondo: tutto l'incentivo va ai soci |
| Se un fondo è negativo | **errore**: creerebbe denaro dal nulla, il riparto distribuirebbe più dell'incassato |
| Se la somma supera 1 | **errore**: i fondi assorbirebbero più del totale e ai soci resterebbe un residuo negativo |

Somma esattamente 1 è invece legittima (un esercizio di sola capitalizzazione): i soci
prendono zero e il rendiconto lo dice.

Nota: se si dichiara un fondo chiamato `finalita_sociali`, l'importo eccedentario che
non trova consumatori idonei ci finisce dentro sommandosi. È voluto — è lo stesso
capitolo — ma nel rendiconto le due provenienze non si distinguono.

### `[quote]` — obbligatoria

Come si divide fra i due blocchi quello che resta dopo i fondi.

| Chiave | Significato |
|---|---|
| `produttori` | quota del blocco di chi immette energia (produttori e prosumer) |
| `consumatori` | quota del blocco di chi la consuma (consumatori e prosumer) |

| | |
|---|---|
| Valori ammessi | percentuali fra `"0"` e `"1"` |
| Vincolo | le due quote devono sommare **esattamente a 1** |
| Se la sezione manca | **errore**: il motore non indovina come si divide il denaro |
| Se manca una delle due chiavi | **errore**: vanno scritte entrambe, anche quando una è `"0"` |
| Se una è negativa | **errore**: non toglie denaro a quel blocco, glielo fa *pagare*, perché l'altro supera il residuo |
| Se non sommano a 1 | **errore**, con i due valori e la loro somma nel messaggio |

Per trattenere una parte del residuo si **aggiunge un fondo**, non si abbassano le
quote: le quote che non chiudono a 1 sono quasi sempre un errore di battitura.

Chi è **prosumer** appartiene a entrambi i blocchi e riceve due quote distinte, che nel
rendiconto restano su due righe.

### `[criteri]` — obbligatoria

Come si ripartisce *dentro* ciascun blocco.

| Chiave | Valori ammessi |
|---|---|
| `produttori` | `"energia_immessa"`, `"quote_uguali"` |
| `consumatori` | `"prelievo_coincidente"`, `"quote_uguali"` |

- `energia_immessa` — in proporzione ai kWh immessi in rete nel periodo.
- `prelievo_coincidente` — in proporzione all'energia prelevata **nelle ore in cui la
  comunità ha condiviso energia**. È il criterio più diffuso: premia chi sposta i
  consumi quando l'impianto produce, che è anche ciò che fa crescere l'incentivo di
  tutti. Come è calcolato: `FORMULE.md` §1-bis.
- `quote_uguali` — parti uguali fra i membri del blocco, indipendentemente dai kWh.

| | |
|---|---|
| Se la sezione o una chiave manca | **errore**: il criterio va detto, non ereditato da un default silenzioso |
| Se il criterio non è fra quelli elencati | **errore**, con l'elenco dei supportati e il suggerimento del più simile |

I due elenchi sono diversi apposta: `energia_immessa` per i consumatori non ha senso
(non immettono) ed è un errore, non un sinonimo.

## Che cosa **non** si decide in questo file

- **Tariffe, soglie, correttivi geografici**: non sono scelte della comunità, sono legge
  (DM CACER 414/2023, Regole Operative GSE). Stanno in `tariffe.py`, ognuna con fonte e
  data. Un file di regole non può ridefinirle — è una delle ragioni per cui ogni chiave
  fuori schema è un errore invece che un valore ignorato.
- **La destinazione dell'importo eccedentario**: vincolata dalle Regole Operative
  (pag. 41) ai soli consumatori diversi dalle imprese e alle finalità sociali sui
  territori degli impianti. Il motore la applica da sé; lo statuto non può derogarvi.
- **Chi sono i soci e che ruolo hanno**: l'anagrafica (`membri`) è un input a parte.

## Perché una chiave sconosciuta è un errore

Perché il danno di un refuso non è un file che non parte, ma un file che parte e
ripartisce male. Se `produttori` diventasse `produttri` e la chiave venisse ignorata,
il motore userebbe un default e il denaro finirebbe altrove, in silenzio, fino a quando
un socio non contesta il rendiconto. Il motore quindi rifiuta ogni chiave che non
conosce e, quando la parola somiglia a una ammessa, la suggerisce:

```
sezione [quote]: chiave sconosciuta 'produttri'; forse intendevi 'produttori'.
Ammesse: produttori, consumatori.
```

La validazione si ferma al **primo** problema: chi legge il messaggio è un socio, non un
compilatore, e dieci errori a cascata generati da un refuso sarebbero meno utili di uno
solo, giusto.

## L'API, per chi scrive codice

| Funzione | I/O | A cosa serve |
|---|---|---|
| `regole.valida(dati)` | no | valida e converte una struttura già caricata. È il motore puro |
| `regole.da_testo(testo)` | no | analizza una stringa TOML e la valida (`tomllib.loads` non tocca il disco) |
| `regole.leggi(percorso)` | **sì** | apre il file e delega. È l'unica funzione del modulo che fa I/O |

Tutti gli errori sono `regole.ErroreRegole`, sottoclasse di `ValueError`. `leggi`
prefissa ogni messaggio col nome del file.

Il valore di ritorno è esattamente il dict che
[`ripartizione.ripartisci`](../src/cer_motore/ripartizione.py) si aspetta, con le
percentuali in `Decimal`:

```python
{"fondi": {"gestione": Decimal("0.10")},
 "quota_produttori": Decimal("0.50"),
 "quota_consumatori": Decimal("0.50"),
 "criterio_produttori": "energia_immessa",
 "criterio_consumatori": "prelievo_coincidente"}
```

`fondi` c'è sempre, eventualmente vuoto: il chiamante non deve distinguere "nessun
fondo" da "regole scritte a metà".

## Punti aperti

- **Nessuna regola dipendente dal tempo**: uno statuto modificato a metà anno oggi si
  rappresenta con due file e due esecuzioni. Se le CER reali lo fanno spesso, servirà
  una data di validità nel file.
- **Nessuna quota nominale per singolo socio** (del tipo "al socio X spetta il 5%"):
  oggi si può solo scegliere un criterio per blocco. È la richiesta più probabile dalle
  interviste, ma va disegnata sapendo che convive con l'invariante al centesimo.
- **`criteri.consumatori` è usato anche per l'importo eccedentario** da `ripartisci`,
  senza che il file possa dire altrimenti: se uno statuto volesse un criterio diverso
  per l'eccedentario, servirebbe un campo in più.
