# MANA-TRANSACTION-01-T02-S01-F01 — JDBC Operation Placement

Data: 21 ottobre 2026. Verdetto: **CONTRACT_DECISION_REQUIRED**.

Il controesempio effettivo R1 è riprodotto integralmente, inclusi fatti AST e modello T01. P1 è dimostrata al primo call site; il contesto al secondo non è dimostrato dall'autorità T01 disponibile. Si applica quindi la clausola di arresto del mandato: nessuna correzione del motore, nessuna assegnazione arbitraria di P1. Il requisito A resta **FAIL**, non FIX_READY_FOR_REVIEW. Le 207 regressioni storiche passano; i nuovi controlli comprendono 11 PASS e i due FAIL di accettazione a due/tre operazioni.

## Controesempio e provenienza

Branch verificato `feature/mana-transaction-02`, HEAD `e3537e3f8c8329a71615fe59d496757d5392c6a8`, indice vuoto. Letti R1 e relativo JSON, Resource Timeline Model v1 e Transaction Model v1, quindi esaminati direttamente generatore, validatori e fixture. Nessuna delega.

Riutilizzata la fixture `tests/fixtures/resource-timeline` in una piccola copia esterna; unica modifica per il caso R1: aggiunta di `@Transactional` a `Operations.sequence()`. Entry `fixture.Operations#sequence()`, `context.json` originale, nessuna modifica alla fixture del repository.

```java
@Autowired JdbcTemplate jdbc;
@Transactional public void sequence() {
    jdbc.execute("SELECT * FROM accounts");
    jdbc.update("DELETE FROM ledger");
}
```

Nel file effettivo il metodo è sulla sola riga 48 di `src/main/java/fixture/Resources.java`. SHA-256 del sorgente modificato: `e24bba87b81eecfa68d51c6eaf7fd8bf4c09100ee0e340840a0b9d4ddb10a284`, identico a R1. Gli span seguenti sono unità UTF-16, fine esclusiva.

| Elemento | Proprietario / posizione | Significato |
|---|---|---|
| Frame F1 | `fixture.Operations#sequence()`, [2590,2706) | Unico frame; caller e call site della root null, perché l'entry è input dello scenario |
| Annotazione | [2590,2604) | REQUIRED di default, manager selezionato `tx` |
| O1 | `jdbc.execute`, [2630,2668), riga 48 | READ, identificatore lessicale `accounts` |
| O2 | `jdbc.update`, [2670,2703), riga 48 | WRITE, identificatore lessicale `ledger` |

Non esistono frame callee JDBC risolti. Il field è direttamente `@Autowired JdbcTemplate`; la configurazione class proxy è esplicita e lo scenario stipula ingresso attraverso proxy. T01 registra `interception: APPLIED`, `previousState: NO_TRANSACTION`, `duringState: TRANSACTION_PHYSICAL/P1/tx`, `effectiveContext: INACTIVE/ACTIVE/UNKNOWN`, `continuation: UNKNOWN` e `afterState: UNKNOWN/null/null`.

## Eventi, contesto e ordine realmente dimostrato

| Sequenza T01 | Evento | Evidenza di contesto |
|---|---|---|
| 1 | FRAME_ENTER F1 | Ingresso dal contesto NO_TRANSACTION |
| 2 | PHYSICAL_BEGIN P1 | P1 simbolica aperta e posseduta da F1 |
| 3 | LOGICAL_BEGIN L1 | L1 associata a P1 |
| prima di 4 | O1 nella timeline T02 | Copia del contesto corrente T01 P1/tx, P1 viva e non sospesa |
| 4 | UNRESOLVED_CALL `jdbc.execute` | Call site esatto di O1; motivo `AMBIGUOUS_OR_DYNAMIC_DISPATCH`; nessun ritorno JDBC risolto |
| 5 | LOGICAL_END L1 | Chiusura condizionale dello scope |
| 6 | PHYSICAL_END_OUTCOME_UNKNOWN P1 | Termine del lifetime modellato, outcome UNKNOWN |
| 7 | FRAME_EXIT F1 | After-state UNKNOWN; non ripristino certo di NO_TRANSACTION |

