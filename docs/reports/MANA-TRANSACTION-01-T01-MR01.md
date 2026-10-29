# MANA-TRANSACTION-01-T01-MR01 — Transition Contract Implementation

Data: 20 ottobre 2026. Verdetto: **IMPLEMENTED_READY_FOR_REVIEW**.

Implementato il contratto MR00 nel validatore v1; distinti nel renderer i marcatori
D2 dagli scope eseguiti. **44/44 oracoli e 24/24 transizioni verificati**, 64 test
MR01 e tutte le 95 regressioni precedenti PASS, zero skipped. I nove witness HIGH
di R4 erano accettati prima della correzione e sono ora rifiutati. Review e
integrazione non avviate; questo verdetto non costituisce review indipendente.

Il replay supplementare dei 27 payload archiviati R4 coincide con le vecchie
aspettative in **24/27 casi**. Tre vecchi positivi sintetici hanno premesse AOP
incompatibili con MR00 e sono ora rifiutati: la classificazione è esplicita sotto,
senza modificare receipt, aspettative storiche o oracoli MR00.

Deliverable: [risultati completi](MANA-TRANSACTION-01-T01-MR01-results.json),
[copertura](MANA-TRANSACTION-01-T01-MR01-coverage.csv),
[diff incrementale MR01](MANA-TRANSACTION-01-T01-MR01.patch).
Fonti normative immutate: [contratto MR00](MANA-TRANSACTION-01-T01-MR00-contract.md),
[matrice MR00](MANA-TRANSACTION-01-T01-MR00-transitions.csv) e relativo piano.

## Baseline e perimetro

Branch iniziale/finale `feature/mana-transaction-01`; HEAD invariato:
`378243883adb101a7a41feef71e2a66b76e7f508`. Indice invariato e vuoto. Il diff
MR01 è relativo al **working tree non committato iniziale**, non al solo HEAD:
conserva le modifiche T01/F01/F02/F03/MR00 preesistenti.

L'inventario iniziale contiene 1.230 file tracked/untracked non ignorati, con
hash e mode nel receipt. Modificati soltanto sei file esistenti: validatore,
renderer, standard e tre punti di collegamento della suite ai controlli già
esistenti. I restanti 1.224 file sono invariati. Aggiunti suite MR01, due file di
fixture e i quattro deliverable. Nessun report/receipt storico o documento MR00
riscritto, nessun test precedente alterato. Le cache ignorate dei controlli Python
non sono deliverable.

## Fase 1 — Corrispondenza e lacune

Letti integralmente i sei input normativi richiesti, incluso il receipt R4
caricato per intero; esaminati direttamente modello, generatore, composizione,
validatore, renderer e regressioni. La matrice di copertura associa singolarmente
T01–T24, O01–O44 e V1–V12 ai test e all'evidenza corrente.

| Vincoli | Prima di MR01 | Intervento |
|---|---|---|
| V1 | Referenze, nesting e coppie principali presenti; controlli incompleti su kind di stato, eventi, root e hash del chiamante | Rafforzati senza campi nuovi |
| V2 | Capability verificate soprattutto nel witness F02 | Concordanza globale contesto/manager e uso coerente nei frame ordinari |
| V3 | Mancava relazione completa APPLIED propagation/capability/effetti | Insieme chiuso, cardinalità, effetti obbligatori/vietati per frame |
| V4 | F03 verificava gli istanti fisici principali | Verificati anche prefisso completo e posizione di corpo/figli rispetto alle chiusure |
| V5–V9 | Lifetime F03 già operativo, inclusi terminali e ripristino | Conservato; collegato all'ownership e agli effetti della transizione; rafforzate identità evento SP e fine del proprietario |
| V10 | Il ripristino era controllato solo con after.physicalId non nullo | Verifica anche NO_TRANSACTION; UNKNOWN soltanto con continuazione motivata |
| V11 | Intersezione e rami F02 già verificati | Conservati; vietata esecuzione del corpo/figli materializzata nel witness |
| V12 | Identità simbolica/runtime UNKNOWN già controllate | Verificati anche outcome/certainty fisici e assenza di prova runtime weaving |

