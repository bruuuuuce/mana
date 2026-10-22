# MANA-TRANSACTION-01-T02-S01-D01 — Bounded Resource Continuation

Data: 21 ottobre 2026. Verdetto: **MODEL_DECISION_REQUIRED**.

La bounded resource continuation è rappresentabile con una futura estensione esplicita di T01, ma il modello pubblico corrente non distingue una leaf supportata con ritorno condizionale da una chiamata con ordine di esecuzione irrisolto. Occorre estendere il vocabolario degli eventi o introdurre un witness pubblico discriminante. Si applica la clausola di arresto del punto 1 del mandato: **nessuna implementazione o modifica del contratto pubblico effettuata**. Non viene introdotto un percorso alternativo in T02. Non è un nuovo rifiuto per mancanza di autorizzazione a studiare la neutralità condizionale: il punto di arresto è la rappresentazione pubblica di tale nuova informazione.

## Fattibilità e vincolo preciso

Branch `feature/mana-transaction-02`, HEAD `e3537e3f8c8329a71615fe59d496757d5392c6a8`; indice vuoto. Esaminati direttamente T01, T02, estrattore AST, renderer, Transaction Model v1, Resource Timeline Model v1, contratto MR00, oracoli MR01 e risultati R1/F01. Nessuna delega.

L'estrattore conserva entrambe le chiamate e i loro argomenti/spans. T01 `model.py:530–554` accetta la normale risoluzione dei metodi zero-argument dichiarati nel progetto; la chiamata JDBC con un argomento non ha quel callee risolto e termina nel ramo `UNRESOLVED_CALL`, `continuation: UNKNOWN`, `break`. Nel controesempio il motivo è `AMBIGUOUS_OR_DYNAMIC_DISPATCH`: il field JdbcTemplate non è un bean concreto risolto fra i metodi sorgente. Non si tratta di un'operazione che consuma P1 o richiede una nuova apertura transazionale.

| Concetto | Contratto esistente | Informazione necessaria alla proposta |
|---|---|---|
| Chiamata JDBC riconosciuta | Fatti AST e classificazione T02 limitata al field/API/argomento supportati | Riconoscimento della leaf assunto da T01, distinto dalla conoscenza del testo SQL |
| Fine esplorazione libreria | Callee JDBC non attraversato | Leaf terminale solo per l'esplorazione del callee, non per il corpo chiamante |
| Continuazione chiamante | UNRESOLVED_CALL interrompe l'ordine del corpo | Passo successivo subordinato al ritorno normale e alla conservazione condizionale del contesto |
| Ordine causale | Prefisso verificato; niente passo dopo frontiera irrisolta | Relazione ordinata fra leaf e istruzione successiva, con premesse esplicite |
| Contesto | Stato corrente T01 e lifetime, non semplice copia globale del during | Stesso stato dopo leaf solo sotto il riepilogo condizionale qualificato |
| Effetti non modellati | UNKNOWN, nessun ritorno positivo implicito | Restano limite esplicito; se non esclusi dalle premesse supportate, si interrompe |

Il vocabolario pubblico è chiuso in `model.py:1075–1089`: l'unico evento di invocazione senza frame è `UNRESOLVED_CALL`. `_validate_causal_order` (`983–1021`) lo tratta sempre come passo non risolto. Il renderer (`plantuml.py:177–180`) lo presenta come `remaining order NOT ASSERTED`; T02 (`resources.py:152–175`) proietta operazioni soltanto a quella frontiera. Non c'è un passo pubblico già disponibile per “API riconosciuta, corpo non esplorato, ritorno normale condizionale che preserva lo stato”.

MR00 V4/V10 e gli oracoli C01/C04/C07 separano ordine del corpo e contesto/lifetime: una P viva non autorizza passi dopo ordine perso. C06 mostra invece che UNKNOWN del contesto non implica sempre ordine perso, quando un witness di corpo vuoto esiste. La proposta potrebbe preservare questi principi se introducesse un witness distinto; non è necessario modificare REQUIRED/REQUIRES_NEW/NESTED o indebolire gli oracoli storici. Tuttavia quel witness sarebbe una **estensione del contratto pubblico**, anche mantenendo la stringa di schema v1: questa sessione deve fermarsi prima di introdurlo.

## Alternative esaminate ed escluse

