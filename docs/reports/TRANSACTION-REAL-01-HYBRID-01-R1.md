# MANA-TRANSACTION-REAL-01-HYBRID-01-R1

Data: 2026-10-24. Review indipendente dell'implementazione locale non committata, senza modifiche a HYBRID-01.

**Verdetto principale: READY_FOR_INTEGRATION**, limitatamente al produttore/verificatore di snapshot semantici opt-in approvato da D02. Nessuna integrazione eseguita. Il classpath locale esplicito permette di dimostrare le due dipendenze originali sul metodo reale. Questo risultato non abilita il traversal transazionale.

| Esito | Valutazione di R1 |
|---|---|
| IMPLEMENTATION_SOUND | PASS nel perimetro D02 e nella toolchain qualificata |
| BINDING_PROVEN | PASS sul metodo reale: 2 tipi, 12 dichiarazioni di metodo/costruttore e 10 relazioni verificate; riscontro strumentale indipendente delle 10 relazioni |
| PILOT_ADVANCED | NO: zero nuovi call site attraversati da T01 |
| PILOT_STILL_BLOCKED | SÌ: stessa frontiera UNKNOWN, bodyTraversal NOT_ASSERTED |

Non è ENVIRONMENT_BLOCKED: gli input necessari a questa attribution sono disponibili localmente. Non emerge un FRONTEND_DEFECT nel caso esaminato. La mancata consumazione dello snapshot da parte di T01 è fuori dall'incremento D02, non un difetto da correggere durante questa review. READY_FOR_INTEGRATION non significa che l'obiettivo di traversal del pilot sia raggiunto.

## Perimetro ed evidenze

Baseline HEAD confermata: `d5c31a87148c73dfceb3802a535f969767fe66fc`. Letti D02, rapporto e risultati HYBRID-01, patch incrementale, contratti `transaction-model-v1.md`, `resource-timeline-model-v1.md` e `java-member-bindings-v1.md`; ispezionati CLI, adapter Python/Java, verificatore e controlli pertinenti. La patch contiene soltanto i 13 nuovi file HYBRID-01; `git apply --reverse --check` termina con exit 0 sul working tree esaminato, senza applicare modifiche.

Evidenze nuove, locali: `/private/tmp/mana-real-01-hybrid-01-r1-evidence/`. I witness reali contengono esclusivamente simboli, firme, tipi, posizioni, hash e stati. Nessun corpo, argomento o snapshot sorgente aziendale è pubblicato. I JAR di appoggio contengono copie di classi già compilate, rimangono nell'area privata locale e non sono artefatti da distribuire.

Questa è una review condotta direttamente sul codice e con strumenti Java indipendenti dal produttore Mana; non è una seconda attestazione ottenuta da un agente. Nessuna consultazione web o trasmissione a servizi esterni.

## Review dell'implementazione

| Requisito | Riscontro indipendente | Esito |
|---|---|---|
| Incremento D02 | Sidecar bounded, identità annidate, containment, firme, relazioni, attribution esplicita e replay dedicato. Nessun interprete di rami o nuovo motore Java proprietario. | PASS |
| Semantica Transaction Boundary Engine | Nessun file core esistente modificato dalla patch HYBRID; nessun import del sidecar nei consumer T01/S01. I due replay reali ricostruiscono i digest storici invariati. | PASS |
| Provenance | Posizioni originali UTF-16 e hash del sorgente, owner annidato, dichiarazioni e siti separati; sorgente reale identico al pilot. Il probe indipendente confronta span e identità, non solo nomi. | PASS |
| Binding mancanti/discordanti | Errori javac invalidano globalmente i positivi; assenze, tipi non supportati e ambiguità restano irrisolti. Contraddizioni parser/sorgente producono CONFLICT; snapshot alterati vengono rifiutati al replay. | PASS |
| UNKNOWN/NOT_ASSERTED | runtimeDispatch UNKNOWN anche con binding statico verificato; nessuna conversione in prova runtime. transactionTraversal NOT_ASSERTED e frontiera T01 immutati. | PASS |
| Isolamento | Solo CLI opt-in. Input sorgenti e JAR espliciti; -proc:none, -implicit:none e sourcepath vuoto. parse/analyze, nessuna generate/call, build o esecuzione applicativa. JAR con manifest Class-Path rifiutati. | PASS |
| Contenimento | Diagnostica allowlist code/line; stream del compiler nello stage temporaneo; witness senza espressioni/corpi. Controlli sentinella e CLI positivo/negativo rieseguiti. | PASS nel perimetro verificato |
| Consumer | Nessuna modifica a schemi/snapshot storici, T01, S01, S02 o VIS-01. Replay e digest T01/S01 invariati. | PASS |