T01–T06 sono i sei confini APPLIED riusciti; T07–T12 i confini irrisolti;
T13–T15 il bypass; T16–T22 le alternative F02; T23–T24 le continuazioni irrisolte.
Gli oracoli originali coprivano positivamente 16 transizioni; otto payload
positivi supplementari verificano T08/T09/T10/T11/T12/T20/T21/T23. Per T23 il frame
osservato è il chiamante ordinario F1 di un figlio con corpo non attraversato.

**Schema v1 sufficiente, confermato.** Ownership, lifetime, contesto corrente,
sospensioni, savepoint e incertezza sono rappresentabili con gli array, gli stati,
gli eventi e il witness esistenti. Nessuna modifica di schema, input, formato
pubblico o propagation; nessun controesempio che richieda un nuovo schema.

## Fasi 2–4 — Implementazione e indipendenza

`tests/fixtures/transaction-transition-contract/cases.json` contiene 44 IR completi
con ID, esiti e riferimenti normativi invariati. Ogni test Oxx confronta anche
l'aspettativa con il CSV MR00. Le fixture hanno envelope, sorgenti sintetiche
esplicite, span del chiamante, hash e contesto coerenti; non sono presentate come
output del parser JDK né come prova che un advice sia stato eseguito. Le sorgenti
sintetiche sono state precisate per rendere leggibili le premesse; nessun esito
manuale è stato modificato per ottenere il verde.

I payload e le attese sono stati costruiti senza `build`, `compose`,
`applied_boundary` o renderer. Prima della correzione sono state conservate le
accettazioni dei nove HIGH esatti R4 e l'esecuzione iniziale dei 44 casi.
Il receipt distingue questi risultati iniziali da quelli finali. I negativi
richiedono ValueError con diagnostica della contraddizione prevista: errori di
formato accidentali non valgono PASS. O13 esercita anche l'IR legacy senza F01.

Il validatore usa un controllo locale delle transizioni e il replay lifetime
esistente, senza richiamare il generatore per decidere la validità. La selezione
manager è una piccola primitiva condivisa; l'attesa delle alternative resta
controllata direttamente dal validatore F02. Nessun secondo modello transazionale
o framework generale introdotto.

Il corpo del motore `build` è invariato, come confermato dal confronto AST con lo
snapshot iniziale. Anche CLI, parser e `alternatives.py` restano invariati: non è
emerso un caso che richiedesse nuove regole di generazione.

- **D1:** capability come premesse condizionali effettive; copie concordi;
  false/null non abilitano SP o sospensione che richiedono true.
- **D2:** L UNKNOWN/null ammesso soltanto come marcatore tentato/irrisolto, senza
  effetti fisici certi. Il renderer usa UNRESOLVED_LOGICAL_MARKER e dichiara che
  esecuzione/effetti non sono stabiliti; mantiene separato il lifetime P1.
- **D3:** classificazione legacy da evidenze di modalità/crossing/configurazione
  e limiti registrati, mai dalla sola annotazione o dagli effetti proposti.
  Il renderer usa la stessa classificazione; i casi non affidabili non certificano
  un confine positivo.
- **D4:** after UNKNOWN richiede limite source-linked, chiamata irrisolta o
  ritorno irrisolto di un figlio, coerenti con la continuazione. Il solo flag
  UNKNOWN non basta e non cancella le informazioni certe su P vive/terminate.

La suite è collegata al workflow e all'acceptance runner già esistenti e al
controllo sintattico repository. Non è stata eseguita la campagna zero-token
completa e non viene dichiarata una CI remota PASS.

## Fase 5 — Verifiche eseguite

