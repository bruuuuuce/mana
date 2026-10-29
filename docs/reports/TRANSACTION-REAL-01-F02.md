# MANA-TRANSACTION-REAL-01-F02 — Nested Type Dependency Classification

Data: 2026-10-23. Verdetto complessivo: **PARTIAL**. La correzione della classificazione è implementata e verificata; il metodo reale resta **UNKNOWN / NOT_ASSERTED** per omissioni effettivamente rilevanti. Non è corretto rimuovere tutti e tre i blocchi come se fossero innocui. Nessuna decisione sul modello transazionale è necessaria per questa correzione; nessuna qualificazione runtime è dichiarata.

## Baseline e perimetro

Branch `develop`, HEAD `a27ae0f3fcc732c064a834aae3d11886a44c8f0d`, indice vuoto prima e dopo. Verificati i due rapporti F01/F01-R1, lo standard, parser e guardie T01, consumer S01/leaf, diagnostica e witness originali. I 13 materiali locali preesistenti, inclusi quelli storicamente protetti, sono preservati per byte e modo; anche il quattordicesimo materiale, il rapporto F01-R1 non tracciato, è preservato. La lista originale è in `preservation-current.json` di R1 e viene confrontata con il nuovo inventario.

Evidenze nuove: `/private/tmp/mana-real-01-f02-evidence/`. Non sono sovrascritte le evidenze REAL-01, F01 o R1. Nessun commit, merge, push, reset, stash, clean, nuovo worktree, clone o modifica al target/Familiar. Nessuna attivazione di skill, adapter Oracle, rete/provider, build/esecuzione del servizio o interrogazione database. S02 e VIS-01 **NOT_RUN**.

## Root cause e tre omissioni originali

La dichiarazione originale è identificata qui tramite simbolo, modificatori e posizione, senza riprodurre codice aziendale. Il witness indipendente `RelationsProbe.java` usa il parser JDK esistente, `parse()` e `-proc:none`: compila solo l'helper, non attribuisce/genera/esegue classi target. Emette esclusivamente metadati di dichiarazione e contesti sintattici, senza receiver, argomenti, annotazioni o corpi.

File: quello della dichiarazione di ingresso, SHA-256 `7fb36e5da7cc1b459ca3eee63b367c1681283e17f8bdc80481d36048334bfc2a`. Offset UTF-16, estremo finale escluso.

| Omissione | Dichiarazione originale: metadati Java | Contenimento | Supertipi dichiarati propri | Rilevanza per l'ingresso |
|---|---|---|---|---|
| O1, `NotificationResult` | CLASS, private static; linea 532, `[21126,22823)` | Classe membro statica | Nessun extends/implements esplicito | Referenza nel tipo di una variabile locale alla linea 86 del metodo selezionato. Non è dimostrabilmente irrilevante. |
| O2, `ServiceUnavailableException` | CLASS, public static; linea 584, `[22833,23207)` | Classe membro statica | extends con grafia `RuntimeException`; nessun implements | Allocazione dentro THROW/IF alla linea 97 del metodo selezionato. Comportamento/costruttore ed esito eccezionale non analizzati. |
| O3, `MessageNotFoundException` | CLASS, public static; linea 597, `[23217,23390)` | Classe membro statica | extends con grafia `RuntimeException`; nessun implements | Referenza in THROW/NEW_CLASS alla linea 312, in altro metodo. Nessuna referenza diretta nell'ingresso; non è un suo supertipo. Restano i limiti globali conservativi di gerarchia/dispatch. |

La grafia dei supertipi è quella dichiarata; non è attribution classpath di `RuntimeException`. Il contenitore non dichiara extends o implements. Nessuna delle tre dichiarazioni è una classe membro non statica, un tipo locale, anonimo o un inizializzatore. Queste altre forme sono coperte separatamente dalle fixture.

