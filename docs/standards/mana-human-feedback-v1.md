# Mana Human Feedback v1

## Decisione

Mana è proprietario dei contributi umani associati agli artefatti prodotti. I
client inviano richieste strutturate al comando `mana human-feedback`; non
scrivono `.mana`, non modificano il Markdown prodotto e non deducono decisioni
dal testo renderizzato.

Il registro canonico è locale al progetto in `.mana/human-feedback`. I file di
thread e decisione sono dati canonici; una risposta `list`, un report o una
vista Familiar sono proiezioni di lettura.

Gli indici per target in `.mana/human-feedback/indexes` sono cache derivate,
mai fonte canonica. Le mutazioni li pubblicano con rename atomico sotto il
lock; `list` valida un indice presente e legge soltanto i thread riferiti. Se
l'indice manca (per esempio dopo un crash tra il record canonico e la cache),
la lettura esegue la scansione canonica senza creare o riparare file. Un indice
malformato, symlink o che riferisce un record indisponibile è rifiutato: non è
lecito restituire un sottoinsieme silenzioso dei contributi.

## Identità e limiti

- Un target contiene `artifactId`, `artifactRevision` e `sectionId` opzionale.
  La revisione viene dal producer; un heading del reader non è un'identità
  valida in assenza del riferimento emesso dal producer.
- Thread e option ID devono avere il formato sicuro del comando. I decision ID
  restano ID logici: il loro nome file è `sha256(decisionId)`, e il valore
  originale viene verificato nel record. Componenti `.` e `..`, slash ripetuti
  e path non sicuri sono rifiutati.
- Il corpo Markdown può contenere al massimo 65.536 byte UTF-8. È conservato
  separatamente dall'artefatto e il decoder stdin conserva i newline finali.
- L'autore è una dichiarazione locale, mai un'identità autenticata: accetta
  Unicode e spazi, fino a 128 byte UTF-8, senza tab/newline.
- L'idempotency key è 1–128 caratteri `[A-Za-z0-9][A-Za-z0-9._:-]*` e vale
  soltanto entro il progetto.

## Operazioni

`capabilities` restituisce `mana.human-feedback.capabilities/v1`; il client
deve negoziare questa risposta prima di mostrare un'azione come disponibile.
`list` restituisce `mana.human-feedback.threads/v1` e non crea directory o
record, anche se `.mana` non esiste. Accetta `--limit 1..200` e un
`--cursor` che è l'ultimo `threadId` della pagina precedente; la risposta
ordinata contiene `nextCursor` e `viewRevision`. Una mutazione cambia
`viewRevision`: il consumer deve ricominciare dalla prima pagina invece di
unire pagine da viste diverse. `operation --operation-id` restituisce
`mana.human-feedback.operation-status/v1` con `persisted`,
`outcome_to_verify` o `unknown`.

Le mutazioni sono `create`, `reply`, `resolve`, `reopen` e `decide`. Per v2,
`decision-targets --decision-source <path>` legge un piano Story Start
pubblicato e restituisce decisioni e opzioni con hash `sourceRevision`.
`decide` richiede lo stesso path e hash, e rifiuta ID/opzione estranei o una
fonte stale prima di creare un record. La decisione conserva una scelta umana e
dichiara `replanning_required`; non costituisce approvazione del piano e non
avvia provider. Al successivo Story Start v2 il producer legge una fotografia
immutabile delle scelte del solo workspace attivo e la passa a Discovery.
Discovery deve preservare domanda, owner, materialita e alternative, dichiarando
la decisione `resolved` con l'opzione registrata. Il host verifica la scelta,
poi il governor impone lo stesso registro a Triage e Planner. Omissioni,
contraddizioni e alternative cambiate bloccano la nuova pubblicazione.

I nuovi record conservano il descrittore e lo story ID oltre al path/hash della
fonte. Questo mantiene il collegamento attraverso gli ID derivati dal contenuto
che cambiano quando la decisione viene risolta. Una nuova scelta esplicita sul
piano rigenerato dichiara le coppie ID/revisione precedenti in `supersedes`, conservandone la
storia. I record v1 precedenti privi di descrittore vengono accettati soltanto
se il loro hash coincide ancora con la fonte: altrimenti richiedono una nuova
registrazione esplicita. Il consumo non promuove scope e non approva il piano.
`validation/story-start-human-decisions-v1.json` conserva la fotografia
verificata; il run status rimane il commit marker pubblicato per ultimo.

## Commit, concorrenza e recupero

Le letture non acquisiscono lock e non inizializzano lo storage. Ogni mutazione
crea lo storage e acquisisce un lock di scrittura per progetto tramite
`mkdir(.mana/human-feedback/locks/write.lock)`. Il lock serializza confronto
revisione e pubblicazione; due richieste sulla stessa revisione producono una
sola mutazione e un conflitto esplicito. Un contendente attende fino a 30
secondi, così una scrittura in corso raggiunge il controllo revisione anziché
fallire immediatamente al confine del lock.

Il commit point è il rename atomico del record canonico. Prima del commit Mana
pubblica una ricevuta operazione `prepared` con digest e risultato previsto;
dopo il commit la stessa ricevuta diventa `committed`. Un retry con stessa
chiave e digest verifica anzitutto che il record previsto esista: se esiste,
finalizza la ricevuta; se non esiste, completa il commit mancante sotto lo
stesso lock. Una chiave con digest diverso viene rifiutata. Il lock e i file
temporanei sono strettamente dentro lo storage Human Feedback.

Il processo non può distinguere automaticamente un crash fra rename del record
e aggiornamento della ricevuta da un ACK perso: per questo il client deve
consultare `operation` prima di dichiarare un fallimento definitivo. Il
recupero dopo una terminazione del processo che lascia la directory lock
richiede il timeout del comando e un'azione amministrativa esplicita; non
viene eseguita una cancellazione silenziosa del lock.

## Compatibilità e prossimi passi

Il contratto non modifica `mana inspect` v1. Producer vecchi, snapshot e
target senza capability restano in sola lettura. Una futura v2 deve aggiungere
target strutturati per decisioni, paginazione, stato di collegamento dopo
rigenerazione e consumo verificato nel planning context Story Start. Questi
cambiamenti richiedono fixture, schema e una versione capability nuova.

`list-history` restituisce `mana.human-feedback.thread-history/v1` per lo
stesso artefatto/sezione attraverso revisioni diverse. Ogni thread conserva il
target originario. Per il report Story Start v2, `targets` espone il manifesto
producer-owned `mana.story-start.feedback-targets/v1`: un `sectionId` stabile
e un `headingIndex` valido solo come locatore nell'esatta revisione pubblicata.
Con quel manifesto `list-history` dichiara `valid`, `changed`, `missing` o
`ambiguous`; una sezione assente o duplicata non viene mai riagganciata dal
titolo Markdown. Artefatti legacy o senza capability restano commentabili a
livello documento e usano soltanto `valid`/`changed` per la revisione.

Inspect announces `human_feedback` only for a Mana project when its bundled
Human Feedback command is present. Familiar additionally negotiates the command
operations. Public Story Start publishes
`planning/story-start-scope-v2.feedback-targets-v1.json` before the final run
marker; its revision is the exact rendered Markdown SHA-256. Clients must not
invent section identities when the capability or manifest is absent.
