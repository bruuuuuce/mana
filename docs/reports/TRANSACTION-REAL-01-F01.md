# MANA-TRANSACTION-REAL-01-F01

Data: 2026-10-23. Verdetto: **FIX_READY_FOR_REVIEW**, limitato alla remediation dell’ingresso e al contenimento diagnostico. Non è un PASS del flusso applicativo reale completo.

Baseline verificata: `f509f83d61258780f6d3e3b151955af637325b68`. Nessun commit, merge, push, nuovo worktree, clone, modifica al target, interrogazione database o esecuzione di transazioni. I 13 materiali locali preesistenti e le evidenze originali REAL-01 sono conservati. Attestazioni e risultati: `/private/tmp/mana-real-01-f01-evidence/`.

## A — Diagnosi dell’ingresso

- Il parser JDK `JavaFacts.java` usava già `MethodTree.getParameters().size()` e registrava `arity`; non imponeva zero parametri alla dichiarazione. Il parse è senza attribution, generation, processors, build o caricamento di classi target. Mancavano i metadati dei singoli parametri.
- `transactions/model.py::build` costruiva soltanto chiavi `Class#method()` per dichiarazioni con `arity == 0`. L’entry veniva cercata per uguaglianza testuale in quella mappa: il metodo REAL-01 non poteva entrarvi. Non esisteva una selezione di overload parametrizzati.
- La guardia alzava `ValueError`. `mana-transaction.py::main` lo intercettava, emetteva JSON su stderr e restituiva 2. Il CLI S01 chiamava T01 internamente e il proprio `main` trasformava lo stesso errore in exit 2. Il parser non produceva quell’exit 2 per questo caso.
- Un limite distinto resta nel traversal: `call["arity"] != 0` impedisce la risoluzione delle chiamate applicative con argomenti. Questa condizione è conservata: il supporto dell’entry non introduce dispatch o binding dei valori ai call site.
- `resources.py::_method` e `resource_leaf.py::source_method` cercavano anch’essi soltanto metodi senza parametri. Ora usano la stessa identità di dichiarazione dell’ingresso, con verifica dell’evidenza sorgente.
- I confini REQUIRED/REQUIRES_NEW/NESTED e le loro transizioni non richiedono valori runtime dei parametri. Dipendono da annotazioni, contesto esplicito, manager, intercettazione e limiti sintattici già esistenti. Lo schema e i campi transazionali v1 restano invariati.

## B — Supporto bounded implementato

`transactions/entry.py` centralizza l’identità di dichiarazione. `Class#method()` continua a significare esattamente zero parametri; `Class#method(types)` seleziona la firma esatta; `Class#method` richiede una sola dichiarazione. Gli errori controllati riportano alternative, arità, metadati dei parametri e riferimenti/digest; non riportano espressioni dei corpi. Collisioni della firma/erasure sono rifiutate con entrambe le alternative.

Il parser conserva nome, ordine, tipo dichiarato, namespace sorgente nel sottoinsieme supportato, posizione UTF-16 e hash del file per ogni parametro. Il valore runtime è sempre `UNKNOWN`. Annotazioni sui parametri non vengono eseguite e i loro argomenti non diventano valori dei parametri. Sono supportati primitivi, array, import espliciti, tipi osservati nello stesso package, un insieme chiuso java.lang e generici concreti come `List<String>` e `Map<String,List<Integer>>`. Gli import wildcard riconoscono tipi sorgenti osservati e il catalogo chiuso java.util documentato nello standard.

Un tipo semplice non legato sotto import wildcard può conservare la sola grafia **DECLARED_ONLY**, con `type: null`: serve a identificare una dichiarazione unica, non ad affermare il suo tipo risolto sul classpath. Qualunque gruppo di overload con namespace o firma non risolti è bloccato. Type variable e forme non supportate restano errori controllati. Non è un resolver Java universale.

Un parametro che nasconde un campo non prova l’identità del bean/JDBC receiver: T01 e S01 conservano UNKNOWN. La forma esplicita `this.field` conserva il significato esistente. Non sono stati aggiunti binding o risoluzioni delle chiamate applicative con argomenti. Le modifiche a S01/leaf riguardano il lookup della dichiarazione e questa guardia, senza cambiare catalogo JDBC, collocamento, causalità o transizioni. Nessuna modifica a S02, motore dei grafi o VIS-01; nel test S02 esistente cambia soltanto l’opt-in al payload interno del parser.

## C — Diagnosi e contenimento dell’AST

