# MANA-TRANSACTION-01-T02-S01-D02-R1 — Resource Leaf Review & Integration

Data: 21 ottobre 2026. Verdetto: **NEEDS_FIX**. Gate semantico non superato; nessuna correzione, staging, commit o integrazione.

La review ha trovato **D02-R1-A, HIGH bloccante**: un override JdbcTemplate dichiarato in una classe membro di una configurazione sfugge all'esclusione dei subtype. La policy emette comunque due RESOURCE_LEAF_CALL con firme dell'implementazione standard e prosegue con P1/P1. Il modello viene accettato sia dal validatore T01 sia dalla Resource Timeline. Il caso equivalente con subtype top-level viene invece fermato correttamente.

## Metodo e baseline

Branch `feature/mana-transaction-02`, HEAD e develop `e3537e3f8c8329a71615fe59d496757d5392c6a8`; commit tree comune `eab3046bed8a9c1f1470d2ec6b602f406fb9ed6e`. Indice vuoto.

Letti contratto Resource Leaf, Resource Timeline, Transaction Model v1, rapporto/risultati/patch D02 e contratto MR00; esaminati direttamente estrattore, catalogo, traversal, validatori, consumer, fixture e oracoli. Gli hash dei file dichiarati dal receipt D02 e del suo patch coincidono con i file reali. Il patch passa `git apply --check --reverse`, senza applicazione.

Eseguite nuove analisi e un controesempio sorgente con oracolo indipendente dal motore. Nessuna delega. Questa conversazione contiene anche lo storico dell'implementazione: non viene rivendicata un'attestazione di reviewer esterno. Il finding è fondato su sorgenti correnti e nuove esecuzioni, non sulla sola dichiarazione del receipt; nessun SEMANTIC_REVIEW_PASS è stato emesso.

## D02-R1-A — override in classe membro classificato come leaf standard

**Requisiti violati:** esclusione degli override/dispatch non risolti; riconoscimento conservativo verificabile; mantenimento della frontiera quando la chiamata non appartiene all'implementazione supportata dimostrabile nel modello. La premessa di dispatch standard non può supplire a un limite di risoluzione esplicito del grafo dei tipi sorgente.

Il controesempio riusa la fixture esistente in tre piccole copie esterne. Come nel witness R1, viene aggiunta soltanto `@Transactional` a `Operations.sequence()`; per il caso negativo si aggiunge in fondo al medesimo sorgente:

```java
@Configuration class CustomConfig {
    static class CustomJdbc extends JdbcTemplate {
        @Override public void execute(String sql) {
            throw new IllegalStateException("custom override");
        }
    }
    @Bean public CustomJdbc customJdbc() { return new CustomJdbc(); }
}
```

Entry e corpo già presenti nella fixture:

```java
@Autowired JdbcTemplate jdbc;
@Transactional public void sequence() {
    jdbc.execute("SELECT * FROM accounts");
    jdbc.update("DELETE FROM ledger");
}
```

Import, manager, proxy e capability restano quelli della fixture. Contesto `resourceLeafPolicy: JDBC_LITERAL_V1`, stato iniziale NO_TRANSACTION, entryThroughProxy true. Nessun input `safe=true`, nessuna manipolazione di fatti, IR, witness o hash; il report viene prodotto e validato dal CLI Python sul sorgente reale della copia. Il finding riguarda la classificazione del dispatch; la possibilità di eccezione, da sola, è già ammessa dal contratto e non costituisce il finding. Nessuna invocazione JDBC è stata eseguita a runtime.

Il sorgente negativo è `src/main/java/fixture/Resources.java`, SHA-256 `2bbb425bb082f9dc4d326942099b1257ab93698115fd45dde961452428811f49`. `sequence()` resta alla riga 48: call site [2630,2668) e [2670,2703), UTF-16, proprietario F1. La configurazione aggiunta è alle righe 55–60, override alla riga 57. Il JSON allegato contiene sorgente completo, contesto, driver e report integrale per riprodurre il caso senza dipendere dalle copie temporanee.

| Variante / oracolo letterale | Leaf attese | Leaf effettive | Posizionamento effettivo | Esito |
|---|---:|---:|---|---|
| Fixture standard, senza CustomConfig | 2 | 2 | P1/P1, entrambe T01_RESOURCE_LEAF | PASS |
| Stesso override in classe top-level | 0 | 0 | Prima T01_FRONTIER/P1, seconda UNPLACED/UNKNOWN | PASS |
| Override in classe membro di CustomConfig | 0 | 2 | P1/P1, entrambe T01_RESOURCE_LEAF | **FAIL** |

