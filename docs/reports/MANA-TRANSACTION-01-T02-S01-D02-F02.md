# MANA-TRANSACTION-01-T02-S01-D02-F02 — Java Semantic Binding Gate

22 ottobre 2026. Verdetto: **FIX_READY_FOR_REVIEW**, per il sottoinsieme ridotto descritto qui. Non è un'attestazione di review indipendente, accettazione runtime o integrazione.

Branch `feature/mana-transaction-02`, HEAD `e3537e3f8c8329a71615fe59d496757d5392c6a8`. Nessun commit, staging, merge, push, nuovo worktree, modifica a Familiar, attivazione di skill o implementazione T02-S02. Consegna e arresto.

## Causa e prima/dopo

Letti direttamente R1, R2, risultati R2, contratto leaf, estrattore, classificatore, traversal T01 e validatore/proiezione T02. I due sorgenti HIGH sono rieseguiti byte per byte, con controllo degli hash registrati nelle review. Il prima usa i report autentici conservati nelle review; il dopo è una nuova analisi del codice corretto.

| Relazione | D02-R1-A | D02-R2-A |
|---|---|---|
| Import dichiarato | Spring JdbcTemplate | Spring JdbcTemplate |
| Dichiarazione pertinente | Campo staticamente Spring; subtype membro CustomConfig.CustomJdbc omesso | Variabile di tipo Operations.JdbcTemplate nasconde l'import |
| Tipo effettivo / bound | API statica non determina il bean concreto | Bound ed erasure ApplicationJdbc, non Spring |
| Target potenziale | Override applicativo execute e hook virtuali | ApplicationJdbc.execute/update o ulteriori override |
| Firma emessa storicamente | Firme standard del catalogo senza prova del dispatch | Firme standard Spring attribuite al tipo sbagliato |
| Origine | Omissione dell'estrattore; producer trattava l'inventario incompleto come sufficiente | qualify applicava l'import senza scope dei parametri generici |
| Witness / validatori | Riclassificazione dalla stessa omissione | Riclassificazione dal medesimo tipo erroneamente qualificato |

La Resource Timeline proiettava l'autorità T01 errata; non era la fonte iniziale del falso positivo. La firma compatibile non prova né la dichiarazione Java né il comportamento consentito dalla policy. La presenza della policy non rende sicura una chiamata.

| Controllo | Leaf storiche | Leaf F02 | Posizionamento F02 |
|---|---:|---:|---|
| HIGH R1, sorgente originale | 2 nella review R1; già 0 dopo F01 | 0 | T01_FRONTIER/P1, UNPLACED/UNKNOWN |
| HIGH R2, sorgente originale | 2 | 0 | T01_FRONTIER/P1, UNPLACED/UNKNOWN |
| Campo Spring iniettato standard | 2 | 0 | T01_FRONTIER/P1, UNPLACED/UNKNOWN |
| Nuovo campo private final con allocazione qualificata dal contratto | Nuovo controllo | 2 | Due T01_RESOURCE_LEAF/P1, dipendenze `[]`, `[4]` |
| Tre call sullo stesso ricevente certificato | Nuovo controllo a tre call | 3 | P1/P1/P1, dipendenze `[]`, `[4]`, `[4,5]` |

Entrambi i validatori rifiutano i witness HIGH storici. R1 incontra il controllo di dispatch; R2 storico non dispone dei byte sorgenti necessari alla nuova prova. Il sorgente R2 riestratto porta anche il marcatore generico bloccante: non è un semplice rifiuto di versione. Il suffisso generico conserva l'osservazione UNKNOWN senza attribuirle un'operazione JDBC dimostrata.

## Contratto positivo e implementazione

Il contratto aggiornato è `docs/standards/resource-leaf-extension-v1.md`. TYPE_BINDING_PROVEN e DISPATCH_PROVEN sono obblighi concettuali; nessun booleano pubblico del witness li sostituisce. La regola passa alla versione 2, con schemi evento/witness e capability esistenti.

Il positivo richiede un campo **private final**, senza annotazioni, dichiarato con il nome importato esplicitamente da Spring e inizializzato esattamente con `new JdbcTemplate()` senza argomenti né corpo anonimo. Dichiarazione e allocazione devono usare quel medesimo import singolo non statico; classe proprietaria concreta, top-level, senza parent o scope omessi. Restano i limiti precedenti su chiamante, contesto, statement, argomento String letterale, API e grammatica SQL.

L'import viene controllato insieme agli scope AST, alla dichiarazione del campo e all'allocazione. L'allocazione esatta conservata da un riferimento private final esclude la sostituzione ordinaria con un subtype applicativo. L'assenza di subtype osservati, da sola, non è una prova runtime e non viene più usata per certificare il campo iniettato. La premessa precedente di dispatch standard presunto per l'iniezione è ritirata.

