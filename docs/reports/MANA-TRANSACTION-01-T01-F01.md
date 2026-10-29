# MANA-TRANSACTION-01-T01-F01 — AspectJ & Self-Invocation Remediation

Data: 20 ottobre 2026. Verdetto: **FIX_READY_FOR_REVIEW**.

Corretto il percorso R1-F01: una self-invocation annotata con modalità AspectJ
senza evidenza di weaving resta UNKNOWN, senza ricevere il bypass dei proxy.
Il motore distingue ora l'applicazione dell'intercettazione dal contesto
transazionale ereditato. Questo rapporto documenta l'implementazione e i test;
non sostituisce la successiva review indipendente e non modifica il verdetto
storico NEEDS_FIX del rapporto R1.

Consegna:

- [Evidenze complete](MANA-TRANSACTION-01-T01-F01-results.json): comandi, output,
  exit code, modelli e PlantUML degli otto casi, hash e controlli di preservazione.
- [Diff F01](MANA-TRANSACTION-01-T01-F01.patch): delta rispetto al working tree
  iniziale di questa remediation, compresi i file T01 ancora untracked.
- [Oracoli](../../tests/fixtures/transaction-self-invocation/oracles.json),
  [fixture](../../tests/fixtures/transaction-self-invocation/README.md) e
  [test mirati](../../tests/transaction-self-invocation.py).
- [Transaction Model aggiornato](../standards/transaction-model-v1.md).

## Correzione e perimetro

Sono stati modificati soltanto quattro file preesistenti: `model.py`, `plantuml.py`,
la CLI `mana-transaction.py` e lo standard del modello. Sono aggiunti i test F01,
le fixture e i tre file di consegna F01. Parser JDK, adapter/lifecycle della factory,
candidate, regressioni originali, rapporti T01/R1 ed esempi storici restano immutati.

Il modello aggiunge `interceptionMode: PROXY|ASPECTJ|UNKNOWN`, distinto dal vecchio
`proxyMode: CLASS|JDK|UNKNOWN`. Ogni nuovo frame espone:

| Informazione | Valori |
|---|---|
| `interception.status` | APPLIED, BYPASSED, UNKNOWN, con reason |
| `effectiveContext.before/during/after` | ACTIVE, INACTIVE, UNKNOWN |

In modalità PROXY nota, una self-invocation BYPASSED non applica la propagation
del metodo chiamato e conserva il contesto precedente. Può quindi essere
BYPASSED/ACTIVE, BYPASSED/INACTIVE oppure BYPASSED/UNKNOWN. L'assenza di advice non
crea una prova di assenza di transazione. Mode/visibilità/configurazione non risolte
mantengono gli esiti limitati. APPLIED non garantisce invece un contesto ACTIVE:
manager o capability mancanti possono rendere il confine UNKNOWN.

AspectJ applica le medesime regole di confine REQUIRED, REQUIRES_NEW e NESTED anche
alle self-invocation **soltanto sotto una premessa esplicita di weaving applicato**.
Il nuovo input opzionale `aspectjWeaving: ASSUMED_APPLIED` descrive quella premessa
condizionale; il default è UNKNOWN. La sola dichiarazione sorgente ASPECTJ non
abilita il percorso positivo. Una modalità UNKNOWN non viene risolta da questa
premessa e non diventa PROXY. L'input non accetta etichette PROVEN/APPLIED o booleani
che possano confondere una dichiarazione con una prova runtime.

I casi positivi non dimostrano un weaver operativo: verificano le conseguenze se
il weaving transazionale si applica ai metodi modellati. Questa è l'alternativa
esplicitamente condizionale consentita dal mandato quando l'applicazione effettiva
non è dimostrabile staticamente. `runtimeApplication` e identità/esito runtime
restano UNKNOWN. Non sono introdotti build, weaving tool o acquisizione di prove
runtime. Il sottoinsieme resta quello T01: metodi pubblici concreti, bean osservati,
chiamate sincrone dirette e manager/capability già supportati.

La distinzione proxy/self-invocation rispetto al weaving segue il riferimento
primario [Spring, Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).
Il motore non deriva dal riferimento alcuna certezza sul runtime del target.

## Fixture, oracoli e risultati

I tre progetti parse-only PROXY, ASPECTJ e UNKNOWN hanno sorgenti reali e un Maven
descriptor minimale. Gli otto oracoli sono valori letterali scritti separatamente
dal motore: stato dell'intercettazione, contesto, identità L/P, conteggi S/SP e ordine
completo degli eventi di confine. Le chiamate sono confrontate con i siti sorgente.
Nei casi con contesto attivo, P1 nasce nel chiamante intercettato prima della
self-invocation; non è inventata un'identità runtime esterna.

