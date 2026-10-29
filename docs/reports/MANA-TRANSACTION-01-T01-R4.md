# MANA-TRANSACTION-01-T01-R4 — Semantic Closure & Conditional Integration

Data: 20 ottobre 2026. Verdetto: **NEEDS_MODEL_REVISION**.

La review indipendente conferma la chiusura dei controesempi R1/R2/R3 ma trova
un nuovo finding HIGH nel validatore. Per i frame APPLIED ordinari manca un
contratto completo che colleghi propagation, capability, effetti e stato di
ritorno. Sono accettati savepoint/sospensioni non supportati, effetti fisici
incompatibili con NESTED/REQUIRES_NEW e INACTIVE dopo una sola chiusura logica
con P1 ancora viva. I 95 test esistenti passano, senza chiudere questa lacuna.

**Integrazione non eseguita. Nessuna correzione F04 implementata.** Occorre una
revisione delimitata del contratto delle transizioni; non è dimostrata la
necessità di sostituire lo schema v1. T02 rimane fuori perimetro.

[Receipt R4](MANA-TRANSACTION-01-T01-R4-results.json): review indipendente,
matrici, payload integrali costruiti a mano e completi, script portabili,
controesempi, replay del coordinatore, log/exit code, rendering e manifest Git.

## Indipendenza e metodo

Il revisore `/root/r4_independent_review` è stato avviato con `fork_turns: none`,
senza cronologia implementativa F03, su mandato della review indipendente finale.
Ha letto gli input richiesti e direttamente motore, validatore, alternative,
renderer, fixture e oracoli. Ha operato in sola lettura sul repository, scrivendo
le proprie prove solo in `/private/tmp/mana-t01-r4-review-t3u0hAmd`.

Le aspettative sono esplicite e indipendenti dall'output del motore/validatore:
regole dello standard, sorgenti delle fixture e regole primarie
[Spring, Transaction Propagation](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html),
con la distinzione [proxy/AspectJ](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html).
I payload manuali sono IR sintetici dichiarati, con evidenza Review.java sintetica;
non sono spacciati per fatti prodotti dal parser JDK. I controesempi sono confermati
anche su IR completi già consegnati, con envelope/provenienza/eventi conservati.

Il coordinatore ha verificato baseline, preservazione, 95 regressioni,
repository/profili/Ruff e candidata, ispezionato le prove e ripetuto tutti i 27
payload del revisore. Risultati coincidenti: 18 comportamenti attesi e nove witness
negativi accettati, raggruppati in un solo finding architetturale. Il verdetto
semantico resta quello del revisore indipendente, non una sostituzione della review
con l'auto-valutazione dell'autore F03.

## R4-F01 — HIGH: contratto incompleto delle transizioni APPLIED

Posizioni attuali:

- `model.py:673-685`: a FRAME_EXIT la verifica di ripristino è condizionata a
  physicalId non nullo nell'afterState; una falsa certezza INACTIVE la evita.
- `model.py:773-788`: per APPLIED ordinario non viene verificata la relazione
  propagation/capability/effetti; `validate_composition` interviene solo col witness.
- `model.py:814-832`: savepoint/sospensioni sono collegati alle identità di ingresso
  e durante, senza verificare la compatibilità con propagation e capability.
- `alternatives.py:177-236`: tali guardie semantiche esistono invece per APPLIED
  all'interno delle alternative UNKNOWN. Ne risulta una validazione asimmetrica.

### Controesempio minimo completo

Caricare `docs/examples/transaction-01-t01/nested/transaction-model.json`, che
valida correttamente. Modificare in memoria soltanto:

```python
model["context"]["managerCapabilities"]["tx"]["savepoints"] = False
model["managers"][0]["capabilities"]["savepoints"] = False
```

Entrambe le dichiarazioni concordano: savepoint non supportati. Tutto il resto,
compresi provenance, L1/L2, P1 e SP1, rimane invariato. F2 APPLIED/NESTED dichiara:

| Punto | Stato / evento |
|---|---|
| Ingresso F2 | P1 corrente, manager tx, scope esterno L1 aperto |
| Evento 5 | LOGICAL_BEGIN L2 |
| Evento 6 | SAVEPOINT_CREATE SP1 P1 |
| Evento 7 | SAVEPOINT_RELEASE_CONDITIONAL SP1 P1 |
| Evento 8 | LOGICAL_END L2 |
| Evento 9 | FRAME_EXIT F2, after ACTIVE/P1 |
| Capability nota | savepoints false, sia scenario sia manager |
| Oracolo indipendente | Rifiutare SP1 concreto incompatibile con capability |
| Risultato effettivo | `validate_model(model) == True` |