Per tutte e tre, l'AST serializzato precedente ometteva identità, modificatori, relazione di contenimento, supertypes propri e membri del tipo annidato; conservava tre stringhe indistinte `UNKNOWN_NESTED_CLASS_OR_INITIALIZER` in `parents`, oltre a un hazard globale. `model.py` trattava qualunque `parents` non vuoto come ereditarietà del contenitore. La perdita informativa e questa guardia spiegano la falsa diagnosi, senza provare tre superclassi.

O1 può essere necessario per il tipo del risultato, i suoi membri e le chiamate che lo producono/usano: nessun binding di tali call site è provato. O2 introduce una dipendenza eseguibile nell'eventuale ramo eccezionale; non ne viene asserita la raggiungibilità. O3 non giustifica un blocco di ereditarietà sull'ingresso. Nessuna delle tre è automaticamente candidata Spring o target di dispatch risolto; la presenza di gerarchie omesse mantiene UNKNOWN dove può compromettere la chiusura del dispatch. Il witness osserva referenze sintattiche, non esecuzione o assenza di dipendenze transitive.

## Correzione minima

Nessun nuovo campo pubblico, schema o parser Java. I concetti logici sono rappresentati usando le strutture interne esistenti:

- **TYPE_CONTAINMENT:** le dichiarazioni membro alimentano un insieme temporaneo di nomi omessi. Non vengono aggiunte a `parents`. La loro sola presenza non blocca un percorso T01 dimostratamente disgiunto nel sottoinsieme supportato.
- **TYPE_INHERITANCE:** `parents` conserva esclusivamente extends/implements dichiarati dal proprietario. Supertipi e annotazioni dei tipi omessi, anche più profondi, mantengono un hazard di gerarchia/wiring senza diventare supertypes del contenitore.
- **EXECUTION_DEPENDENCY:** un riscontro positivo o ambiguo sul nome omesso nell'AST completo del metodo, incluse firma e istruzioni non estratte come call, produce un hazard del metodo. Modificatori della classe, campi e costruttori sono controllati come dipendenze strutturali conservative; non basta che il nome manchi nei call site estratti. I tipi membro omessi non vengono risolti come parametri di un omonimo tipo top-level.

Le dipendenze omesse producono `OMITTED_TYPE_EXECUTION_DEPENDENCY_NOT_MODELED`; i blocchi inizializzatori mantengono `CLASS_INITIALIZER_EXECUTION_NOT_MODELED`. Tipi locali/anonimi nel corpo restano espliciti hazard, senza visitarne il comportamento. Gerarchie/wiring omessi mantengono `OMITTED_TYPE_DISPATCH_NOT_MODELED` sull'owner e sulle chiamate iniettate anche da altri owner: il controllo evita di abilitare override su self-call o sostituzioni di bean non dimostrate. Le superclassi/interfacce reali irrisolte conservano il blocco originario.

Il validatore accetta le nuove ragioni solo con la normale incertezza collegata all'evidenza del frame e `bodyTraversal: NOT_ASSERTED`; i controlli negativi rifiutano la rimozione del witness o l'affermazione di traversal. Nessuna nuova transizione, risorsa, JDBC operation o continuazione viene introdotta. La guardia globale leaf JDBC sulle omissioni resta conservativa anche quando T01 può analizzare un metodo ordinario disgiunto. Gli snapshot storici con fatti di omissione cambiati non sono aggiornati silenziosamente: la ri-validazione resta fail closed.

## Regressioni e oracoli indipendenti

Nuova suite: `python3 tests/transaction-type-dependencies.py -v`, **17 test PASS**. Fixture Java 8 distinte in `tests/fixtures/transaction-type-dependencies/`; aspettative letterali scritte manualmente. I file con Entry omonimo sono inventari separati, non un unico progetto compilabile insieme.