| Tentativo | Risultato / motivo |
|---|---|
| Riutilizzare UNRESOLVED_CALL e aggiungere un altro passo | Rifiuto T01: `body call follows unresolved execution order`; perderebbe la distinzione richiesta |
| Aggiungere soltanto una frase in `assumptions` | Stesso rifiuto; il testo libero non è un witness validato per call site e stato |
| Rendere una stringa `reason` un discriminante operativo | Cambierebbe il significato pubblico dell'evento per validator, renderer e consumer: estensione semantica, non soluzione senza modifica del modello |
| Nuovo evento illustrativo `RESOURCE_LEAF` | Rifiuto T01: `unrecognized transaction event`; serve approvare tale estensione o un equivalente strutturato |
| Cancellare l'evento JDBC | Un modello senza passi del corpo può validare, ma T02 conserva entrambe le operazioni UNPLACED: cancellare non dimostra un percorso |
| Fabbricare un frame callee JDBC | Mancano un metodo zero-argument dichiarato e la sua evidenza sorgente; sarebbe falsa provenienza. `bodyTraversal: STRAIGHT_LINE` non significa leaf esterna con corpo opaco |
| Usare `contextComposition` F02 | Riguarda alternative APPLIED/BYPASSED su confini risolti; non riepiloghi di effetti di API esterne |
| Posizionare il suffisso direttamente in T02 | Aggira l'autorità T01 ed è vietato dal mandato |

I primi, secondo, quarto e quinto tentativo sono stati esercitati su oggetti esterni/in memoria, senza modificare il motore. I risultati mostrano il comportamento attuale, non una prova di completezza del validator: il caso con eventi cancellati evidenzia precisamente la differenza tra validità strutturale e testimonianza del percorso.

## Contratto sintetico proposto, non implementato

Questa è una proposta da sottoporre alla decisione sul modello, **non una nuova regola normativa del v1**. Nome, campi, versione e compatibilità del witness rimangono da decidere.

1. **Leaf e provenienza.** T01 riconosce un sottoinsieme chiuso di API JdbcTemplate, receiver/binding e forma degli argomenti. Registra il call site e le evidenze del riconoscimento. Non attraversa la libreria. Il riconoscimento di una API non equivale a enlistment né alla risoluzione di ogni SQL; overload/dispatch o argomenti non qualificabili restano incerti. Le variabili `sqlA/sqlB/sqlC` dell'esempio non diventano automaticamente risolte dal parser attuale.
2. **Premesse esplicite.** Il witness deve dichiarare chiamata sincrona, assenza di callback applicativi non risolti, ritorno normale condizionale e assenza, nel riepilogo supportato, di modifiche non modellate al contesto. Non è una conclusione generale su tutte le implementazioni JDBC, driver, sottoclassi o advisor runtime.
3. **Stato autorevole.** Al passo leaf, T01 fornisce lo stato corrente e ne verifica identità, manager, lifetime e non sospensione. La continuazione conserva quello stato soltanto sotto le premesse del witness. Nessuna allocazione di P aggiuntiva, nessun motore di propagation T02.
4. **Percorso normale.** La seconda invocazione richiede il ritorno normale della prima; la terza richiede quelli della prima e della seconda. L'ordine è una catena condizionale di call site, mai prova di esecuzione reale o di riuscita del SQL. Il witness deve essere disponibile ai consumer per evitare che il suffisso appaia incondizionato.
5. **Percorso eccezionale.** Una leaf può terminare eccezionalmente. Il suffisso normale non è allora affermato. Nessuna simulazione di catch/finally, rollback o outcome fisico; qualunque chiusura presente resta un marcatore condizionale T01. Non si deve aggiungere un ramo runtime fittizio per far passare un oracolo.
6. **Arresto.** Effetti transazionali sconosciuti, chiamate opache arbitrarie, TransactionTemplate/demarcazione programmatica, callback, async/cambio thread, dispatch irrisolto, ordine non dimostrato o contesto non determinabile non ricevono questo witness. P1 terminata non può essere riutilizzata; P1 sospesa non può essere corrente. Dopo un figlio risolto si usa l'afterState T01, compreso eventuale ripristino dopo P2.
7. **Consumer e validazione.** T02 copia il contesto T01 del passo e conserva le premesse di raggiungibilità. Un validator deve rifiutare witness senza provenienza/premesse, con API fuori sottoinsieme, callback o stato incompatibile; una semplice etichetta non deve diventare auto-certificazione. Il formato concreto e il trattamento dei consumer v1 precedenti richiedono la decisione sul modello.
8. **Separazioni.** Identificazione statica dell'operazione, contesto applicativo, enlistment della connessione e lock acquisito sono proprietà distinte. Datasource/enlistment/lock restano UNKNOWN senza evidenza specifica.

La decisione necessaria è quindi sull'introduzione e validazione di un evento/witness pubblico di leaf condizionale e sulla sua compatibilità con i consumer esistenti. Non basta autorizzare il nome del concetto o dichiarare transaction-neutral tutto JdbcTemplate. Nessuna scelta di campi/versione viene anticipata nell'implementazione.

## Prima/dopo e regressioni

Riutilizzati in sola lettura i piccoli progetti esterni F01. Una sola nuova piccola copia della fixture per il controllo letterale TransactionTemplate/callback. Nuova analisi del controesempio R1 identica all'intero `counterexampleFullReport` storico, inclusi T01, fatti, hash e call site. Sorgente SHA-256 `e24bba87b81eecfa68d51c6eaf7fd8bf4c09100ee0e340840a0b9d4ddb10a284`; F1 `fixture.Operations#sequence()`, O1 [2630,2668), O2 [2670,2703), riga 48, offset UTF-16.

