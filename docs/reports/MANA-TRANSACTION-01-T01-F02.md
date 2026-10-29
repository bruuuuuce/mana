# MANA-TRANSACTION-01-T01-F02 — Conditional Context Preservation

Data: 20 ottobre 2026. Verdetto: **FIX_READY_FOR_REVIEW**.

Corretto R2-F01 nel motore e nel validatore. Advice UNKNOWN può ora coesistere
con ACTIVE/P1 quando APPLIED e BYPASSED condividono quella proprietà. Attività,
identità fisica e manager sono composti separatamente; gli effetti esclusivi del
ramo APPLIED rimangono condizionali e non diventano eventi o entità incondizionati.
Questo è un risultato d'implementazione e regressione locale, da sottoporre a nuova
review indipendente. Il verdetto storico R2 NEEDS_FIX rimane immutato.

- [Evidenze complete](MANA-TRANSACTION-01-T01-F02-results.json): comandi, output,
  exit code, riproduzione R2 prima/dopo, otto modelli/PlantUML F02, hash e stato Git.
- [Diff F02](MANA-TRANSACTION-01-T01-F02.patch): delta rispetto al working tree
  all'inizio di F02, inclusi file T01 ancora untracked; non rispetto al solo HEAD.
- [Oracoli F02](../../tests/fixtures/transaction-context-alternatives/oracles.json)
  e [suite](../../tests/transaction-context-alternatives.py).
- [Semantica aggiornata](../standards/transaction-model-v1.md).

## Ricostruzione prima delle modifiche

Letti rapporto/receipt R2, rapporto F01 e standard, quindi codice e oracoli reali.
Prima di modificare il codice sono stati identificati entrambi i responsabili:

1. `model.py`, `uncertain()` (riga 181 del pre-F02), imponeva `duringState =
   unknown()`, eliminando attività, physicalId e manager. La fase finale del frame
   imponeva inoltre afterState UNKNOWN per ogni frame incerto.
2. Il validatore (righe 648–649 del pre-F02) vietava UNKNOWN dell'intercettazione
   con un duringState diverso da UNKNOWN, anche con P1 dimostrabile.

Il `previousState` rimaneva conservato, ma quella conoscenza non era utilizzabile
come contesto effettivo e la continuazione del chiamante diventava UNKNOWN.
Lo stesso azzeramento riguardava REQUIRED, REQUIRES_NEW e NESTED; non tutti i
risultati però potevano essere conservati nello stesso modo.

La sorgente esatta del controesempio R2 e il suo contesto sono stati estratti dal
receipt immutabile in una directory esterna. Prima della correzione la CLI usciva
0 e produceva per il figlio `before: ACTIVE`, `during/after: UNKNOWN`. La nuova
fixture `r2-original` conserva quella sorgente byte per byte e la regressione CLI
confronta anche il contesto con il receipt R2, senza sostituire il controesempio.

## Composizione limitata delle alternative

Il nuovo helper `scripts/skill_factory/transactions/alternatives.py` descrive il
solo confine transazionale supportato, senza un interprete simbolico generale.
`model.py` lo usa quando l'incertezza riguarda l'applicazione dell'advice, dopo i
controlli su async, annotazioni, risoluzione del target, hazard e controllo di flusso.
Gli altri motivi di incertezza mantengono i limiti precedenti.

Il campo additivo `frame.contextComposition` registra premesse con evidenza sorgente,
alternative APPLIED/BYPASSED e proprietà comuni. Lo schema resta
`mana.transaction-model/v1`; i modelli storici sono ancora leggibili/validabili.

| Caso con advice UNKNOWN | Contesto comune durante il confine | Effetti nel solo ramo APPLIED |
|---|---|---|
| REQUIRED con P1 e stesso manager tx | ACTIVE/P1/tx | Scope logico IF_APPLIED |
| REQUIRED senza transazione iniziale | Attività e identità UNKNOWN | Transazione fresca e scope logico |
| REQUIRES_NEW con P1/tx, suspend true | ACTIVE/tx, identità fisica UNKNOWN | Sospensione P1, identità fresca, scope logico e ripristino |
| NESTED con P1/tx, savepoints true | ACTIVE/P1/tx | Scope logico e savepoint IF_APPLIED sulla stessa P1 |
| NESTED con savepoints null/false | APPLIED irrisolto; nessuna certezza fisica comune inventata | Supporto/savepoint UNKNOWN |
| REQUIRES_NEW con suspend null | APPLIED irrisolto | Nessuna sospensione inventata |
| Manager ambiguo o identità precedente irrisolta | APPLIED irrisolto | Nessun binding/capability inventato |

`IF_APPLIED` rappresenta presenza **CONDITIONAL** sotto quella specifica alternativa.
Lo scope condizionale è descritto nel ramo, senza allocare una L certa nel vecchio
array `logicalScopes`. Analogamente savepoint, sospensione e nuova identità fisica
restano descrittori di ramo, senza falsi BEGIN/END o entità globali. La distinzione
fra scope logico condizionale e P1 nota è quindi esplicita anche quando
`frame.logicalScope` resta null.

