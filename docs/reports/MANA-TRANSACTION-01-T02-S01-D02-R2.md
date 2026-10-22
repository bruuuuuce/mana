# MANA-TRANSACTION-01-T02-S01-D02-R2 — Dispatch Safety Review & Conditional Integration

Data: 22 ottobre 2026. Verdetto: **NEEDS_FIX**. Nessun SEMANTIC_REVIEW_PASS, consolidamento, staging, commit o integrazione.

La correzione F01 blocca il controesempio originale D02-R1-A e supera nuovamente tutte le 260 regressioni richieste e i 12 replay. La review individua però **D02-R2-A, HIGH bloccante**: un parametro di tipo Java chiamato `JdbcTemplate`, con bound applicativo, viene confuso con l'import Spring. Il producer emette due leaf standard e prosegue P1/P1; entrambi i validatori accettano il report autenticamente estratto. Una prova Java separata conferma che il ricevente e i metodi invocati sono applicativi.

## Metodo e baseline

Verificati branch `feature/mana-transaction-02`, HEAD e develop `e3537e3f8c8329a71615fe59d496757d5392c6a8`, indice vuoto. Letti i sette input richiesti, i risultati completi R1/F01, codice effettivo, estrattore, classificatore, traversal, validatori, Resource Timeline, fixture e oracoli. Gli hash dei cinque file dichiarati dalla patch F01 coincidono con i file reali; corrisponde anche l'hash della patch.

Questa conversazione comprende lo storico dell'implementazione: non si rivendica l'attestazione di un reviewer esterno. L'indipendenza del finding consiste in un nuovo controesempio sorgente, aspettative letterali non derivate dalla policy, due controlli e una prova di binding con javac/javap indipendente dal classificatore. Nessuna delega. Non si assume che producer e validatori siano autorità indipendenti quando riusano la stessa regola.

## D02-R2-A — shadow del tipo importato mediante parametro di tipo

**Gravità HIGH; bloccante.** Requisiti violati: distinzione fra tipo statico, dichiarazione del metodo e possibile implementazione; shadow del tipo locale da rifiutare; nessuna certificazione positiva da informazioni di tipo incomplete; mantenimento della frontiera per implementazioni applicative non qualificate.

Il progetto minimo usa gli stessi import Spring, manager DataSourceTransactionManager e contesto condizionale della fixture. Il solo cambiamento determinante rispetto al ricevente applicativo esplicito è l'introduzione del parametro di tipo che ne nasconde il nome:

```java
import org.springframework.jdbc.core.JdbcTemplate;

@Service
class Operations<JdbcTemplate extends ApplicationJdbc> {
    @Autowired JdbcTemplate jdbc;
    @Transactional public void sequence() {
        jdbc.execute("SELECT * FROM accounts");
        jdbc.update("DELETE FROM ledger");
    }
}

@Service
class ApplicationJdbc {
    public void execute(String sql) {
        throw new IllegalStateException("application implementation");
    }
    public int update(String sql) { return 0; }
}
```

Entry `fixture.Operations#sequence()`, policy JDBC_LITERAL_V1, initialState NO_TRANSACTION, entryThroughProxy true, capability esplicite del manager tx. Il JSON associato conserva sorgente completo, contesto e report. Sorgente `src/main/java/fixture/Resources.java`, SHA-256 `3b86e740a4459ddd87d4612be73b457e3477a53d126e4b1e16da2c53074e6ea7`. Il parametro è alla riga 17, campo alla 18, chiamate alle righe 20/21, UTF-16 `[845,883)` e `[893,926)`.

**Relazioni Java effettive:** `JdbcTemplate` nel campo è la variabile di tipo dichiarata da Operations, non la classe importata. Il bound e l'erasure sono `fixture.ApplicationJdbc`. La selezione dei metodi è `ApplicationJdbc#execute(String):void` e `ApplicationJdbc#update(String):int`; il dispatch può raggiungere quelle implementazioni applicative o override di loro sottoclassi. Non è un dispatch autorizzato all'implementazione standard Spring. Nessuna risoluzione dinamica completa dei bean è necessaria per rilevare questa incompatibilità statica.

La catena del difetto nei file correnti è:

1. `JavaFacts.java:22` risolve il nome tramite la mappa degli import senza scope dei parametri di tipo.
2. `JavaFacts.java:78` applica tale risoluzione al campo, emettendo `type=org.springframework.jdbc.core.JdbcTemplate`.
3. `JavaFacts.java:58`/`:135` non rappresentano i parametri di tipo o i relativi bound; il nuovo scanner segnala classi annidate, non questo shadow. Config, Operations e ApplicationJdbc hanno tutte `parents=[]` e `dispatchHazards=[]`.
4. `resource_leaf.py:53` controlla classi/parent/factory/annotazioni, ma non dispone dell'informazione omessa; `classify` accetta il tipo del campo e assegna le firme Spring standard.
5. `resource_leaf.py:297` riclassifica con quei medesimi fatti incompleti: il witness del producer coincide con quello atteso e passa. La serializzazione/ricaricamento non cambia l'accettazione.
6. `resources.py:94` valida T01 e proietta le leaf: T02 accetta entrambe le operazioni come T01_RESOURCE_LEAF su P1. L'autorità T01 è erronea già prima della proiezione.

Trace effettiva accettata: FRAME_ENTER → PHYSICAL_BEGIN P1 → LOGICAL_BEGIN L1 → RESOURCE_LEAF_CALL 4 → RESOURCE_LEAF_CALL 5 → LOGICAL_END → PHYSICAL_END_OUTCOME_UNKNOWN → FRAME_EXIT. La seconda leaf ha dipendenza di ritorno normale `[4]`; nessuna frontiera e afterState NO_TRANSACTION. **Atteso:** zero leaf standard, prima chiamata UNRESOLVED_CALL con contesto P1, nessuna continuazione certa sulla seconda, che deve restare non posizionata/UNKNOWN.

Il finding non dipende dall'eccezione del corpo applicativo: il difetto è l'identità del ricevente/metodo. Non è una falsificazione coordinata di JSON: non sono alterati fatti, witness, hash, IR o eventi dopo l'analisi. Il CLI estrae il sorgente reale e i validatori lo accettano. La premessa «bounded source dispatch screen is complete» è falsa per una relazione lessicale osservabile nel sorgente.

## Oracolo indipendente del binding Java

Il driver `prove-java-binding.py`, esterno al repository, compila con `javac -proc:none` **due piccoli sorgenti fissi di controllo linguistico**, senza annotazioni, Spring reale o processori. Il primo mantiene parametro di tipo, campo e due invocazioni; il secondo è soltanto uno stub del tipo importato. Non viene compilato il progetto analizzato dal CLI, eseguita alcuna classe o qualificato alcun runtime Spring/JDBC.

`javap -c -p -s fixture.Operations` restituisce:

```text
class fixture.Operations<JdbcTemplate extends fixture.ApplicationJdbc>
  descriptor: Lfixture/ApplicationJdbc;
  invokevirtual ... fixture/ApplicationJdbc.execute:(Ljava/lang/String;)V
  invokevirtual ... fixture/ApplicationJdbc.update:(Ljava/lang/String;)I
```

Entrambi i comandi terminano con exit 0. Questo conferma, separatamente dall'estrattore Mana, che il tipo importato viene nascosto e i target simbolici dei due invokevirtual sono applicativi. Il JSON conserva i due sorgenti, argv, log/hash e bytecode disassemblato. La prova riguarda il binding Java, non l'avvio del contesto Spring.

| Controllo nuovo / aspettativa letterale | Leaf attese | Leaf effettive | Contesto effettivo osservazioni | Esito |
|---|---:|---:|---|---|
| Ricevente standard, nessun parametro di tipo | 2 | 2 | P1/P1 | PASS |
| Campo esplicito ApplicationJdbc | 0 | 0 | Prima frontiera P1; nessuna seconda osservazione JDBC | PASS |
| Campo con parametro JdbcTemplate extends ApplicationJdbc | 0 | 2 | P1/P1, entrambe T01_RESOURCE_LEAF | **FAIL** |

Il driver termina exit 1 per la sola violazione attesa del nuovo caso; non modifica l'oracolo per ottenere PASS. I tre progetti restano identici prima/dopo l'analisi. Dopo questo finding non sono state aggiunte altre campagne né applicate correzioni.

## Open-world e contratto

Resource Leaf Extension v1, righe 154–163, dichiara esplicitamente la selezione condizionale dell'implementazione standard e l'assenza di override/advisor esterni; Transaction Model v1 dichiara il wiring chiuso alle dichiarazioni osservate. Il contratto precisa che tali premesse non dimostrano il bean concreto a runtime e non possono scavalcare un controllo sorgente incompleto o contraddittorio.

Questa delimitazione consente i positivi standard **soltanto nello scenario dichiarato**; il progetto analizzato non costituisce l'universo delle implementazioni runtime. La review non equipara assenza di subtype locali ad assenza di subtype esterni. In D02-R2-A il problema è ancora più diretto: il ricevente non è staticamente il tipo della libreria. Una premessa sul dispatch standard non può correggere quel binding Java falso o dichiarare completo il controllo che lo ha omesso. Il contratto non giustifica il report prodotto dal controesempio.