Rieseguiti soltanto sei controlli esistenti pertinenti: conflitto parser, replay/manomissione, ambiguità, omonimo, contenimento/fallimento tool, CLI positivo/negativo. **6/6 PASS, exit 0**, log `targeted-review.log`. Nessuna campagna generale; i 297 PASS storici non sono ripresentati come prova corrente o utilità del pilot.

Limiti conservati: l'invalidazione globale riduce la precisione; alcuni siti non attribuiti possono non apparire nell'elenco delle relazioni. Il confronto 9→10 non rappresenta un elenco completo di tutti i siti falliti. Il replay dimostra riproducibilità contro input fissati, non autenticità di un host same-user. Java 17/21 e altri OS restano NOT RUN.

## Catena O1 — NotificationResult

Owner canonico: `com.nexi.npg.phoenixkafkaservices.services.NotificationService`; tipo richiesto: `NotificationService.NotificationResult`, membro `private static`, span `[21126,22823)`, linea 532. Nessun extends/implements esplicito; superclass effettiva `java.lang.Object`. Non servono metodi ereditati per i siti selezionati.

Catena da dimostrare:

1. Tipo locale `NotificationResult`, linea 86, `[3806,3824)`, → dichiarazione membro nell'owner indicato.
2. Inizializzatore `[3834,3963)` → `NotificationService#processNotificationInternal(com.nexi.npg.phoenixkafkaservices.model.NotificationPayload,java.lang.String,java.lang.String,java.lang.String,java.lang.String,java.lang.String,boolean)` → risultato `NotificationService.NotificationResult`.
3. Receiver locale → `NotificationResult#isDuplicate()` (boolean), `#isPublished()` (boolean), `#getMessageId()` (java.lang.String), con cinque siti d'invocazione alle linee 90, 91, 94, 95 e 97.

Il produttore ha **sette** parametri, mentre l'ingresso ne ha sei. La selezione non va confusa con l'arità dell'ingresso. Nel sorgente non esiste un overload concorrente del produttore o dei tre metodi selezionati; i metodi factory e il costruttore di Result non sono sostituti del produttore.

Informazioni già disponibili prima: dichiarazione annidata, owner, membri e firme sintattiche, variabile e sito di produzione. Informazione inizialmente mancante nell'input semantico: identità del primo parametro del produttore e dell'ingresso, scritto `NotificationPayload` sotto wildcard import del package model.

**Prima dipendenza mancante nella catena O1: `com.nexi.npg.phoenixkafkaservices.model.NotificationPayload`.** Il sorgente esiste nel modulo service-model, sotto `target/generated-sources/openapi/src/gen/java/main/.../model/NotificationPayload.java`; il binario esiste in `service-model/target/classes/.../model/NotificationPayload.class`. Nessuno dei due era incluso nell'inventario singolo-file/classpath vuoto del pilot HYBRID-01. Il probe indipendente conferma prima `payload: ERROR` e tipo dell'invocazione `<any>/ERROR`; dopo il classpath esplicito conferma tipo canonico, firma completa e risultato corretto. Il ritorno dell'ingresso `SyncSuccessResponse`, anch'esso nel modulo model, era un'altra assenza della stessa unità.

Il producer non verifica positivamente neppure i getter che javac recupera nel caso incompleto: `errors` dell'intera unità impedisce ogni VERIFIED. Questo è un rifiuto conservativo deliberato; la presenza sintattica di Result non basta a provare la produzione del valore.

## Catena O2 — ServiceUnavailableException