| Verifica | Esito corrente |
|---|---|
| Suite MR01 | PASS, 64 test: O01–O44, otto positivi supplementari, 12 controlli indipendenti; zero skipped |
| Regressioni precedenti | PASS: T01 16, F01 16, F02 21, F03 19, factory 23 = 95; zero skipped |
| R1/R2, sorgenti e contesti esatti dal receipt | PASS CLI exit 0; advice UNKNOWN corretto; R2 conserva P1; progetti esterni invariati |
| R3 | PASS: tre payload negativi archiviati rifiutati; conservata la copertura F03 |
| R4 HIGH | PASS: nove rifiuti attesi su payload esatti; prima della correzione erano nove accettazioni indebite |
| Replay R4 esteso | 24/27 aspettative storiche coincidenti; tre positivi sintetici non conformi classificati sotto |
| Repository e profili | PASS, entrambi exit 0; nessuna candidata attivata |
| Ruff check / format --check | PASS sui percorsi engine/factory e sei suite interessate |
| PlantUML dedicato | PASS: 19 sintassi, 19 SVG, 19 PNG; quattro PNG ispezionati direttamente |
| PlantUML nelle suite precedenti | PASS nei test già previsti T01/F01/F02, nessuno skipped |
| Candidate validation | PASS strutturale; generated, trusted/registered/executable false, approval pending |
| Immutabilità | PASS sui progetti analizzati, fixture precedenti, candidata, MR00 e artefatti storici; hash/mode nel receipt |
| Diff e Git | Controlli di whitespace/integrità; branch/HEAD/indice invariati; nessuno staging o commit |

Rendering dedicato: otto IR storici, nove selezioni MR00 e i replay R1/R2.
Ispezionati O33 (D2), O04 (NEW), O06 (NESTED), O28 (NEW con advice UNKNOWN).
Identità, SP, sovrapposizione di P1 sospesa, END P2 prima di RESUME P1 ed effetti
solo IF_APPLIED sono leggibili; nessuna attività riportata oltre il terminale.
Jar locale `plantuml-1.2024.8.jar`, hash nel receipt, nessun download.

Sei diagrammi storici restano byte-identici al renderer precedente. Due cambiano
intenzionalmente: capability_unknown distingue il marcatore D2; unsupported_propagation
mostra advice APPLIED sotto la premessa proxy registrata, mantenendo contesto e
confine UNSUPPORTED/UNKNOWN. APPLIED non viene convertito in transizione riuscita.
Gli artefatti storici nel repository restano immutati.

### Classificazione dei tre positivi sintetici R4

`hand-unknown-REQUIRED`, `hand-unknown-NESTED`, `hand-unknown-REQUIRES_NEW`
dichiarano tutti modalità globale ASPECTJ/ASSUMED_APPLIED, ma il loro frame F1 ha
`SCENARIO_PROXY_CALL`, proxy CLASS e `crossed: true`. Il caller è quindi stipulato
con premesse incompatibili con lo scenario T01 a singola modalità d'intercettazione.
MR00 distingue quelle modalità e non autorizza un caso misto né una certificazione
positiva da effetti/annotazioni. Il nuovo rifiuto avviene su quelle premesse del
caller, non sulla conservazione del contesto F02 nel figlio.

Classificazione: **HISTORICAL_SYNTHETIC_PREMISE_CONTRADICTION**. Le vecchie attese
restano visibili come non coincidenti, non vengono riscritte o contate come PASS.
O27/O28/O29 sono i positivi MR00 coerenti degli stessi tre rami e passano;
passano anche le regressioni sorgente F02 e il replay R2 esatto. Nessun test
precedente è stato modificato per assorbire questa differenza.

## Copertura, limiti e arresto

La matrice CSV copre ogni Txx/Oxx e V1–V12, D1–D4, F01/F02/F03 e R4-HIGH.
Questa è copertura completa degli esempi e vincoli della matrice MR00 nel perimetro
del mandato; non è una prova universale di assenza di difetti, una nuova qualifica
runtime o un'accettazione indipendente dell'implementazione.

Restano UNKNOWN identità/outcome runtime, weaving, driver, esiti commit/rollback
e percorsi di eccezione non modellati. Renderer e validatore verificano i fatti
IR forniti; non riparsano indipendentemente ogni sorgente sintetica. Le sequenze
PlantUML mantengono il limite geometrico documentato sui lifetime sovrapposti.
I tre positivi sintetici R4 non conformi restano una differenza esplicita da
valutare nella futura review, senza riaprire le decisioni D1–D4.

Il patch comprende l'intero incremento rispetto allo snapshot iniziale, inclusi
i deliverable testuali, eccetto il file patch stesso. Il receipt conserva i
manifest e i log; i temporanei di esecuzione sono esterni al repository.

**Nessun commit, merge, push o nuovo worktree; nessuna modifica a Familiar,
REL-01/A o ai progetti analizzati; nessuna attivazione skill o implementazione
T02. Review e integrazione: NOT RUN. Arresto alla consegna MR01.**