Il positivo standard ha lo stesso SHA sorgente del witness R1 (`e24bba87b81eecfa68d51c6eaf7fd8bf4c09100ee0e340840a0b9d4ddb10a284`). Nella variante top-level, `fixture.CustomJdbc` e il parent JdbcTemplate compaiono nei fatti e attivano la guardia. Nella variante membro i fatti contengono soltanto:

```text
fixture.CustomConfig
parents = ["UNKNOWN_NESTED_CLASS_OR_INITIALIZER"]
customJdbc.returnType = "CustomJdbc"
```

Non contengono `fixture.CustomConfig.CustomJdbc` né il suo override. Il limite di estrazione è esplicito, ma il catalogo non lo tratta come impossibilità di escludere un dispatch alternativo.

**Catena causale del difetto:**

- `JavaFacts.java:119–120` sostituisce la classe membro con il marcatore UNKNOWN sul contenitore, senza estrarre subtype/metodi annidati.
- `resource_leaf.py:138–144` esclude soltanto classi/parent JdbcTemplate già materializzati o metodi il cui returnType è esattamente JdbcTemplate. Il marcatore sul contenitore non corrisponde a quei controlli; `CustomJdbc` restituito dal bean non viene risolto.
- La guardia locale sui parent del chiamante non aiuta: il chiamante è Operations, non CustomConfig. La classificazione assegna la firma standard `JdbcTemplate#execute(java.lang.String):void` a una chiamata il cui dispatch sorgente non è qualificato.
- `validate_call`, righe 271–283, riclassifica con la medesima regola incompleta e accetta il witness. La verifica è stata ripetuta anche sul JSON serializzato e ricaricato.
- T02 copia correttamente l'autorità T01: riceve leaf alle sequenze 4 e 5, con dipendenza di ritorno normale `[4]` per la seconda. Proprio l'autorità di classificazione fornita da T01 è insufficiente.

Trace negativo accettato: FRAME_ENTER F1 → BEGIN P1 → BEGIN L1 → RESOURCE_LEAF_CALL 4 → RESOURCE_LEAF_CALL 5 → END L1 → END P1(outcome UNKNOWN) → FRAME_EXIT. Nessuna frontiera irrisolta; after-state NO_TRANSACTION sul percorso normale condizionale. Il comportamento richiesto è conservare la chiamata come irrisolta e non autorizzare il secondo passo certo con una leaf standard non qualificata; il contesto noto al primo call site non va cancellato.

Questo non è il limite documentato dell'autenticazione di JSON coordinatamente falsificato: tutti i fatti provengono da una nuova estrazione del sorgente e il marcatore UNKNOWN è autentico. Le 31 regressioni D02 verificano il subtype top-level, ma non questo caso membro. Il green delle suite non copre tale distinzione.

**Disposizione:** NEEDS_FIX. Non è stato ampliato il catalogo, non è stato modificato l'estrattore e non è stata implementata una correzione. Una futura correzione deve conservare l'incertezza del dispatch quando il grafo pertinente è incompleto e mantenere i positivi qualificati; questa review si ferma al finding.

## Verifiche eseguite

| Suite / controllo nuovo | Risultato |
|---|---|
| transaction-boundaries | 16 PASS |
| transaction-self-invocation | 16 PASS |
| transaction-context-alternatives | 21 PASS |
| transaction-physical-lifetime | 19 PASS |
| transaction-transition-contract | 64 PASS |
| transaction-aop-causal-order | 26 PASS |
| mana-skill-factory | 23 PASS |
| resource-timeline | 22 PASS |
| transaction-resource-leaves | 31 PASS |
| **Totale esistente** | **238 PASS, zero skipped** |
| Replay D01/D02 | **12 PASS** |
| Nuovo probe con i tre controlli sopra | **2 PASS, 1 FAIL**, exit 1 |
| `bash scripts/validate-repo.sh` | PASS, exit 0 |
| Ruff check e format --check sugli otto Python pertinenti | PASS, exit 0 |
| Patch D02, controllo inverso senza applicazione | PASS, exit 0 |