Tipo richiesto: `NotificationService.ServiceUnavailableException`, stesso owner; membro `public static`, `[22833,23207)`, linea 584. Costruzione alla linea 97, `[4230,4301)`. Un solo costruttore dichiarato: `#<init>(java.lang.String,java.lang.String)`; nessun overload locale concorrente.

Catena: identità del membro → superclass `java.lang.RuntimeException` → costruttore selezionato con due String; il secondo argomento dipende da `NotificationResult#getMessageId()`. La delega `super` nel costruttore usa `RuntimeException(String)`; il fatto non autorizza traversal del costruttore, trasferimento eccezionale, raggiungibilità o rollback.

**Non manca un simbolo nella catena nominale propria di O2.** Tipo annidato, String e RuntimeException sono disponibili nel sorgente/JDK selezionato. Anche il probe a classpath vuoto restituisce la superclass java.lang.RuntimeException e il costruttore corretto: sono risultati di recovery in una compilazione con errori, riportati solo per diagnosi, mai certificati come binding del pilot incompleto.

**Prima dipendenza mancante nella catena di ammissione del witness O2:** chiusura senza errori dell'intera unità di compilazione. Il primo errore riportato dal compiler è l'import `com.fasterxml.jackson.core.JsonProcessingException`, linea 3, assente dal classpath vuoto; segue `ObjectMapper`, oltre ai tipi applicativi e alle altre librerie dell'unità. Il simbolo è disponibile nel JAR locale jackson-core 2.13.5. Sul sottopercorso che produce il secondo argomento, la prima assenza è quella O1, NotificationPayload. Non si attribuisce a RuntimeException una dipendenza mancante inesistente.

Il rifiuto globale spiega perché il witness storico non verificava neppure ereditarietà/costruttore già recuperabili. Con unità attribuita senza errori entrambe le relazioni di tipo e la selezione del costruttore sono dimostrate; il probe indipendente conferma owner, firma e span.

## Classpath locale verificato

Esaminati esclusivamente il progetto storico autorizzato, i suoi POM e le cache locali Maven/Gradle per gli artefatti pertinenti. Nessuna sorgente da altri checkout. Il reactor dichiara service, service-model, service-client, service-mock e liquibase; il service dipende esplicitamente dal service-model. I source roots convenzionali e quelli OpenAPI già generati esistono. Non è stato eseguito alcun generatore.

Catena di configurazione locale: POM reactor → parent `com.nexigroup.npg:npg-parent-pom:1.6.2` già in .m2 → BOM Spring Boot 2.7.18 → Spring Framework 5.3.31, Spring Data BOM 2021.2.18 / moduli 2.7.18, Jackson BOM 2.13.5, Micrometer 1.9.17, SLF4J 1.7.36. Java source/target 1.8 nel parent. Le proprietà jackson.version=2.16.1 e micrometer.version=1.13.3 presenti nel parent non sostituiscono da sole le versioni interne del BOM importato; non sono state usate per inventare dipendenze mancanti o scegliere sostituti arbitrari. Questo è un grafo dichiarato locale pertinente all'attribution, non un dependency:tree eseguito o il grafo runtime completo.

Classpath B esplicito: **14 JAR, 8.509.120 byte**, sotto i limiti invariati di 32 JAR/32 MiB:

- Due archivi privati prodotti copiando esclusivamente i `.class` già esistenti in service/target/classes e service-model/target/classes; esclusi tutti i `NotificationService*.class` per impedire che binari pregressi sostituiscano le dichiarazioni sotto review. Nessuna compilazione o modifica del target.
- spring-context, spring-tx, spring-core, spring-beans 5.3.31;
- spring-data-jpa e spring-data-commons 2.7.18;
- jackson-core, jackson-databind, jackson-annotations 2.13.5;
- micrometer-core 1.9.17, slf4j-api 1.7.36, javax.persistence-api 2.2.

`classpath.json` fissa percorsi, coordinate, dimensioni, digest e manifest delle classi copiate; `build-metadata-hashes.json` fissa i POM letti. Non vengono inclusi driver, starter, librerie di test o dipendenze non necessarie a questa attribution. Il classpath è sufficiente per il singolo-file selezionato; non si afferma che sia il più piccolo insieme matematico o l'ambiente di avvio del servizio.

