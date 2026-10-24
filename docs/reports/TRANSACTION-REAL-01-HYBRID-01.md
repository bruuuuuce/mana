# MANA-TRANSACTION-REAL-01-HYBRID-01

Data: 2026-10-24. **Verdetto complessivo: PARTIAL.** Il primo incremento D02 è **IMPLEMENTED_READY_FOR_REVIEW**; il pilot reale rimane UNKNOWN / NOT_ASSERTED, senza binding aziendali dimostrati e senza nuovi call site attraversati. Non è classificato USEFUL. L'attribution utilizzabile sul target è **BLOCKED** per input semantici mancanti; lo snapshot conserva il risultato **INCOMPLETE**, anziché attestare risoluzione.

## Decisione applicata e confine

Letti integralmente D02, F02, F02-R1, F01-R1, Transaction Model v1, contratto MR00 e Resource Timeline v1/S01; esaminati JavaFacts, source.py, guardie T01, verifica leaf e consumer S01. Baseline verificata: `develop`, `d5c31a87148c73dfceb3802a535f969767fe66fc`, indice vuoto. Creato soltanto il branch `feature/transaction-real-01-hybrid-01`, sullo stesso HEAD e senza nuovo worktree.

D02 seleziona C, frontend parse-only più adapter javac locale esplicito. Il solo incremento raccomandato è lo **snapshot bounded e verificabile dei binding delle dipendenze membro statiche dell'ingresso**: identità annidata/owner/modificatori, supertypes propri, firme/provenance, riferimenti di tipo, produzione del valore e costruzione. Non comprende CFG, traversal di rami, nuovi effetti transazionali o un resolver Java proprietario.

Implementati `JavaBindings.java`, `semantic.py` e il CLI opt-in `mana-java-member-bindings.py`. [Contratto e utilizzo](../standards/java-member-bindings-v1.md). Nessuna modifica al collector parse-only, a model.py, ai consumer S01/leaf, a T02-S02 o VIS-01. I progetti semplici continuano a usare il percorso precedente, senza importare o richiedere l'adapter.

Lo snapshot supplementare è un produttore di fatti separato, `mana.java-member-bindings/v1`. Non viene inserito nei formati T01/S01/S02 esistenti, non modifica sourceFacts e non produce eventi. T01 rimane l'unico modello canonico. Non è stato rimosso alcun hazard per far avanzare il target. Nessuna modifica breaking e nessuna decisione MODEL/DESIGN necessaria per questo incremento.

## Contratti, provenienza e garanzie conservative

Ingresso: elenco esplicito di sorgenti bounded, evidenza esatta del metodo, fino a 16 identità membro richieste, JDK/release/classpath offline espliciti. Il CLI seleziona la dichiarazione con il selector esistente, compatibile con zero/sei parametri e overload. Nel replay supplementare sono stati selezionati soltanto il file originale e O1/O2, con basename/percorso preservati; nessuna indicizzazione del repository o ricerca di dipendenze.

Uscita: dichiarazioni e relazioni con stato VERIFIED/UNRESOLVED/ABSENT, offset UTF-16, linee e hash; TYPE_CONTAINMENT e TYPE_INHERITANCE restano distinti da TYPE_REFERENCE, VALUE_PRODUCTION ed EXECUTION_DEPENDENCY. VALUE_PRODUCTION collega sito del tipo, dichiarazione della variabile e sito dell'inizializzatore alla dichiarazione produttrice quando verificabile. I metodi conservano appartenenza e firma; le firme soltanto dichiarate restano separate dall'identità attribuita. Le chiamate ereditate mantengono l'owner della dichiarazione selezionata. `runtimeDispatch` resta UNKNOWN.

Il collector supplementare invoca parse()/analyze(), mai generate()/call(). Processing e compilazione implicita sono disabilitati. Si compilano/eseguono soltanto helper Mana fissi, in stage esterno. Il controllo dello stage rifiuta eventuali classi target generate. Nessuna esecuzione applicativa, inizializzazione di classi target, build, database o rete di risoluzione.

Qualunque errore compiler invalida **tutti** i binding positivi del tentativo. Questa scelta evita di certificare binding di recovery; può anche bloccare siti corretti a causa di errori in altre parti dello stesso file. Tipi membro non statici, generic variables/captures e produttori non supportati restano irrisolti. Individuare una dichiarazione non risolve il suo utilizzo. Non vengono esplorati ricorsivamente corpi, costruttori o call graph.

La verifica parse-only esistente viene eseguita prima dell'attribution: fatti parser contrari ai sorgenti producono CONFLICT, senza preferire un target. Un guasto del verificatore produce invece BLOCKED. La verifica semantica dedicata ricalcola il witness con sorgenti, ambiente e richiesta fissati separatamente dal chiamante e confronta l'intero risultato. I test rifiutano target manomessi e classpath cambiato. Nessun booleano del produttore sostituisce il replay; nessuno snapshot storico viene aggiornato. Questa verifica attesta coerenza/riproducibilità, non autenticità di un host amministrato dallo stesso utente.