Per REQUIRES_NEW l'intersezione preserva ACTIVE e tx ma usa physicalId null:
`FRESH_IF_APPLIED` non può diventare P1. Non viene creata una P2 globale comune
anche al bypass. Il validatore richiede il witness di composizione per questa
identità parziale; il renderer la etichetta PHYSICAL_ID_UNKNOWN.

`duringState` descrive il contesto al confine d'ingresso, senza qualificare un corpo
non attraversato. La conservazione dell'after-state è limitata a corpi osservati
vuoti e confini APPLIED supportati: al normale unwind sincrono entrambe le
alternative ripristinano il contesto precedente. Non si afferma che la chiamata
sia avvenuta, che il ritorno abbia successo o che avvenga commit/rollback.
Un corpo non vuoto non attraversato o un confine irrisolto mantiene after UNKNOWN.
La continuazione del chiamante può proseguire soltanto quando il figlio vuoto
ripristina lo stesso contesto noto; una regressione controlla la chiamata successiva.

Le regole sono confrontate con le fonti primarie Spring
[Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
e [Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html),
consultate durante F02. Le conclusioni dei modelli rimangono condizionali e statiche.

## Validatore

La precedente implicazione UNKNOWN advice → UNKNOWN fisico è rimossa soltanto
in presenza di una composizione coerente. Il validatore controlla:

- Entrambe le alternative e il contesto ereditato del bypass.
- Semantica APPLIED ricontrollata da propagation, manager identificato e capability,
  senza fidarsi della risoluzione dichiarata dal ramo o del suo stato comune.
- Coerenza delle capability con il contesto di scenario e della modalità/weaving
  con il motivo dell'incertezza.
- Premesse sincrone e loro evidenza; contesto iniziale rispetto allo scenario,
  contesto precedente rispetto al chiamante e durata della P ereditata negli eventi.
- Uguaglianza delle proprietà comuni con i due esiti e con gli stati del frame.
- Assenza di effetti di ramo materializzati come entità incondizionate.

Restano i controlli v1 su referenze, ordine/frame, provenienza dei siti di chiamata,
identità distinte, mapping logico/fisico, savepoint e durate degli eventi. Sono
rafforzati anche i controlli di coerenza fra kind fisico, manager e identità.
UNKNOWN/ACTIVE senza witness valido resta rifiutato. I test negativi alterano
identità, alternative, capability, premesse, contesto del chiamante, after-state e
scope logico per verificare che la correzione non renda il validatore permissivo.

La verifica riguarda la consistenza del modello con i fatti/premesse forniti.
Il validatore non rilegge autonomamente il sorgente né prova l'esecuzione runtime;
l'analizzatore continua a legare gli snapshot con hash e a rifiutare modifiche del
target durante l'analisi.

## Oracoli e regressioni

Gli otto oracoli F02 sono valori letterali formulati dalle regole APPLIED/BYPASSED,
non dal risultato del generatore. I conteggi e le identità sono confrontati con le
sorgenti: P1 nasce nel chiamante, REQUIRED condivide o eredita P1, REQUIRES_NEW
ha identità divergenti, NESTED ha un savepoint solo sotto advice e capability.
La variante ambigua qualifica esplicitamente tx nel chiamante e lascia irrisolto
il default del figlio, così P1 non viene ottenuta da un manager ambiguo.

La suite copre tutti i dieci punti richiesti e aggiunge controlli per sospensione
ignota, corpo non vuoto, async/hazard, alterazioni del modello, immutabilità,
compatibilità storica e injection delle nuove etichette.

Due aspettative F01 sono aggiornate intenzionalmente: `aspectj_weaving_unproven`
e `unknown_mode` mantengono UNKNOWN **durante** il figlio, ma dopo il corpo vuoto
ritornano INACTIVE in entrambe le alternative. Gli oracoli ora dichiarano tale
risultato anche per il chiamante. I conteggi, l'assenza di P comune, le attese di
intercettazione e gli eventi precedenti non sono stati indeboliti. Il primo run F01
ha evidenziato proprio questi due mismatch; la deduzione di normal unwind è ora
documentata e testata. Rapporti, receipt e diagrammi storici F01/R2 non sono riscritti.
Un primo test CLI F02 usava un temporaneo non canonico su macOS: corretto il solo
harness con `Path.resolve()`, conservando il rifiuto dei path symlink nella CLI.

| Verifica finale | Esito |
|---|---|
| `python3 tests/transaction-context-alternatives.py -v` | PASS, 21 test, zero skipped, exit 0 |
| `python3 tests/transaction-self-invocation.py -v` | PASS, 16 test, zero skipped, exit 0 |
| `python3 tests/transaction-boundaries.py -v` | PASS, 16 test originali immutati, zero skipped, exit 0 |
| `python3 tests/mana-skill-factory.py -v` | PASS, 23 test immutati, zero skipped, exit 0 |
| `bash scripts/validate-repo.sh` | PASS, exit 0 |
| `bash tests/profile-skill-activation.sh` | PASS, exit 0 |
| Ruff check sui moduli e quattro suite pertinenti | PASS, exit 0 |
| Ruff format --check sugli stessi percorsi | PASS, 13 file, exit 0 |
| `git diff --check` | PASS, exit 0 |
| `git apply --reverse --check` sul patch F02 | PASS, sola verifica, nessuna applicazione |
| Otto invocazioni CLI F02 e R2 esatto dopo correzione | PASS, exit 0, oracoli e immutabilità |
| Validazione candidata T01 consegnata | PASS strutturale, exit 0, lifecycle invariato |

Nel controesempio R2 finale il figlio è interception UNKNOWN, context ACTIVE/P1/tx
sia durante sia dopo; lo scope logico aggiuntivo è IF_APPLIED. Il chiamante
conserva ACTIVE/P1 durante il proprio scope e al normale termine ripristina
NO_TRANSACTION, senza predire l'outcome runtime.

## PlantUML

I nuovi diagrammi distinguono advice UNKNOWN, P1 ereditata, scope logico
condizionale, savepoint condizionale e identità fisica incerta. REQUIRED/P1 e
NESTED/P1 restano verdi con note separate per l'incertezza; REQUIRES_NEW mostra
ACTIVE e PHYSICAL_ID_UNKNOWN, con SUSPEND/FRESH/RESUME esplicitamente IF_ADVICE_APPLIED.
Il savepoint condizionale su P1 ha una nota gialla. Capability/manager irrisolti
restano UNKNOWN. Premesse weaving, source evidence nel modello e normal-unwind
rimangono visibili o collegate; non si convertono ipotesi runtime in certezze.

Renderizzati 25 diagrammi: otto F02, otto F01 attuali, otto riletti dai JSON storici
T01 e il controesempio R2 esatto. Tutti passano sintassi, SVG e PNG con exit 0;
nessun SVG contiene Syntax Error. Ispezionati visivamente REQUIRED/P1, NESTED/P1,
capability ignota, REQUIRES_NEW con sospensione condizionale, assenza iniziale e
manager ambiguo. Il gruppo conserva il contesto certo senza mascherare l'advice.
I gruppi rimangono regioni di metodi; le durate fisiche e gli effetti condizionali
si distinguono attraverso eventi/note, senza simulare sovrapposizioni arbitrarie.

Tutte le nuove etichette variabili passano per `label()`; il controllo negativo
su newline, include e markup passa. La CLI non invoca PlantUML. Jar locale
`/Applications/plantuml-1.2024.8.jar`, SHA-256
`b88519d2f37c089a470ee7044ec011a72d130e70a61f7fcaa424179f1c1f4641`.
Nessun download. Artefatti esterni in
`/private/tmp/mana-t01-f02-4y136noq/final-artifacts/rendered`.
Modelli, PlantUML e comandi sono conservati anche nel receipt F02.

## Preservazione e stato Git

Branch iniziale/finale: `feature/mana-transaction-01`.
HEAD e develop locale: `378243883adb101a7a41feef71e2a66b76e7f508`.
Tree HEAD: `d5b7ae2cf2625ab6a788eb31f5fc62cbe0d39ee4`. Indice vuoto.

Il manifest iniziale contiene 1.206 file tracked/untracked non ignorati, copiati
anche esternamente prima degli interventi. Cambiano soltanto cinque file
preesistenti autorizzati: modello, renderer, standard e due file di test/oracolo
F01 sopra descritti. Si aggiungono helper delle alternative, suite e fixture F02,
e i tre deliverable F02 (rapporto, receipt, patch). Nessun file preesistente è
rimosso; hash e mode degli altri file restano identici, compresi i rapporti
storici, candidata, factory, parser/CLI, profili e modifiche T01 già presenti.
Lo stato Git completo e i confronti prima/dopo sono nel receipt.

La candidata mantiene generated, trusted/registered/executable false e approval
pending. Nessuna attivazione, nessun commit, merge, push o nuovo worktree; nessuna
modifica a Familiar o REL-01/A. Nessuna implementazione T02 o campagna QA generale.
Il working tree resta intenzionalmente non pulito con il lavoro preesistente e
la correzione F02, senza staging.

## Limiti residui

La composizione non estende l'intercettazione positiva all'intera superficie
AspectJ: il metodo final R2 rimane interception UNKNOWN. Non prova weaving,
capability reali del manager, identità runtime, classpath, commit/rollback o ritorno
senza eccezioni. Corpi non vuoti incerti non vengono esplorati attraverso i rami;
non sono introdotti risoluzione simbolica generale o effetti di risorse/lock.
La nuova suite ha un entry point esplicito; non è stata eseguita CI remota.

Runtime Spring/AspectJ, altre piattaforme, qualifica generale e accettazione
indipendente della correzione: **NOT RUN**. T02 deve attendere un mandato distinto
e conservare queste separazioni e UNKNOWN; i PASS locali non qualificano ownership
di connessioni/lock, concorrenza o deadlock. L'attività F02 termina alla consegna.