Toolchain invariata: Corretto 1.8.0_442, release 8; il witness ne registra i fingerprint. Le directory di classi non sono accettate dall'adapter: il solo confezionamento ZIP delle classi esistenti rende l'input conforme al contratto JAR, senza generare nuovi binari applicativi. Non sono stati creati stub. L'identità statica è qualificata rispetto a questi esatti binari locali; la loro corrispondenza a una release distribuita o a ogni sorgente del reactor non è qualificata.

## Esperimento A — fixture indipendente

Nuova fixture minima esterna al repository: `synthetic/Case.java`, con due membri statici Result/Failure, variabile locale prodotta da metodo con overload Payload/String, chiamate sul risultato, metodo ereditato da deps.Base e costruzione eccezionale con due String. Due sole dipendenze sintetiche note: deps.Payload e deps.Base, compilate localmente e confezionate in un JAR. Nessuna classe sintetica viene eseguita.

La medesima CLI/API HYBRID-01 invariata produce e riverifica i witness nelle due configurazioni. javac/javap indipendenti compilano/ispezionano solo la fixture sintetica: confermano descrittore dell'overload Payload, costruttore a due String, superclass Base e dichiarazione inherited() su Base. L'oracolo non usa Mana per stabilire i risultati Java.

| Misura A | Classpath incompleto | Classpath completo |
|---|---:|---:|
| Dichiarazioni recuperate | 2 | 2 |
| Tipi VERIFIED | 0 | 2 |
| Relazioni osservate | 7 | 9 |
| Relazioni VERIFIED / UNRESOLVED | 0 / 7 | 9 / 0 |
| Ambiguità diagnosticate | 0 | 0 |
| javac indipendente, exit | 1, rifiuto atteso | 0 |
| Snapshot | INCOMPLETE | COMPLETE |
| Nuovi call site T01 attraversati | 0 | 0 |
| Frontiera T01 | UNKNOWN, omissione membro | Identica |
| Body traversal | NOT_ASSERTED | NOT_ASSERTED |

Il binding atteso è dimostrato nella fixture completa; nessun controesempio di frontend difettoso emerge. Il controllo separato sull'ambiguità è PASS e conserva il rifiuto anziché scegliere un candidato. Dati: `a-summary.json`, `a-incomplete.json`, `a-complete.json`, `a-t01-frontier.json`, log `oracle-a-*`, `oracle-a-members.txt`, runner `experiment_a.py` e `verify_a_frontier.py`.

## Esperimento B — stesso metodo reale

Eseguito solo dopo A positiva e verifica degli input locali. Stesso ingresso `NotificationService#submitNotificationSync`, sei parametri, linea 77, span `[3516,4318)`; SHA-256 sorgente invariato `7fb36e5da7cc1b459ca3eee63b367c1681283e17f8bdc80481d36048334bfc2a`. Stesso singolo sorgente, dipendenze richieste, entry evidence, limiti, release e implementazione. **Unica differenza della richiesta: environment.classpath.**

| Misura B | Vuoto, replay del caso storico | Esplicito locale |
|---|---:|---:|
| Dichiarazioni O1/O2 recuperate | 2 | 2 |
| Tipi VERIFIED | 0 | 2 |
| Membri dichiarati VERIFIED | 0 | 12 |
| Relazioni osservate | 9 | 10 |
| Relazioni VERIFIED / UNRESOLVED | 0 / 9 | 10 / 0 |
| Snapshot / replay dedicato | INCOMPLETE | COMPLETE |
| Errori compiler | Presenti | 0 |
| Nuovi call site T01 attraversati | 0 | 0 |
| Frame / frontiere UNKNOWN T01 | 1 / 1 | 1 / 1 |
| Body traversal | NOT_ASSERTED | NOT_ASSERTED |
| Osservazioni S01 | 0 | 0 |

Le 10 relazioni sono due riferimenti di tipo, una produzione del valore e sette dipendenze esecutive; produzione e relativa invocazione condividono lo stesso sito. Non sono dieci nuovi call site né dieci target distinti. Le sette invocazioni selezionate corrispondono a cinque identità eseguibili distinte: produttore, isDuplicate, isPublished, getMessageId e costruttore. Le due chiamate createSuccessResponse sono fuori dalla selezione O1/O2; il probe le osserva senza estendere lo scope del sidecar.