Il replay minimo del revisore è conservato come testo nel receipt R4. Può essere
estratto ed eseguito dalla root senza dipendere dalla directory temporanea:

```sh
python3 - <<'PY'
import json
from pathlib import Path
receipt = json.loads(Path('docs/reports/MANA-TRANSACTION-01-T01-R4-results.json').read_text())
exec(compile(receipt['proofScripts']['minimal-replay.py'], 'minimal-replay.py', 'exec'))
PY
```

Output: expectedAccepted false, actualAccepted true, defectReproduced true.
Exit 0 significa che il difetto è riprodotto, **non** PASS semantico. Nessun
modello del repository viene modificato. Il coordinatore ha ripetuto questo
replay e quello dei payload completi/manuali.

### Varianti della stessa lacuna

| Payload indipendente | Atteso | Osservato |
|---|---|---|
| NESTED con savepoints false/null | Rifiuto del savepoint concreto | Accettato |
| REQUIRES_NEW con suspend false | Rifiuto della sospensione concreta | Accettato |
| REQUIRES_NEW dichiarato, effetti NESTED/SP1 sulla stessa P1 | Rifiuto | Accettato |
| NESTED dichiarato, P1 sospesa e P2 indipendente | Rifiuto | Accettato |
| REQUIRED condiviso, solo LOGICAL_END L2, after NO_TRANSACTION | Rifiuto: P1/L1 ancora vive, P1 da conservare | Accettato |

L'ultima variante è riprodotta sia manualmente con effectiveContext.after INACTIVE
coerente, sia sull'IR REQUIRED completo storico che non ha i campi additivi F01.
Non dipende quindi dall'omissione o incoerenza di effectiveContext. I primi due
casi sono confermati anche sui modelli completi consegnati, modificando solo le
due capability concordanti. Le nove accettazioni sono witness dello stesso
finding; non sono nove difetti architetturali indipendenti.

L'esistenza temporale di P1 non basta a rendere possibile uno SP1 con capability
false. Analogamente, referenze e durate ordinate non rendono equivalenti NESTED e
REQUIRES_NEW. La falsa certezza INACTIVE mostra che controllare solo riferimenti
fisici non nulli lascia scoperta una parte della transizione.

### Decisione architetturale proposta, senza implementazione

Definire una relazione semantica delimitata per i confini ordinari APPLIED che
copra tutti gli stati dichiarati, inclusi NO_TRANSACTION e UNKNOWN, collegandoli
allo stato precedente, propagation, manager identificato, capability, scope,
nuove P, savepoint, sospensione e normale ripristino. Verificarne la coerenza con
le alternative F02, senza convertire effetti di ramo in entità incondizionate.
Mantenere oracoli indipendenti dal generatore e test negativi su payload forniti.

Componenti interessati: contratto dello standard, validatore `model.py`, coerenza
con `alternatives.py`, fixture/oracoli della superficie APPLIED. Nei controlli CLI
mirati il generatore risponde correttamente alle capability mancanti/false con
UNKNOWN e senza SP/sospensione: non è provato un analogo difetto di generazione.
Il renderer resta un consumatore dell'IR validato; la correttezza grafica non
rende valida una combinazione semantica impossibile.

I campi v1 rappresentano già i due lati della contraddizione. Non è necessaria,
sulla base di queste prove, una nuova API, un framework universale di stati o un
monitor runtime. Non è attribuita questa lacuna a uno specifico patch storico.
Nessuna proposta è stata applicata e non viene avviato F04.

## Contratto compatto delle transizioni

La matrice descrive le regole attese, non certifica che il validatore le imponga
tutte. P indica l'identità corrente al confine; il successivo è riferito agli
eventi indicati o al normale unwind. FRAME_ENTER/EXIT delimitano i metodi e non
sono autonomamente inizio/fine di una transazione fisica.

