# MANA-TRANSACTION-01-T01-F03 — Physical Transaction Lifetime Validation

Data: 20 ottobre 2026. Verdetto: **FIX_READY_FOR_REVIEW**.

Il validatore rifiuta ora ACTIVE/P1 dopo la fine fisica di P1, anche nel chiamante
ordinario e con continuazione UNKNOWN. Il motore generava già il modello corretto:
la correzione riguarda il controllo temporale del modello fornito. Le semantiche
condizionali F01/F02 restano conservate. Questo è un risultato d'implementazione
con verifiche locali; review indipendente e accettazione finale restano NOT RUN.

- [Receipt e prove riproducibili](MANA-TRANSACTION-01-T01-F03-results.json).
- [Diff F03](MANA-TRANSACTION-01-T01-F03.patch), rispetto al working tree iniziale,
  inclusi i file T01 ancora untracked, non rispetto al solo HEAD.
- [Suite lifetime](../../tests/transaction-physical-lifetime.py).
- [Invariante documentato](../standards/transaction-model-v1.md#physical-lifetime-invariant-f03).

## Ricostruzione prima del fix

Letti rapporto R3, receipt R3, rapporto F02 e standard; ispezionati direttamente
motore, validatore, composizione, renderer e oracoli preesistenti. Prima di cambiare
il codice sono stati riprodotti i tre controesempi R3 archiviati: tutti accettati
con `validate_model() == True`. Il receipt F03 conserva i modelli originali
integrali, i risultati prima/dopo e lo script portabile R3 immutato.

Nel caso HIGH esatto `required_active`, F1 apre P1 nell'evento 2, F2 UNKNOWN/REQUIRED
condivide P1 nelle alternative e F1 chiude L1 nell'evento 6. La transizione
responsabile è:

| Punto | Stato fisico |
|---|---|
| Prima dell'evento 7 | P1 viva e corrente, manager tx; L1 già chiusa |
| Evento 7 | `PHYSICAL_END_OUTCOME_UNKNOWN`, entity P1, frame F1 |
| Subito dopo | P1 terminata; nessuna P corrente, nessun contesto sospeso da ripristinare |
| Evento 8 | `FRAME_EXIT F1` |
| After-state corretto | NO_TRANSACTION, physicalId/manager null; INACTIVE |
| After-state alterato R3 | TRANSACTION_PHYSICAL/P1/tx; ACTIVE |
| Prima del fix | True: stato fisicamente impossibile accettato |
| Dopo il fix | ValueError: `physical context outside its active lifetime` |

La mutazione originale cambia soltanto `F1.afterState := F1.duringState` e
`F1.effectiveContext.after := ACTIVE`. Il vecchio ciclo degli eventi rimuoveva P1
da `active_physical`, ma a FRAME_EXIT propagava l'after-state dichiarato senza
controllarlo. I controlli aggiuntivi F02 riguardavano i frame con composizione,
non il chiamante ordinario. Il difetto è quindi nel validatore; il modello v1
contiene già identità, eventi e stato necessari. Lo standard rende ora esplicita
l'invariante, senza cambiare schema, generatore o renderer.

## Correzione delimitata

Il ciclo temporale esistente distingue P iniziate, P vive e contesti sospesi.
Una P non può essere riaperta con la stessa identità simbolica. Il previousState
di ogni frame deve coincidere con lo scenario iniziale o con il contesto corrente
del chiamante. Il duringState ereditato deve riferirsi a una P viva e non sospesa;
una nuova P richiede PHYSICAL_BEGIN del proprio frame e identità coerente.
FRAME_ENTER precede gli eventi di apertura: la P posseduta viene verificata al
suo BEGIN, evitando di trattarla come già aperta prima dell'evento.

LOGICAL_BEGIN/END e SAVEPOINT_CREATE/RELEASE richiedono una P viva quando
identificata, senza terminarla. Il termine fisico richiede la chiusura dei relativi
scope/savepoint e il corretto endFrame. SUSPEND conserva la durata della vecchia
P, escludendola dagli stati correnti. RESUME_CONDITIONAL richiede P conservata
ancora viva e sostituta già iniziata e terminata. A FRAME_EXIT una P dichiarata
attiva deve essere viva, non sospesa e coerente con il contesto da ripristinare.
UNKNOWN continuation non autorizza una certezza su una P terminata.

Rimangono invariati i controlli F02 sulle alternative e sui witness: P1 comune a
UNKNOWN/REQUIRED e UNKNOWN/NESTED resta certa; REQUIRES_NEW con advice UNKNOWN
mantiene ACTIVE con physicalId null e descrittori di ramo. Nessuna P di ramo è
materializzata come evento incondizionato. Nessun framework di stati o event
sourcing è introdotto. La Skill Factory, il parser, i profili e i file F01/F02
preesistenti non sono modificati.

## Matrice e oracoli

Le aspettative sono letterali, dedotte dalle regole di durata e dalle sorgenti,
non dagli output del motore/validatore. Le fixture IR storiche e il receipt R3
sono input immutabili; il nuovo test non chiede al generatore il proprio oracolo.
La CLI rigenera inoltre il caso R3 dalla sorgente `r2-original` e dal contesto
R3 esatto: after-state radice INACTIVE, figlio UNKNOWN/REQUIRED ACTIVE/P1.

| Scenario | Esito locale |
|---|---|
| Commit fisico di P1 | PASS per l'effetto astratto di fine durata; nessuna distinzione/prova runtime del commit |
| Rollback fisico di P1 | PASS per lo stesso effetto astratto; nessuna distinzione/prova runtime del rollback |
| REQUIRED, chiusura del solo scope condiviso | PASS: after F2 P1, un solo termine fisico nel proprietario |
| NESTED, chiusura savepoint | PASS: stessa P1 ancora attiva |
| REQUIRES_NEW, P2 terminata | PASS: ripristino P1 viva dopo termine P2 |
| REQUIRES_NEW, P2 ancora attiva | PASS negativo: ripristino anticipato rifiutato |
| UNKNOWN/REQUIRED con P1 comune | PASS: P1 preservata; scope IF_APPLIED |
| Termine P1 e after-state ACTIVE/P1 | PASS negativo: tre controesempi R3 rifiutati |
| Nuova identità senza BEGIN | PASS negativo: rifiuto |
| Riutilizzo simbolico di P1 già terminata | PASS negativo: rifiuto |

Il v1 ha soltanto `PHYSICAL_END_OUTCOME_UNKNOWN`, non eventi distinti di commit
e rollback. Entrambi gli esiti possibili terminano la durata; il test esercita
questo unico marker mantenendo outcome UNKNOWN. Non sono inventate API né
qualificate separatamente le due esecuzioni runtime. Altri negativi coprono
assenza di resume, begin prima di suspend, fine prima della chiusura logica,
contesto iniziale/chiamante alterato e proprietario del termine errato.

## Verifica e renderer

| Verifica | Risultato |
|---|---|
| Nuova suite F03 | PASS, 19 test, zero skipped |
| F02 | PASS, 21 test, zero skipped |
| F01 | PASS, 16 test, zero skipped |
| T01 | PASS, 16 test, zero skipped |
| Skill Factory | PASS, 23 test, zero skipped |
| Repository e profili | PASS, exit 0 |
| Ruff check / format --check | PASS, exit 0 |
| `git diff --check` | PASS, exit 0 |
| Patch F03, `git apply --reverse --check` | PASS, nessuna applicazione |
| Candidata T01 | PASS strutturale; generated, pending, non eseguibile |
| CLI R3 esatta e tre negativi archiviati | PASS con i risultati descritti |
| PlantUML, sintassi / SVG / PNG | PASS, 17 diagrammi, zero Syntax Error |

I 76 test precedenti non sono modificati. Un primo nuovo negativo spostava il
termine F1 dentro F2: era rifiutato dal controllo di nesting prima del controllo
che si voleva provare. Corretto l'harness spostandolo prima della chiusura L1 nel
suo frame; ora prova direttamente l'ordine fisico/logico. Nessun oracolo positivo
è stato indebolito.

Il renderer invariato rappresenta gruppi di metodi; gli eventi BEGIN/END definiscono
le durate fisiche. I nuovi controlli testuali verificano che dopo END P1 non
compaiano context=ACTIVE o identità INHERITED/INDEPENDENT P1, e che END P2 preceda
RESUME P1. Ispezionati visivamente i PNG R3 rigenerato, REQUIRES_NEW e NESTED:
nessuna attività rappresentata oltre il termine; scope e savepoint non simulano
termini fisici. La nota F02 sul ritorno ACTIVE/P1 del figlio precede il successivo
termine del chiamante. La CLI valida prima del rendering; il renderer puro non
è un secondo validatore per IR arbitrari forniti direttamente.

I 17 diagrammi comprendono R3 rigenerato, otto casi R3/F02 e otto modelli storici
T01. Jar locale `/Applications/plantuml-1.2024.8.jar`, SHA-256
`b88519d2f37c089a470ee7044ec011a72d130e70a61f7fcaa424179f1c1f4641`.
Modelli, PlantUML, log, hash e script sono nel receipt; PNG/SVG esterni in
`/private/tmp/mana-t01-f03-y7ukqc9e/rendered`. Nessun download.

## Preservazione, limiti e arresto

Branch iniziale/finale `feature/mana-transaction-01`; HEAD invariato
`378243883adb101a7a41feef71e2a66b76e7f508`. Indice vuoto. Nessun commit, merge,
push o nuovo worktree; nessun intervento su Familiar, attivazione candidata,
implementazione T02 o campagna QA generale.

I 1.219 file inventariati da R3 corrispondevano integralmente al preflight F03
per SHA-256 e mode. Il manifest F03 contiene 1.221 file, inclusi i due deliverable
R3, copiati esternamente prima delle modifiche. Si modificano soltanto
`model.py` e lo standard autorizzati, con delta nel patch; tutti gli altri 1.219
file attuali conservano hash e mode. Nessun file eliminato. Si aggiungono soltanto
suite F03 e tre deliverable F03. Rapporti/receipt/patch storici, sorgenti delle
fixture, candidata e tutte le modifiche non correlate restano immutati.

La verifica riguarda la consistenza temporale di un percorso statico condizionale,
non weaving, capacità reali, identità o esiti runtime. Non viene aggiunto parsing
indipendente dei fatti sorgente nel validatore, né qualificata la completezza di
ogni campo semantico del v1. L'osservazione R3 supplementare sul campo outcome
non diventa una nuova qualifica runtime. Review indipendente F03, CI remota,
Spring/AspectJ runtime e altre piattaforme: NOT RUN. T02 resta fuori perimetro.
L'attività termina con questa consegna.
