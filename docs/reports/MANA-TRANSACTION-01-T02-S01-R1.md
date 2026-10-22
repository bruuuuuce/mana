# MANA-TRANSACTION-01-T02-S01-R1 — Resource Timeline Review & Integration

Data: 21 ottobre 2026. Verdetto: **NEEDS_FIX**. Consolidamento non autorizzato dal gate semantico; nessun commit o merge creato.

Review eseguita in questa sessione distinta dall'implementazione S01, senza delegare all'implementatore. Letti i cinque input richiesti; esaminati direttamente CLI, proiezione, estrattore AST, autorità T01, validatori, fixture, oracoli, test e diff. Le dichiarazioni del receipt S01 sono state confrontate con sorgenti, esecuzioni nuove e hash reali. I risultati storici restano invariati.

**Finding R1-A — HIGH, bloccante per il requisito A del mandato.** La fondazione conserva correttamente l'incertezza, ma non soddisfa il caso richiesto con due operazioni REQUIRED entrambe attribuite al contesto P1. La prima invocazione JDBC è una frontiera `UNRESOLVED_CALL` per T01; il suffisso diventa non attraversato. T02 emette una sola operazione cronologica e conserva la seconda come `UNPLACED`, con contesto UNKNOWN e physicalId null.

Controesempio minimo, con i medesimi import, field, configurazione proxy e capacità della fixture esistente:

```java
@Autowired JdbcTemplate jdbc;
@Transactional public void sequence() {
    jdbc.execute("SELECT * FROM accounts");
    jdbc.update("DELETE FROM ledger");
}
```

L'unica modifica sperimentale è l'aggiunta di `@Transactional` a `Operations.sequence()` in una copia **esterna** della fixture; nessun sorgente del repository è stato cambiato. Entry `fixture.Operations#sequence()`, contesto originale `context.json`.

| Osservazione | Oracolo del requisito A | Risultato effettivo |
|---|---|---|
| READ accounts | Posizionata, P1 | T01_FRONTIER, P1/tx |
| WRITE ledger | Posizionata, P1 | UNPLACED, UNKNOWN/null |
| Operazioni nella timeline | 2 | 1 |
| Transazioni fisiche | 1 | 1 |

Il modello effettivo passa il validatore: è coerente con il contratto ristretto della fondazione, che dichiara espressamente questo limite. Il finding è quindi una **lacuna funzionale rispetto all'accettazione R1**, non una falsa assegnazione di P o un difetto della conservazione di UNKNOWN. Il report S01 e gli oracoli a operazione singola non dimostrano l'intero caso A. Non è lecito correggere il risultato assegnando arbitrariamente P1 alla seconda operazione: un'eventuale evoluzione richiederebbe evidenza causale autorevole T01, oppure una revisione esplicita del criterio di accettazione. Nessuna di queste attività è stata eseguita.

Catena verificata: `model.py:535-554` interrompe T01 alla chiamata non risolta; `resources.py:152-175` posiziona la prima operazione; `resources.py:182-203` conserva il suffisso senza contesto; `tests/resource-timeline.py:222-236` verifica intenzionalmente una sola operazione cronologica nella fixture sequenziale non transazionale. Il controesempio aggiunge soltanto il confine REQUIRED necessario al caso A, senza chiedere test aggiuntivi per comportamenti già coperti.

**Review architetturale e operazioni.** `mana-transaction.analyze(include_facts=True)` restituisce modello e fatti dal medesimo snapshot; l'API precedente mantiene la restituzione del solo modello. T02 chiama `validate_model` e incorpora T01 integralmente. Non contiene un motore di propagation: copia `duringState`, usa `afterState` al ritorno dei figli e conserva gli eventi T01 senza modificarli. Gli ID fisici provengono soltanto da T01; lifetime e sospensione sono verificati prima di attribuire un'operazione. UNKNOWN non viene sostituito con P1/P2.

