# MANA-TRANSACTION-01-T02-S01-D02-F01 — Dispatch-Safe Resource Leaf

Data: 22 ottobre 2026. Verdetto: **FIX_READY_FOR_REVIEW**. Correzione locale verificata; nessuna attestazione di review semantica indipendente o integrazione.

D02-R1-A non produce più leaf standard: la prima chiamata resta `UNRESOLVED_CALL`, con contesto corrente P1 noto alla frontiera; la seconda operazione resta `UNPLACED/UNKNOWN`. I positivi standard del catalogo e tutti i dodici replay precedenti passano. Le 238 regressioni esistenti e 22 nuovi test passano senza skip; validazione repository e Ruff passano. Il JSON associato conserva risultati, hash, sorgente esatto, report completi prima/dopo e driver dei replay.

## Ricostruzione prima della modifica

Branch e HEAD iniziali verificati: `feature/mana-transaction-02`, `e3537e3f8c8329a71615fe59d496757d5392c6a8`. Letti direttamente rapporto e risultati D02-R1, Resource Leaf Extension v1, Resource Timeline Model v1 e Transaction Model v1; esaminati estrattore, classificatore, traversal e le due catene di validazione. Il sorgente originale D02-R1-A è stato rieseguito con il codice precedente **prima di qualunque modifica al codice**, ottenendo due leaf e accettazione T01/T02.

Le tre identità da distinguere sono:

| Oggetto | Evidenza / significato |
|---|---|
| Dichiarazione catalogata | `org.springframework.jdbc.core.JdbcTemplate#execute(java.lang.String):void`; è la firma attribuita dalla regola, non un risultato di attribution javac |
| Ricevente statico | Campo `Operations.jdbc`, dichiarato `@Autowired JdbcTemplate jdbc`, import esplicito Spring |
| Possibile implementazione dinamica | Standard JdbcTemplate oppure `CustomConfig.CustomJdbc#execute(String)`, override applicativo fornibile dal bean `customJdbc()`; quest'ultimo restituisce `CustomJdbc` |

Il primo call site è `Operations#sequence()`, riga 48, UTF-16 `[2630,2668)`; il secondo è `jdbc.update("DELETE FROM ledger")`, `[2670,2703)`, erroneamente continuato come `JdbcTemplate#update(java.lang.String):int`. SHA-256 del sorgente originale: `2bbb425bb082f9dc4d326942099b1257ab93698115fd45dde961452428811f49`.

L'estrattore precedente non materializza `fixture.CustomConfig.CustomJdbc` o il suo metodo. Registra soltanto `fixture.CustomConfig`, `parents=["UNKNOWN_NESTED_CLASS_OR_INITIALIZER"]` e `customJdbc.returnType="CustomJdbc"`. La guardia JDBC_LITERAL_V1 escludeva subtype materializzati, shadow del nome JdbcTemplate e factory con returnType esattamente JdbcTemplate. Non escludeva il grafo incompleto o quella factory dal tipo non risolto. Il chiamante Operations non ha parent, quindi la guardia locale non rilevava il contenitore CustomConfig.

T01 `validate_call` riclassificava con quella stessa regola incompleta. T02 validava T01 e ne proiettava correttamente le due leaf: il difetto era l'autorità di dispatch, non la copia dei contesti. La dipendenza di ritorno normale `[4]` della seconda leaf non qualificava l'implementazione della prima. L'eccezione esplicita nell'override non costituisce, da sola, il finding: anche il vecchio contratto condizionava il suffisso al ritorno normale.

## Correzione circoscritta

`JavaFacts.java:60` aggiunge una segnalazione parse-only `dispatchHazards` per ciascuna classe: la presenza di una classe membro, locale, anonima o più profondamente annidata produce `UNEXTRACTED_APPLICATION_TYPE`. Non ne risolve gerarchia, bean o corpo. Mantiene anche il precedente marcatore UNKNOWN sul contenitore. Il controllo visita sintassi già nel medesimo snapshot, senza attribution, class loading, build del target o nuova infrastruttura Java.