`BindingOracle.java` è un probe separato senza import o dipendenze Mana: legge il sorgente originale, esegue parse/analyze senza generazione, disabilita processor/source discovery, emette soltanto metadati. Nel classpath completo, **10/10 relazioni coincidono per span e identità canonica**, con firme tipizzate, superclass Object/RuntimeException e zero errori. I recovery del caso vuoto restano diagnostici, non prove positive. Il primo tentativo di compilazione del solo probe aveva omesso tools.jar dal classpath del compilatore JDK 8; corretto esclusivamente il runner esterno, senza cambiare HYBRID-01 o il target.

Dati: `request-b-empty.json`, `request-b-explicit.json`, `b-empty.json`, `b-explicit.json`, `b-summary.json`, `oracle-b-empty.json`, `oracle-b-explicit.json`, `t01-comparison.json`; runner `experiment_b.py`, `run_oracle.py`, `verify_t01.py`.

T01 viene ricostruito in entrambi i casi dallo stesso engine, che non consuma il classpath del sidecar. SHA-256 T01 invariato `b450846aaa01a4ed4aef630f37fb4a89ba664e38fb1caf24e54c8ba43a43346c`; S01 invariato `e7a282c2adfe91bbdd6f12b44cb56d89ab3bf81838d5ee0067cfe16d7c28c040`, entrambi uguali anche ai risultati storici F02-R1/HYBRID-01.

## Causa del mancato avanzamento e decisione

Due cause distinte sono ora circoscritte:

1. **Zero binding storici:** il singolo sorgente e il classpath vuoto non fornivano NotificationPayload alla firma del produttore; inoltre l'unità aveva import/tipi esterni mancanti. La policy globale invalidava anche i binding locali recuperabili di O2. Il classpath verificato risolve questa frontiera semantica per entrambe le dipendenze.
2. **Zero avanzamento T01 anche ora:** lo snapshot è intenzionalmente supplementare e non entra nei fatti canonici/guardie T01. Le due dichiarazioni restano omesse dal modello canonico, che arresta il frame con `OMITTED_TYPE_EXECUTION_DEPENDENCY_NOT_MODELED`. Non è stata raggiunta una nuova frontiera T01. Anche una futura sostituzione motivata di quella guardia non risolverebbe automaticamente le gerarchie omesse residue, la dichiarazione locale, IF/THROW, argomenti e controllo del flusso già distinti da D02.

L'utilità del recupero semantico è verificata sul metodo reale, quindi la componente D02 è pronta per una successiva integrazione autorizzata. **Non è pronta una promozione del metodo reale a percorso attraversato.** Nessun commit, merge, push o integrazione viene eseguito in R1.

Un solo eventuale incremento successivo: **D03, contratto di consumo del witness verificato alla frontiera O1/O2 di T01**, prima di implementarlo. Deve distinguere soddisfacimento della dipendenza dichiarativa da autorizzazione al traversal, fissare replay/input identici e mantenere UNKNOWN per gerarchie/corpo/continuazione non modellati. Nessun CFG, interprete di throw o rimozione globale delle guardie è incluso o avviato qui.

## Preservazione e arresto

Inventario R1 iniziale dei 1.545 file Mana tracciati/non ignorati, contenuti e modi; inventario completo del sottoprogetto service, inclusi target preesistenti; digest delle evidenze precedenti; HEAD, stato, indice e worktree. Controllo finale in `integrity.json`: originali invariati, implementazione non committata preservata, 17 materiali locali e tutti i sei storicamente protetti preservati, evidenze precedenti immutate. Unica aggiunta nel repository: questo rapporto. JAR e classi locali usati come input confrontati per hash; nessun input modificato.

Nessun nuovo worktree, build del servizio, codice applicativo eseguito, transazione, accesso database, download, modifica Maven/Gradle, nuova skill o modifica S02/VIS-01. Runtime, deployment, S02 e VIS-01 NOT RUN. Review e consegna concluse; nessuna correzione automatica.