| Precedente | Advice / configurazione | Eventi esistenti | Scope | P corrente | Sospesa | Successivo | Condizioni |
|---|---|---|---|---|---|---|---|
| NO_TRANSACTION | APPLIED REQUIRED; NEW/NESTED senza P precedente seguono apertura fisica | PHYSICAL_BEGIN P1; LOGICAL_BEGIN L1 | L1 | P1 | Nessuna | ACTIVE/P1 | Manager identificato, scenario esplicito; nessun savepoint fittizio |
| ACTIVE/P1 | APPLIED REQUIRED | LOGICAL_BEGIN L2; LOGICAL_END L2 | L2 condiviso | P1 | Nessuna | ACTIVE/P1 | Stesso manager; solo scope chiuso |
| ACTIVE/P1 | APPLIED NESTED | LOGICAL_BEGIN L2; SAVEPOINT_CREATE SP1; SAVEPOINT_RELEASE_CONDITIONAL SP1; LOGICAL_END L2 | L2 su P1 | P1 | Nessuna | ACTIVE/P1 | savepoints true; nessuna P2 |
| ACTIVE/P1 | APPLIED REQUIRES_NEW | SUSPEND S1; PHYSICAL_BEGIN P2; LOGICAL_BEGIN/END L2; PHYSICAL_END_OUTCOME_UNKNOWN P2; RESUME_CONDITIONAL S1 | L2 su P2 | P2 poi P1 | P1 durante P2 | ACTIVE/P1 | suspend true; P2 distinta e terminata prima di resume |
| P1 o assenza | BYPASSED / non annotato | FRAME_ENTER; FRAME_EXIT | Nessun nuovo L | Ereditata | Nessuna nuova | Contesto ereditato | Regole PROXY/direct pertinenti; non presumere bypass AspectJ |
| ACTIVE/P1 | UNKNOWN REQUIRED | FRAME_ENTER; FRAME_EXIT | IF_APPLIED | P1 comune | Nessuna | ACTIVE/P1 a corpo vuoto | Advice-only uncertainty; APPLIED e BYPASSED concordano |
| ACTIVE/P1 | UNKNOWN NESTED | FRAME_ENTER; FRAME_EXIT | L e SP IF_APPLIED | P1 comune | Nessuna | ACTIVE/P1 a corpo vuoto | savepoints true; nessun SP incondizionato |
| ACTIVE/P1 | UNKNOWN REQUIRES_NEW | FRAME_ENTER; FRAME_EXIT | IF_APPLIED | ACTIVE, identità null | P1 IF_APPLIED | ACTIVE/P1 a corpo vuoto | suspend true; identità fresca solo nel ramo APPLIED |
| ACTIVE/P1 posseduta | APPLIED termine del proprietario | LOGICAL_END L1; PHYSICAL_END_OUTCOME_UNKNOWN P1; FRAME_EXIT | L1 chiuso | Nessuna | Nessuna | NO_TRANSACTION | Nessun riferimento attivo successivo a P1 terminata |
| Capability non true o confine irrisolto | APPLIED/UNKNOWN secondo causa | Nessun effetto concreto non giustificato | Incerto | UNKNOWN dove necessario | Non inventata | UNKNOWN dove necessario | Conservare solo proprietà dimostrabili; R4-F01 viola il controllo APPLIED |

## Matrice degli invarianti

| Invariante | Esito circoscritto |
|---|---|
| Lifetime / identità dopo termine | PASS: tre R3 originali e negativi manuali rifiutati; P1 non riciclata |
| Scope logico condiviso | Positivo legittimo PASS; **FAIL validatore** sulla falsa uscita INACTIVE |
| Sospensione e ripristino | Ordine temporale PASS, resume anticipato rifiutato; **FAIL capability/propagation** |
| Savepoint e P condivisa | Generati legittimi PASS; **FAIL capability/propagation** nel validatore |
| Proprietà comuni alle alternative | PASS sui tre witness manuali UNKNOWN e casi sorgente; non-common P1 e SP condizionale impossibile rifiutati |
| Identità distinte NESTED/REQUIRES_NEW | Positivi generati PASS; **FAIL validatore** sugli effetti scambiati |
| Renderer | PASS sui sette input coerenti mirati; non è un oracolo semantico per IR arbitrari |

Commit e rollback fisici condividono nel v1 l'unico terminale
PHYSICAL_END_OUTCOME_UNKNOWN: il lifetime termina in entrambi gli esiti possibili,
che restano UNKNOWN. Non esistono eventi distinti di commit/rollback o rollback
al savepoint da inventare in questa review. Rilascio SP1 non termina P1. La
computazione dei percorsi di eccezione/rollback rimane un limite già dichiarato,
non un nuovo requisito runtime né la causa del verdetto negativo.

## Regressioni, replay e rendering

