# MANA-TRANSACTION-01-T02-S01-D02 — Resource Leaf Contract Extension

Data: 21 ottobre 2026. Verdetto: **IMPLEMENTED_READY_FOR_REVIEW**.

Implementata l'estensione pubblica autorizzata `RESOURCE_LEAF_CALL`, distinta da `UNRESOLVED_CALL`, con catalogo ristretto, witness versionato e riclassificazione autorevole nel validatore T01. T02 consuma quei passi senza ricostruire propagation. Sul sorgente effettivo R1: **P1/P1**; sulla variante a tre operazioni: **P1/P1/P1**, nel solo percorso normale condizionale. Enlistment JDBC e lock acquisiti restano UNKNOWN. **238 test PASS, 0 skipped**, più 12 replay PASS; validazione repository e Ruff PASS. Questo è un risultato locale pronto per review, non un'accettazione indipendente o runtime.

## Contratto e attivazione

Il [contratto Resource Leaf Extension v1](../standards/resource-leaf-extension-v1.md) descrive formato, catalogo, premesse, verifiche e compatibilità. Sono stati aggiornati i due standard T01/T02 con il riferimento all'estensione, senza riscrivere il contratto MR00 o i suoi oracoli.

Il nuovo input scenario è esplicito:

```json
"resourceLeafPolicy": "JDBC_LITERAL_V1"
```

Omissione o `DISABLED` mantiene il comportamento legacy. La policy seleziona regole Mana fisse, non autorizza classificazioni `safe=true` del progetto. Il risultato mantiene `mana.transaction-model/v1` e aggiunge `resourceLeafExtension`, schema `mana.transaction-resource-leaves/v1`, con lo snapshot dei fatti sorgente. Ogni evento leaf porta un `mana.resource-leaf-witness/v1`: regola/versione, firma, tipo receiver, call site, evidenze del metodo/field/argomento, ordinalità sorgente, sequenza T01, dipendenze dai ritorni normali precedenti, contesto corrente, premesse e limiti.

È un'estensione additiva possibile senza riscrittura incompatibile della propagation: la nuova leaf rappresenta un passo del corpo sotto premesse proprie; i set chiusi degli effetti MR00 del confine rimangono invariati. `UNRESOLVED_CALL` conserva esattamente il taglio causale originale. Nessun secondo motore in T02.

## Implementazione e riconoscimento

`resource_leaf.py` contiene il catalogo e le verifiche. Sottoinsieme iniziale: overload standard JdbcTemplate `execute(String)`, `update(String)`, `queryForList(String)`, un solo SQL letterale compatibile con la grammatica chiusa già usata da S01. La classificazione dipende da tipo esatto, field direttamente Autowired non inizializzato/non qualificato, assenza di parent e hazard, chiamante pubblico non statico con sole annotazioni supportate, receiver diretto, forma autonoma dell'invocazione, argomenti e SQL: non dal solo nome del metodo. La grammatica SQL è condivisa con T02, senza estenderne le forme legacy.

L'estrattore JDK parse-only aggiunge `statementCall`. Una chiamata annidata in argomenti, espressioni condizionali o callback non può così diventare una leaf di una sequenza lineare. Non vengono introdotte attribution, code generation, dipendenze Spring o esecuzione del target.

Sottotipi JdbcTemplate osservati, shadow del tipo e factory sorgenti che restituiscono JdbcTemplate invalidano il dispatch standard. Callback, SQL dinamico/non supportato, `COMMIT`, autocommit, API fuori catalogo e riferimenti ambigui non ricevono witness. Chiamate opache, TransactionTemplate e operazioni Connection manuali incontrate nel percorso conservano la frontiera; async, controllo di flusso non supportato e contesto sconosciuto conservano i limiti T01.