I replay sono stati eseguiti con un driver piccolo nella nuova directory di review: riuso in sola lettura dei progetti e del validatore pre-D02, nuovi contesti/output esterni, nessuna sovrascrittura delle evidenze D02. I dieci casi sorgente, il controllo legacy R1 e il rifiuto del nuovo evento da parte del vecchio validatore sono PASS. I witness negativi D01/D02 su opacità, programmatico, async/UNKNOWN, causalità persa, terminali, versioni e witness manomessi restano verificati dalle suite e dai replay. Non sono stati rietichettati FAIL storici.

Le aspettative su due/tre REQUIRED, P2 corrente con P1 sospesa, NESTED/SP su P1, frontiera irrisolta e P terminate sono coerenti negli scenari coperti. La suite causale conserva anche la distinzione C06 fra ordine dimostrato e contesto UNKNOWN; C01/C04/C07 non autorizzano un suffisso con ordine perso. Il finding è circoscritto all'eleggibilità della leaf, non a una deduzione di nuovi identificatori fisici in T02.

Le suite verificano snapshot dei target, isolamento del parser, assenza di build del target, corrispondenza T01/T02 e rifiuto della sovrascrittura. I tre progetti avversari hanno hash identici prima/dopo ciascuna analisi. La fixture originale del repository è inclusa anche nell'inventario byte/mode iniziale/finale. La governance factory controlla integrità dei candidate, comandi di approvazione/attivazione non disponibili, esclusione da discovery/profile compilation e preservazione del target; tutti i relativi test sono PASS. Nessuna candidate attivata.

## Limiti semantici confermati

L'evento leaf è distinto dalla frontiera e le premesse di ritorno normale sono pubbliche; un ritorno normale non è dichiarato realmente avvenuto o equivalente a successo SQL. I consumer aggiornati rifiutano eventi/versioni incompatibili e il validatore pre-D02 rifiuta l'evento nuovo. La riclassificazione rifiuta molti witness falsificati, ma non rileva il difetto di eleggibilità D02-R1-A.

Negli scenari verificati l'output separa operazione statica, identificatore lessicale della risorsa, contesto applicativo, datasource, enlistment e lock. Datasource UNKNOWN/id null, enlistment UNKNOWN, lockAcquired UNKNOWN, identità runtime e granularità UNKNOWN rimangono tali anche nel controesempio: il finding non certifica coinvolgimento JDBC o acquisizione di lock. Non sono state emesse diagnosi di deadlock.

Per S02 restano da qualificare identità datasource/risorsa, alias, connessione/enlistment, acquisizione e ritenzione dei lock, compatibilità, concorrenza e dipendenze di attesa. S01 non prova deadlock o assenza di deadlock. Runtime Spring/JDBC, database, CI remota e release acceptance: NOT RUN.

## Integrità e arresto Git

Tutti i **1.293 file iniziali** tracciati e non ignorati sono identici per byte e mode. I sei materiali protetti coincidono con il receipt S01 e le salvaguardie originali; manifest esterno SHA-256 `f93d950fea5ba28ed2215e90f69013b48515386acdcf83d68bf16fc058174af8`. CSV conservati con 69/92 CRLF, zero LF isolati; normalizzazione soltanto virtuale uguale a HEAD. Report/risultati/patch e sorgenti D02 preesistenti rimangono invariati.

La review aggiunge soltanto questo rapporto e `MANA-TRANSACTION-01-T02-S01-D02-R1-results.json`. Probe, tre piccole fixture, output, cache e log sono esterni in `/private/tmp/mana-t02-s01-d02-r1-ovqw2cqq`, circa 2,3 MiB alla verifica. Nessuna copia integrale, archivio voluminoso, nuovo backup o worktree; riusate le salvaguardie esistenti.

Il gate semantico negativo impedisce il consolidamento. Selezione definitiva dei file da integrare, staging esplicito, commit firmato, verifica firma/parent di un nuovo commit, switch e fast-forward: **NOT RUN**. Commit SHA creato: **nessuno**. Non è stata simulata una condizione READY_FOR_INTEGRATION né attribuito l'arresto a ipotetici problemi di switch: la causa è D02-R1-A.

HEAD e develop restano alla baseline; indice vuoto e commit tree comune invariato. Il JSON contiene lo stato Git finale completo e le verifiche di integrità. Nessun reset, stash, clean, force, push, modifica a Familiar, attivazione di skill o avvio T02-S02. Arresto alla consegna NEEDS_FIX.