`resource_leaf.py:53` introduce un unico controllo autorevole di dispatch, usato dal classificatore e dalla validazione. Occorrono fatti espliciti completi per questo controllo (`dispatchHazards=[]`), nessun marcatore UNKNOWN, nessuno shadow/subtype JdbcTemplate e nessun supertipo sorgente irrisolto. Le factory che restituiscono JdbcTemplate e i bean con implementazione non determinata impediscono la leaf; la sola dichiarazione del manager DataSourceTransactionManager, già gestita da T01 e disgiunta da JdbcTemplate, non è un provider JDBC. Non si tenta di risolvere factory, proxy o decoratori. Anche annotazioni di wiring non supportate su classi, metodi o campi conservano l'incertezza: import/registrar, provider composti e advisor sorgente possono introdurre un'implementazione senza un @Bean diretto; non viene introdotto un risolutore di meta-annotazioni.

Si escludono anche subtype che **ereditano** l'overload catalogato ma possono ridefinire un hook virtuale come `getDataSource()`. L'assenza di un callback negli argomenti non prova l'assenza di un target applicativo nella libreria. Un catalog overload senza prova del dispatch rimane irrisolto.

`model.py:587` registra una motivazione `RESOURCE_LEAF_*` nella normale incertezza della frontiera. Il taglio causale esistente e gli identificatori fisici restano quelli di T01. Nessun nuovo evento, campo di scenario, firma JDBC, propagazione o associazione fisica è introdotto.

`resource_leaf.py:297` verifica sito, ricevente e nome rispetto ai fatti, applica il controllo di dispatch e ricostruisce l'intero witness con il catalogo fisso. Restano verificati hash, contenimento, firma/tipo, argomento, ordine, contesto, dipendenze e premesse esatte. T02 usa `validate_model` nella propria proiezione; non viene introdotta una seconda implementazione della policy. I test impongono che entrambe le API di validazione rifiutino i falsi witness per la motivazione semantica prevista, prima che un disallineamento della proiezione possa nascondere il difetto.

Il witness pubblico esistente contiene già fatti sorgente e premesse: il controllo è ricostruibile e la premessa aggiunta è fissa, non un booleano di sicurezza fornito dal chiamante. Non serve inventare una prova o una nuova decisione di modello per questo fix. I fatti precedenti senza il controllo esplicito non possono certificare nuove leaf; i modelli legacy senza estensione restano validi. Gli artefatti storici non sono riscritti. Per ricertificare un vecchio report abilitato occorre una nuova analisi.

## Controesempio prima/dopo

| Stesso sorgente D02-R1-A | Prima, nuova esecuzione del codice precedente | Dopo |
|---|---|---|
| Leaf | 2, sequenze 4 e 5 | 0 |
| Primo evento di chiamata | RESOURCE_LEAF_CALL execute | UNRESOLVED_CALL execute |
| Prima osservazione | T01_RESOURCE_LEAF, P1 | T01_FRONTIER, P1 |
| Seconda osservazione | T01_RESOURCE_LEAF, P1 | UNPLACED, UNKNOWN / nessun P |
| Continuazione | Assunta normale | UNKNOWN |
| Motivazione di dispatch | Nessuna frontiera | RESOURCE_LEAF_SOURCE_DISPATCH_INCOMPLETE |
| Report prodotto | Accettato dai vecchi validatori | Valido come report conservativo irrisolto |
| Vecchio witness falso presentato ai validatori corretti | — | Rifiutato da T01 e T02: `resource leaf dispatch not demonstrated` |

Il sorgente del probe non cambia durante le due analisi. Il positivo senza CustomConfig conserva due leaf su P1, con dipendenze `[]`, `[4]`; il positivo a tre operazioni conserva P1/P1/P1 e dipendenze `[]`, `[4]`, `[4,5]`. Ogni suffisso ammesso resta condizionale al ritorno normale delle leaf precedenti, mai a successo JDBC osservato.