| Verifica corrente | Esito |
|---|---|
| T01 / F01 / F02 / F03 / factory | PASS: 16 + 16 + 21 + 19 + 23 = 95, zero skipped, exit 0 |
| Repository / profili | PASS, entrambi exit 0 |
| Ruff check / format --check | PASS, exit 0 |
| git diff --check | PASS, exit 0 |
| Validazione candidata | PASS strutturale, exit 0; pending e non eseguibile |
| R1 sorgente/contesto esatti | PASS corrente: ASPECTJ senza weaving resta UNKNOWN, nessun falso bypass |
| R2 sorgente/contesto esatti | PASS corrente: UNKNOWN REQUIRED conserva ACTIVE/P1, ritorno condizionale P1 |
| R3 tre IR negativi archiviati | PASS corrente: tutti rifiutati per P terminata |
| Payload indipendenti del revisore | 27 controlli: 18 attese soddisfatte, nove witness **FAIL semantico** |
| Replay coordinatore | Stessi 27 risultati; minimo e cinque varianti ripetuti separatamente |
| PlantUML pertinente | PASS: sette sintassi, sette SVG, sette PNG; cinque ispezioni visive |

I rapporti e verdetti storici non sono riscritti. I replay R1/R2 confrontano gli
hash delle sorgenti e conservano il contesto originale; R3 usa i payload esatti.
L'inventario finale conferma che i progetti analizzati e tutti i file originali
sono rimasti immutati. La candidata è generated, trusted/registered/executable
false, approval pending; nessuna attivazione.

F02 aveva 25 diagrammi: otto F01, otto F02, otto T01 storici e R2 esatto.
F03 ne aveva 17: otto T01 storici, otto selezioni R3/F02 e R3 rigenerato.
La differenza numerica deriva dall'omissione degli otto F01 autonomi; inoltre la
selezione F03 sostituisce nested_false/new_unknown con following/proxy_bypass.
Questo spiega i conteggi, senza dichiarare equivalenti le coperture o appena
rieseguiti i casi omessi. Non è automaticamente una regressione del renderer.

R4 sceglie sette diagrammi pertinenti: R1/R2 esatti, REQUIRED/NESTED/REQUIRES_NEW
noti, NESTED/REQUIRES_NEW con advice UNKNOWN. Il revisore ha confrontato note/eventi,
identità, IF_ADVICE_APPLIED, savepoint e premesse, ispezionando cinque PNG. Nessuna
etichetta di attività P1 oltre il suo terminale; END P2 precede RESUME P1. I gruppi
sono regioni dei metodi, come esplicitato in legenda; le note BEGIN/END definiscono
le durate. Nessun nuovo difetto distinto di renderer trovato su questi input.

Jar locale `/Applications/plantuml-1.2024.8.jar`, SHA-256
`b88519d2f37c089a470ee7044ec011a72d130e70a61f7fcaa424179f1c1f4641`.
Warning CodeCache nel PNG, non fatale: sette file prodotti, exit 0; log conservato.
Nessun download o ampliamento generale della matrice.

## Git, preservazione e mancata integrazione

Branch iniziale/finale `feature/mana-transaction-01`.
HEAD e develop locale invariati alla baseline originale
`378243883adb101a7a41feef71e2a66b76e7f508`.
Tree HEAD `d5b7ae2cf2625ab6a788eb31f5fc62cbe0d39ee4`. Indice vuoto.

I 1.225 file iniziali tracked/untracked non ignorati conservano SHA-256 e mode;
nessuna rimozione o modifica. Aggiunti solo rapporto R4 e receipt R4. Input F03,
T01/F01/F02, candidate, fixture, proposta T02 e tutte le modifiche preesistenti
sono preservati. Il receipt include manifest prima/dopo e stato Git completo.

È stato inventariato in lettura il diff preesistente: nove tracked modificati e
72 untracked prima di R4; la proposta T02 è identificata come preesistente ed
estranea alla selezione d'integrazione. Nessuna selezione/staging è stata eseguita.
Questo inventario non è una qualifica segreti o un'approvazione del diff.

SEMANTIC_REVIEW_PASS non ottenuto: selezione finale/segreti, commit atomico
firmato, verifica firma/parent/nuovo SHA/tree, verifica finale writer/clean tree,
checkout develop, merge ff-only e ricevuta d'integrazione sono **NOT RUN**.
Commit SHA nuovo: nessuno. Nessun tentativo di commit o firma, merge o push;
nessun nuovo worktree, intervento su Familiar/REL-01/A o modifica T02.

## Limiti residui per T02 e arresto

Il validatore non può ancora essere assunto come certificazione semantica del
percorso o delle capability prima di fondarvi risorse, ownership o lock. Prima
serve revisionare il contratto APPLIED e ripetere la review pertinente, preservando
le semantiche F02/F03 corrette. Non viene avviata automaticamente una remediation.

Identità e outcome runtime, weaving, driver, connessioni, lock, concorrenza e
deadlock restano fuori dalla prova statica. Runtime Java/Spring, CI remota e altre
piattaforme sono NOT RUN, senza renderli requisiti aggiuntivi di questa review.
T02 resta non implementato. L'attività R4 termina con questa consegna.