JavaFacts registra nei fatti interni modificatori e forma dell'allocazione; riusa dispatchHazards per parametri generici di classe/metodo, import statici/ambigui e scope omessi. Un campo che usa il parametro di classe non viene più risolto all'import: il tipo diventa UNKNOWN_TYPE_PARAMETER. Non vengono risolti bound, overload generali, inheritance o wiring Spring.

Per una leaf dichiarata, il validatore T01 rilegge i byte UTF-8 incorporati in sourceFacts.sources, verifica gli hash e **riesegue il parser AST** in una directory temporanea esterna, confrontando i fatti ricostruiti. I puntatori bindingEvidence aggiunti dal traversal sono verificati separatamente contro il campo del ricevente. La cache è indicizzata dal contenuto sorgente. Falsificare flags/allocation mantenendo byte e hash autentici non passa. T02 valida T01 prima della proiezione e usa la stessa regola: nessuna seconda policy semantica.

La riparsificazione usa lo stesso adapter parse-only, disabilita i processori e compila soltanto l'helper Mana. Non attribuisce, compila o esegue il progetto target. I nuovi fatti interni e i byte sono necessari per verificare evidenza assente dal formato precedente; non vengono aggiunte proprietà pubbliche TYPE_BINDING_PROVEN/DISPATCH_PROVEN.

Gli esiti restano distinguibili senza nuovi exit code: report valido con leaf = certificazione supportata; report valido con UNRESOLVED_CALL e ragione RESOURCE_LEAF_* = chiamata riconosciuta ma non certificabile; ValueError/errore CLI esistente = witness o prova incompatibile. Nessuna frontiera autorizza una continuazione certa nel suffisso.

## Matrice e oracoli indipendenti

`tests/transaction-resource-binding.py` contiene 10 test e una matrice letterale di 14 sorgenti: import Spring con allocazione positiva; tipo completamente qualificato; HIGH R2 generico; omonimo applicativo; subtype con override; ricevente Spring dinamico; overload a due argomenti; tre call; classe membro; classe locale; bound Spring non sufficiente; parametro generico di metodo; campo mutabile; allocazione anonima. Si aggiungono il sorgente HIGH R1 esatto e controlli di witness/fatti contraffatti o byte mancanti.

I positivi a due e tre leaf verificano dipendenze di ritorno normale e P1. L'iniezione incerta seguita da operazione conserva P1 alla frontiera e lascia il secondo passo UNPLACED/UNKNOWN. Restano UNKNOWN datasource, enlistment, lock, granularità e identità runtime.

Tutti i **14 sorgenti della matrice**, gli stessi analizzati da Mana, sono compilati separatamente in directory isolate con `javac -proc:none`, classpath vuoto salvo piccoli stub espliciti, e disassemblati con `javap -c -p -s`: exit 0 per ogni comando. Nessuna classe viene eseguita. Aspettative e owner simbolici sono letterali nel test, non generati dal classificatore. Il HIGH R2 completo è tra i sorgenti compilati; il HIGH R1 completo contiene una dipendenza intenzionalmente non definita della fixture storica (`unknownReceiver`) e viene analizzato senza build. Per il suo binding Java si compila il controllo membro ridotto che conserva ricevente Spring e override CustomConfig.CustomJdbc.

L'oracolo R2 mostra `descriptor: Lfixture/ApplicationJdbc;` e invokevirtual ApplicationJdbc.execute/update. I casi override/membro/locale/anonimo disassemblano anche la classe applicativa: un invokevirtual con owner simbolico Spring non prova l'implementazione dinamica. Il caso completamente qualificato compila con owner Spring, ma Mana lo lascia UNKNOWN perché non dispone della stessa attribuzione sul classpath reale. Gli stub provano regole linguistiche, non comportamento della libreria Spring o del database.

## Impatto e aspettative storiche

Prima della migrazione dei test sono state eseguite tutte le 260 regressioni: le otto suite estranee alla certificazione leaf, **207 test**, passano; le due suite leaf, **53 test**, terminano exit 1 con le aspettative iniettate originali. Questi log sono conservati, senza dichiararli PASS. Includono anche rifiuti diagnostici di formato/provenienza, quindi non rappresentano un conteggio di sole certificazioni perdute.

Le due suite positive sono poi migrate **esplicitamente** alla nuova allocazione nei soli progetti temporanei di test. Gli oracoli JSON, la fixture storica del repository, gli esempi e i report precedenti non sono modificati. Le aspettative P/L/SP/S, SQL, dipendenze e causalità sono riutilizzate sul nuovo positivo; i due span del controllo r1 migrato cambiano da `[2630,2668) / [2670,2703)` a `[2654,2692) / [2694,2727)` per l'inizializzatore più lungo. I test di contraffazione ora possono fallire prima, al confronto con il sorgente riparsificato. Il negativo sul campo non inizializzato sostituisce quello precedente sull'inizializzazione, esplicitamente nel test.