Le associazioni positive sono ristrette a field JdbcTemplate diretto e forma SQL chiusa. File, metodi, receiver, hash e span UTF-16 sono collegati ai fatti AST; commenti e stringhe contenenti codice non diventano chiamate. SQL dinamico, grammatica/API non supportata e injection ambigua conservano UNKNOWN. I nomi SQL sono identificatori lessicali, non identità runtime. Manager contestuale e datasource sono campi separati; datasource ed enlistment restano UNKNOWN. READ, WRITE e FOR UPDATE restano classificazioni/richieste; `lockAcquired` e granularità rimangono UNKNOWN. Nessuna deduzione da repository, datasource o configurazione prova il coinvolgimento di una connessione.

Il modello dichiara osservazioni sintattiche condizionali, senza presentarle come accessi già eseguiti. Non è implementato JPA/flush differito e non ne vengono dedotti effetti. Le operazioni UNPLACED non entrano nella timeline o in un grafo di attese. Premesse, incertezze e modello T01 originale sono preservati. Il validatore del JSON controlla coerenza interna, non autentica fatti coordinatamente falsificati: il limite documentato resta valido e non è stato esteso a garanzia di autenticità.

**Scenari indipendenti.** Gli oracoli seguenti derivano dal mandato e dalle fixture letterali, non dagli esempi generati. Le suite esistenti sono state rieseguite; il solo esperimento aggiuntivo riguarda il requisito A mancante.

| Caso | Esito e ambito dimostrato |
|---|---|
| A REQUIRED, due operazioni/P1 | FAIL: controesempio R1-A; il positivo a una operazione passa |
| B REQUIRES_NEW | PASS: P1 sospesa e viva, operazione su P2, END P2 prima di RESUME P1; operazione successiva a figlio vuoto usa P1 ripristinata |
| C NESTED | PASS: SP1 su P1, nessuna P2, savepoint non termina P1 |
| D nessuna transazione | PASS: operazione posizionata con NO_TRANSACTION, nessuna P |
| E UNKNOWN | PASS: nessuna P inventata; corpi non attraversati restano UNPLACED |
| F lifetime | PASS: rifiutati spostamento dopo END, riattribuzione a P2 terminata e attribuzione a P1 sospesa |
| G causalità indipendente dal contesto | PASS nel contratto T01: C06 accetta ordine sincrono dimostrato con contesto UNKNOWN; C07/C04 rifiutano suffissi non dimostrati. T02 preserva eventi e lascia fuori le operazioni senza posizione |
| H lock | PASS: SELECT/UPDATE e richiesta FOR UPDATE non diventano acquisizione o granularità; alterazioni positive vengono rifiutate |

**Regressioni locali nuove.** Tutti i comandi seguenti hanno exit 0; nessun test saltato.

| Suite / controllo | Risultato |
|---|---|
| transaction-boundaries.py | 16 PASS |
| transaction-self-invocation.py | 16 PASS |
| transaction-context-alternatives.py | 21 PASS |
| transaction-physical-lifetime.py | 19 PASS |
| transaction-transition-contract.py | 64 PASS |
| transaction-aop-causal-order.py | 26 PASS |
| mana-skill-factory.py | 23 PASS |
| resource-timeline.py | 22 PASS |
| Totale | **207 PASS**, 0 skipped |
| bash scripts/validate-repo.sh | PASS |
| ruff check sui quattro Python interessati | PASS |
| ruff format --check sugli stessi file | PASS |
| Tre esempi documentali | Validati e identici a nuova analisi degli stessi input |

La suite factory include governance, rifiuto dei comandi di attivazione, esclusione dalla discovery/profile compilation, integrità del candidato e preservazione del target. T01/S01 verificano isolamento temporaneo, argomenti JDK, assenza di build del target, confronto snapshot e rifiuto della sovrascrittura. Solo il helper Mana viene compilato; il target è letto con parser JDK e `-proc:none`, senza analisi/codegen/caricamento delle classi del target. Nessuna nuova campagna QA generale, download o accesso database. CI remota, Spring/database runtime, concorrenza e lock effettivi: **NOT RUN**.

