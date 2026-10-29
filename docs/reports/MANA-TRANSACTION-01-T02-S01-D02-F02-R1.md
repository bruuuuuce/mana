# MANA-TRANSACTION-01-T02-S01-D02-F02-R1 — Binding Soundness & Utility Review

22 ottobre 2026. **SEMANTIC_REVIEW_PASS; UTILITY_DEMONSTRATED**, limitatamente al sottoinsieme rule-2. Nessuna certificazione positiva ingiustificata trovata nei casi revisionati. Consolidamento condizionato autorizzato dal mandato. Verdetto finale, commit SHA, firma, tree e stato Git sono nel [receipt finale](MANA-TRANSACTION-01-T02-S01-D02-F02-R1-results.json), generato dopo il consolidamento e separato dal commit cui si riferisce.

## Metodo e baseline

Branch iniziale `feature/mana-transaction-02`; HEAD e develop `e3537e3f8c8329a71615fe59d496757d5392c6a8`, tree `eab3046bed8a9c1f1470d2ec6b602f406fb9ed6e`. Indice inizialmente vuoto. Inventariati 1.306 file tracciati/non ignorati per byte e mode prima della review. Nessun file iniziale è stato modificato dalla review.

Letti R1, R2, F02, JSON/patch F02 e i due standard; esaminati JavaFacts, source snapshot/reparse, classificazione, traversal T01, validatori, proiezione, test, fixture e witness HIGH reali. Patch F02 verificato inversamente con `git apply --check --reverse`, senza applicarlo. Hash degli input e prove riproducibili sono nelle [evidenze](MANA-TRANSACTION-01-T02-S01-D02-F02-R1-evidence.json).

L'indipendenza consiste nell'esame del codice e dei sorgenti, nei nuovi controlli letterali e negli oracoli javac/javap, indipendenti dal classificatore. I due validatori condividono la policy: il loro reciproco accordo non è usato come oracolo Java indipendente. Nessuna delega o attestazione di reviewer esterno.

## Binding e dispatch

Il positivo richiede l'import singolo non statico Spring, campo senza annotazioni `private final JdbcTemplate jdbc = new JdbcTemplate()`, proprietario concreto top-level senza parent e scope incompleti, metodo e chiamata nel sottoinsieme ammesso. Un import singolo ha precedenza sui tipi omonimi di package importati implicitamente; uno shadow lessicale richiede invece attenzione allo scope. Il controllo globale rifiuta parametri di tipo di classe/metodo, import statici/ambigui, omonimi applicativi, classi membro/locali/anonime e inizializzatori omessi. Il parametro generico R2 non è più trasformato nell'import: il campo è `UNKNOWN_TYPE_PARAMETER:JdbcTemplate`.

Per la forma positiva l'allocazione e la dichiarazione passano attraverso lo stesso import. L'oggetto nasce esattamente dalla classe catalogata; un riferimento private final già inizializzato non può essere sostituito ordinariamente con una sottoclasse. La prova non dipende dall'assenza di override nell'inventario. Un campo iniettato mantiene solo il tipo statico e non qualifica il target dinamico. Bound Spring, spelling completamente qualificato, campi mutabili e allocazioni anonime rimangono fuori dal sottoinsieme; non sono stati risolti mediante un nuovo frontend.

La riparsificazione verifica i byte UTF-8 e gli hash, ricostruisce tutti i fatti AST del snapshot e li confronta, controllando separatamente i puntatori derivati bindingEvidence. Non basta falsificare modificatori/allocation o la firma del witness. Le sei falsificazioni nuove — firma, dipendenze, contesto, modificatori, byte mancanti e span — sono rifiutate da entrambi i validatori. Restano il limite dichiarato dell'autenticazione esterna del snapshot e l'assunzione di libreria autentica: una sostituzione coordinata dell'intero input non viene autenticata rispetto a un repository esterno.

Rieseguiti i 14 oracoli Java F02: tutti compilano/disassemblano; R2 ha erasure/owner `fixture.ApplicationJdbc`, i controlli membro/locale/anonimo espongono gli override applicativi. Un owner simbolico Spring in invokevirtual non prova da solo l'implementazione dinamica. I 14 controlli usano stub linguistici espliciti; il caso di overload artificiale non qualifica un overload della libreria reale. Per la nuova prova positiva è stata aggiunta anche compilazione contro Spring reale locale, descritta sotto.

I sorgenti HIGH R1/R2 sono riestratti con hash originali: zero leaf, prima frontiera P1 e secondo passo UNPLACED/UNKNOWN. I vecchi witness sono respinti da entrambi i validatori; R1 per dispatch incompleto, R2 storico per assenza dei byte necessari, oltre al blocco generico dimostrato dalla nuova estrazione. Nessuna modifica ai witness storici.