La timeline T02 ha otto elementi: gli stessi sette eventi T01 più O1 immediatamente prima dell'evento T01 4. O2 non ha posizione cronologica. Non esiste un evento T01 che raggiunga o delimiti O2, né eventi di inizio/fine delle esecuzioni JDBC: O1 rappresenta la sintassi di invocazione alla frontiera, non l'intera durata della chiamata. Gli eventi 5–7 sono marcatori di unwind condizionale; non provano che O1 sia ritornata o che O2 sia avvenuta prima della chiusura.

Nessuna sospensione, savepoint, ripresa o cambio di thread è registrato nel controesempio; vi sono un solo P e un solo L. L'assenza di questi eventi nel tratto non attraversato non dimostra che il contesto sia preservato al suo interno. La sorgente prova l'ordine lessicale O1 → O2 e la forma straight-line; T01 dimostra il prefisso fino all'invocazione O1. Non dimostra il ritorno attraverso la frontiera né il contesto corrente al secondo call site. Non si conclude che P1 sia realmente assente in O2: l'associazione resta non dimostrata nel contratto disponibile.

## Diagnosi e decisione di contratto

La catena è `sourceFacts.calls[0]` → `model.py:535–554` → evento UNRESOLVED_CALL e `break` → `resources.py:152–175` → O1 con P1. `sourceFacts.calls[1]` non riceve un passo T01; `resources.py:182–203` conserva O2 come UNPLACED/UNKNOWN. Il frame `duringState` vale al confine d'ingresso, non certifica il contesto in ogni punto di un corpo non attraversato.

Non è un consumo errato di PHYSICAL_BEGIN né una regola che richieda una nuova apertura per ogni operazione. La lacuna funzionale segnalata in R1 resta, ma manca la testimonianza causale autorevole necessaria alla correzione minima T02. La presenza sintattica di `JdbcTemplate` e di SQL letterale non è una testimonianza T01 del comportamento del callee esterno o della conservazione del contesto al suo ritorno.

Il Resource Timeline Model v1, sezione causalità, conserva espressamente la prima frontiera e vieta di riprendere il suffisso; il Transaction Model v1 limita la risoluzione positiva e mantiene UNKNOWN per chiamate non risolte. `_validate_causal_order` (`model.py:983–1021`) rifiuta un secondo passo del corpo dopo una frontiera non risolta. Un controllo negativo aggiunge proprio una seconda UNRESOLVED_CALL con il call site di O2: il validatore T01 risponde `body call follows unresolved execution order`. Un altro assegna P1 a O2 nel report: il validatore T02 rifiuta la proiezione alterata.

Serve una decisione esplicita su quale evidenza T01 possa autorizzare il ritorno sincrono e la conservazione del contesto attraverso questa API esterna, oppure una revisione del criterio di accettazione. Nessuna delle due viene introdotta qui. Un eventuale riepilogo qualificato del callee dovrà appartenere all'autorità T01 e distinguere ordine causale da contesto; non sarebbe una nuova implementazione della propagation in T02. Nessun campo pubblico, evento, schema o Transaction Model v1 è stato modificato.

## Prima / dopo e regressioni

| Operazione | Oracolo del mandato | Prima R1 | Dopo diagnosi F01, senza modifica |
|---|---|---|---|
| O1 READ accounts | Posizionata, P1 | T01_FRONTIER prima di 4, P1/tx | Identico |
| O2 WRITE ledger | Posizionata, P1 | UNPLACED, UNKNOWN/null/null | Identico: accettazione FAIL |
| Terza WRITE audit, variante | Posizionata, P1 | Non presente nel caso R1 | UNPLACED, UNKNOWN/null/null: accettazione FAIL |

Gli oracoli positivi P1/P1 e P1/P1/P1 sono letterali, scritti prima del confronto, non generati dal motore. I FAIL non sono trasformati in PASS dall'accettazione del validatore. Il confronto integrale con R1 è un controllo distinto di riproducibilità.

