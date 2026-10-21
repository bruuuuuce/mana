# MANA-TRANSACTION-01-T01-MR00 — Contratto delle transizioni

Data: 20 ottobre 2026. Fase esclusivamente architetturale. Decisioni MR00
recepite dall'approvazione dell'utente: D1/D3 APPROVED, D2/D4 APPROVED WITH
CONSTRAINT. **MR01 non avviato; R4-F01 non dichiarato corretto.**

Branch verificato: `feature/mana-transaction-01`; HEAD:
`378243883adb101a7a41feef71e2a66b76e7f508`. Il contratto riguarda il working tree
T01/F01/F02/F03 presente su questa baseline, inclusi i file non committati.

Deliverable collegati: [matrice CSV](MANA-TRANSACTION-01-T01-MR00-transitions.csv)
e [piano MR01](MANA-TRANSACTION-01-T01-MR00-implementation-plan.md).

## 1. Autorità, letture e provenienza

Le etichette distinguono **E** (requisito già espresso dagli input), **I**
(interpretazione che rende verificabile quel requisito), **D** (decisione
architetturale MR00 approvata dall'utente, con i vincoli sotto riportati).
L'approvazione delle decisioni non autorizza l'implementazione MR01. «Deve» definisce il contratto
revisionato, non una garanzia sull'implementazione attuale.

Sono stati letti R1, R2, R3, R4, il receipt R4 e lo standard v1. Esaminati
direttamente `scripts/skill_factory/transactions/model.py` (motore e validatore),
`alternatives.py`, le osservazioni della CLI/renderer, le quattro suite
`tests/transaction-*.py`, i tre `oracles.json` e le rispettive fixture Java.
Non sono stati eseguiti motore, replay, suite o rendering in MR00.

| Fonte locale | Vincolo ricostruito / riscontro nel codice attuale |
|---|---|
| [Standard v1](../standards/transaction-model-v1.md), Propagation State Rules e F03 | **E**: L distinto da P; REQUIRED condivide, NEW separa, NESTED usa SP; istanti e lifetime distinti |
| [R1](MANA-TRANSACTION-01-T01-R1.md), [R2](MANA-TRANSACTION-01-T01-R2.md) | **E**: niente falso bypass AspectJ; UNKNOWN dell'advice non cancella proprietà fisiche comuni |
| [R3](MANA-TRANSACTION-01-T01-R3.md) | **E**: una P terminata non torna attiva; outcome UNKNOWN non prolunga il lifetime |
| [R4](MANA-TRANSACTION-01-T01-R4.md), [receipt](MANA-TRANSACTION-01-T01-R4-results.json) | **E**: rifiutare capability incompatibili, scambio NESTED/NEW, falsa uscita INACTIVE |
| `model.py:383-515` | Generazione APPLIED: selezione manager, guardie capability, allocazione P/SP/S; crea anche un L UNKNOWN nei fallimenti di capability |
| `model.py:516-600` | Aperture prima del corpo; chiusure, terminali e resume prima di FRAME_EXIT; continuazione incerta può lasciare after UNKNOWN |
| `model.py:612-870` | Validatore: lifetime e riferimenti; guardia after limitata a physicalId non nullo; mancano vincoli completi APPLIED |
| `alternatives.py:30-109,177-250` | APPLIED/BYPASSED e intersezione F02, con guardie semantiche più forti dei frame ordinari |

Il receipt R4, sezioni `finding.variants` e
`independentReview.handChecks.cases`, contiene 27 controlli storici e nove witness
accettati contro l'attesa, incluso il caso completo senza campi additivi F01.
Sono **risultati R4**, letti e confrontati con i controlli presenti, non rieseguiti
né riclassificati come PASS corrente da MR00.

Il riscontro primario esterno è circoscritto: Spring distingue scope logici e
transazioni fisiche, indipendenza di REQUIRES_NEW e savepoint NESTED
([propagation 6.2](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html)).
La compatibilità JDBC nested dipende anche dalle impostazioni del manager e dal
supporto effettivo dei savepoint
([DataSourceTransactionManager](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html)).
La self-invocation PROXY e il weaving AspectJ hanno presupposti diversi
([annotazioni 6.2](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)).
Queste fonti non qualificano versione, driver o comportamento runtime dei target.
Le regole operative seguenti precisano il contratto locale T01.

## 2. Oggetti e posizioni temporali

**E/I.** A ogni posizione del percorso si distinguono:

| Asse | Significato | Rappresentazione v1 |
|---|---|---|
| Scope logico | L aperto/chiuso, proprietario del confine del metodo; può partecipare a P altrui | `logicalScopes`, `frame.logicalScope`, LOGICAL_BEGIN/END |
| Esistenza fisica | P non iniziata, viva o terminata; esistenza indipendente dal suo essere corrente | `physicalTransactions`, PHYSICAL_BEGIN / PHYSICAL_END_OUTCOME_UNKNOWN |
| Contesto corrente | P associata all'esecuzione sincrona considerata, assenza certa, oppure informazione insufficiente | `previousState`, `duringState`, `afterState`; proiezione `effectiveContext` |
| Sospensione | P viva sottratta al contesto corrente mentre una P distinta la sostituisce | `suspensions`, SUSPEND / RESUME_CONDITIONAL |
| Savepoint | SP aperto/chiuso sulla stessa P del nested, senza lifetime fisico indipendente | `savepoints`, SAVEPOINT_CREATE / SAVEPOINT_RELEASE_CONDITIONAL |
| Intercettazione | Advice APPLIED, BYPASSED o UNKNOWN, indipendente dalla riuscita del confine | `interception`; `certainty`, `reason`, `uncertainties` per i limiti |
| Manager | Identità del bean selezionato, tipo supportato e capability esplicite dello scenario | `configuration.managerQualifier`, `managers`, `context.managerCapabilities` |

Notazione del documento/CSV: `N` = stato canonico NO_TRANSACTION (effective
INACTIVE); `A(P1,tx)` = TRANSACTION_PHYSICAL/P1/tx (ACTIVE); `U` = stato canonico
UNKNOWN con identità/manager null. `A(?,tx)` = attività comune dimostrata ma
identità divergente, ammessa soltanto con witness F02. Queste abbreviazioni non
sono nuovi valori pubblici. `P1`, `P2`, `L`, `SP`, `S` sono simboli locali alla
riga, rinominabili in modo coerente. Nessuna identità runtime viene affermata.

I tre campi di stato accettano soltanto NO_TRANSACTION, TRANSACTION_PHYSICAL o
UNKNOWN: i kind delle entità L/SP/S non sono stati del contesto corrente. N e U
sono canonici; una P identificata deve avere il suo manager. La sola eccezione
all'identità fisica concreta è il during parziale giustificato da F02.

**E/I — quattro posizioni da non sovrapporre:**

1. `previousState`: immediatamente prima di FRAME_ENTER, uguale al contesto
   corrente del chiamante o all'input iniziale. Non è lo stato dopo l'advice.
2. `duringState`: al confine d'ingresso **dopo l'intero prefisso di apertura**
   del frame (SUSPEND, PHYSICAL_BEGIN, LOGICAL_BEGIN, SAVEPOINT_CREATE applicabili),
   prima del corpo. FRAME_ENTER precede quel prefisso: durante quel singolo evento
   una P posseduta può non essere ancora iniziata. Il validatore deve completare
   la verifica del during al termine del prefisso, prima del primo figlio/corpo
   o della chiusura in un metodo vuoto.
3. Posizione immediatamente dopo un terminale fisico: la P indicata è terminata;
   non è più corrente né ripristinabile. P2 terminata non rende automaticamente
   corrente P1: serve RESUME_CONDITIONAL. Durante la sospensione P1 è ancora viva.
4. `afterState`: a FRAME_EXIT, **dopo** chiusura SP/L, termine delle P possedute e
   ripristino delle sospese pertinenti. È il contesto restituito al chiamante
   sul normale unwind sincrono condizionale, non l'outcome della transazione.

Il during non vale per ogni istante del corpo: una chiamata figlia può cambiare
temporaneamente P corrente. L'after non prova che il metodo sia stato invocato o
ritorni realmente. Per corpi/continuazioni non risolti il v1 conserva il limite
UNKNOWN; non simula percorsi di eccezione o operazioni programmatiche.

**E/I.** INACTIVE significa assenza certa nel contesto corrente, non «L chiuso»
e neppure «nessuna P viva nel sistema». Nel sottoinsieme supportato, tuttavia,
chiudere un L non proprietario lascia P1 corrente: dichiarare N in quel punto
contraddice gli eventi. UNKNOWN non termina P, non cancella il suo evento BEGIN
e non autorizza una successiva riattivazione dopo END.

## 3. Premesse comuni e capability

**E.** I soli confini riusciti qui normati sono REQUIRED, REQUIRES_NEW e NESTED
nel sottoinsieme sincrono T01. Il manager positivo è un bean univoco di tipo
esatto `org.springframework.jdbc.datasource.DataSourceTransactionManager`;
qualifier esplicito o unico default osservato. Alias, duplicati, manager diverso
da quello della P corrente, tipo non modellato e identità pregressa ignota non
diventano supportati per effetto di MR00. L'input iniziale resta N oppure U:
P1 esistente nei casi positivi nasce da un frame antenato, non da un nuovo input.

**I.** Le due copie delle capability (contesto e manager) devono concordare anche
nei frame ordinari. Entry manager assente equivale alla coppia null/null;
un valore assente/ignoto non equivale a true. Le premesse iniziali, evidenze di
configurazione/annotazione, hash e siti di chiamata rimangono necessarie.

**D1 — APPROVED: significato di true.** `savepoints: true` stipula la
compatibilità effettiva del ramo NESTED con P esistente: manager configurato per
nested e risorsa capace di SP nel caso ipotizzato. `suspend: true` stipula la
sospensione/ripresa supportata in quel caso. Non si aggiungono capability né si
deducono da nome/classe/default del framework. Un'impostazione sorgente osservata
incompatibile invalida la premessa; una configurazione non risolta resta una
premessa condizionale, non una qualifica runtime.

Non si estende il parser per risolvere configurazioni nuove del manager: D1
precisa il significato della premessa esistente, non introduce una nuova analisi.

Per NESTED **senza** P corrente il sottoinsieme T01 apre una P come REQUIRED:
savepoints true non è richiesto perché non si usa SP. Analogamente REQUIRES_NEW
senza P non richiede suspend true. Le sole capability esistenti non sono guardie
generali alla creazione di P: essa rimane una premessa condizionale del manager
risolto, non una promessa di successo JDBC.

## 4. Matrice normativa APPLIED

Ogni riga presuppone advice APPLIED e premesse comuni della sezione 3. Il CSV
contiene separatamente precondizioni, capability, effetti consentiti/obbligatori/
vietati, stati, lifetime ed evidenze per tutte le transizioni. La tabella seguente
riassume i sei confini riusciti, sul normale unwind supportato.

| ID CSV | Ingresso / propagation | Apertura obbligatoria del frame | Durante | Chiusura obbligatoria del frame | Dopo |
|---|---|---|---|---|---|
| T01 | N / REQUIRED | BEGIN P2; BEGIN L su P2 | A(P2,tx) | END L; END P2 | N |
| T02 | A(P1,tx) / REQUIRED | BEGIN L su P1 | A(P1,tx) | END L soltanto | A(P1,tx) |
| T03 | N / REQUIRES_NEW | BEGIN P2; BEGIN L su P2 | A(P2,tx) | END L; END P2 | N |
| T04 | A(P1,tx) / REQUIRES_NEW; suspend true | SUSPEND P1; BEGIN P2 distinta; BEGIN L su P2 | A(P2,tx) | END L; END P2; RESUME P1 | A(P1,tx) |
| T05 | N / NESTED | BEGIN P2; BEGIN L su P2; nessuno SP | A(P2,tx) | END L; END P2 | N |
| T06 | A(P1,tx) / NESTED; savepoints true | BEGIN L su P1; CREATE SP su P1 | A(P1,tx) | RELEASE SP condizionale; END L | A(P1,tx) |

Qui BEGIN/END P abbreviano PHYSICAL_BEGIN/PHYSICAL_END_OUTCOME_UNKNOWN;
BEGIN/END L abbreviano LOGICAL_BEGIN/LOGICAL_END; RELEASE e RESUME mantengono il
suffisso `CONDITIONAL` degli eventi v1.
FRAME_ENTER/EXIT racchiudono tutte le righe. Non si introducono eventi abbreviati.

**I — insieme chiuso di effetti.** Gli effetti del confine sono esattamente quelli
della riga, una sola coppia per ogni entità posseduta. Le cardinalità sono per
frame: i figli possono avere propri confini validi. Nel frame REQUIRED condiviso
sono vietati P nuova, SP, S e termine P1; nel NESTED/P1 sono vietati P nuova,
sospensione e termine P1; nel NEW/P1 sono vietati SP come sostituto di P2,
riutilizzo P1 e termine P1. Nei tre casi senza P sono vietati SP e S fittizi.
Un effetto aggiunto deve appartenere a un figlio validato e non può essere
attribuito arbitrariamente al frame corrente.

**E/I — ownership e risultato.** Solo il frame che apre P la possiede e la termina
nel percorso T01 supportato (`beginFrame == endFrame`). Tutti gli L/SP su P devono
essere chiusi prima del terminale. Il terminale è obbligatorio per P posseduta
sul percorso completo e ha outcome UNKNOWN: copre il lifetime concluso senza
selezionare commit o rollback. La chiusura di un partecipante REQUIRED può, nella
semantica generale, influenzare rollback-only; T01 non lo calcola e non lo traduce
in termine anticipato di P1.

**E — NESTED e rollback.** Il percorso rappresentato rilascia condizionalmente SP;
P1 resta viva. Un rollback al savepoint avrebbe la stessa conservazione di P1,
ma T01 non dispone di un evento che affermi che quel rollback è avvenuto. Non
chiamare RELEASE una prova di rollback; non aggiungere tale percorso a MR01.
Un'analisi che incontri un percorso di eccezione non supportato deve esporre il
limite, senza inventare un evento o una conclusione riuscita.

### Confine APPLIED non risolto

**E/I.** APPLIED significa advice applicato sotto le premesse, non transizione
riuscita. Capability false/null nei casi che la richiedono, manager irrisolto o
incompatibile, prior U o identità parziale non permettono un confine completo.
I casi T07–T12 nel CSV sono IR ammissibili **irrisolti**, non successi.
Durante resta U nel comportamento conservativo T01; after U richiede anche la
continuazione effettivamente irrisolta e motivata secondo D4. Body NOT_ASSERTED,
certainty UNKNOWN e motivo source-linked coerente sono necessari. Nessuna P/SP/S
concreta del frame può essere affermata per superare quella mancanza.

**D2 — APPROVED WITH CONSTRAINT: compatibilità con il L tentato.** I fallimenti di capability
attualmente mantengono un L con certainty UNKNOWN, physicalId null e coppia
LOGICAL_BEGIN/END. È conservato per compatibilità v1 come marcatore di **confine logico
non risolto**, non scope transazionale riuscito. Ammesso solo in quel caso, con
frame APPLIED irrisolto e motivo coerente, senza P/SP/S possedute. Non soddisfa
gli obblighi dei sei casi riusciti, non modifica lifetime o contesto P1 e non
può essere associato arbitrariamente a una P. Manager/prior irrisolti non
richiedono quel marcatore. Non si cambia il formato né si eliminano fixture.

Il vincolo vale per **validatore, renderer e ogni consumer**: il marcatore non
deve mai rappresentare uno scope sicuramente eseguito, una transazione riuscita
o una fonte certa di effetti transazionali. I suoi LOGICAL_BEGIN/END delimitano
il tentativo irrisolto; da soli non provano apertura/chiusura di uno scope
eseguito. Etichette, conteggi di scope eseguiti e inferenze dei consumer devono
conservare questa distinzione anche quando il payload è strutturalmente valido.

### Corpo e continuazione

**E/I.** Per confine riuscito e continuazione risolta, after è esattamente quello
della tabella, anche quando è N: il controllo non dipende da physicalId non nullo.
**D4 — APPROVED WITH CONSTRAINT.** After U è ammesso soltanto con una continuazione
effettivamente irrisolta e motivata: il motivo e le evidenze esistenti devono
spiegare perché il contesto al ritorno non sia determinabile. La sola etichetta
UNKNOWN o NOT_ASSERTED non basta. Anche nei casi di confine irrisolto il motivo
deve giustificare il limite sulla continuazione, non solo l'incertezza dell'advice.
Il prefisso d'ingresso e le chiusure
concrete restano soggetti a tutti i vincoli; UNKNOWN non sana effetti impossibili.
Un after certo incompatibile è sempre vietato. Esempio: P1 nota viva, nessun
evento che la sottragga e solo END L non giustificano INACTIVE neppure invocando
una continuazione incerta. Il terminale di una P posseduta resta valido sul
normale unwind condizionale anche se la continuazione è U; non prova il corpo.

Ogni informazione certa sul lifetime fisico resta conservata separatamente da
afterState: P iniziate, ancora vive, sospese o terminate e vincoli d'identità
restano fatti del percorso condizionale. UNKNOWN non giustifica effetti
incompatibili e non cancella invarianti dimostrati. Il vincolo riguarda anche
renderer e consumer quando mostrano o usano quei fatti.

## 5. BYPASSED e UNKNOWN: preservazione F01/F02

**E.** BYPASSED non applica la propagation dichiarata dal metodo: nessuna nuova
L/P/SP/S di quel confine. Durante eredita il contesto precedente. Dopo eredita
il contesto se il corpo sincrono è risolto; l'incertezza del corpo può richiedere U.
I figli possono avere propri confini. Bypass PROXY non va trasferito ad AspectJ;
ASSUMED_APPLIED è una premessa condizionale di weaving, mai prova runtime.

**E/I.** Con UNKNOWN dovuto **solo** all'advice, F02 richiede entrambe le
alternative APPLIED e BYPASSED, ciascuna semanticamente ammissibile, e la loro
intersezione proprietà per proprietà. Non usare UNKNOWN per unire effetti
contraddittori o per cancellare fatti comuni.

| Ingresso | Propagation / premessa | Durante comune | Effetti solo IF_APPLIED | Dopo comune a corpo vuoto |
|---|---|---|---|---|
| A(P1,tx) | REQUIRED, stesso manager | A(P1,tx) | L | A(P1,tx) |
| A(P1,tx) | REQUIRES_NEW, suspend true | A(?,tx) | P fresca, L, S su P1 | A(P1,tx) |
| A(P1,tx) | NESTED, savepoints true | A(P1,tx) | L e SP su P1 | A(P1,tx) |
| N | Ciascuna delle tre, manager risolto | U | P fresca e L; nessuno SP/S | N |
| N o P1 | APPLIED irrisolto | Solo proprietà comuni dimostrate, nel caso attuale U | UNKNOWN, non presenza certa | U |

Le P fresche di ramo sono `FRESH_IF_APPLIED`, non P allocate negli array globali.
L/SP/S condizionali non devono trapelare negli eventi incondizionati. P1 rimane
viva in entrambi i rami NEW/P1, ma non è corrente in entrambi: è corretto conservare
ACTIVE e manager, lasciando identità null. Un U totale in questo caso perde
informazione certa; una P1 corrente certa afferma informazione divergente.

Le premesse F02 rimangono SYNCHRONOUS_BOUNDARY, NONE_OBSERVED per altri meccanismi,
evidence uguale al metodo; after affinato solo per corpo EMPTY e confine APPLIED
supportato. Corpo non vuoto non attraversato: after U, senza estendere questa
regola a tutta l'esecuzione. Async, dispatch/hazard irrisolti e controllo di flusso
fuori perimetro non acquisiscono un witness F02 per artificio.

## 6. Vincoli di validità indipendenti

La validità richiede **tutti** i vincoli, non l'unione libera di eventi riconosciuti.

| ID | Vincolo normativo |
|---|---|
| V1 | Forma, ID univoci, kind, riferimenti, siti di chiamata/hash e coppie begin/end coerenti, inclusi campi additivi se presenti |
| V2 | Manager selezionato e capability concordi con scenario; stessa identità di manager per P condivisa e per il sottoinsieme NEW supportato |
| V3 | Una sola riga semantica applicabile; cardinalità e insieme completo degli effetti del confine esattamente compatibili con quella riga |
| V4 | Prefisso, durante, chiusure e dopo verificati ai rispettivi istanti; previous del figlio deriva dal contesto corrente del chiamante, non sempre dal suo during iniziale |
| V5 | BEGIN rende viva una P fresca mai usata; solo terminale giustificato del proprietario la termina; L/SP/S e FRAME_EXIT non terminano P |
| V6 | P sospesa resta viva, non è corrente né utilizzabile da nuovi scope fino a RESUME; replacement distinta, già iniziata e terminata prima del ripristino; ordine LIFO per sospensioni annidate |
| V7 | SP appartiene alla P viva/corrente del nested; chiusura SP prima di L; nessuna sostituzione di P2 con SP o viceversa |
| V8 | Chiusure dei figli non chiudono L/SP/P degli antenati; un frame non proprietario non può terminare la P ereditata |
| V9 | Un terminale impedisce ogni stato successivo attivo con quella identità, compresi after, previous di fratelli, during, resume e tentativi di nuovo BEGIN |
| V10 | After completo deve essere quello della riga anche se N; U ammesso soltanto con continuazione effettivamente irrisolta e motivata, conservando separatamente ogni informazione certa sul lifetime fisico; assenza certa non deriva dalla sola chiusura logica |
| V11 | Witness F02 con entrambi i rami, effetti condizionali non materializzati e intersezione esatta; conservare tutte le proprietà comuni giustificate |
| V12 | Nessuna pretesa runtime: identità SYMBOLIC_SCENARIO, runtimeIdentity/outcome UNKNOWN; nessun commit/rollback concreto dedotto dal terminale |

Si verifica la proiezione degli eventi appartenenti al frame, mantenendo il
contesto e lo stack dei figli nel replay globale. Gli scope e le sospensioni
degli antenati vengono preservati: non si richiede che gli array globali siano
vuoti all'uscita di ogni figlio. Le P/L/SP/S create nel percorso devono essere
chiuse al termine del percorso completo, come nel v1 corrente.

Un terminale senza evento END è una falsa affermazione di stato. Anche un END
presente è invalido se non giustificato dall'ownership e dalla transizione:
aggiungere un evento strutturalmente valido non rende lecita la terminazione di
P1 da parte di un partecipante. Eventi indipendenti esterni non sono modellati
da T01 e non possono essere invocati tacitamente come giustificazione.

## 7. Oracoli indipendenti e uso del CSV

Il CSV è UTF-8 con intestazione, celle quotate e separatore virgola. Categoria
TRANSITION = specifica normativa; categoria ORACLE = esempio positivo/negativo
derivato dalle regole, con attesa ACCEPT/REJECT. ACCEPT_UNRESOLVED sulle transizioni
ammette un IR che dichiara il limite, non una transizione fisica riuscita.
`allowed_effects` è un insieme chiuso di effetti del confine; `required_effects`
ne impone ordine e presenza. Gli eventi del corpo/figli rimangono soggetti al
contratto ricorsivamente. Tutte le righe incorporano le premesse comuni di questo
documento; il riferimento a Txx in un oracolo ne eredita gli otto vincoli.
Negli oracoli negativi queste colonne descrivono gli obblighi della riga base;
`example_or_delta` specifica la proposta da rifiutare. Le eventuali celle con
«dichiarato ma vietato» riportano esplicitamente il valore invalido proposto.

Gli esempi O01–O44 sono specifiche manuali, **non test implementati/eseguiti**.
Usano identità letterali e differenze esplicite di stato/eventi/capability. Le
aspettative non sono ricavate da `build`, `applied_boundary`, `compose`, renderer
o risultato di `validate_model`. Il receipt R4 è un set storico da confrontare,
non l'autorità che decide l'attesa.

Per renderli test in MR01, costruire IR completi dichiaratamente sintetici o
copie di modelli storici completi mantenendo envelope, hash e provenance. Il
fixture loader può rinumerare gli eventi; non deve calcolare l'oracolo con codice
produttivo. Nei negativi aggiornare anche effectiveContext e entrambe le copie
capability quando necessario: il rifiuto deve derivare dalla contraddizione
semantica, non da campi accidentalmente malformati. Ogni negativo ha un positivo
equivalente o una riga Txx di riferimento.

## 8. Sufficienza del v1 e decisioni approvate

**Conclusione: v1 sufficiente per tutte le transizioni nel sottoinsieme T01
supportato.** Non è dimostrata la necessità di cambiare schema, input CLI, JSON
pubblico o eventi. I dati necessari si ricavano senza nuovi campi:

| Informazione necessaria | Testimone esistente / controesempio discriminabile |
|---|---|
| L partecipante rispetto a P posseduta | `logicalScopes.frame/physicalId`, P.beginFrame/endFrame: END L2 con P1 viva distingue T02 da O13 |
| P viva ma sospesa rispetto a corrente | P BEGIN/END + S.physicalId/replacementPhysicalId + ordine SUSPEND/RESUME: T04 distingue O16 |
| P2 indipendente rispetto a SP su P1 | Array separati, manager, ID e mapping al during: T04/T06 distinguono O11/O12 |
| Capability incompatibile con effetto | Context e manager conservano false/null mentre SP/S conserva l'effetto: O07–O10 sono già esprimibili |
| Informazione comune e divergente | `contextComposition.alternatives`, stati e descrittori IF_APPLIED: T16–T21 distinguono O18–O23 |
| Stato a un istante e durata conclusa | FRAME_ENTER/EXIT, opening prefix e terminale ordinato: O14/O17 non richiedono timestamp |

V1 non rappresenta come fatti distinti commit, rollback fisico, rollback al
savepoint, rollback-only o guasti durante apertura/completion. Non sono percorsi
supportati dal perimetro modellato T01 e restano esplicitamente fuori da MR01. Se si
richiedesse in futuro «SP1 ha subito rollback e non release», due esecuzioni con
stessi campi/eventi v1 sarebbero indistinguibili: mancherebbe il tipo di esito SP.
Questo è un limite concreto per **quella futura richiesta**, non un controesempio
alla sufficienza del v1 per il mandato corrente. Non si risolve ora ampliando T01.

| Decisione | Stato approvato dall'utente | Regola vincolante |
|---|---|---|
| D1 | APPROVED | Capability come premesse di compatibilità effettiva dello scenario, senza validazione runtime automatica, nuovi campi o inferenza dal tipo manager |
| D2 | APPROVED WITH CONSTRAINT | L UNKNOWN/null resta marcatore di confine tentato/irrisolto per compatibilità v1. Validatore, renderer e consumer non lo rappresentano mai come scope sicuramente eseguito, transazione riuscita o fonte certa di effetti transazionali |
| D3 | APPROVED | Compatibilità legacy preservata; niente APPLIED dalla sola presenza di effetti o annotazioni. Usare evidenze affidabili di modalità, crossing, configurazione, certainty e reason; se non consentono classificazione affidabile, non certificare positivamente il confine |
| D4 | APPROVED WITH CONSTRAINT | After UNKNOWN soltanto con continuazione effettivamente irrisolta e motivata. Conservare separatamente ogni informazione certa sul lifetime fisico; UNKNOWN non giustifica effetti incompatibili né cancella invarianti dimostrati |

Le decisioni approvate fissano le interpretazioni per questa matrice; nessun suo
esempio dipende da un'opzione lasciata indeterminata. D3 mantiene opzionali i campi
F01 degli IR storici senza esentarli dai vincoli APPLIED; un'annotazione isolata
non dimostra intercettazione. L'approvazione non autorizza modifiche di schema,
ampliamenti delle propagation, attivazione skill o T02 e non avvia MR01.

MR00 termina alla consegna di questi tre documenti. Nessuna modifica a codice,
test o standard esistente; nessun commit, merge, push, worktree, intervento su
Familiar, attivazione skill, T02 o nuova campagna QA.