## Audit individuale delle nove degradazioni

Il [CSV completo](MANA-TRANSACTION-01-T02-S01-D02-F02-R1-degradations.csv) registra operazione, certificazioni prima/dopo, evidenza mancante, ragione, recuperabilità e span/hash. Gli eventi storici sono stati letti dagli artifact F01 autentici, verificandone gli hash; ogni call site è confrontato con la nuova osservazione del medesimo sorgente immutato.

| Caso / operazione | Prima | Ora | Classificazione |
|---|---|---|---|
| required-two 1: execute SELECT accounts | leaf/P1 | frontiera/P1 | JUSTIFIED_DEGRADATION |
| required-two 2: update DELETE ledger | leaf/P1 | UNPLACED/UNKNOWN | JUSTIFIED_DEGRADATION |
| required-three 1: execute SELECT accounts | leaf/P1 | frontiera/P1 | JUSTIFIED_DEGRADATION |
| required-three 2: update DELETE ledger | leaf/P1 | UNPLACED/UNKNOWN | JUSTIFIED_DEGRADATION |
| required-three 3: update INSERT audit | leaf/P1 | UNPLACED/UNKNOWN | JUSTIFIED_DEGRADATION |
| requires-new: update UPDATE ledger | leaf/P2 | frontiera/P2 | JUSTIFIED_DEGRADATION |
| nested: execute SELECT accounts FOR UPDATE | leaf/P1 | frontiera/P1 | JUSTIFIED_DEGRADATION |
| restored: update DELETE accounts | leaf/P1 | frontiera/P1 ripristinata | JUSTIFIED_DEGRADATION |
| terminated: update DELETE accounts | leaf/NO_TRANSACTION | frontiera/NO_TRANSACTION | JUSTIFIED_DEGRADATION |

Tutte e nove usano lo stesso tipo di campo iniettato senza evidenza di allocazione o wiring che determini l'implementazione. La configurazione del manager non determina quel bean JDBC. javac può confermare il tipo statico, ma gli strumenti esistenti non provano il target iniettato; l'assenza di subtype visibili non colma il vuoto. Nei tre passi di suffisso manca anche una continuazione certificata attraverso i predecessori. Le degradazioni non sono approvate soltanto perché conservative: derivano da queste prove mancanti, verificate per ogni evento. Nessun caso UNNECESSARY_DEGRADATION o INSUFFICIENT_EVIDENCE nella matrice. Recuperare lo stesso sorgente richiederebbe evidenza aggiuntiva; cambiare il sorgente in una nuova fixture positiva non ripristina la vecchia certificazione.

## Utilità positiva end-to-end

Nuova fixture `audit.Operations`, conservata integralmente nelle evidenze, con campo private final allocato esattamente, costruttore `Operations(javax.sql.DataSource ds) { jdbc.setDataSource(ds); }` e manager dichiarato separatamente. Il setup del datasource rende il controllo più rappresentativo della sola allocazione no-arg; non è interpretato come prova di identità datasource o enlistment. Il costruttore non viene attraversato da T01 e nessun metodo è stato aggiunto al catalogo leaf.

Due invocazioni CLI reali su sorgenti, senza IR/witness precompilati:

| Entry | Operazioni consecutive | Leaf / contesto | Dipendenze di ritorno normale |
|---|---|---|---|
| `audit.Operations#two()` | execute SELECT accounts; this.jdbc.update DELETE ledger | 2, P1/P1 | `[]`, `[4]` |
| `audit.Operations#three()` | execute SELECT accounts FOR UPDATE; this.jdbc.update UPDATE ledger; queryForList SELECT audit | 3, P1/P1/P1 | `[]`, `[4]`, `[4,5]` |

Producer e pubblicazione CLI exit 0. I JSON pubblicati vengono riletti in processi distinti e accettati da T01 e T02. Verificati slice UTF-16, hash sorgenti, firma e allocation, identità P1 e uguaglianza esatta degli eventi T01 dopo rimozione delle osservazioni Timeline. Snapshot target immutato.

La stessa fixture compila separatamente con `javac -proc:none` contro gli otto jar Spring **5.3.27** già presenti in `.m2`, senza stub, Maven o download. javap conferma campo private final, `new JdbcTemplate`, costruttore standard, setDataSource e i tre owner/descriptor del catalogo. Hash e comandi dei jar sono registrati. Questa prova qualifica il binding della fixture contro quei jar locali, non la libreria installata in un progetto terzo o il runtime Spring/database. Nessuna classe eseguita.