## Verifiche richieste, rieseguite

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
| transaction-resource-leaves | 31 PASS |
| **Regressioni originali** | **238 PASS, zero skipped** |
| transaction-resource-dispatch F01, invariata | **22 PASS, zero skipped** |
| **Totale suite richieste** | **260 PASS, zero FAIL, zero skipped** |
| Dodici replay | **12 PASS** |
| HIGH originale D02-R1-A, nuova analisi | PASS: zero leaf; T01_FRONTIER/P1 poi UNPLACED/UNKNOWN |
| Witness HIGH originale, validatori correnti | Rifiutato da entrambi per dispatch non dimostrato |
| Nuovo controesempio e due controlli | **2 PASS, 1 FAIL**, exit 1 |
| Prova indipendente javac/javap | PASS, exit 0/0 |
| bash scripts/validate-repo.sh | PASS, exit 0 |
| Ruff check / format --check, nove Python pertinenti | PASS, exit 0 |

I dodici replay riusano in sola lettura le piccole fixture F01 e il singolo validatore pre-D02 già salvato; contesti/output sono nuovi nella directory R2. Conservano gli oracoli precedenti. I casi a due/tre operazioni standard mantengono P1 e dipendenze di ritorno normale; REQUIRES_NEW usa P2 con P1 sospesa, NESTED conserva P1; ordine perso e contesto UNKNOWN non autorizzano il suffisso; dopo terminazione non si ricicla P1. La suite causale e la proiezione mantengono le rispettive distinzioni.

I 22 test F01 rifiutano witness mancanti/alterati/incompatibili, tipo arbitrario esplicito, sourceFacts senza il nuovo controllo, classi membro statiche/non statiche, subtype, hook, factory e wiring opaco. Entrambi i validatori passano questi negativi; non coprono però lo shadow di un parametro di tipo autenticamente estratto. La riclassificazione condivisa, pur evitando due policy divergenti, conferma reciprocamente quest'ultimo errore.

Datasource UNKNOWN/id null, enlistment JDBC UNKNOWN, lockAcquired UNKNOWN, granularità e identità runtime UNKNOWN restano tali anche nel nuovo controesempio. T02 non alloca nuove transazioni fisiche: il finding consiste nell'associazione e continuazione non autorizzate delle due osservazioni su P1, non nell'invenzione di P2 o nella certificazione di un lock. Nessuna diagnosi di deadlock.

## Immutabilità, governance e arresto Git

I **1.300 file iniziali** tracciati/non ignorati restano identici per byte e mode. I sei materiali protetti coincidono con l'inventario iniziale e con gli hash originali dei receipt; CSV con 69/92 CRLF e zero LF isolati. Report, risultati, patch F01, oracoli storici, esempi e sorgenti precedenti non sono modificati. Questa review aggiunge soltanto il presente rapporto e il relativo `-results.json`.

I controlli di isolamento e governance sono PASS nelle suite pertinenti: parser esterno e nessuna build del target; output isolati e snapshot immutabili; candidate pending/untrusted, non registrate, non attivate e non ammesse alla discovery/compilazione dei profili. Il controllo linguistico separato non cambia il comportamento parse-only del CLI. Nessuna modifica a Familiar o ai percorsi di attivazione.

Evidenze esterne: `/private/tmp/mana-d02-r2-w8zxcm_k`, circa 2,6 MiB alla verifica. Nessuna copia completa, nuovo worktree, backup voluminoso, modifica o cleanup di archivi qualificati. Riutilizzate le salvaguardie precedenti. Nessun reset, stash, clean, force, push o cambio branch.

Il finding HIGH fa fallire il gate semantico. Selezione per consolidamento, staging, commit firmato, verifica di firma/parent/tree di un nuovo commit, verifica writer per integrazione, switch e merge --ff-only: **NOT RUN**, per precondizione semantica fallita. Non viene attribuito l'arresto a un ipotetico impedimento Git. SHA del commit creato: **nessuno**. HEAD e develop restano alla baseline, indice vuoto e lista worktree invariata; stato Git completo nel JSON.

Per T02-S02 restano da qualificare identità datasource/risorsa e alias, connessioni/enlistment, acquisizione/ritenzione/compatibilità dei lock, concorrenza e dipendenze di attesa. Runtime Spring/JDBC/database, CI remota, release acceptance e attestazione di reviewer esterno: **NOT RUN**. Nessuna implementazione S02. Consegna e arresto a **NEEDS_FIX**; nessuna correzione automatica del nuovo finding.
