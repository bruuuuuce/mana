# MANA-TRANSACTION-01-VIS-01

Verdetto: **IMPLEMENTED_READY_FOR_REVIEW**.

Renderer integrato PlantUML consegnato, con tre scenari, sorgenti e SVG effettivi.
La modifica estende `scripts/skill_factory/transactions/plantuml.py`; la CLI
`scripts/mana-transaction-visualization.py` legge esclusivamente artefatti offline.
Nessun cambiamento semantico a T01, S01 o S02 e nessun secondo analizzatore.

## Baseline, provenienza e conservazione

Preflight: branch `develop`, HEAD esattamente
`a222018fa50a3e1286a01f6da6c224a4dea242ed`, indice vuoto. Creato il branch
`feature/mana-transaction-visualization` dalla stessa baseline, senza worktree.
La protezione filesystem di `.git` ha richiesto escalation per la sola creazione
del branch; l'operazione autorizzata è riuscita senza alterare il contenuto locale.

| Componente integrato | Commit di provenienza |
|---|---|
| T01 | `e3537e3f8c8329a71615fe59d496757d5392c6a8` |
| T02-S01 e resource leaves | `9d3468101ccdcf40f680418955be17aec098c9e6` |
| T02-S02 | `a222018fa50a3e1286a01f6da6c224a4dea242ed` |

I 13 file inizialmente modificati/untracked sono preservati byte per byte,
inclusi i deliverable finali S02-R1 untracked. I sei materiali storici protetti
coincidono anche per hash e mode con il receipt storico S01-D02-F02-R1:
MR00-transitions.csv, MR01-R2-results.json, MR01-R2.md, MR01-coverage.csv,
roadmap TRANSACTION-01-T02.md e TRANSACTION-01.md. Nessuna normalizzazione CRLF.
I moduli semantici T01/S01/S02 restano identici a HEAD. L'indice resta vuoto.
Nessun reset, stash, clean, checkout forzato, commit, merge, push o nuovo worktree.

## Consegna e scelte di rappresentazione

[Contratto della visualizzazione](../standards/transaction-visualization-v1.md).
[Indice navigabile degli esempi](../examples/transaction-01-vis-01/README.md).
[Test e oracoli di presentazione](../../tests/transaction-visualization.py).
[Risultati, log mirati, hash e conservazione](TRANSACTION-01-VIS-01-results.json).

La CLI confronta lo scenario esplicito con quello del report e applica il
validatore S02 esistente, inclusi digest esatti Timeline, digest canonici T01,
identità di scenario e proiezione completa. Non ripara né rigenera gli input.
Il renderer riutilizza gruppi, palette ed eventi del renderer T01. Le operazioni
S01 appaiono nella posizione originale, con entrambe le coordinate Timeline/T01,
risorsa, contesto fisico, metodo JDBC ed evidenza sorgente. UNPLACED resta fuori
dall'ordine causale. Bean/proxy sono etichettati con la certezza originale.

Ogni partecipante ha una sequenza separata: non esiste un ordine globale inventato
fra due transazioni concorrenti. I gruppi rappresentano annidamento dei metodi;
gli eventi espliciti definiscono i confini fisici e la sospensione. Il lifetime
sospeso di P1 non è falsificato con un rettangolo di attività continua. La
notazione LIVE / SUSPENDED e il ripristino condizionale restano espliciti.

Le viste DB usano archi rossi tratteggiati waiter→holder; le viste applicative
archi blu continui fra frame; le relazioni miste sono viola puntinate e tipizzate.
Il colore è sempre accompagnato da label. Le viste miste mantengono separati i
domini frame/P; non fabbricano un arco applicativo DB fra transazioni fisiche.
Le relazioni applicative sono obblighi dello scenario; solo gli archi DB vengono
filtrati per cut. Non si uniscono cut distinti per asserire un ciclo fattibile.

