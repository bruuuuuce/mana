# MANA-TRANSACTION-01-T02-S02-I01-F02-R1

22 ottobre 2026. Verdetto **NEEDS_FIX**.

Le tre aspettative F01 residue sono **SUPERSEDED_EXPECTATION**, dimostrate
indipendentemente nel perimetro D00. Il quarto FAIL è
**BREAKING_COMPATIBILITY**: F02 rende obbligatoria una nuova rappresentazione
JSON mantenendo `mana.wait-dependency/v1`. Il validatore precedente respinge
gli output F02 e quello F02 respinge i report A/B/C precedenti, pur essendo
semanticamente equivalenti. Nessun consolidamento, commit o integrazione.

Baseline verificata: `develop`, HEAD
`9d3468101ccdcf40f680418955be17aec098c9e6`, tree
`d653a29de2823722b6753fcdf619410d4c5d8817`, indice senza modifiche staged.
Le tre modifiche tracked iniziali e tutti gli untracked preesistenti sono
conservati. Esito finale e manifest in
[risultati indipendenti](TRANSACTION-01-T02-S02-I01-F02-R1-results.json).

## Perimetro ed evidenza indipendente

Letti contratto D00, review/matrice F01-R1, rapporto/risultati F02; consultati
decisioni D01, standard v1, oracoli e runner pertinenti. Esaminati direttamente
motore, validatore e CLI. Non è stato ripetuto l'audit architetturale D00.

Il [riproduttore versionato della review](TRANSACTION-01-T02-S02-I01-F02-R1-checks.py)
ricostruisce i due moduli pre-F02 **in memoria**, invertendo i soli hunk della
patch F02 e verificando ogni riga di contesto e gli SHA-256 registrati prima
della correzione:

- Motore: `1d99e1df9894592c8ec7e90bbfd555aac786f70c79874f65ac6af99855abe7c1`.
- Validatore: `009d43bfa59c71612cc1168546b22f0a121b3168de1a4fa9b39878012caa3fc9`.

La riproiezione pre-F02 riproduce esattamente i tre JSON A/B/C preservati.
Non sono state applicate patch al checkout. Il validatore storico usa il
proprio motore ricostruito, senza sostituire i moduli correnti.

## Disposizione dei tre FAIL F01

La suite storica è stata eseguita immutata: 12 PASS e 3 FAIL, exit 1.
La classificazione riguarda le asserzioni fallite, non cancella le ulteriori
guardie presenti nei medesimi metodi.

| FAIL storico | Aspettativa storica e comportamento F02 riprodotto | Disposizione |
|---|---|---|
| Test 11, `missing_pending_and_premise_dependency` | B senza pending: atteso UNKNOWN; restituito NO_CYCLE_IN_MODELED_SCENARIO | SUPERSEDED_EXPECTATION |
| Test 12, `one_incomplete_cut_blocks_global_negative` | B con secondo cut senza holdings: attesi secondo cut/global UNKNOWN; entrambi i cut e globale risultano NO_CYCLE_IN_MODELED_SCENARIO | SUPERSEDED_EXPECTATION |
| Test 15, `frontier_and_same_P_cut_do_not_use_identity_fallback` | REQUIRED/NESTED con cut senza holdings: atteso UNKNOWN; restituito NO_CYCLE_IN_MODELED_SCENARIO. La frontiera irrisolta conserva UNKNOWN | SUPERSEDED_EXPECTATION |

Per i due casi B, dai soli input sorgente risultano a1=4, a2=5, b1=4,
b2=5, prefissi a=5/b=4. a1 è l'unica acquisizione potenzialmente precedente
al proprio cut; b non ha operazioni pregresse. Considerando ogni operazione
alla frontiera come possibile richiedente, anche quando pending è vuoto,
e ignorando tutte le restrizioni W2–W5, l'unico arco DB possibile è
`b/P1 → a/P1`. Non ci sono chiamate applicative attive fra P distinte.
Entrambe le alternative `{}` e `{b→a}` sono acicliche. Nel caso a due cut
vale la stessa sovrastima per ciascuno e per la loro unione.