| Caso obbligatorio | Risultato verificato |
|---|---|
| PROXY REQUIRED senza transazione | BYPASSED/INACTIVE; nessuna L/P |
| PROXY REQUIRED con P1 attiva | BYPASSED/ACTIVE; P1 ereditata, nessuna L nuova |
| PROXY REQUIRES_NEW con P1 attiva | BYPASSED/ACTIVE; nessuna P2 o sospensione |
| ASPECTJ REQUIRED, weaving assunto applicato | APPLIED; L/P aperte condizionalmente |
| ASPECTJ REQUIRES_NEW, weaving assunto applicato | P1 sospesa, P2 distinta, fine P2 e ripristino P1 |
| ASPECTJ NESTED, weaving assunto applicato | SP1 sulla stessa P1; nessuna P2 |
| ASPECTJ dichiarato, weaving non dimostrato | Intercettazione e contesto del metodo annotato UNKNOWN |
| Modalità UNKNOWN | Nessun bypass PROXY dedotto; incertezza conservata |

La suite aggiunge anche REQUIRED AspectJ su P1 attiva, capability false/mancanti,
contesto iniziale sconosciuto, rifiuto di input ambigui, controlli negativi sul
validatore, immutabilità del target e la riproduzione esatta del controesempio R1.
Quest'ultima ora produce UNKNOWN con incertezze esplicite e nessuna P inventata.

| Verifica rieseguita | Esito finale |
|---|---|
| `python3 tests/transaction-self-invocation.py -v` | PASS, 16 test, exit 0, nessuno skipped |
| `python3 tests/transaction-boundaries.py -v` | PASS, 16 test originali immutati, exit 0 |
| `python3 tests/mana-skill-factory.py -v` | PASS, 23 test, exit 0 |
| `scripts/validate-repo.sh` | PASS, exit 0 |
| `tests/profile-skill-activation.sh` | PASS, exit 0 |
| Ruff check e format check sui moduli/test interessati | PASS, exit 0; 11 file formattati |
| `git diff --check` | PASS, exit 0 |
| `git apply --reverse --check` sul diff F01 | PASS; sola verifica, nessuna applicazione |
| Otto invocazioni CLI F01 con output esterno nuovo | PASS, exit 0; confronto con gli oracoli |

Un primo run delle regressioni originali aveva segnalato soltanto l'assenza della
parola PROXY nel nuovo diagnostico di modalità sconosciuta. Il diagnostico finale
nomina entrambe le modalità (`PROXY_OR_ASPECTJ_MODE_NOT_ESTABLISHED`), conservando
l'esito UNKNOWN; i sedici test originali sono passati senza modificarli.

## PlantUML e compatibilità

Le note distinguono APPLIED/BYPASSED/UNKNOWN, ACTIVE/INACTIVE/UNKNOWN e P ereditata
o indipendente. Nei casi attivi bypassati compare INHERITED P1, senza regioni
NO_TRANSACTION. I casi AspectJ riportano la premessa di weaving; le ragioni sono
etichettate come advice e non come proxy. `proxy.crossed` è false per AspectJ.
La sanitizzazione dei dati sorgente rimane attiva anche per le nuove etichette.

I sedici diagrammi (otto F01 e otto riletti dai modelli storici) passano `-checkonly`
e rendering SVG. Gli otto PNG F01 finali sono stati aperti e ispezionati: scope,
identità, sospensione/ripristino, savepoint e stati incerti sono distinguibili.
Il confronto con gli otto modelli storici conferma invariati eventi, identità e
stati prima/durante/dopo; i vecchi file JSON/PUML/SVG non sono stati riscritti.
I nuovi campi sono additivi; validatore e renderer accettano i vecchi modelli v1.

Jar locale: `/Applications/plantuml-1.2024.8.jar`, SHA-256
`b88519d2f37c089a470ee7044ec011a72d130e70a61f7fcaa424179f1c1f4641`.
Un warning JVM CodeCache durante PNG non ha impedito la produzione degli otto
output; exit code 0. Nessun download. Rendering e temporanei rimangono esterni
al repository; modelli e testo PlantUML sono anche nel receipt F01.

## Preservazione, stato Git e rischi residui

Branch: `feature/mana-transaction-01`. HEAD e develop locale rimangono a
`378243883adb101a7a41feef71e2a66b76e7f508`; indice vuoto. Il working tree contiene
le modifiche T01/R1 precedenti e il delta F01 non staged. Gli hash/mode dei file
preesistenti sono stati confrontati: cambiano soltanto i quattro file autorizzati
per questa correzione. I sorgenti analizzati e le candidate rimangono immutati.
La candidata conserva generated/untrusted/unregistered/non-executable e approval
pending; i test della factory confermano i vincoli di lifecycle.

Nessun commit, merge, push o worktree. Nessuna modifica a Familiar o REL-01/A,
nessuna attivazione di candidate, nessuna implementazione T02 e nessuna campagna
QA generale. CI, altre piattaforme e runtime/weaving Spring restano NOT RUN.

Rischi residui: correttezza delle premesse esterne, manager/capability effettivi,
weaving realmente applicato e comportamento runtime non sono qualificati. Non è
supportata tutta la superficie AspectJ/Spring; i casi fuori dal sottoinsieme restano
UNKNOWN. Gli input storici rimangono leggibili, mentre i nuovi output aggiungono
campi ed etichette. I nuovi test F01 hanno un entry point esplicito separato.

La prossima review deve concentrarsi su R1-F01, separazione dei due assi, premessa
di weaving e regressioni correlate, usando il diff F01. Non occorre ripetere
l'intero audit T01 per valutare questa remediation.
