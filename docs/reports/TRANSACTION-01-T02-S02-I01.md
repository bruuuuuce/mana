# MANA-TRANSACTION-01-T02-S02-I01 — Wait dependency implementation

22 ottobre 2026. **IMPLEMENTED_READY_FOR_REVIEW**.
Implementazione e verifica locale circoscritta; review semantica indipendente e
qualificazione runtime **NOT RUN**. Nessuna diagnosi di deadlock confermato.

Il preflight ha verificato `develop` e HEAD
`9d3468101ccdcf40f680418955be17aec098c9e6`, letto integralmente
[contratto D00](TRANSACTION-01-T02-S02-contract.md),
[35 oracoli A–J](TRANSACTION-01-T02-S02-oracles.csv) e
[piano](TRANSACTION-01-T02-S02-implementation-plan.md). Le decisioni del
proprietario sono registrate separatamente in
[D01](TRANSACTION-01-T02-S02-D01-decisions.md). Nessun conflitto materiale e
nessun budget impedisce i casi obbligatori del primo incremento. Gli originali
D00 conservano byte, mode e formulazioni storiche.

## Risultato implementato

Nuovo consumer offline
[`wait_dependencies.py`](../../scripts/skill_factory/transactions/wait_dependencies.py),
nuova [CLI](../../scripts/mana-wait-dependencies.py) e
[validatore S02](../../scripts/skill_factory/transactions/wait_validation.py).
Le API, i projector e i validatori T01/S01 canonici non cambiano. Nessuna nuova
analisi del target è eseguita dalla CLI S02: consuma soltanto artifact già
esistenti, validandoli attraverso `validate_timeline` e le verifiche embedded
rule-2 correnti. Le fixture di verifica sono sorgenti sintetiche parse-only,
mai applicazioni eseguite o database.

Il sidecar `mana.wait-scenario/v1` riferisce i byte Timeline mediante SHA-256 e
stabilisce premesse esplicite per istanze, risorse opache, binding ipotetico,
richieste, acquisizioni, ritenzione e cut. Il report
`mana.wait-dependency/v1` conserva inventario completo, sorgenti, witness,
normal-return dependencies strutturate, lifetime P ed eventi di sospensione.
Ogni claim ha certezza qualitativa, regola, premesse con provenance e riferimenti
alle evidenze. Nessun parser di frasi libere, nome SQL, WRITE o P null crea
identità, lock, holder, causalità o semantica JDBC.

Le cinque categorie D00 restano distinte. Gli archi DB waiter→blocker richiedono
W1–W8 nel medesimo cut; gli archi applicativi caller→callee esprimono soltanto
un obbligo condizionale di completamento della chiamata sincrona risolta.
EXECUTES_IN, SUSPENDS_FOR e RESUME_REQUIRES_COMPLETION sono relazioni tipizzate
separate. Il controllo dei cicli non converte l'unione di cut diversi in un
ciclo fattibile. UNKNOWN/CONTRADICTED e input rifiutati hanno effetti distinti.

Il validatore controlla esplicitamente categorie, certezza, namespace, riferimenti,
identità, direzioni, W1–W8, separazione dei grafi e limiti. Verifica inoltre la
proiezione completa contro i byte originali. La sola uguaglianza con il producer
non è l'oracolo semantico: la suite usa attese manuali separate derivate dal CSV
D00 e controlli contrari.

## Utilità riproducibile

| Esempio | Risultato locale | Artifact |
|---|---|---|
| A: X/Y contro Y/X | Due archi DB condizionali al cut comune; CONDITIONAL_CYCLE_RISK | [Report](../examples/transaction-01-t02-s02/A/report.md), [JSON](../examples/transaction-01-t02-s02/A/wait-dependency.json) |
| B: X/Y per entrambe | Un arco DB al cut scelto; NO_CYCLE_IN_MODELED_SCENARIO; nessuna sicurezza generale asserita | [Report](../examples/transaction-01-t02-s02/B/report.md), [JSON](../examples/transaction-01-t02-s02/B/wait-dependency.json) |
| C: outer/REQUIRES_NEW | DB P2→P1, app Fouter→Finner; CONDITIONAL_CROSS_LAYER_COMPLETION_RISK; nessun P1→P2 DB | [Report](../examples/transaction-01-t02-s02/C/report.md), [JSON](../examples/transaction-01-t02-s02/C/wait-dependency.json) |

Ogni directory contiene input sintetici immutati, sidecar, JSON, spiegazioni W e
sorgenti Mermaid distinte per DB/app/cross-layer. La CLI ha pubblicato in nuove
directory esterne e ha rivalidato ciascun JSON prima della copia versionabile
in `docs/examples/transaction-01-t02-s02/`. I report JSON sono rispettivamente
86.426, 74.919 e 54.527 byte, entro il budget di 2 MiB. Diagrammi verificati per
contenuto/direzione/separazione nella suite; rendering e sintassi mediante motore
Mermaid esterno **NOT RUN**, eseguibile locale assente. Nessun renderer generale
nuovo o download di dipendenze.

## Verifiche e copertura