Per REQUIRED, O1=6 e O2/cut=9; per NESTED, O1=7 e O2/cut=11.
L'unica P1 è viva in entrambi i cut e i due frame condividono quella P.
La sola alternativa inter-P è il grafo vuoto: W1 vieta endpoint uguali,
SP1 non costituisce un'altra P. Le chiamate tra frame sulla stessa P
non sono self-loop DB. La prova non richiede holdings.

Il nuovo controllo legge **tutto l'inventario delle osservazioni**, verifica
selezione completa, identità, eventi di lifetime/sospensione, frontiere e
stack dei frame. Enumera tutti i sottoinsiemi degli archi della sovrastima
e verifica la raggiungibilità con un algoritmo distinto dai due algoritmi
del prodotto. Non legge il certificato per decidere l'aspettativa.
Ogni grafo ammissibile è un sottoinsieme di questa sovrastima, quindi nessuna
scelta di W2–W5 può introdurre un ciclo nei cut esaminati.

D00 §§4–6/W1/W6 e O-B01/O-D01/O-E01 giustificano questi negativi limitati:
W4 serve per provare l'esistenza dell'attesa, ma non è indispensabile alla
dimostrazione di esclusione descritta. UNKNOWN sui lock e coverage INCOMPLETE
restano esposti. Nessun caso dei tre costituisce VALID_REGRESSION o
CONTRACT_AMBIGUITY.

Le sostituzioni versionate per le attese attive sono F02-02 per le quattro
varianti, F02-13 per le riduzioni REQUIRED/NESTED e il runner di questa review
per l'enumerazione indipendente. F02-01 mantiene la frontiera UNKNOWN;
F02-15 mantiene il rifiuto delle acquisizioni/premesse dipendenti UNKNOWN
contenuto nel test 11. Gli oracoli, i runner e i risultati storici restano
immutati e i loro FAIL originali non sono rinominati PASS.

## Finding bloccante R1-JSON — incompatibilità bidirezionale v1

Il controllo I01-R1 `visual-json-mermaid-parity` fallisce dapprima su
`('A', 'wait-dependency.json')`: confronta tutti i byte rigenerati. Il test
non raggiunge B/C dopo quel primo assert. Questa review li ha verificati
separatamente e ha isolato le modifiche.

Per A/B/C, rimuovendo **in memoria** i soli nuovi campi
`assessment.exclusionProof` e `assessment.cuts[*].exclusionProof`, l'oggetto
F02 coincide interamente con il JSON precedente. I Mermaid restano identici.
Questo spiega il confronto storico, ma non dimostra compatibilità dei consumer.

| Report A/B/C | Validatore pre-F02 | Validatore F02 |
|---|---|---|
| JSON storico v1 | ACCEPT, tutti e tre | REJECT, tutti e tre |
| JSON F02 v1 | REJECT, tutti e tre | ACCEPT, tutti e tre |

La CLI F02 `--validate` sui tre report storici restituisce exit 2.
Per A/C il motivo è `S02 derivation/reference projection mismatch`.
Per B è `NO_CYCLE requires a source exclusion proof; missing W4 cannot be self-certified`.
L'attesa B resta semanticamente corretta e il vecchio motore la rigenera:
il rifiuto non elimina un vecchio falso negativo A/C senza holdings.

La causa è precisa:

1. Il producer inserisce sempre i nuovi campi nel JSON del cut e
   dell'assessment, con oggetto oppure null; versione e status restano invariati.
2. `validate_negative_assessments` richiede un dict di prova anche per il
   vecchio B evidence-complete. Il requisito è nuovo sotto la stessa v1.
3. Il confronto finale `report == build_report(...)` rende i campi di fatto
   obbligatori anche per gli esiti non negativi, nei quali sono null.
4. Il consumer pre-F02 fa lo stesso confronto con la propria rappresentazione
   precedente e respinge gli output nuovi. Il rifiuto è stato riprodotto con
   il codice storico, non inferito da uno schema ipotetico.

Riferimenti al codice corrente: `wait_dependencies.py:1415` e `:1537`
(campi pubblicati), `wait_validation.py:243` (certificato richiesto),
`:589` (riproiezione esatta), `mana-wait-dependencies.py:274` (lettura del
report esistente). Nessun test storico viene riscritto per aggirare questi gate.