La policy assume esplicitamente il dispatch dell'implementazione standard e l'assenza di override/advisor esterni qualificati; assume ritorno normale sincrono e assenza di modifiche non modellate al contesto da libreria/driver/database lungo quel percorso. Le contraddizioni osservabili nel sorgente vengono escluse. Queste sono premesse dello scenario ristretto, **non risoluzione del dispatch runtime** né una proprietà universale di JdbcTemplate. Se tali premesse non sono sostenibili per lo scenario reale, la capability va lasciata disabilitata. Le [firme dell'API Spring](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html) motivano il catalogo degli overload; non identificano il binario installato sul target.

T01 emette la leaf, conserva lo stato corrente e prosegue solo nel percorso normale. Dopo un figlio risolto usa il suo `afterState`; il validatore continua a controllare P corrente, lifetime, sospensioni, ripristini, savepoint e ownership. Le leaf non aprono o chiudono entità transazionali. Il limite globale è 128 leaf: la successiva invocazione eleggibile diventa una normale frontiera UNRESOLVED_CALL con motivo `RESOURCE_LEAF_BUDGET_EXCEEDED`; il prefisso resta e il suffisso non viene attraversato. Restano i budget JDK/input/pubblicazione, compreso 4 MiB per il risultato.

## Verifica del witness e integrazione T02

Il validatore non si limita alla presenza del witness. Verifica capability e versioni, hash degli stessi fatti sorgente, unicità del metodo, containment di metodo/field/chiamata/argomento, ordine degli span delle istruzioni, corrispondenza del prefisso dei call site e completezza fino alla frontiera. Riclassifica l'API con il catalogo autorevole e confronta l'intero witness, comprese dipendenze e contesto ottenuto dal replay T01. Rifiuta versioni false, firme arbitrarie, witness mancanti o con premesse modificate, `safe=true`, dipendenze inventate e finanche booleani al posto della versione numerica.

La validazione causale distingue leaf da frontiera realmente irrisolta: un witness altrimenti coerente dopo UNRESOLVED_CALL viene comunque rifiutato. Valgono anche i divieti su P1 sospesa o terminata. Rimuovere una leaf dal modello abilitato non rende valido un suffisso mancante.

T02 richiede che il proprio snapshot coincida con quello dell'estensione T01. Inserisce l'osservazione immediatamente prima della leaf, con `T01_RESOURCE_LEAF` e il suo `beforeT01Sequence`, copia il contesto ed espone premesse e dipendenze in `premises`. Non inventa eventi o nuove P. Le osservazioni dopo una vera frontiera restano UNPLACED/UNKNOWN. L'array di eventi T01 incorporato rimane integro.

## Controesempio prima/dopo

Riutilizzati in sola lettura i piccoli progetti esterni F01/D01. Per il witness R1 il sorgente è identico a quello della review, SHA-256 `e24bba87b81eecfa68d51c6eaf7fd8bf4c09100ee0e340840a0b9d4ddb10a284`: unica modifica rispetto alla fixture originale è `@Transactional` su `fixture.Operations#sequence()`. Nessuna modifica ai progetti originali del repository o ai report storici.

| Operazione | Call site UTF-16, riga 48 | Prima R1/D01 | Dopo, policy esplicita |
|---|---|---|---|
| READ accounts | [2630,2668), proprietario F1 | T01_FRONTIER prima di 4, P1/tx | T01_RESOURCE_LEAF prima di 4, P1/tx |
| WRITE ledger | [2670,2703), proprietario F1 | UNPLACED, UNKNOWN | T01_RESOURCE_LEAF prima di 5, P1/tx, dipende dal ritorno normale di 4 |
| Terza WRITE audit, variante | Terzo call site reale della variante | UNPLACED, UNKNOWN | T01_RESOURCE_LEAF prima di 6, P1/tx, dipende dai ritorni normali di 4 e 5 |

Il percorso R1 abilitato è: FRAME_ENTER → BEGIN P1 → BEGIN L1 → leaf 4 → leaf 5 → END L1 → END P1(outcome UNKNOWN) → FRAME_EXIT. Una sola P e un solo L. L'after-state NO_TRANSACTION è il ripristino sul normale unwind condizionale; non dichiara commit, rollback o ritorno realmente avvenuto. Se la prima operazione termina eccezionalmente, il suffisso normale non è affermato: non è stato aggiunto un simulatore di rami eccezionali.

Il controllo senza policy riproduce **esattamente Transaction Model, osservazioni e timeline R1**. I nuovi fatti estratti hanno soltanto il metadato additivo `statementCall`; i vecchi fatti e gli IR archiviati restano validabili senza modificarli. I vecchi FAIL non sono stati cancellati o rietichettati. I nuovi positivi derivano dall'evento implementato e dagli oracoli indipendenti, con una capability che prima non esisteva.

## Compatibilità dei consumer

IR legacy e tre esempi S01 rimangono validi. Nessun oracolo MR00/MR01 o test delle 207 regressioni è stato modificato. È stato eseguito anche il **vero validatore pre-D02**, caricato dalla piccola copia iniziale di `model.py`: sul nuovo IR rifiuta `unrecognized transaction event`, come richiesto. Non si presume compatibilità di interpretazione con un consumer vecchio che ignori errori o salti la validazione.

Il renderer aggiornato valida i report con la nuova capability e rifiuta eventi/versioni non supportati; mostra `RESOURCE_LEAF_CALL`, continuazione `IF normal return` e runtime UNKNOWN. Per UNRESOLVED_CALL resta `remaining order NOT ASSERTED`. Il contratto vieta di “degradare” cancellando gli eventi leaf: per un consumer legacy occorre una nuova analisi con la policy disabilitata, che conserva il suffisso non posizionato.

## Regressioni ed evidenze

Oracoli manuali in `resource-leaf-oracles.json`: P, risorse, sequenze e dipendenze attese da fixture letterali e MR00; nessuna generazione dal motore. `transaction-resource-leaves.py` aggiunge 31 test con positivi e controlli avversari.

| Suite finale | PASS |
|---|---:|
| transaction-boundaries | 16 |
| transaction-self-invocation | 16 |
| transaction-context-alternatives | 21 |
| transaction-physical-lifetime | 19 |
| transaction-transition-contract | 64 |
| transaction-aop-causal-order | 26 |
| mana-skill-factory | 23 |
| resource-timeline | 22 |
| transaction-resource-leaves, nuova | 31 |
| **Totale** | **238, zero skipped** |

I nuovi test coprono due/tre REQUIRED, REQUIRES_NEW/P2 con P1 sospesa, NESTED/SP su P1, leaf seguita da istruzione, operazione potenzialmente eccezionale e dipendenze del suffisso, callback anche lambda, opacità, TransactionTemplate, commit/autocommit manuali, ordine incerto, SQL di demarcazione, UNKNOWN, sottotipi/shadow, binding ambiguo, witness falsificati o mancanti, source snapshot diverso, fatti/eventi riordinati, P terminata/sospesa, versioni consumer, budget e CLI reale con isolamento del target.

Inoltre **12 replay PASS**: i dieci sorgenti/scenari D01 con capability esplicita (incluso il controllo TransactionTemplate), riproduzione legacy R1 e rifiuto da parte del validatore pre-D02. I controlli incerti restano negativi: nessun suffisso JDBC oltre opacità/programmatico/async/UNKNOWN è diventato positivo.

`bash scripts/validate-repo.sh`, Ruff check e Ruff format --check sugli otto Python pertinenti: exit 0. `git apply --check --reverse` sul patch D02: exit 0, verifica senza applicazione. Log, exit, tempi, hash, replay, witness prima/dopo e source del driver sono nel JSON allegato. I tentativi di sviluppo precedenti restano nei log esterni; il conteggio è quello della campagna finale, non la somma dei rerun.

## Diff, integrità e limiti residui

Il [patch D02](MANA-TRANSACTION-01-T02-S01-D02.patch) è calcolato contro lo stato locale iniziale, non contro HEAD: **11 file, +1298/−40**. Produzione: 6 file, +429/−38; test/oracoli: 2 file, +674/−0; standard: 3 file, +195/−2. Include la piccola relocation della grammatica SQL condivisa. Report e risultati sono receipt separati dal patch. Il lavoro preesistente S01 non è attribuito a D02.

Sono stati modificati soltanto i sette file iniziali autorizzati necessari a CLI/T01/T02/estrattore/renderer e standard; tutti gli altri file iniziali sono identici per byte e mode. I sei materiali protetti coincidono prima/dopo con il receipt e con le copie originali; manifest esterno SHA-256 `f93d950fea5ba28ed2215e90f69013b48515386acdcf83d68bf16fc058174af8`. CSV: 69/92 CRLF, zero LF isolati, confronto normalizzato con HEAD solo virtuale. Report R1/F01/D01, oracoli MR00, esempi e roadmap preesistenti conservati integralmente. Le verifiche analitiche sono nel JSON.

Nessun worktree, copia integrale o archivio grande. Salvaguardie preesistenti riutilizzate; per il diff sono state copiate soltanto le sette piccole versioni iniziali dei file interessati. Fixture temporanee piccole e riutilizzo in sola lettura dei witness precedenti. Evidenze/log/cache D02 esterni in `/private/tmp/mana-t02-s01-d02-0ybf5ikr`, circa 2,1 MiB alla verifica.

Restano limiti espliciti: classificazione standard-dispatch condizionale, nessuna autenticazione di JSON coordinatamente falsificato contro sorgenti non riparsati, nessuna risoluzione di driver/database/trigger, SQL dinamico, Spring binario o wiring runtime. Il validatore riclassifica i fatti e controlla la loro coerenza/provenance dichiarata; il CLI è il percorso per rinnovare la prova sorgente sul progetto reale. Gli snapshot duplicati nella capability consumano parte del budget di pubblicazione.

Contesto applicativo P1, identificatore lessicale della risorsa, datasource, enlistment e lock rimangono separati. Datasource ed enlistment sono UNKNOWN, così come lockAcquired, identità runtime e granularità; anche FOR UPDATE resta richiesta sintattica. Runtime Spring/JDBC, concorrenza, lock, CI remota e release acceptance: **NOT RUN**.

Branch e HEAD invariati, indice vuoto. Nessun commit, merge, push, modifica a Familiar, attivazione di candidate, build del target o attività T02-S02/deadlock. Arresto alla consegna per review.