La [suite dedicata](../../tests/wait-dependencies.py) esegue **22 test PASS**:
include i 31 controlli di oracolo implementabili in I01, controlli semantici
specifici, input falsificati, output alterati, parser, budget, CLI senza overwrite,
compatibilità read-only dei tre esempi S01 canonici e preservazione delle fixture.
Il test degli oracoli comprende più casi; 22 e 31 sono conteggi di unità diverse,
non test da sommare. Attese manuali in
[oracles.json](../../tests/fixtures/wait-dependencies/oracles.json), payload e
riferimenti in [scenarios.py](../../tests/fixtures/wait-dependencies/scenarios.py).

| Verifica | Stato e ambito |
|---|---|
| 30 oracoli statici A–I | PASS nelle fixture sintetiche del minimo I01 |
| J05: etichette OBSERVED/runtimeIdentity statiche arbitrarie | PASS: rifiuto del sidecar; ulteriori mutazioni OBSERVED del report rifiutate dal validatore |
| J01–J04 | DEFERRED / NOT RUN: ingestione e correlazione runtime richiedono adapter fuori I01 |
| Inversione/stesso ordine/outer REQUIRES_NEW | PASS: direzioni, namespace, W1–W8, cut comuni e grafi distinti |
| REQUIRED/NESTED, L/SP end | PASS: P condivisa; nessun self-loop DB, nuova P o rilascio lock inventato |
| F02 ACTIVE/null, UNPLACED, async, frontiere | PASS: identità/ordine/corpi irrisolti conservati |
| PHYSICAL_END prima/dopo cut e falsificazione afterState | PASS: P terminata esclusa; input incoerente rifiutato; END futuro non elimina il rischio |
| Premesse UNKNOWN/CONTRADICTED/dipendenze cicliche; tabella incompatibile | PASS: nessuna qualificazione arbitraria |
| Digest, contesto, placement e witness alterati | PASS: input rifiutati |
| Budget/scope/overwrite | PASS: arresto o incompletezza esplicita, nessun troncamento o pubblicazione parziale |
| Ruff check e format --check | PASS sui soli cinque file Python nuovi |
| Suite T01/S01 generale, CI, provider, runtime | NOT RUN; nessuna nuova campagna generale |
| Review semantica indipendente I01 | NOT RUN; questa consegna non è approvazione/release acceptance |

Copertura completa delle 35 righe, esiti per caso, comandi, exit code, log finale,
digest di input/sidecar e dettagli degli esempi sono in
[coverage.csv](TRANSACTION-01-T02-S02-I01-coverage.csv) e
[results.json](TRANSACTION-01-T02-S02-I01-results.json).
Nessuna aspettativa J è dichiarata soddisfatta da un adapter inesistente. Le
aspettative runtime originali restano visibili nella matrice e nella ricevuta.

## Budget e limiti residui

Applicati 4 MiB per Timeline e per T01 embedded canonico, 8 MiB combinati dei byte
Timeline, 2 MiB sia per sidecar sia per report S02, 100.000 confronti candidati,
5.000 archi serializzati inclusi i collegamenti tipizzati. Gli stop per byte,
confronti e archi sono verificati; i limiti di confronti/archi sono esercitati
mediante budget ridotti iniettati, senza pretendere un carico da 100.001 confronti.
Timeline, sidecar/report e pubblicazione hanno anche controlli sulle soglie byte
effettive. I budget sono conservativi I01, non nuovi requisiti di release.

Perimetro: uno/due artifact, massimo due istanze, due risorse opache, quattro
operazioni DB selezionate e un livello di sospensione. L'inventario restante è
conservato fuori dalla selezione DB. Eccessi di perimetro sono UNSUPPORTED con
coverage INCOMPLETE, nessun arco DB qualificato sull'eccesso e risultato UNKNOWN.
Mancanza di cut, binding, holder, overlap, modo o causalità è riportata; nessuna
conclusione di assenza globale di rischi viene emessa su dati incompleti.

Nessuna risoluzione SQL generale, wiring JDBC, semantica DB reale, capture runtime,
solver di schedule o ricostruzione async. I digest dimostrano identità dei byte,
non autenticazione esterna delle sorgenti. T01 embedded è riferito mediante
codifica canonica dichiarata, senza attribuire quel digest a un file T01 separato
non fornito. Le definizioni normative R1–R7 restano invariate in D00.
Uso e schema completi: [standard S02](../standards/wait-dependency-model-v1.md).

## Diff e preservazione

Il diff I01 aggiunge esclusivamente modulo/validatore/CLI, suite e fixture nuove,
standard nuovo, decisioni D01, copertura e nuovi esempi A/B/C. Il
[patch](TRANSACTION-01-T02-S02-I01.patch) include queste superfici, con i file
untracked rappresentati come aggiunte; esclude deliberatamente questo report e
la ricevuta JSON che ne registra hash e inventario, evitando autoriferimenti.
Non incorpora i tre originali D00 né le 11 modifiche locali iniziali.

Audit finale registrato nella ricevuta: tutti i **1.313 file iniziali** sono
identici per SHA-256, dimensione e mode, inclusi **11 percorsi locali preesistenti**
e **sei materiali protetti**. I sei coincidono anche con il receipt storico
S01-D02-F02-R1. Nessuna modifica a T01/S01 canonici, Familiar, REL-01/A o skill.
HEAD e branch invariati; indice vuoto. Nessun commit, merge, push, reset,
worktree/clone o integrazione. Arresto alla consegna.