Trace invariata: FRAME_ENTER F1 → BEGIN P1 → BEGIN L1 → O1 prima di UNRESOLVED_CALL(4) → END L1 → END P1(outcome UNKNOWN) → FRAME_EXIT. O2 non ha evento T01; during P1/tx, continuation e after UNKNOWN. Nessuna sospensione nel controesempio. Prima e dopo D01: O1 P1, O2 UNPLACED/UNKNOWN; variante a tre: P1/null/null. Il “dopo” è una nuova misura senza implementazione, non un fix.

| Controllo | Esito e ambito |
|---|---|
| 207 regressioni T02-S01, incluse suite T01 pertinenti | PASS, 0 skipped |
| Witness R1 completo | PASS di riproducibilità, accettazione A ancora FAIL |
| Due / tre JDBC consecutive REQUIRED/P1 | 2 FAIL di accettazione; nessuna P inventata |
| REQUIRES_NEW, sospensione P1 e operazione P2 | PASS del comportamento esistente |
| NESTED, SP su P1 e una sola transazione fisica | PASS del comportamento esistente |
| Ripristino P1 dopo P2 vuota | PASS del comportamento esistente |
| Chiamata opaca prima del suffisso JDBC | PASS di conservazione: JDBC UNPLACED |
| UNKNOWN e async | PASS di conservazione dell'incertezza |
| Operazione dopo termine P1 | PASS: NO_TRANSACTION; test storici rifiutano il riuso di P terminata |
| Datasource/enlistment/lock | PASS: UNKNOWN mantenuti separatamente dal contesto |
| Nuovo evento, sole assumptions, frontiera cancellata | PASS dei tre probe di rappresentazione descritti sopra |
| Seconda frontiera inventata / P1 forzata | PASS di rifiuto |
| Leaf con normale ritorno seguita da istruzione, secondo il nuovo witness | NOT RUN: witness non introdotto per arresto del modello |
| Ramo eccezionale di tale leaf | NOT RUN: nessun nuovo modello di ramo implementato |
| Transazione programmatica/callback | PASS del nuovo probe letterale `template.execute(callback)` prima dei due JDBC: continuation UNKNOWN, entrambi JDBC UNPLACED; guardie sugli hazard anche nelle regressioni context-alternatives |

Conteggi delle suite: boundaries 16, self-invocation 16, context-alternatives 21, physical-lifetime 19, transition-contract 64, aop-causal-order 26, factory 23, resource-timeline 22. Il probe principale ha **14 PASS e 2 FAIL di accettazione**, exit 1 intenzionalmente conservato; il probe programmatico aggiunge **1 PASS**, exit 0. Gli oracoli P1/P1 e P1/P1/P1 sono letterali, non ricavati dall'output. Non si sommano questi FAIL a una falsa suite verde. Risultati, log, source dei driver e hash sono nel JSON D01.

Eseguiti anche validazione repository, Ruff check e Ruff format --check; esiti analitici nel JSON. Nessuna validazione runtime Spring/JDBC, database, driver, concorrenza o lock; CI e rilascio NOT RUN.

## Integrità, diff e limiti residui

Tutti i file iniziali tracciati e non ignorati conservati per byte e mode, inclusi F01, R1 e le modifiche T02 non committate. Sei materiali protetti uguali al receipt S01 e alle copie originali; manifest esterno SHA-256 `f93d950fea5ba28ed2215e90f69013b48515386acdcf83d68bf16fc058174af8`. CSV con 69/92 CRLF, zero LF isolati; confronto normalizzato con HEAD solo virtuale. Nessuna nuova salvaguardia grande o copia integrale: soltanto inventario hash, piccoli report diagnostici e cache/log esterni in `/private/tmp/mana-t02-s01-d01-jpdxfzi_`.

Diff D01: **zero righe di implementazione/test/standard modificate; due nuovi deliverable**, questo rapporto e `MANA-TRANSACTION-01-T02-S01-D01-results.json`. Il JSON include il confronto contro l'inventario iniziale; il diff preesistente non è attribuito a D01. Contratto sintetico contenuto soltanto in questo rapporto come proposta. Nessuna modifica ai witness storici, ai sei materiali o al Transaction Model v1.

Il rischio residuo principale è rendere una premessa generica equivalente a prova di neutralità o nascondere la dipendenza del suffisso dai ritorni normali. L'estensione deve esporre e validare tale distinzione. Anche dopo una futura estensione, connessione, datasource ed enlistment resterebbero non provati dal solo P1; SQL e FOR UPDATE non proverebbero lock acquisiti.

Nessun commit, staging, merge, push, worktree, build del target, Docker/Flutter/Android, nuova infrastruttura di qualificazione, analisi deadlock o avvio T02-S02. Implementazione e relativi nuovi test positivi **non eseguiti per la clausola MODEL_DECISION_REQUIRED del mandato**. Arresto alla consegna.