Catena dell’esposizione storica: `JavaFacts.visitMethodInvocation` serializzava `select.getExpression().toString()` nel campo `receiver`; `source.java_facts` deserializzava il payload AST. Durante il preflight REAL-01 il supervisore stampò una selezione troppo ampia di questi metadati, che divenne un risultato tool visibile nella conversazione Codex. È il canale descritto esplicitamente dal rapporto originale, non una chiamata a provider eseguita da Mana.

| Canale | Evidenza e confine |
|---|---|
| Payload AST locale interno | Receiver/espressioni, letterali e annotazioni; Python aggiunge inoltre `sources`, necessario alla ri-validazione degli snapshot leaf. È materiale sorgente, non diagnostica sicura. |
| stdout del subprocess Java | Protocollo interno catturato da Python, non inoltrato automaticamente al terminale/provider. Non viene salvato come dump in F01. |
| stdout/stderr dei CLI del pilot | Due rifiuti dell’entry e nessun artefatto pubblicato, come da report/manifest originali. Non dimostrano l’invio del payload AST. |
| Conversazione col provider | L’incidente preesistente è attestato dal rapporto REAL-01: alcune espressioni receiver sono entrate nella conversazione Codex tramite output del supervisore. Gli esatti byte e il payload completo non sono ricostruibili dai file consegnati: il dump intermedio risulta rimosso. Non si attribuisce l’invio di tutti i sorgenti. |
| Log persistenti e report | I log degli analyzer originali e il rapporto documentano il rifiuto/incidente. Non c’è evidenza qui di altre destinazioni, log remoti o ulteriori invii. F01 salva soltanto risultati, metadati, digest, patch Mana/fixture e log dei controlli locali. |

La remediation autorizzata affronta l’incidente già dichiarato nell’input; non è emersa una nuova trasmissione di espressioni sorgente del target. Non sono stati invocati strumenti di rete o provider per l’analisi. Non si afferma di avere telemetria completa del provider o di poter annullare l’esposizione storica.

Ora **`java_facts` restituisce per default una proiezione diagnostica allowlist**: simboli, firme, metadati dei parametri, hazard, arità e riferimenti relativi con posizione/hash. Esclude `sources`, receiver, valori degli argomenti e testi delle annotazioni. L’analisi interna e le regressioni che necessitano del contratto sorgente usano esplicitamente `source_snapshot=True`; questo flag non autorizza trasmissioni a provider. I contratti locali source-bearing S01/leaf rimangono intatti. Il confronto di snapshot storici ammette l’assenza del solo nuovo metadato derivato `parameters`, mantenendo il confronto degli altri fatti e la ri-parsificazione sorgente.

Anche i canali di errore sono contenuti: il fallimento del subprocess non riecheggia stderr; gli errori di sintassi JDK espongono solo codice diagnostico e linea, senza estratti. Lo stdout dei CLI resta un riepilogo. Gli output completi previsti dai contratti sono confinati alla destinazione locale esplicitamente richiesta; nella verifica reale F01 vengono validati in memoria e non salvati.

Le fixture usano sentinelle in receiver, argomenti, SQL e inizializzatore statico. I controlli verificano l’assenza nella diagnostica predefinita e in stdout/stderr, e distinguono lo snapshot S01 esplicitamente autorizzato, che per contratto contiene sorgenti e viene rimosso con la directory temporanea del test. Nessun dump reale o estratto del corpo è incluso in questa consegna.

## D — Regressioni e verifiche

Fixture indipendente: `tests/fixtures/transaction-entry-parameters/`. Suite: `python3 tests/transaction-entry-parameters.py -v`.

Copertura: metodo zero parametri; uno e sei parametri; overload con arità diversa; stessa arità/tipi diversi; parametro annotato; generici concreti annidati; firma non risolvibile/type variable; sentinelle AST/errori; REQUIRED con ingresso parametrizzato. Controlli aggiuntivi: firma wildcard DECLARED_ONLY e overload bloccati, collisione di erasure, shadowing di campi/receiver, call site parametrizzati ancora UNKNOWN, S01 sul frontier JDBC, fixture immutabile, argv JDK parse-only e ri-validazione di uno snapshot leaf storico. REQUIRED mantiene P1 per entrambi i frame e due scope L1/L2 nelle fixture positive, senza valori runtime.

**PASS: 259 test, 11 suite, nessun test saltato.** Validazione repository, Ruff check e Ruff format check: **PASS**, tutti exit 0.