## Regressioni indipendenti

Nuova suite: `python3 tests/transaction-resource-dispatch.py -v`, **22 test PASS**. Sorgenti avversari e aspettative sono letterali, scritti separatamente dal classificatore; non importano le sue firme, guardie o motivazioni per derivare l'oracolo. Gli oracoli storici rimangono invariati.

| Requisito | Evidenza nuova |
|---|---|
| 1. Originale D02-R1-A | Sorgente completo e SHA esatti dal receipt; zero leaf, frontiera/P1 e suffisso UNKNOWN |
| 2. Subtype top-level con override | Zero leaf, APPLICATION_SUBTYPE |
| 3. Membro statico con override | Zero leaf, SOURCE_DISPATCH_INCOMPLETE |
| 4. Membro non statico con override | Zero leaf, SOURCE_DISPATCH_INCOMPLETE |
| 5. Statico JdbcTemplate / concreto applicativo | Campo statico verificato e bean CustomJdbc; nessuna certificazione standard |
| 6. Bean non risolvibile | Factory Object, proxy JdbcTemplate e decoratore con supertipo esterno respinti |
| 7. Overload fuori catalogo | execute(String, callback) conserva UNRESOLVED_CALL |
| 8. Standard sufficientemente qualificato nello scenario | Firma completa execute(String)/update(String), tipo e provenance verificati; anche i positivi JDBC preesistenti passano |
| 9. Due REQUIRED/P1 | Due leaf con dipendenza di ritorno normale, P1/P1 |
| 10. Tre REQUIRED/P1 | Tre leaf, P1/P1/P1 e dipendenze cumulative |
| 11. Override seguito da operazione | Nessuna leaf; prima frontiera con P1, seconda UNKNOWN senza associazione fisica |
| 12. Witness mancante/alterato/incompatibile | Entrambi i validatori respingono firma/tipo/provenance/premesse/certezza falsi e witness applicativi arbitrari |

Coperti inoltre: hook virtuale applicativo senza callback argomento; classi locali, anonime, annidate su più livelli; initializer opaco; @Import non risolto, provider con annotazione composta e advisor sorgente; fatti privi della nuova segnalazione; vecchio witness HIGH. Per tutti i sedici sorgenti negativi di dispatch si presenta anche un witness standard formalmente coerente con span/hash aggiornati e fatti autentici del negativo: entrambe le validazioni devono rifiutarlo precisamente per dispatch non dimostrato. I report conservativi prodotti da quei sorgenti superano invece entrambe le validazioni; il negativo non dipende da uno schema rotto. L'overload fuori catalogo è respinto per effettiva inapplicabilità della firma.

## Verifica completa

| Suite / controllo | Risultato |
|---|---:|
| transaction-boundaries | 16 PASS |
| transaction-self-invocation | 16 PASS |
| transaction-context-alternatives | 21 PASS |
| transaction-physical-lifetime | 19 PASS |
| transaction-transition-contract | 64 PASS |
| transaction-aop-causal-order | 26 PASS |
| mana-skill-factory | 23 PASS |
| resource-timeline | 22 PASS |
| transaction-resource-leaves, invariata | 31 PASS |
| **Regressioni D02 esistenti** | **238 PASS, zero skipped** |
| Nuova transaction-resource-dispatch | **22 PASS, zero skipped** |
| **Totale suite** | **260 PASS, zero FAIL, zero skipped** |
| Dodici replay precedenti | **12 PASS** |
| Controesempio HIGH prima/dopo | PASS, differenza attesa riprodotta |
| bash scripts/validate-repo.sh | PASS, exit 0 |
| Ruff check e format --check sui nove Python pertinenti | PASS, exit 0 |
| Patch incrementale, controllo inverso senza applicazione | PASS, exit 0 |