Ogni arco DB indica claim, candidato, cut, risorsa e premesse. `evidence.json`
conserva il report S02 completo, obblighi W1–W8, evidenze e namespace originali.
Gli alias Rn collegano le relazioni miste agli elementi originali del sidecar.
Link tipizzati identici condividono una sola freccia con tutti i riferimenti.
Gli input non possono introdurre direttive PlantUML arbitrarie: il renderer usa
la whitelist ASCII T01 e alias generati internamente; i valori completi restano
nel JSON di evidenza. Output sorgente e indice sono deterministici.

| Scenario | Risultato mostrato | Limite mantenuto |
|---|---|---|
| A | X→Y e Y→X nei due percorsi; due archi DB; CONDITIONAL_CYCLE_RISK nel cut common | INCOMPLETE; nessun deadlock osservato |
| B | Un solo arco DB; NO_CYCLE_IN_MODELED_SCENARIO nel cut one_wait | Esclusione strutturale locale distinta da UNKNOWN; nessuna garanzia universale |
| C | P1 LIVE/SUSPENDED, P2 indipendente, completamento sincrono, DB candidato P2→P1 e ripristino condizionale | CONDITIONAL_CROSS_LAYER_COMPLETION_RISK; nessun commit o rilascio lock dedotto |

## Validazione eseguita

- **PASS**: 113 test mirati, inclusi 13 nuovi controlli di presentazione e 100
  regressioni esistenti: transaction-boundaries (16), physical-lifetime (19),
  context-alternatives (21), resource-timeline (22), wait-dependencies (22).
- **PASS**: digest alterati, scenario diverso, identità fisiche/claim falsificati
  e modello T01 diverso sono rifiutati; pubblicazione assente su input respinto.
- **PASS**: ordine JDBC A/B, ciclo condizionale A, esclusione B con lacune visibili,
  sospensione/app/DB/mixed C, savepoint sullo stesso P, UNKNOWN e UNPLACED sulle
  fixture S01 originali, preservazione input, determinismo e sanitizzazione.
- **PASS**: `bash scripts/validate-repo.sh`, Ruff check e format sui tre file
  Python interessati; controllo whitespace sul renderer.
- **PASS**: PlantUML locale `/Applications/plantuml-1.2024.8.jar`, `-checkonly`
  e `-tsvg`, exit 0 sui 14 sorgenti: 5 sequenze, 3 DB, 3 applicativi, 3 misti.
  Verificati tutti gli SVG XML e la presenza effettiva di Coverage e NOT_RUN.
- **PASS nel campione ispezionato**: anteprime PNG locali di sequenze A/C e grafi
  DB A/B e mixed C. Il controllo ha corretto una legenda sostituita da PlantUML
  e ridotto la larghezza delle note JDBC. I sorgenti risultanti sono stati
  rigenerati e renderizzati; gli SVG restano navigabili a scala desktop.

## Limiti residui

KNOWN/VERIFIED qualifica struttura e riferimenti statici, mai esecuzione Spring.
Runtime, provider, lock acquisiti, thread bloccati e deadlock reali: **NOT_RUN**.
La review indipendente della modifica VIS-01: **NOT_RUN**. Non è stata avviata
una nuova campagna generale QA. Nessun adapter Oracle runtime, skill attivata,
framework grafico aggiuntivo, modifica Familiar o REL-01/A.

INCOMPLETE e UNKNOWN sono preservati; una regione sconosciuta non dimostra assenza
di dipendenze. L'esito B vale soltanto per operazioni selezionate e cut modellato.
I diagrammi non descrivono durate misurate né eccezioni o outcome commit/rollback.
Digest e validazione non autenticano da soli un'origine sorgente esterna.
La leggibilità è verificata sui tre esempi, non su ogni possibile input nei budget
S02; label molto lunghe sono limitate con riferimenti completi nel JSON. La
riproducibilità byte per byte degli SVG fra versioni diverse di JVM, PlantUML,
Graphviz e font non è qualificata. I contratti D00 preesistenti untracked restano
locali come richiesto e non vengono inclusi in alcun commit.
