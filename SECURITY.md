# Sicurezza

## Il modello di minaccia di questo progetto è diverso dal solito

`cer-motore` è un motore di calcolo puro. Non apre socket, non fa richieste di rete, non
esegue un server, non parla con un database, non ha un'interfaccia web, non gestisce
autenticazione né sessioni, non ha dipendenze di runtime oltre alla libreria standard di
Python. Le funzioni di calcolo non toccano nemmeno il disco: l'I/O vive in tre posti soli
(`mock.py`, `__main__.py` e l'adapter `regole.leggi`).

La superficie di attacco classica, di conseguenza, è quasi nulla — e sarebbe disonesto
scrivere qui il modello di SECURITY.md che si trova ovunque, con la matrice delle versioni
supportate e la promessa di una patch entro 90 giorni.

**La vulnerabilità vera di questo progetto è il calcolo sbagliato.** Questo codice ripartisce
denaro fra i soci di una comunità energetica: un errore in una formula, in un
arrotondamento o nell'interpretazione di una regola GSE non fa crashare nulla e non lascia
tracce nei log. Sposta soldi da un socio a un altro, mese dopo mese, e nessuno se ne accorge
finché qualcuno non rifà i conti a mano. È questo che chiediamo di segnalare, ed è questo che
trattiamo con l'urgenza che altrove si riserva a una RCE.

### Non è un'ipotesi: è già successo

Il 7 agosto 2026 una verifica pagina per pagina sul PDF ufficiale delle Regole Operative ha
trovato che `scomponi_eccedentario` calcolava la quota eccedentaria come
`(rapporto − soglia) / rapporto`, cioè come *frazione* di energia condivisa oltre la soglia,
mentre le Regole Operative (pag. 42) la definiscono come **differenza in punti percentuali**
fra il rapporto energia condivisa / energia immessa e il valore soglia:

```
% E_ACI,ecc,j,n = max[0 ; (E_ACI,j,n / E_immessa,j,n * 100)% − valore soglia]
```

Con rapporto 0,60 e soglia 0,55 la norma dà il 5% del contributo, la vecchia formula ne dava
l'8,33%. **La sovrastima arrivava al +79% a rapporto 0,56**, cioè proprio appena sopra la
soglia, dove ricadono le configurazioni realistiche, e restava dell'11% anche a rapporto
0,90. L'importo eccedentario è quello che va destinato ai soli consumatori diversi dalle
imprese e alle finalità sociali: l'errore toglieva denaro agli altri membri per darlo a
quella categoria, in silenzio, con l'invariante contabile "la somma delle quote è il totale"
perfettamente soddisfatto per tutto il tempo.

Tre test "risolti a mano" **pinnavano i valori sbagliati**, perché erano stati derivati dalla
stessa lettura errata della formula. Nessun test è fallito. Nessuna eccezione è stata
sollevata. La correzione, e i tre test ricalcolati, sono al punto 2 di
[`docs/ROADMAP.md`](docs/ROADMAP.md).

Un secondo caso, dello stesso genere, è documentato nelle guardie di
`ripartizione._valida_eccedentario`: passare la soglia come `55` invece di `0.55` —
percentuale invece di frazione, il refuso più naturale del mondo — **azzerava l'importo
eccedentario senza sollevare nulla e senza produrre numeri assurdi**. Semplicemente non
pagava i consumatori non-imprese. Oggi solleva `ValueError` con un messaggio che spiega il
perché, ma è stato scoperto per fortuna, non da un test.

## Cosa segnalare

Sono i benvenuti, e sono trattati come priorità:

- **Errori di formula**: la funzione non implementa quello che la norma prescrive.
- **Errori di interpretazione normativa**: la formula è implementata correttamente ma la
  lettura del testo GSE, ARERA o MASE è discutibile o sbagliata.
- **Errori di arrotondamento**: centesimi che si creano o si perdono, invarianti di somma
  che non chiudono, incoerenze fra intestazione e tabella di un rendiconto.
- **Parametri normativi obsoleti o errati** in `tariffe.py`: soglie, tariffe base, cap,
  correttivi zonali, valore TIAD. Le Regole Operative sono già state aggiornate tre volte.
- **Casi limite che producono un risultato silenziosamente sbagliato**: valori scambiati fra
  argomenti, unità di misura confuse, percentuali contro frazioni, tipi che attraversano una
  guardia che credevi li fermasse.
- **Regole marcate `[verificato]` in [`docs/FORMULE.md`](docs/FORMULE.md) che verificate non
  sono.** Quella marcatura è una promessa, e va contestata se è falsa.

Sono benvenuti, con meno urgenza, anche i problemi tradizionali: input malformati che fanno
sollevare un'eccezione non gestita o consumare risorse in modo irragionevole nei due punti che
leggono file scritti da qualcun altro: l'adapter `regole.leggi`, che interpreta lo statuto in
TOML, e `mock.carica`, che interpreta i CSV delle misure ed è il codice destinato a diventare
l'adapter dell'export GSE reale.

## Cosa NON è una vulnerabilità qui

Per evitare a entrambi di perdere tempo:

- **Non c'è nulla da esfiltrare.** Nessuna credenziale, nessun token, nessun segreto in
  questo repository, e nessun dato personale: i dati sono generati da `mock.py` con un seme
  fisso, e i nomi dei membri sono etichette inventate.
- **Non c'è nulla da compromettere in esecuzione.** Nessun server, nessuna porta, nessuna
  deserializzazione di dati remoti, nessun `eval`, nessuna chiamata a subprocess.
- **Nessuna dipendenza di runtime**, quindi nessun avviso di CVE transitivo. `pytest` serve
  solo a chi sviluppa e non entra in nulla che venga distribuito.
- **La demo scrive su disco**, di proposito: `python -m cer_motore` crea `./data/` nella
  directory corrente. È documentato, è la sua cartella usa-e-getta ed è ignorata da git.
- **`regole.leggi` legge un file TOML** indicato dall'utente, con `tomllib` della libreria
  standard. Un file di statuto è un documento che chi lo esegue ha scritto o approvato: non è
  input ostile, e il modello non prevede di eseguire statuti di terzi non fidati.
- **Il fatto che il motore non sia certificato dal GSE** non è una vulnerabilità, è lo stato
  dichiarato del progetto. Vedi la sezione qui sotto.
- **Le scelte marcate `[modellazione]` in `docs/FORMULE.md`** — per esempio il criterio di
  attribuzione dell'energia condivisa ai singoli impianti, che la norma non prescrive — non
  sono errori. Discutibili sì, e la discussione è benvenuta come issue: ma sono scelte
  documentate, non bug.

## Come segnalare

**Apri una issue pubblica** su <https://github.com/nqwrc/cer-motore/issues>. È il canale
giusto per praticamente tutto quello che riguarda questo progetto: un errore di calcolo in un
motore open source non è un segreto da custodire finché non c'è una patch, è un avviso che
chiunque lo stia usando ha bisogno di leggere **subito**, perché nel frattempo sta producendo
rendiconti.

Se ritieni davvero che una segnalazione non debba essere pubblica — per esempio perché sai
che una CER sta già ripartendo denaro con la formula sbagliata e vuoi darle il tempo di
fermarsi — usa la **segnalazione privata di GitHub**: scheda *Security* del repository,
pulsante *Report a vulnerability*. È attiva.

Non c'è comunque alcun obbligo di riservatezza a senso unico: se preferisci pubblicare la tua
analisi per conto tuo, fallo pure. E se il canale privato non funzionasse, apri una issue che
dica soltanto che hai qualcosa da segnalare, senza i dettagli.

### Cosa deve contenere la segnalazione

Una segnalazione utile su un errore di calcolo contiene tre cose. Con queste, il problema si
riproduce e si chiude; senza, diventa una conversazione lunga.

1. **La formula.** Quella implementata e quella che secondo te è corretta, scritte per
   esteso. Se il disaccordo è sull'interpretazione, di' esattamente dove le due letture
   divergono.
2. **La fonte, con il numero di pagina.** Documento (Regole Operative CACER, DM CACER
   414/2023, delibera ARERA, ...), paragrafo e pagina. Per le Regole Operative si cita il
   **numero stampato a piè di pagina**, non quello dell'indice del lettore PDF: i due sono
   **sfasati di 1** (l'Appendice B è a pag. stampata 160 = pag. 161 del lettore). Il PDF è
   pubblico e interamente estraibile: link e hash sha256 in fondo a
   [`docs/FORMULE.md`](docs/FORMULE.md). Una citazione verbatim vale più di una parafrasi.
3. **Un caso numerico che diverge.** Gli input esatti, il risultato che dà il motore, il
   risultato che dovrebbe dare, e il calcolo passo per passo che porta al secondo. Idealmente
   nella forma di un test: guarda
   `test_scomponi_eccedentario_insiemi_caso_a_mano` in `tests/test_ripartizione.py` per il
   formato che usiamo. **Non derivare il valore atteso dall'output del codice** — è
   esattamente il modo in cui l'errore del 7 agosto 2026 è sopravvissuto ai suoi test.

Se hai solo uno dei tre pezzi, segnala comunque: un dubbio circostanziato su una formula è
più utile del silenzio. Ma dillo, così sappiamo cosa manca.

## Stato del progetto e uso

Va detto senza giri di parole, perché è la premessa di tutto il resto:

> **`cer-motore` è uno spike su dati mock, in fase pre-v0.1, e non va usato per riparti
> reali.**

Il formato dell'export GSE reale dall'area clienti non è ancora stato osservato: i dati in
ingresso sono generati da `mock.py` secondo un'assunzione documentata in
[`docs/MOCK-GSE.md`](docs/MOCK-GSE.md). Le formule sono verificate verbatim sui documenti
ufficiali, ma la verifica del vincolo eccedentario è applicata al periodo di calcolo mentre
il GSE la esegue **a conguaglio su base annuale**, e il cumulo con il contributo in conto
capitale è modellato solo in parte (manca la partizione dell'energia esente dal fattore F).
Punti aperti aggiornati in [`docs/ROADMAP.md`](docs/ROADMAP.md).

Il progetto non è approvato, validato o certificato dal GSE, da ARERA o da alcuna autorità:
è un'implementazione indipendente, pubblicata perché sia possibile controllarla. Chi lo usa
per prendere decisioni che riguardano denaro di altre persone lo fa sotto la propria
responsabilità, come dice la licenza [MIT](LICENSE), e dovrebbe rifare i conti a mano prima.

## Versioni supportate

Una sola: `main`. Non ci sono ancora release pubblicate e non esistono branch di
manutenzione. Una correzione arriva su `main` e viene annotata nel
[`CHANGELOG.md`](CHANGELOG.md); se sposta denaro, l'entità dello spostamento viene dichiarata
lì con un numero, non con un aggettivo.