I dodici replay mantengono gli oracoli del driver D02-R1: dieci casi sorgente (due/tre REQUIRED, REQUIRES_NEW, NESTED, ripristino, terminazione, ordine perso, UNKNOWN, async e programmatico), legacy R1 immutato e rifiuto del nuovo evento da parte del validatore pre-D02. Le directory /tmp storiche non erano disponibili. Le sole piccole fixture sono state ricostruite dalle istruzioni sorgente incorporate nei receipt F01/D01, senza alterarne gli oracoli. Il singolo file del validatore pre-D02 è stato recuperato invertendo la patch storica **in una directory esterna**, con SHA verificato `1246568a9a0c73db5f0686794454b9af41440e7688e122453addddfe13034c99`. Nessuna copia integrale del repository.

Le suite esistenti verificano isolamento temporaneo del parser, assenza di build del target, snapshot immutabili, confini di output, lifetime, causalità e governance candidate. I relativi test sono PASS: candidate non registrate, non accettate dalla compilazione dei profili, non trusted e pending approval; nessun comando di approvazione/attivazione introdotto o eseguito. Il nuovo probe verifica inoltre ogni snapshot sorgente prima/dopo.

## Conservazione e diff

L'inventario iniziale contiene **1.296 file** tracciati/non ignorati. Restano identici per byte e mode **1.292 file**; cambiano soltanto quattro file esistenti autorizzati: JavaFacts.java, resource_leaf.py, model.py e resource-leaf-extension-v1.md. Il nuovo test è separato. I sei materiali protetti coincidono sia con l'inventario iniziale sia con gli hash originali conservati nei receipt; CSV con 69/92 CRLF e zero LF isolati. Nessun oracolo, rapporto storico, esempio o altro lavoro locale è sovrascritto.

La patch `MANA-TRANSACTION-01-T02-S01-D02-F01.patch` è relativa al **working tree sporco iniziale**, non a HEAD: cinque file, +501/-10 righe; produzione +77/-9, contratto +36/-1, test +388/-0. Esclude tutte le modifiche D02/locali precedenti e i tre deliverable del fix. Hash prima/dopo di ciascun file e controllo inverso sono nel JSON. Nessun cambiamento di mode ai file preesistenti.

Le evidenze nuove sono in `/private/tmp/mana-d02-f01-6_cchm7t`: inventario, piccole fixture ricostruite, report prima/dopo, replay e log. Nessuna scrittura, spostamento, nuova copia o cleanup degli archivi qualificati; non si dichiara un nuovo controllo di archivi /tmp storici assenti. Branch, HEAD, indice vuoto e lista worktree restano invariati. Nessun commit, merge, push, staging, reset, stash o cleanup; nessuna modifica a Familiar, attivazione candidate o implementazione T02-S02.

## Rischi residui e confine del verdetto

La selezione standard rimane una premessa condizionale di JDBC_LITERAL_V1, subordinata al controllo sorgente positivo e ai vincoli locali del catalogo: non dimostra il bean concreto a runtime. Wiring esterno, classpath effettivo, versione della libreria, advisor/proxy esterni, mutazioni del ricevente e comportamento di driver/database non sono qualificati. Se tali premesse non sono accettabili nello scenario desiderato, la capability va disabilitata; non esiste una certificazione runtime implicita.

Il controllo è intenzionalmente conservativo sull'intero inventario: anche tipi annidati, supertypes o bean estranei possono rendere irrisolta una chiamata standard. Una futura riduzione di questi falsi negativi richiede un mandato e prove dedicati; qui non è stato costruito un risolutore dinamico. I fatti importati restano una prova di coerenza interna, non l'autenticazione di una falsificazione coordinata di JSON/hash; per autenticità sorgente occorre rieseguire il CLI sul target.

Dopo una frontiera non viene inventato alcun P/datasource/enlistment. Enlistment JDBC, lock acquisiti, granularità e identità runtime restano UNKNOWN per tutte le osservazioni. Test Spring/JDBC/database a runtime, CI remota, release acceptance e review esterna: **NOT RUN**. Nessuna diagnosi di deadlock o assenza di deadlock. Consegna e arresto a **FIX_READY_FOR_REVIEW**.