## Budget, dipendenze e distribuzione

Limiti: 64 sorgenti/2 MiB; 16 identità; 20.000 visite AST/profondità 64; 32 JAR offline/32 MiB, senza Class-Path implicito nei manifest; limiti aggiuntivi sulle directory JAR e sul fingerprint JDK. Deadline condivisa di 60 s per compilazione helper più attribution supplementare; heap JVM 128 MiB, stack 1 MiB; letture output entro 4 MiB. I limiti Python possono solo diminuire. Esaurimento budget lascia BLOCKED, senza binding positivi. La verifica parser precedente conserva i suoi timeout distinti: il totale del CLI con replay non viene dichiarato bounded a 60 s. Heap e stack non equivalgono a un limite RSS del processo.

Nessuna libreria nuova, download o binario vendorizzato. Usato il JDK già installato Amazon Corretto `1.8.0_442`, distribuzione `8.442.06.1`, GPLv2 con Classpath Exception, verificata nel LICENSE locale. Ogni witness include hash di launcher, runtime/compiler, librerie native, versione e licenza, oltre ai byte dei JAR esplicitamente forniti. Il classpath reale è dichiaratamente vuoto; quello positivo delle fixture contiene soltanto un JAR sintetico generato dall'oracolo esterno. Nessuna dipendenza aziendale è stata introdotta o scaricata.

Java 8 qualificato sul macOS corrente. Il contratto accetta release 8/17/21 con toolchain compatibile esplicita; **Java 17/21 e Windows/Linux NOT_RUN**, senza affermare portabilità qualificata. Il frontend resta facoltativo.

## Regressioni ed evidenze indipendenti

**297 test PASS, zero skip**, 13 suite. Le 276 regressioni precedenti coprono type-dependencies 17, entry-parameters 12, boundaries 16, self-invocation 16, context-alternatives 21, aop-causal-order 26, transition-contract 64, physical-lifetime 19, resource-timeline 22, resource-leaves 31, resource-binding 10, resource-dispatch 22. La nuova suite `tests/transaction-member-bindings.py` aggiunge **21 test PASS**.

| Requisito | Fixture/controllo e oracolo |
|---|---|
| Classe senza annidate | Plain; dichiarazione zero argomenti, percorso T01 precedente invariato |
| Membro statico / non statico | Good.Result statico; Good.Inner con enclosing-instance field, resta UNRESOLVED |
| Annidata usata / irrilevante | Good.run usa Result/Failure; Irrelevant non espansa, zero() senza relazioni inventate |
| Superclass / interfaccia | Result extends Base implements Relevant; metodo inherited dichiarato da Base |
| Binding univoco | produce(), costruttore String e metodi del risultato; posizioni/hash collegati |
| Binding ambiguo | Ambiguous: javac rifiuta new con null, nessun candidato promosso |
| Dipendenza assente | Missing/External senza JAR: errori espliciti, zero binding positivi |
| Overload / sei parametri | Good.six seleziona produce(String), mai produce() |
| Cicli / ricorsione | Campo Result→Result e metodo ricorsivo; nessuna espansione del grafo |
| Limiti operativi | Nodi, profondità, bytes sorgenti/classpath/output; timeout controllato tramite fault injection |
| Discordanza | Fatti parser manomessi: CONFLICT; snapshot semantico alterato: rifiuto al replay |
| Omonimi | Shadow seleziona il membro, mai il Result top-level |
| Ambiente / riservatezza | JAR cambiato, manifest transitivo, guasti JDK/verificatore, sentinelle e CLI positivo/negativo |

Un runner esterno che **non importa Mana** compila/ispeziona separatamente i sei inventari sintetici con javac/javap: **6/6 PASS**. Good/Plain/Shadow compilano; Ambiguous/Missing/External senza dipendenze sono rifiutati. I predicati letterali verificano firme dei target, costruttori, static/inner, ereditarietà, interfaccia e omonimi. Nessuna classe fixture viene eseguita. Questo è un oracolo strumentale indipendente, non una review di secondo agente o prova runtime.

Validazione repository, Ruff check e Ruff format check: **PASS**, exit 0. I log iniziali falliti restano nelle evidenze: stack 512 KiB inferiore al minimo del JDK ARM, fixture CLI con percorso temporaneo non canonico, aspettativa temporale non deterministica poi sostituita da fault injection. Correzioni limitate all'incremento. Un errore di chiave nel solo runner REAL-01 è stato corretto prima della raccolta finale; nessun risultato incompleto è presentato come PASS.

## Contenimento e replay REAL-01

Contenimento AST F01 preservato. Nuovi test su stdout/stderr, errori, literal sentinella e witness: PASS; regressioni F01 pertinenti PASS. La verifica strutturale del witness reale conferma soli simboli, posizioni, hash e stati: niente receiver/argomenti/espressioni/corpi/snapshot sorgenti. I sorgenti aziendali sono usati solo in memoria e nello stage locale temporaneo, poi eliminato. Nessun fatto source-bearing del target è persistito. Consultate soltanto pagine API pubbliche Oracle con URL generici, senza inviare sorgenti o identificatori aziendali. L'incidente storico F01 non viene annullato.

