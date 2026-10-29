# MANA-TRANSACTION-01-T01-MR01-F01 — AOP & Causal Ordering

Data: 20 ottobre 2026. Verdetto: **FIX_READY_FOR_REVIEW**.

Corrette le due false accettazioni MR01-R1. I quattro payload originali passano
da ACCEPT a REJECT; i positivi vicini, l'incertezza legittima e il prefisso già
dimostrato rimangono accettati. **26 nuove verifiche e tutti i 159 test precedenti
PASS, zero skipped.** Non costituisce una nuova review indipendente della fix.

Deliverable: [risultati e witness prima/dopo](MANA-TRANSACTION-01-T01-MR01-F01-results.json),
[diff incrementale](MANA-TRANSACTION-01-T01-MR01-F01.patch),
[fixture fornite](../../tests/fixtures/transaction-aop-causal-order/cases.json),
[suite mirata](../../tests/transaction-aop-causal-order.py).

## Controllo architetturale prima della modifica

Branch e HEAD iniziali confermati: `feature/mana-transaction-01`,
`378243883adb101a7a41feef71e2a66b76e7f508`. Inventariati 1.256 file iniziali,
inclusi tutti gli untracked non ignorati. Letti report/receipt MR01-R1,
contratto/CSV MR00 e codice effettivo; riprodotti i quattro witness esatti prima
di modificare il validatore. Tutti erano erroneamente accettati.

**Decisione: v1 sufficiente.** Sono due controlli locali mancanti con una causa
concettuale comune: un percorso UNKNOWN lasciava scoperte obbligazioni che non
dipendono dalla certezza dello stato transazionale. Non occorre una nuova
rappresentazione dell'incertezza o del controllo di flusso.

- AOP: modalità, crossed/reason, evidenze di configurazione e premessa weaving
  sono già presenti. La loro coerenza vale anche prima di entrare nel ramo F02.
- Ordine: sequence/nesting, UNRESOLVED_CALL, bodyTraversal e premesse F02
  EMPTY/SYNCHRONOUS_BOUNDARY permettono di distinguere perdita dell'ordine da
  semplice contesto transazionale UNKNOWN. Non basta leggere afterState.

L'assessment salvato prima dell'edit è riportato nel receipt. Non è stato
dimostrato un controesempio che richieda MODEL_DECISION_REQUIRED. MR00,
O01–O44, standard v1 e formato/eventi pubblici sono immutati.

## Correzione AOP

`model.py` verifica ora le premesse AOP per **ogni** frame, prima dei percorsi
APPLIED/BYPASSED/UNKNOWN e dei campi legacy opzionali. AspectJ richiede
`crossed=false` e `NOT_APPLICABLE_ASPECTJ`; premesse proxy, bypass e motivi
AspectJ non possono essere combinati con una modalità incompatibile. UNKNOWN
non evita questo controllo. I controlli semantici dei rami F02 rimangono attivi.
Un bypass PROXY certo (mancato crossing o metodo non intercettabile) non può
ammettere artificialmente il ramo APPLIED in una composizione UNKNOWN.

La lettura della modalità è unica per classificazione e validazione. Un valore
esplicito UNKNOWN non diventa PROXY per la presenza di CLASS. La compatibilità
D3 resta circoscritta agli IR originali senza il campo modalità che registrano
la premessa CLASS: l'APPLIED legacy richiede ancora crossing, reason ed evidenze
di configurazione con hash; la sola annotazione o la presenza di effetti non
sono sufficienti. Anche quei frame subiscono i controlli comuni.

AspectJ senza weaving stabilito mantiene advice UNKNOWN; ASSUMED_APPLIED resta
soltanto una premessa condizionale. Nessuna certezza di weaving runtime aggiunta.
Riferimenti: MR00 §§1/5/6 V1, D3; standard v1, Bounded Resolution.

## Correzione dell'ordine causale

Dopo le verifiche di stato, effetti e provenance, un controllo dal figlio al
genitore esamina le chiamate nell'ordine degli eventi. UNRESOLVED_CALL interrompe
l'ordine dimostrato del corpo; un figlio con ordine non dimostrato interrompe
il seguito del chiamante. Chiamate figlie o ulteriori chiamate irrisolte dopo
quel punto vengono rifiutate. La perdita si propaga senza affidarsi al solo
flag continuation o a uno stato UNKNOWN.

Il controllo non usa lo stato transazionale per decidere l'ordine: un corpo
STRAIGHT_LINE validato o un witness F02 sincrono EMPTY può mantenere l'ordine
anche se il contesto restituito è UNKNOWN. Il caso positivo C06 ammette così
una chiamata successiva che eredita U, senza inventare P, scope riusciti o un
contesto attivo. C07, con corpo non vuoto NOT_ASSERTED, rifiuta la stessa
pretesa di seguito certo. Non sono introdotti meccanismi per ristabilire
arbitrariamente l'ordine dopo un segmento irrisolto.

Prefisso già dimostrato, chiusure degli scope e terminale delle P possedute sul
normale unwind condizionale rimangono validi. Sono controllati separatamente
dalle successive chiamate del corpo. Riferimenti: MR00 §2, §4 D4, §6 V4/V10;
standard v1, Bounded Resolution e invarianza del lifetime.

## Regressioni fornite e witness prima/dopo

Le attese sono letterali, derivate da MR00 e dalle premesse v1. Le fixture sono
materializzate senza importare build/compose/validate/render; il loader non
calcola gli oracoli con codice produttivo. Sorgenti/hash/span coerenti dichiarano
IR sintetici, senza affermare parsing JDK o comportamento Spring runtime.