| Suite | Test | Esito |
|---|---:|---|
| transaction-entry-parameters | 12 | PASS |
| transaction-boundaries | 16 | PASS |
| transaction-self-invocation | 16 | PASS |
| transaction-context-alternatives | 21 | PASS |
| transaction-aop-causal-order | 26 | PASS |
| transaction-transition-contract | 64 | PASS |
| transaction-physical-lifetime | 19 | PASS |
| resource-timeline | 22 | PASS |
| transaction-resource-leaves | 31 | PASS |
| transaction-resource-binding | 10 | PASS |
| transaction-resource-dispatch | 22 | PASS |

Risultati definitivi e comandi sono in `regressions.json` e `validation.json`, con i relativi log. Sono state eseguite soltanto le regressioni pertinenti T01/S01, la validazione repository e Ruff; nessuna suite generale o build pesante. Il runner locale riproducibile è `run-checks.py`. Gli eventuali tentativi intermedi falliti durante la preparazione delle fixture non sono presentati come risultati definitivi.

## E — Verifica limitata del caso reale

Eseguita solo dopo il PASS dei controlli sentinella. Stesso progetto storico e medesimo `com.nexi.npg.phoenixkafkaservices.services.NotificationService#submitNotificationSync`, senza sostituirlo con un target più semplice. Selezione per nome univoco, sei parametri; file, offset, linea, hash e digest dello span coincidono con il pilot. Il tipo dichiarato `NotificationPayload` mantiene namespace non risolto e grafia DECLARED_ONLY; i cinque `String` conservano metadati di tipo sorgente. Non sono stati inventati valori o binding.

| Stadio | Esito limitato |
|---|---|
| T01 | Modello v1 validato in memoria; precedente blocco zero argomenti **CLEARED**. Un frame, zero scope e zero transazioni fisiche ricostruiti. |
| T02-S01 | Timeline validata in memoria, T01 conservato identico; zero osservazioni e nessun collocamento ricostruito. |
| T02-S02 / VIS-01 | **NOT_RUN**; fuori dalla verifica richiesta, nessuna esecuzione downstream. |
| Database / runtime target | **NOT_RUN**. |

Limite residuo effettivo: `INHERITANCE_OR_INTERFACE_RESOLUTION_NOT_MODELED`, con `bodyTraversal: NOT_ASSERTED`. In questo caso il parser registra tre marker `UNKNOWN_NESTED_CLASS_OR_INITIALIZER` nel campo parents e `UNEXTRACTED_APPLICATION_TYPE`; non è prova di tre supertipi o di ereditarietà reale. Sono inoltre presenti tre hazard del corpo `unsupported-control-or-expression`, già segnalati dal preflight originale. Non vengono aggirati o corretti in F01. Zero scope/osservazioni significa nessuna ricostruzione nel modello limitato, non assenza di transazioni o persistenza a runtime.

`real-reproduction.json` conserva metadati, limiti e digest dei risultati; `reproduce-real.py` rende ripetibile il controllo locale senza mostrare o conservare dump sorgenti. La validazione strutturale T01/S01 non equivale alla qualificazione dell’intero flusso, di Spring, di datasource o di lock.

## Consegna e limiti

Patch circoscritta: metadati del parser, selettore condiviso, lookup S01/leaf, guardia di shadowing e proiezione diagnostica/errori; test e chiarimenti documentali. La rappresentazione transazionale v1 esistente è sufficiente e non viene sostituita o estesa con nuovi campi transazionali. Non occorre MODEL_DECISION_REQUIRED.

In `/private/tmp/mana-real-01-f01-evidence/`: risultati delle regressioni, log dei controlli, esito reale, attestazione di conservazione, manifest con hash e `minimal.patch` che esclude i 13 materiali preesistenti. Nessuna copia integrale del progetto e nessun grande dump AST. I controlli di conservazione coprono contenuto/modo dei 13 materiali e dei file target tracciati/non ignorati inventariati, HEAD/status target e file originali del pilot; i file ignorati/interni Git non sono attestati.

Restano non supportati resolver Java generale, attribuzione classpath, dispatch applicativo con argomenti, controllo/espressioni complesse e i limiti transazionali già documentati. L’incidente storico resta irreversibile. **FIX_READY_FOR_REVIEW** riguarda questa remediation; l’analisi completa del flusso reale resta incompleta per i limiti successivi, con runtime/database non eseguiti. Attività fermata alla consegna, senza commit.