**Integrità e inventario.** HEAD e develop sono ancora `e3537e3f8c8329a71615fe59d496757d5392c6a8`; branch `feature/mana-transaction-02`; indice vuoto. Tree committato comune `eab3046bed8a9c1f1470d2ec6b602f406fb9ed6e`. L'hash del manifest esterno coincide con S01: `f93d950fea5ba28ed2215e90f69013b48515386acdcf83d68bf16fc058174af8`; le sei voci coincidono col receipt e con gli originali/copie effettivi, inclusi byte e mode 0644.

| Materiale iniziale escluso | SHA-256 confermato |
|---|---|
| docs/reports/MANA-TRANSACTION-01-T01-MR00-transitions.csv | 14e1b536fea9ecea15c41cc8dd1747cf00e9334ad357297a2fc94f73195da8a7 |
| docs/reports/MANA-TRANSACTION-01-T01-MR01-coverage.csv | 07fb543921d0e6332d92f03264eb0031f54c4471753dc7a1c5b572610e22d8d0 |
| docs/reports/MANA-TRANSACTION-01-T01-MR01-R2.md | f095c7b5f3516a113e380fbc6ee6492145e0cb0b989be89fc89848d0cd33c933 |
| docs/reports/MANA-TRANSACTION-01-T01-MR01-R2-results.json | 301e313f6cc5d3bd6fcfe1cb415e88edee7aab028f6160a489d882a5ef5854ad |
| docs/roadmap/TRANSACTION-01-T02.md | f1f6f4e3a119b294c1e41958aad7cbfd7b498aebccbc8603cbe50f5399d913e7 |
| docs/roadmap/TRANSACTION-01.md | d9f49200ee122f0e981f94cf4da0625fd7757fe5986f88fad347d3a51dc33a6c |

I CSV originali hanno 69 e 92 CRLF, zero LF isolati; la sola normalizzazione virtuale coincide col blob HEAD. Nessuna riscrittura. I deliverable R2 e i due materiali roadmap preesistenti restano preservati ed esclusi dalla feature. Tutti i 18 hash dell'inventario implementazione S01 coincidono col receipt originale.

L'inventario JSON distingue precisamente: 19 file S01 (18 voci del receipt più il receipt stesso), i sei materiali preesistenti e i due deliverable R1. I tre JSON negli esempi sono artefatti generati S01, non oracoli. Log, cache Python della validazione, copia avversaria e timeline diagnostica sono esterni in `/private/tmp/mana-t02-s01-r1-z414j_47`. Non sono file da committare. Nessun file iniziale tracciato o non ignorato del repository è stato modificato durante R1; soltanto i due deliverable R1 sono stati aggiunti. Configurazioni, skill, progetti target originali, Familiar e REL-01/A non sono stati modificati o attivati dalle azioni di questa review. Una snapshot odierna non prova da sola l'assenza di esecuzioni storiche precedenti a R1; le garanzie riportate per la review si basano anche sul percorso eseguito e sulle suite d'isolamento.

**Decisione e Git finale.** Gate semantico **NEEDS_FIX** per R1-A; nessun SEMANTIC_REVIEW_PASS. Staging, commit firmato, verifiche firma/parent di un nuovo commit, verifica writer al punto di merge e merge ff-only: **NOT RUN**, perché la condizione preliminare è fallita. Commit SHA creato: nessuno. Develop è stato verificato in sola lettura alla baseline, senza switch. Nessun push, worktree, reset, stash, clean o checkout forzato. Il working tree conserva tutte le modifiche iniziali S01 e tutti i sei materiali; il JSON allegato contiene lo stato Git finale completo.

Per T02-S02 restano da qualificare identità datasource/risorsa, enlistment, alias, scenario concorrente, acquisizione/ritenzione, compatibilità delle richieste e prove di attesa. Le osservazioni UNPLACED non possono sostenere archi causali; un ciclo condizionale non prova deadlock e l'assenza di ciclo non prova assenza di deadlock. Nessuna implementazione S02 effettuata. Arresto alla consegna R1.