| Finding / ruolo | Casi | Attesa e risultato finale |
|---|---|---|
| AOP, negativi R1 esatti | A01/A02/A03 = O27/O28/O29 mutati archiviati | REJECT: contraddizione AspectJ/proxy |
| AOP, positivo vicino | A04 | ACCEPT |
| AOP, incertezza weaving legittima | A05 | ACCEPT, weaving/advice UNKNOWN |
| AOP, informazioni comuni preservate | A06 | ACCEPT, ACTIVE/tx con identità parziale, ritorno P1 |
| AOP, legacy incerto / legacy contraddittorio | A07/A08 | ACCEPT / REJECT |
| Modalità UNKNOWN / mancato fallback positivo | A09/A10 | ACCEPT incerto / REJECT effetti positivi |
| Compatibilità originale v1 con evidenze | A11 | ACCEPT |
| Ramo APPLIED incompatibile con bypass PROXY certo / positivo vicino | A12/A13 | REJECT / ACCEPT con P1 conservata |
| Ordine, negativo R1 esatto | C01 | REJECT: figlio dopo UNRESOLVED_CALL |
| Ordine, positivo vicino | C02 | ACCEPT |
| Ordine, suffisso irrisolto legittimo | C03 | ACCEPT, prefisso e unwind conservati |
| Seconda chiamata irrisolta arbitraria | C04 | REJECT |
| Ordine, chiamata certa prima del suffisso | C05 | ACCEPT, precedente F2 e lifetime preservati |
| Contesto U con ordine giustificato | C06 | ACCEPT, nessuna nuova certezza fisica |
| Perdita di ordine del figlio propagata | C07 | REJECT |

Totale 20 IR: undici ACCEPT e nove REJECT. Il confronto esegue sia il validatore
iniziale preservato sia quello corretto sugli stessi input: otto false
accettazioni corrette (quattro R1 più quattro varianti mirate); undici positivi
preservati; A10 era già rifiutato. I nove negativi finali falliscono con
ValueError e diagnostica semantica pertinente, non per malformazioni accidentali.
Tutti gli input rimangono immutati durante la validazione.

## Verifiche eseguite

| Controllo | Esito corrente |
|---|---|
| Nuova suite AOP/ordine | PASS, 26 test: 20 IR e sei controlli di integrità/proprietà |
| Suite MR01 precedente | PASS, 64 test |
| T01/F01/F02/F03/factory precedenti | PASS, 16 + 16 + 21 + 19 + 23 |
| Totale locale | **185 test PASS, zero skipped**, inclusi tutti i 159 precedenti |
| Witness MR01-R1 esatti | Quattro REJECT contro quattro ACCEPT iniziali; due finding chiusi nell'implementazione |
| Nove HIGH R4 esatti | PASS del rifiuto atteso, 9/9 con cause semantiche pertinenti |
| Tre vecchi positivi R4 | Tutti REJECT e **LEGITIMATELY_REJECTED**: ASPECTJ globale con F1 proxy incompatibile; input/attese storici immutati |
| Oracoli MR00 | 44 oracoli + otto positivi T, incl. variante legacy: tutte le 53 attese confermate |
| Repository / profili | PASS, entrambi exit 0 |
| Ruff check / format --check | PASS sui percorsi interessati, nuova suite inclusa |
| PlantUML dedicato | PASS: A04/A05/A06/A13/C02/C03/C05/C06, otto sintassi + otto SVG + otto PNG |
| Ispezione PNG diretta | A05, C05, C06: weaving incerto, prefisso conservato, seguito con contesto U |
| Governance candidata | PASS strutturale, generated; trusted/registered/executable false; approval pending; nessuna attivazione |
| Whitespace / diff | PASS; patch incrementale verificato in reverse con --check |

Jar locale `/Applications/plantuml-1.2024.8.jar`, SHA-256 nel receipt, nessun
download. La suite mirata è collegata ai tre controlli già esistenti (workflow,
acceptance runner, validazione sintattica repository). Non è stata eseguita la
campagna zero-token generale. CI remota e runtime Spring restano NOT RUN.

## Perimetro, preservazione e rischi residui

Modificati soltanto quattro file iniziali: validatore e i tre collegamenti di
test. Aggiunti suite, fixture/README e i tre deliverable F01. I restanti 1.252
file iniziali conservano hash e mode; i diff dei quattro modificati sono
rispetto allo snapshot iniziale del working tree, preservando gli incrementi
T01/F01/F02/F03/MR01 già presenti. Nessun report, receipt o witness storico è
riscritto. Build AST invariato; renderer, composer, parser, CLI e candidata
immutati. Nessun file temporaneo di esecuzione aggiunto al repository.

Il patch copre esclusivamente codice, suite, fixture e collegamenti di questa
correzione rispetto al working tree iniziale, non rispetto al solo HEAD. Report
e receipt sono deliverable separati, esclusi dal patch insieme al patch stesso.

Il validatore controlla premesse fornite; non riparsa indipendentemente i sorgenti
né verifica weaving, driver o esecuzione reale. L'ordine resta dimostrato soltanto
nel sottoinsieme sincrono rappresentato; non sono qualificati percorsi di
eccezione, riprese di controllo non modellate, commit/rollback, risorse, lock o
deadlock. Il positivo C06 qualifica l'IR fornito, non una nuova capacità di
traversal del generatore. Review indipendente della correzione: NOT RUN.

Branch/HEAD/develop/indice invariati; nessun commit, merge, push, nuovo worktree,
modifica a Familiar, attivazione candidata o implementazione T02.
**Arresto alla consegna MR01-F01.**