Terza entry `barrier()`: leaf SELECT, poi `System.gc()` irrisolta, poi DELETE. Risultato: `T01_RESOURCE_LEAF`, `T01_FRONTIER`, `UNPLACED`; l'ultimo contesto è UNKNOWN. Il ritorno normale delle leaf non elimina la barriera UNRESOLVED_CALL.

Sei nuovi controlli sorgente negativi — iniezione, tipo completamente qualificato, campo mutabile, allocazione anonima, classe membro e parametro generico di metodo — compilano/disassemblano e producono zero leaf. Per il proprietario con classe membro T01 lascia tutto il corpo UNPLACED; non viene inventata una frontiera attraversata. Le limitazioni globali possono ridurre ulteriormente la copertura di codice non pertinente; l'utilità dimostrata riguarda il sottoinsieme esplicito, non bean arbitrariamente iniettati.

## Regressioni e governance

| Gate rieseguito | Esito |
|---|---|
| Sei suite T01, 16/16/21/19/64/26 | 162 PASS |
| Factory / Resource Timeline | 23 + 22 PASS |
| Resource leaves / dispatch, aspettative F02 già migrate | 31 + 22 PASS |
| Totale precedente | **260 PASS**, zero skipped |
| Nuova suite F02 binding | **10 PASS**, zero skipped |
| Oracoli F02 javac/javap | **14 PASS** |
| Replay originali | 12 eseguiti: **6 PASS storici + 6 DEGRADED**, contratto attuale 12 PASS |
| HIGH R1/R2 originali | zero leaf; vecchi witness rifiutati da entrambi |
| Nuovi controlli review | 3 percorsi CLI, 6 negativi sorgente, 6 falsificazioni PASS |
| Spring 5.3.27 reale sulla fixture nuova | javac/javap exit 0/0 |
| Validazione repository / Ruff check / Ruff format --check | PASS, exit 0 |
| Patch inverso / whitespace dei file selezionati esclusi i patch storici | PASS, nessuna applicazione |

Il controllo whitespace completo dello staging segnala 53 righe di contesto vuote dei tre patch storici (una singola spaziatura, richiesta dal formato unified diff). Il controllo sui restanti file selezionati passa. I patch non vengono normalizzati o riscritti.

Non vengono ribattezzate PASS le vecchie aspettative degradate né ripristinati gli oracoli per copertura artificiale. Le 260 regressioni correnti comprendono la migrazione F02 dichiarata; il loro PASS non significa conservazione di quelle nove certificazioni storiche.

La Timeline mantiene RESOURCE_LEAF_CALL condizionale e preserva gli eventi e gli invarianti T01: P vive/correnti, sospensione/ripresa, NESTED/SP, terminazione, ordine causale e intercettazione UNKNOWN. Datasource UNKNOWN/id null, enlistment UNKNOWN, lockAcquired UNKNOWN, identità runtime e granularità UNKNOWN verificati anche nella nuova prova positiva e nei replay. FOR UPDATE resta sintassi di richiesta.

Isolamento e governance verificati nelle suite: nessuna build del target da parte del producer, parser esterno, output senza sovrascrittura, snapshot target invariati, candidate pending/untrusted escluse da discovery e compilazione dei profili, nessun comando di attivazione. Validare i metadata delle skill esistenti non ne attiva una.

## Consolidamento e limiti residui

L'inventario per staging esplicito è nelle evidenze. Esclusi rigorosamente i sei materiali protetti originali e `docs/architecture/MANA-EXEC-CONTRACT-001.md`, estraneo. La proposta S02 già consegnata da S01 viene conservata immutata come documento storico nel consolidamento S01; nessuna implementazione o esecuzione S02. Report, esempi e patch precedenti non vengono riscritti. Il receipt finale è deliberatamente esterno al commit che identifica, evitando SHA autoreferenziali.

Il consolidamento richiede parent baseline, firma valida, tree corrispondente al contenuto selezionato e develop ancora alla baseline, poi switch sicuro e fast-forward. Ogni byte/mode iniziale e i sei protetti devono rimanere invariati. Nessun reset, stash, clean, force, nuovo worktree o push. In caso di switch impedito il mandato impone READY_FOR_INTEGRATION.

Per S02 restano datasource/alias e identità risorsa, connessioni/enlistment, acquisizione/ritenzione/compatibilità dei lock, concorrenza e dipendenze di attesa. Nessuna diagnosi di deadlock o assenza di deadlock. Generics, FQ names e wiring restano UNKNOWN dove non qualificati; ampliare il binding richiederebbe una decisione separata e il solo frontend statico non determinerebbe il bean dinamico.

Runtime Spring/JDBC/database, CI remota, deployed binary e release acceptance: **NOT RUN**. Nessuna modifica a Familiar, attivazione di skill, correzione automatica o avvio T02-S02. Arresto alla consegna.