Anche A senza holdings resta UNKNOWN in entrambi i motori e viene accettato
dal rispettivo validatore, ma fallisce la validazione incrociata. Qui F02 cambia
inoltre `coverage.candidateComparisons` da 9 a 17 per il tentativo strutturale:
è una variazione del contatore, non una promozione semantica. Rimuovendo i soli
campi null da un UNKNOWN appena generato, il validatore corrente lo rifiuta
ancora per differenza di proiezione.

### Envelope, versione e serializzazione

- Report: `mana.wait-dependency/v1`, status `CONDITIONAL_STATIC_SCENARIO`.
  L'envelope chiuso rimane quello documentato: schema, status, inputs, scenario,
  operations, claims, waitCandidates, databaseGraph, applicationGraph,
  crossLayerRelations, unknowns, limits, coverage, assessment. Nessuna chiave
  top-level viene aggiunta da F02; la rottura è nei record nested e nel consumer.
- Sidecar: `mana.wait-scenario/v1`, oggetto invariato prima/dopo. Tutte le sue
  chiavi documentate sono obbligatorie; UNKNOWN/assenza sono rappresentati da
  null/liste vuote nei campi ammessi, non da chiavi aggiunte o omesse. Nessuna
  nuova versione di sidecar o di regola pubblica è stata dichiarata da F02.
- `exclusionProof` è descritto come additivo da F02, ma il validatore non lo
  tratta come opzionale. Per risultati negativi la prova è un oggetto; per
  risultati non negativi e aggregazione per cut è null. Senza cut, il negativo
  per identità singola porta la prova nell'assessment globale.
- JSON corretto sintatticamente, senza NaN, con escaping ASCII. Il digest T01
  conserva la codifica dichiarata `sorted-compact-ascii-json/v1`. La CLI usa
  JSON indentato con newline finale, distinto dalla codifica canonica dei digest.
  Build ripetute e CLI in processi con PYTHONHASHSEED=1/97 producono byte
  identici per ciascuno dei tre stessi input. Nessun SERIALIZATION_DEFECT
  osservato nei controlli richiesti.
- UNKNOWN è un risultato rappresentato esplicitamente; NO_CYCLE resta limitato
  al modello e può accompagnarsi a coverage INCOMPLETE e dati lock UNKNOWN.
  I certificati non sono nuovi archi DB qualificati. La semantica di queste
  rappresentazioni è valida; la loro accettazione tra generazioni è rotta.

Classificazione definitiva del quarto FAIL: **BREAKING_COMPATIBILITY**.
Non è HISTORICAL_FIXTURE_SUPERSEDED: il report B storico è un controesempio
valido del contratto v1 e non è stato dimostrato non applicabile. Non è
CONTRACT_DECISION_REQUIRED per decidere se il difetto esiste. Un'eventuale
scelta di rompere intenzionalmente v1 richiederebbe invece una decisione
esplicita, assente da questo mandato.

### Controesempio minimo ripetibile

Dal repository, senza generare o riscrivere alcun artifact:

```sh
python3 scripts/mana-wait-dependencies.py \
  --timeline ta=docs/examples/transaction-01-t02-s02/B/inputs/ta.json \
  --timeline tb=docs/examples/transaction-01-t02-s02/B/inputs/tb.json \
  --scenario docs/examples/transaction-01-t02-s02/B/scenario.json \
  --validate docs/examples/transaction-01-t02-s02/B/wait-dependency.json
```

Atteso per compatibilità v1: VALIDATED, exit 0. Osservato: REJECTED_INPUT,
coverage INCOMPLETE, published false, exit 2; manca il nuovo certificato.
Il runner della review riproduce anche l'accettazione pre-F02 e termina
exit 1 finché persiste la rottura.