I dodici replay originali sono rieseguiti sui progetti F01 preesistenti, immutati. **Sei aspettative storiche restano PASS; sei sono DEGRADED**, non rinominate PASS. Tutti e dodici rispettano il nuovo contratto conservativo. Il controllo del vecchio validatore usa un nuovo positivo rule-2 per verificare realmente il rifiuto dell'evento leaf.

| Replay con certificazioni degradate | Leaf prima → dopo | Contesto dopo |
|---|---:|---|
| required-two | 2 → 0 | P1 alla prima frontiera, secondo passo UNKNOWN |
| required-three | 3 → 0 | P1 alla prima frontiera, secondo/terzo UNKNOWN |
| requires-new | 1 → 0 | Frontiera su P2; nessuna leaf |
| nested | 1 → 0 | Frontiera su P1; nessuna leaf |
| restored | 1 → 0 | Frontiera su P1 ripristinata; nessuna leaf |
| terminated | 1 → 0 | Frontiera NO_TRANSACTION; nessun riuso di P1 |

Sono **9 certificazioni storiche rimosse nei sei replay**. Inoltre tutti i positivi iniettati dei cinque casi nell'oracolo resource-leaf-oracles.json e i controlli standard/three F01 perdono la certificazione sul sorgente storico. La motivazione è comune: import e tipo statico non dimostrano l'implementazione dell'oggetto iniettato. Gli UNKNOWN precedenti rimangono tali. Anche tipo pienamente qualificato, generics e campi mutabili/anonimi restano conservativamente fuori dal nuovo sottoinsieme, senza inseguire la copertura originale.

## Verifiche finali e limiti

| Gate rieseguito sul risultato finale | Esito |
|---|---|
| Sei suite T01, conteggi 16/16/21/19/64/26 | 162 PASS |
| mana-skill-factory | 23 PASS |
| resource-timeline | 22 PASS |
| transaction-resource-leaves, positivi migrati dichiaratamente | 31 PASS |
| transaction-resource-dispatch, positivi migrati dichiaratamente | 22 PASS |
| Totale suite richieste | **260 PASS**, zero skipped |
| Nuova suite binding | **10 PASS**, zero skipped |
| Oracoli javac/javap | 14 fixture PASS; override ispezionati separatamente |
| Replay | 12 eseguiti: 6 storici PASS + 6 DEGRADED; nuovo contratto 12 PASS |
| Witness HIGH R1/R2, entrambi i validatori | Rifiutati |
| Validazione repository, Ruff check, Ruff format --check | PASS, exit 0 |
| Diff incrementale, controllo inverso senza applicazione | PASS |
| Isolamento/governance | PASS nelle suite; snapshot dei target invariati |

Rimane assunto che la dichiarazione importata sia la libreria Spring autentica con l'API catalogata. Non sono qualificati binary/versione installata, mutazione riflessiva/Unsafe, weaving/riscrittura di bytecode, advisor esterni, comportamento driver/database o ritorno normale effettivo. I byte incorporati verificano la coerenza semantica; una sostituzione coordinata di sorgenti, hash e IR non viene autenticata rispetto a un repository esterno.

Per estendere il sottoinsieme conviene valutare un frontend Java dedicato con attribuzione sul classpath e informazioni di allocazione/wiring. Un frontend statico aiuterebbe FQ names, scope, generics e overload; il solo tipo statico continuerebbe a non risolvere il dispatch di un bean arbitrariamente iniettato. Recuperare quella copertura richiederebbe un contratto di evidenza aggiuntivo. Nessun resolver universale, nuovo frontend o infrastruttura di qualificazione viene introdotto qui.

L'inventario iniziale comprende 1.302 file: 1.294 restano identici per byte e mode; cambiano solo gli otto file iniziali del fix, indicati nel JSON. Nuovi file: test binding e tre deliverable F02. I sei materiali protetti coincidono con gli hash iniziali e storici; CSV preservati con 69/92 CRLF e zero LF isolati. Ref, indice e lista worktree invariati. L'implementazione preesistente e il lavoro estraneo al fix sono preservati nel diff incrementale rispetto allo stato iniziale, non sostituiti con HEAD.

Evidenze riproducibili, log, inventario, progetti minimi e output sono in `/private/tmp/mana-d02-f02-njwq7u4c`; il JSON consegnato incorpora matrice, output javap, report nuovi, dettagli dei replay e hash. Nessuna copia integrale di repository o archivio voluminoso. Il patch contiene solo codice, contratto e test del fix, senza ricopiare i receipt precedenti.

Runtime Spring/JDBC/database, CI remota, release acceptance e review esterna: **NOT RUN**. Le modifiche sono pronte per review nel sottoinsieme dichiarato; non certificano i casi UNKNOWN e non implementano S02.