| Controllo nuovo | Esito |
|---|---|
| Riproduzione integrale del controesempio R1 | PASS |
| Due operazioni REQUIRED/P1 | FAIL: P1, null; una sola posizionata |
| Tre operazioni REQUIRED/P1 | FAIL: P1, null, null; una sola posizionata |
| REQUIRES_NEW, P1 sospesa e P2 corrente | PASS: operazione P2; SUSPEND → BEGIN P2 → END P2 → RESUME |
| NESTED condivide P1 | PASS: una P, savepoint su P1 |
| Ripristino P1 dopo figlio REQUIRES_NEW vuoto | PASS |
| Operazione realmente dopo termine P1 | PASS: NO_TRANSACTION, nessuna P riutilizzata |
| Prefisso causale non risolto prima di due chiamate JDBC | PASS: entrambe le chiamate JDBC UNPLACED |
| Contesto UNKNOWN legittimo | PASS: identità e manager null |
| Corpo async non attraversato | PASS: UNPLACED, nessuna P propagata |
| Datasource, enlistment, identità runtime e lock | PASS: UNKNOWN separati dal contesto P |
| Seconda frontiera inventata / P1 forzata sul suffisso | PASS: entrambi rifiutati |

Il controllo di causalità seleziona esplicitamente i due receiver JDBC: la frontiera precedente `unknownReceiver.run()` è a sua volta rappresentata come osservazione API UNKNOWN, e non è una terza chiamata JDBC. Il primo tentativo del probe includeva erroneamente anche quella osservazione nel confronto: selettore corretto, rivalutazione sui medesimi report catturati, nessuna modifica al motore. Primo tentativo e log conservati esternamente.

Rieseguiti con exit 0: `transaction-boundaries.py` **16**, `transaction-self-invocation.py` **16**, `transaction-context-alternatives.py` **21**, `transaction-physical-lifetime.py` **19**, `transaction-transition-contract.py` **64**, `transaction-aop-causal-order.py` **26**, `mana-skill-factory.py` **23**, `resource-timeline.py` **22**. Totale **207 PASS, 0 skipped**. Le suite includono controlli avversari su P terminate/sospese, causalità, contratto e isolamento. I probe hanno exit 1 per i due FAIL di accettazione dichiarati; non sono una suite verde. Driver riproducibile, oracoli, risultati e riferimenti ai log sono inclusi nel JSON F01.

## Distinzioni e limiti residui

Lo schema separa già `transactionContext` applicativo, `resource` lessicale, `datasource`, `enlistment` e `lockAcquired`. P1/tx prova soltanto il contesto applicativo condizionale alla frontiera. `tx` non identifica il datasource o una connessione: il suo bean non dimostra quel binding. Tutte le osservazioni mantengono datasource UNKNOWN/id null, enlistment UNKNOWN, runtimeIdentity UNKNOWN, lockAcquired e granularità UNKNOWN. Nessuna equivalenza fra nome SQL e oggetto runtime, nessuna deduzione di lock dalla presenza di una P. Non servono nuovi campi pubblici per conservare queste distinzioni.

## Integrità, diff e arresto

I sei materiali preesistenti coincidono prima/dopo per SHA-256, dimensione e mode 0644 con il receipt S01 e con le copie esterne originali. Verificato il manifest esterno SHA-256 `f93d950fea5ba28ed2215e90f69013b48515386acdcf83d68bf16fc058174af8`. CSV preservati: rispettivamente 69 e 92 CRLF, zero LF isolati; normalizzazione soltanto virtuale uguale a HEAD. Tutti i file iniziali tracciati e non ignorati sono rimasti identici per byte e mode, inclusi motore, fixture, esempi, report storici, roadmap e standard. Il JSON contiene le verifiche analitiche.

Diff F01: **zero modifiche di implementazione/test/standard; due nuovi deliverable**, questo rapporto e `MANA-TRANSACTION-01-T02-S01-F01-results.json`. Il diff preesistente non viene attribuito a F01. Nessun commit, merge, push, staging, worktree, copia integrale del repository o archivio. Usate soltanto copie della piccola fixture e log in `/private/tmp/mana-t02-s01-f01-eozx3kim`. Nessuna build del target, Android, Flutter, Docker, database, analisi lock o attività T02-S02.

Verifica runtime Spring/JDBC, acquisizioni, concorrenza, CI remota e rilascio: **NOT RUN**. Requisito A: **FAIL**. Correzione: **non applicata per CONTRACT_DECISION_REQUIRED**. Arresto alla consegna.