Correzione minima richiesta, **non implementata durante la review**:
preservare la rappresentazione pubblica v1 e ricostruire internamente le prove
da fonti validate, senza imporre i nuovi campi ai report v1 né ai vecchi consumer.
Il controllo indipendente W1–W8/strutturale deve continuare a rifiutare i falsi
negativi storici A/C senza holdings; non basta rimuovere il gate di sicurezza
o ignorare arbitrariamente differenze JSON. Se si vuole pubblicare un formato
diverso, serve prima la decisione esplicita su schema/versione e migrazione.
Non è stata prodotta una patch di codice, rispettando lo stop alla regressione.

## Verifica semantica e regressioni pertinenti

Confermate le quattro UNKNOWN: A senza holdings, C senza holdings, A con
una holding omessa, prefisso oltre UNRESOLVED_CALL. In A l'arco non qualificato
può chiudere un ciclo; in C può completare il circuito applicativo/DB.
W4 rimane obbligatoria quando necessaria alla conclusione. Un grafo DB vuoto
o parziale aciclico non viene automaticamente considerato completo.

Il validatore ricostruisce il certificato dalle fonti e confronta inventario,
prefissi e sovrastima prima della riproiezione. I controlli con producer simulato
che ripete una prova errata respingono archi omessi, prove cicliche e coverage
falsamente completa. La verifica indipendente usa eliminazione topologica,
mentre il motore usa DFS; il runner di review usa raggiungibilità.
Condivide comunque col producer parser, inventario e altre primitive: questo
non è una seconda implementazione integralmente indipendente del sistema.

DB inner→outer e app caller→callee restano distinti; REQUIRED/NESTED non
introducono P aggiuntive; le direzioni su cut incompatibili non diventano un
ciclo fattibile. Nessun risultato statico diventa DEADLOCK_CONFIRMED/OBSERVED.
globalRiskAbsence resta NOT_ASSERTED; runtime resta NOT_RUN.

| Verifica rieseguita | Risultato |
|---|---|
| F02 | PASS, 24/24, exit 0 |
| I01 | PASS, 22/22, exit 0 |
| Oracoli statici nel primo test I01 | PASS, 31/31: 30 A–I e J05 |
| F01 immutata | 12 PASS / 3 FAIL, exit 1; classificati sopra |
| I01-R1 immutato | 26 PASS / 1 FAIL, exit 1; compatibilità JSON bloccante |
| Controesempi originali I01-R1 A/C | PASS, 2/2, exit 0 |
| F01-R1 checks immutati | PASS, 19/19, exit 0 |
| F01-R1 controesempi minimi REQUIRED/NESTED | PASS, 2/2, exit 0 |
| Review corrente, quattro esclusioni | PASS; tutte le alternative della sovrastima acicliche |
| Review corrente, consumer v1 | FAIL; runner exit 1 per incompatibilità bidirezionale |
| Validazione repository | PASS, exit 0; output integrale nel receipt |
| Ruff check e format --check | PASS, exit 0, 12 file Python pertinenti |
| J01–J04 | NOT_RUN |

I conteggi si sovrappongono; non sono sommati come casi indipendenti unici.
Nessuna nuova campagna QA generale, prova provider/CI/deployment o adapter Oracle.

## Preservazione e stato Git finale

Inventariati prima del lavoro 1.372 file tracked/untracked non ignorati,
con SHA-256, dimensione e mode. Verificati separatamente gli 11 percorsi locali
e i sei materiali protetti anche rispetto al receipt F02. Il manifest e il
confronto conclusivo sono inclusi nei risultati correnti. I file preesistenti,
il codice del prodotto, D00, golden, fixture e test storici restano invariati.

Aggiunti soltanto rapporto, risultati JSON e riproduttore della review.
Familiar, T01/T02-S01 canonici, skill e superfici di attivazione non modificati.

HEAD e branch finali coincidono con la baseline; tree, refs, indice e lista
worktree invariati. SHA di integrazione: **nessuno**. Revisione completa del
diff per consolidamento, staging, firma, branch feature e ff-only: **NOT_RUN**
per il finding JSON. Lo stato non è READY_FOR_INTEGRATION: il blocco precede
qualsiasi tentativo di cambio branch. Nessun push, reset, stash, clean o nuovo
worktree. Arresto alla consegna NEEDS_FIX, senza remediation automatica.