| Caso richiesto | Riscontro |
|---|---|
| Tre membri irrilevanti, zero parametri | Due frame, L1/L2, P1 condivisa; nessuna incertezza. Un utilizzo in altro metodo non contamina il percorso. |
| Membro statico usato | NOT_ASSERTED per dipendenza omessa. |
| Membro non statico tramite chiamata | Campo tipizzato e chiamata restano NOT_ASSERTED. |
| Superclass esterna necessaria | Ereditarietà reale conservata e NOT_ASSERTED. |
| Interfaccia irrisolta per dispatch | Implements conservato e NOT_ASSERTED. |
| Annidata con proprio extends | Nessun parent sul contenitore; dispatch UNKNOWN. Inclusi self-call e subtype in altro owner. |
| Tipo omonimo | Nessun binding al bean top-level; firma con tipo membro omesso rifiutata. |
| Sei argomenti | Stesso percorso positivo, due frame e L1/L2; nessun valore runtime inventato. |
| Zero argomenti storico | Suite F01/T01 esistenti preservate. |
| Omissione realmente rilevante | Dipendenza rilevata anche in VARIABLE/THROW non presenti nel call list supportato; NOT_ASSERTED conservato. |

Controlli aggiuntivi: locali/anonimi, initializer, costruttore che usa il tipo omesso prima di un metodo vuoto, sentinelle diagnostiche, immutabilità fixture, witness e traversal contraffatti. L'oracolo indipendente della suite compila soltanto `OracleTypes.java`, ispeziona con `javap` static/inner, superclass/interfaccia, EnclosingMethod e anonimo; non esegue le classi.

`independent-fixtures.py` verifica inoltre **13/13 fixture effettive** con javac Java 8 e javap, usando stub sintetici espliciti solo per il compilatore indipendente. Gli stub mancanti nell'inventario dell'analyzer non vengono forniti a Mana: i casi irrisolti restano tali. Confermati anche il binding al tipo membro omonimo e le gerarchie dei subtype. Il runner non importa il classificatore; nessun oracolo è generato dal suo risultato. Probe e compilatore indipendenti non costituiscono una review umana/di secondo agente né prova runtime.

Regressioni mirate: **276 test PASS, zero skip**, tutti exit 0.

| Suite | Test |
|---|---:|
| transaction-type-dependencies | 17 |
| transaction-entry-parameters | 12 |
| transaction-boundaries | 16 |
| transaction-self-invocation | 16 |
| transaction-context-alternatives | 21 |
| transaction-aop-causal-order | 26 |
| transaction-transition-contract | 64 |
| transaction-physical-lifetime | 19 |
| resource-timeline | 22 |
| transaction-resource-leaves | 31 |
| transaction-resource-binding | 10 |
| transaction-resource-dispatch | 22 |

Validazione repository, Ruff check e Ruff format check: **PASS**, exit 0. Eseguiti i test F01 pertinenti e i relativi controlli di contenimento stdout/stderr, errori JDK e snapshot. Nessuna nuova campagna QA generale. I primi tentativi della nuova suite hanno evidenziato un lookup posizionale errato nella fixture e la necessità di registrare le nuove ragioni nel validatore; sono stati corretti prima dei risultati definitivi, senza presentarli come PASS intermedi.

## Riservatezza e provenance

La diagnostica predefinita resta l'allowlist F01. Il nuovo scan usa identificatori internamente e aggiunge solo codici di hazard/ragioni: non serializza receiver, espressioni, testi di annotazioni o corpi annidati. Le sentinelle in inizializzatori annidati e di classe non compaiono nella proiezione diagnostica; firma, file, posizioni e digest restano disponibili. I test F01 coprono anche receiver, argomenti, SQL, errori di sintassi, stderr del subprocess e CLI. Nessuna trasmissione a provider è stata invocata per il target. Lo storico incidente F01 non viene dichiarato annullato.

La verifica reale usa i fatti source-bearing soltanto in memoria e salva metadati/digest; nessun dump AST, snapshot sorgente o codice aziendale è pubblicato. I contratti source-bearing locali S01/leaf restano invariati e non autorizzano trasmissioni. I nuovi diagnostici di tipo non aggiungono canali sorgente.

## Prima/dopo sul medesimo metodo reale