Dopo regressioni e controlli di contenimento è stato ripetuto **NotificationService#submitNotificationSync**, sul medesimo progetto storico e contesto REAL-01, senza wrapper o entry alternativa. Sei parametri, linea 77, `[3516,4318)`, hash sorgente e digest dello span identici al pilot.

Recuperate le dichiarazioni O1 `[21126,22823)` e O2 `[22833,23207)`, con owner/modificatori, 12 dichiarazioni di metodo/costruttore e relativi span/firme dichiarate. O2 conserva extends scritto `RuntimeException`, ma **non** un binding verificato a java.lang.RuntimeException. Il witness individua nove relazioni richieste; restano tutte UNRESOLVED per errori di risoluzione nell'ambiente esplicito. Non sono stati introdotti stub, recuperati JAR o corrette nuove frontiere.

| Metrica | F02 | HYBRID-01 |
|---|---|---|
| Classi rilevanti ancora omesse dal modello canonico T01 | 2 | 2; il sidecar conserva entrambe le dichiarazioni, ancora non verificate semanticamente |
| Binding dimostrati O1/O2 | 0 | 0 |
| Call site applicativi nuovi attraversati | 0 | 0 |
| Frame / frontiere UNKNOWN T01 | 1 / 1 | 1 / 1; nove relazioni irrisolte supplementari non sono eventi T01 |
| Body traversal | NOT_ASSERTED | NOT_ASSERTED |
| Motivo T01 | OMITTED_TYPE_EXECUTION_DEPENDENCY_NOT_MODELED | Identico; nessuna guardia aggirata |
| S01 | Zero osservazioni | T01 identico, zero osservazioni, validazione PASS |
| Tempo | 0,9977 s storico F02-R1, risorse non disponibili | Fallback 1,459 s; verifica dedicata 0,772 s; raccolta completa 4,310 s |

La raccolta completa include due analisi T01 e il replay semantico: i tempi non sono un confronto prestazionale a parità di lavoro. Il fallback usa un solo file, **23.393 byte**, **1.813 visite**, due subprocess supplementari e **15.148 byte** di output helper prima dell'arricchimento. CPU figli durante il fallback, inclusa la ri-verifica parser: 3,087 s user + 0,310 s system; CPU parent 0,118 s. High-water RSS figli 122.224.640 byte, già raggiunto durante il parsing precedente: **non è una misura RSS isolata dell'attribution**. Restano distinti questo dato osservato e il limite heap 128 MiB.

Digest T01 `b450846aaa01a4ed4aef630f37fb4a89ba664e38fb1caf24e54c8ba43a43346c`; digest S01 `e7a282c2adfe91bbdd6f12b44cb56d89ab3bf81838d5ee0067cfe16d7c28c040`, entrambi identici a F02-R1. S01 incorpora esattamente il modello canonico. Nessuna transazione/persistenza runtime viene esclusa dal conteggio zero. **S02 e VIS-01 NOT_RUN.**

## Preservazione, limiti e consegna

Inventariati prima delle modifiche **1.532 file Mana**, inclusi i **17 materiali locali** (tutti i sei storicamente protetti, D02 e consegne F02-R1), contenuti/modi e stato Git; cinque directory di evidenze precedenti inventariate senza sovrascriverle. Controllo finale: tutti gli originali preservati per byte/modo; indice vuoto, HEAD invariato, stessa lista di worktree. Preservati i 39 file inventariati del sottoprogetto target, insieme di percorsi, HEAD e status. Esclusi dai conteggi file ignorati e interni Git.

Le sole aggiunte appartengono a questo incremento: adapter/CLI, contratto, sei fixture, suite e consegne. Nessun commit, merge, push, reset, stash, clean, checkout forzato, clone o nuovo worktree. Nessuna modifica a target, Familiar, skill, configurazioni, adapter Oracle, S02 o VIS-01. Una ricerca iniziale di soli percorsi AGENTS.md si è estesa al parent ed è stata interrotta senza risultati né letture di sorgenti esterni.

Restano UNKNOWN i binding reali senza ambiente sufficiente, il primo parametro DECLARED_ONLY, tutti i valori runtime, gli effetti/ordine dei produttori e dei costruttori, rami/throw, gerarchie omesse residue, dispatch/wiring/proxy effettivi e risorse/database. Il rifiuto globale su errori compiler limita la precisione. Nessuna di queste frontiere è stata corretta automaticamente. La consegna qualifica il primo produttore/verificatore locale, non il traversal reale né il frontend Java generale.

Risultati condivisibili: `TRANSACTION-REAL-01-HYBRID-01-results.json`. Evidenze riproducibili in `/private/tmp/mana-real-01-hybrid-01-evidence/`: inventari before/target-before, runner e log delle regressioni, oracoli indipendenti, witness source-free reale, replay, costi, confidentiality/integrity, stato Git, `incremental.patch` e manifest. La patch incrementale esclude tutti i materiali preesistenti e non usa staging. **Arresto alla consegna.**