Ripetuto dopo il PASS delle regressioni il medesimo `com.nexi.npg.phoenixkafkaservices.services.NotificationService#submitNotificationSync`, sei parametri, stesso checkout storico e contesto REAL-01. Evidenza dell'ingresso identica al pilot: linea 77, span UTF-16 `[3516,4318)`, digest dello span verificato. Nessuna selezione di un metodo più semplice, build o esecuzione del target.

| Misura | Prima F02, riprodotto sulla baseline | Dopo F02 |
|---|---|---|
| Parents del contenitore | Tre marker di omissione | Lista vuota; falso blocco di ereditarietà superato |
| Prima ragione | INHERITANCE_OR_INTERFACE_RESOLUTION_NOT_MODELED | OMITTED_TYPE_EXECUTION_DEPENDENCY_NOT_MODELED |
| Omissioni superate | Nessuna classificazione individuale | Contenimento distinto; O1/O2 rimangono dipendenze effettive, O3 non è un parent dell'owner |
| Frame / bodyTraversal | 1 / NOT_ASSERTED | 1 / NOT_ASSERTED |
| Call site applicativi attraversati | 0 | 0 |
| Scope / transazioni fisiche ricostruiti | 0 / 0 | 0 / 0 |
| S01 | Validato, zero osservazioni | Validato, T01 identico a quello prodotto dopo F02, zero osservazioni |

Il percorso dimostrato resta l'identità dell'ingresso, i sei parametri con valori UNKNOWN, la configurazione estratta, le premesse di scenario e la frontiera motivata prima del corpo. Le tre omissioni originali **non sono tutte superate**: viene superata la guardia sbagliata, non viene inventata la risoluzione delle due dipendenze effettive. Il tipo del primo parametro resta DECLARED_ONLY, senza attribution. Non si asserisce un percorso applicativo completo né assenza di transazioni/persistenza a runtime.

S01 consuma il risultato correttamente: validazione strutturale e conservazione esatta del nuovo T01, nessun collocamento o JDBC inventato. I tre hazard già osservati sulle istruzioni VARIABLE/IF/IF alle linee 86/90/94 rimangono presenti, non sono stati aggirati né attraversati. La successiva frontiera richiede supporto bounded alle dipendenze davvero usate e a quelle forme di corpo, senza dedurre il percorso da annotazioni. Non è stata avviata questa ulteriore remediation. S02/VIS-01 restano NOT_RUN e non ricevono input fabbricati.

## Consegna e limiti

Modifiche circoscritte a JavaFacts, guardie/validator T01, standard e nuove fixture/suite/report. Nessuna modifica semantica a S01, leaf, S02 o VIS-01; nessun nuovo campo pubblico. Il matching sintattico conserva falsi positivi per omonimi, campi/costruttori e gerarchie innocue: è una rinuncia esplicita a risolvere binding non dimostrati, non un resolver Java generale. La guardia globale di dispatch resta più conservativa dell'analisi di un singolo percorso.

Risultati pubblicabili: `TRANSACTION-REAL-01-F02-results.json`. Evidenze locali riproducibili: `run-checks.py`, log, `regressions.json`, `validation.json`, `independent-fixtures.py/json`, `RelationsProbe.java`, `probe-real.py`, `original-relations.log`, `reproduce-real.py`, `real-before.json`, `real-reproduction.json`, `before.json`, `preservation.json`, `minimal.patch` e manifest nella nuova directory esterna. La patch incrementale esclude tutti i materiali preesistenti e il rapporto F01-R1; non usa staging.

I confronti finali attestano contenuto/modo dei materiali locali, inventari target, HEAD/status target e immutabilità delle evidenze precedenti; non attestano file ignorati o interni Git. HEAD/branch Mana e indice sono invariati. Le superfici di governance già inventariate sono immutate; nessuna modifica a skill/configurazione o Familiar. **PARTIAL** riguarda l'obiettivo reale ancora non attraversabile; la correzione della classificazione è consegnata per review con controlli positivi e negativi completati. Attività fermata alla consegna.
