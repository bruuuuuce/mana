# MANA-TRANSACTION-01-T02-S02-I01-F03 — Wire Contract Compatibility

22 ottobre 2026. Verdetto **FIX_READY_FOR_REVIEW**. Caso A: preservato il wire
contract originario `mana.wait-dependency/v1`. Nessuna v2 necessaria o introdotta.
Correzione e verifiche locali; nuova review indipendente **NOT_RUN**.
I runner storici non sono modificati né tutti verdi: i loro esiti integrali,
inclusi ERROR e FAIL, sono nella [ricevuta](TRANSACTION-01-T02-S02-I01-F03-results.json).

Baseline verificata: `develop`, HEAD
`9d3468101ccdcf40f680418955be17aec098c9e6`, tree
`d653a29de2823722b6753fcdf619410d4c5d8817`. Indice senza staging.
Nessun commit, merge, push, reset, cleanup, copia completa o nuovo worktree.

## Diagnosi riprodotta e primo delta incompatibile

Letti D00, F01, F02, F02-R1, risultati e checks F02-R1; esaminati direttamente
producer, validatore, CLI, standard v1, sidecar, JSON A/B/C e patch storiche.
Lo schema S02 effettivo è definito da standard, controlli Python e proiezione
esatta; non esiste un JSON Schema S02 separato da aggiornare.

Il runner F02-R1 immutato è stato eseguito **prima degli edit**: exit 1,
BREAKING_COMPATIBILITY. Successivamente la nuova suite recupera integralmente
in memoria i due consumer e producer dalle patch I01 → F01 → F02. Controlla
ogni byte di contesto e gli hash dei receipt a ogni passaggio; nessuna patch
viene applicata al checkout. Il validatore di ciascuna generazione importa le
primitive del proprio motore ricostruito, non quelle aggiornate.

| Generazione | SHA-256 producer | SHA-256 validatore |
|---|---|---|
| Pre-F02, dopo F01 | `1d99e1df9894592c8ec7e90bbfd555aac786f70c79874f65ac6af99855abe7c1` | `009d43bfa59c71612cc1168546b22f0a121b3168de1a4fa9b39878012caa3fc9` |
| F02 | `d9bca2a5154f183b04db09fa879b594827b247367a9a4ec4434b6f4ef3a41849` | `a4c585a5d8292e4d45c36af92858199371bce1cd8a1a603eb64786cdc1344fb9` |

Prima della correzione, per **ciascuno** degli esempi A, B e C:

| Report prodotto da | Consumer pre-F02 | Consumer F02 |
|---|---|---|
| Pre-F02 | ACCEPT | REJECT |
| F02 | REJECT | ACCEPT |

Il primo delta recuperabile che rompe il formato è **F02**, non F01: la patch
F02 aggiunge `assessment.exclusionProof` e `assessment.cuts[*].exclusionProof`,
anche quando valgono null. Il consumer pre-F02 confronta l'intero oggetto con
la proiezione precedente e rifiuta i campi inattesi. Il consumer F02 richiede
un dict di prova per i negativi e confronta la nuova proiezione per tutti gli
esiti: i campi diventano obbligatori sotto lo stesso identificativo v1.
Non è attribuito un commit a questo delta: le superfici sono ancora untracked.

Classificazione delle celle incrociate:

- **Parsing:** nessun errore; i JSON sono leggibili. Sono separatamente testati
  JSON malformato, chiavi duplicate e numeri non finiti, che vengono rifiutati.
- **Envelope:** nessuna incompatibilità nei report validi; versione, status e
  chiavi top-level coincidono. Schema/versione alterati sono rifiutati.
- **Struttura/campi:** F02 → pre-F02 introduce campi nested inattesi;
  pre-F02 → F02 manca i nuovi campi. A/C falliscono la riproiezione; B fallisce
  prima sul requisito di prova. Non sono nuovi enum o valori sconosciuti.
- **Semantica:** A/B/C originali hanno conclusioni giustificate e riprodotte;
  il loro rifiuto è erroneo, dovuto alla rappresentazione. Anche A senza holdings
  resta UNKNOWN nei due motori, ma F02 cambia il contatore da 9 a 17 e aggiunge
  i null: ulteriore incompatibilità di proiezione, senza cambiamento del rischio.
- **Vecchi falsi negativi:** I01 prima di F01 produceva NO_CYCLE per A/C senza
  holdings. Il recupero reale di quel producer riproduce entrambi; F03 li respinge
  nel gate sorgente, prima della riproiezione. È un **rifiuto semantico legittimo**,
  non una regressione di formato.

## Contratto canonico v1 effettivamente preservato

Il riferimento è il wire implementato in I01 e preservato in F01, ricostruito
byte per byte; D00 è l'autorità semantica. Quattro livelli restano distinti:

1. **Sintassi:** JSON UTF-8, chiavi univoche, numeri finiti, profondità entro 128.
   La CLI produce indentazione a due spazi, escaping ASCII e newline finale.
2. **Struttura:** envelope chiuso, record discriminati e campi di seguito;
   la riproiezione esatta verifica anche i campi nested e i riferimenti.
3. **Semantica:** input validati, W1–W8, identità, causalità, cut e prova negativa.
   La sola leggibilità strutturale non autorizza NO_CYCLE.
4. **Autorità:** digest e snapshot provano identità dei byte e coerenza del modello;
   non autenticano fatti runtime, lock, autore o corrispondenza al deployment.

### Envelope, campi obbligatori e varianti

Tutte le 14 chiavi top-level sono obbligatorie, anche quando contengono liste
vuote: `schema`, `status`, `inputs`, `scenario`, `operations`, `claims`,
`waitCandidates`, `databaseGraph`, `applicationGraph`, `crossLayerRelations`,
`unknowns`, `limits`, `coverage`, `assessment`.
`schema = mana.wait-dependency/v1`; `status = CONDITIONAL_STATIC_SCENARIO`.

| Record | Campi obbligatori / interpretazione |
|---|---|
| `inputs[*]` | `id, sha256, bytes, t01Sha256, t01Bytes, t01Encoding`; digest dei byte Timeline originali e digest separato del T01 embedded |
| `scenario` | Copia esatta del sidecar `mana.wait-scenario/v1`: `schema, id, inputs, participants, premises, resources, operations, lockRule, cuts` |
| `operations[*]` | `id, namespace, observation, timelineSequence, t01Sequence, event, normalReturnDependencies, lifetime, suspension, selectedForDatabase`; observation/witness originali, due sequence distinte, null espliciti |
| Namespace P/frame | `scenarioId, participantId, inputDigest` e rispettivamente `originalPhysicalId` / `originalFrameId`; P null rimane UNKNOWN, nessuna fusione fra partecipanti |
| Claim comune | `id, category, rule, certainty, operationRefs, premises, evidence, modelPremises, propertyCertainty, excludedProperties` |
| Claim di operazione | Aggiunge `endpoint`; rappresenta la sintassi sorgente |
| Claim di richiesta | `origin, endpoint, mode, acquisition, retention`; `abstractRule` soltanto per `EXPLICIT_SCENARIO_RULE`, assente per `EXPLICIT_REQUEST_SYNTAX` |
| Claim di conflitto | `resource, orientation, holder`; orientation UNORIENTED, holder UNKNOWN; endpoint tramite operationRefs |
| Claim DB | `waiter, blocker, resource, cut, candidate, obligations, request, holding`; riferimenti distinti a richiesta, acquisizione e ritenzione |
| Claim applicativo | `caller, callee, callerPhysical, calleePhysical, resource, source, completionPremises`; risorsa FRAME_COMPLETION/FRAME, database NOT_APPLICABLE |
| `waitCandidates[*]` | `id, cut, waiter, holder, obligations, status`; ledger W1–W8 con `id, state, reason, premises, evidence` |
| Grafi | `nodes, edges`; nodi `{id, namespace}`; archi `{from,to,claim,certainty}` con `cut,resource` aggiuntivi per il grafo DB |
| Relazioni cross-layer | Varianti EXECUTES_IN (operazione/frame), SUSPENDS_FOR, RESUME_REQUIRES_COMPLETION; riferimenti sorgente, certainty ed evidence, fuori dagli archi DB |
| `assessment` | `result, cuts, scope`; ogni cut ha esattamente `cut, result, contradictions, unknowns, claims` |
| `coverage` | `status, reasons, scope, scopeStatus, budgets, candidateComparisons, serializedEdges, inventoryOperations, selectedOperations, globalRiskAbsence, runtime` |
| `unknowns` | Record discriminati dalla ragione, con riferimenti a cut/candidate/operation e, dove pertinente, missingObligations/contradictedObligations/limits; riproiezione esatta |
| `limits` | Le sei limitazioni originali, confrontate integralmente |

Non ci sono campi top-level opzionali né un contenitore generico di estensioni.
I campi di variante sono richiesti per quella categoria, assenti per le altre.
Ipotesi opzionali sono rappresentate con null o liste vuote **nelle chiavi già
previste**, non omettendo arbitrariamente chiavi. Le strutture sidecar nested
sono chiuse come documentato nello [standard originale](../standards/wait-dependency-model-v1.md).
`exclusionProof` **non è un campo opzionale del wire canonico v1**.

### Valori, premesse, certezza e conclusioni

- Cinque categorie: RESOURCE_OPERATION, LOCK_REQUEST_CANDIDATE,
  LOCK_CONFLICT_CANDIDATE, DB_WAIT_DEPENDENCY, APPLICATION_WAIT_DEPENDENCY.
- `rule` contiene id/versione. Certezza del claim: STATIC_SYNTAX, CONDITIONAL
  oppure UNKNOWN; runtimeExecution e runtimeWait restano UNKNOWN. OBSERVED
  è previsto concettualmente da D00 per un futuro mandato R1–R7, vietato in I01.
- Premesse sidecar: `{id,statement,scope,state,provenance,dependsOn}`; provenance
  `{source,reference}` non vuota, scope uguale allo scenario, dipendenze DAG.
  Stati ammessi EXPLICIT_ASSUMPTION/UNKNOWN/CONTRADICTED. MODEL_EVIDENCE è generata
  soltanto da input validati. RUNTIME_EVIDENCE e MODEL_EVIDENCE autoattribuite nel
  sidecar sono respinte. Nessuna stringa libera viene interpretata come W4.
- Relazioni risorsa SAME/DISJOINT/UNKNOWN; granularità UNKNOWN/OPAQUE_TARGET.
  Modi astratti dichiarati, al massimo otto; compatibilità simmetrica
  COMPATIBLE/INCOMPATIBLE/UNKNOWN. Coppie assenti rimangono UNKNOWN.
  Temporalità CONCURRENT/SERIAL/OUTER_REQUIRES_NEW/UNKNOWN con premessa distinta.
- Candidati QUALIFIED/EXCLUDED/UNKNOWN. Solo W1–W8 tutte giustificate generano
  DB_WAIT_DEPENDENCY(CONDITIONAL), waiter → blocker con P distinte e identificate.
- Esiti: UNKNOWN, CONDITIONAL_CYCLE_RISK, CYCLE_FEASIBILITY_UNKNOWN,
  NO_CYCLE_IN_MODELED_SCENARIO, CONDITIONAL_CROSS_LAYER_COMPLETION_RISK.
  Nessun DEADLOCK_FREE o DEADLOCK_CONFIRMED. NO_CYCLE è limitato a scope e cut;
  può coesistere con coverage INCOMPLETE e lock UNKNOWN.
- Coverage INCOMPLETE/COMPLETE_MODELED_SCOPE; scope SUPPORTED/UNSUPPORTED.
  `globalRiskAbsence = NOT_ASSERTED`, `runtime = NOT_RUN` invarianti.

Timeline: SHA-256 dei byte esattamente forniti. T01 embedded: JSON ordinato,
compatto, ASCII, senza nonfinite, encoding `sorted-compact-ascii-json/v1`.
La serializzazione CLI non è la codifica canonica dei digest. Hash, path,
linee, span UTF-16, normal-return dependencies e provenance restano originali.

### Estensibilità e obblighi dei consumer

Il consumer deve rifiutare versione/envelope sconosciuti, campi inattesi,
riferimenti corrotti, digest errati, promozioni OBSERVED e conclusioni non
supportate. Non deve usare l'uguaglianza con un nuovo layout incompatibile
per imporre campi aggiuntivi sotto v1. La correzione mantiene l'uguaglianza con
la rappresentazione v1 originaria e la validazione semantica indipendente.

F03 legge anche **la precisa rappresentazione storica F02**: non ignora campi
arbitrari. Ricostruisce e verifica i certificati negativi, poi esige uguaglianza
integrale con la derivazione F02, inclusi null e contatori. È un percorso di
lettura delimitato per gli artifact esistenti; il producer pubblico non emette
quella rappresentazione. Un certificato alterato non viene semplicemente rimosso.

## Correzione incrementale

[Patch F03](TRANSACTION-01-T02-S02-I01-F03.patch), riferita ai tre file pre-F03
salvati all'avvio, non a HEAD che non contiene ancora S02.

- `_derive_report` conserva internamente la derivazione F02 e i certificati.
  `build_report` pubblica la forma v1 originaria, senza campi di prova, anche null.
- I confronti aggiuntivi delle prove consumano ancora il budget F02. Nel wire
  `candidateComparisons` torna a contare i confronti del modello v1;
  `serializedEdges` conta gli archi effettivamente pubblicati. Le guardie interne
  continuano a includere lavoro e archi delle prove, senza aumentare i limiti.
- Il validatore ricostruisce da input validati inventario completo, prefissi,
  lifetime/sospensione e sovrastima DB/app; verifica l'aciclicità con eliminazione
  topologica indipendente dal DFS del producer. L'assenza del campo JSON non
  elimina la prova né autorizza un negativo per il solo grafo vuoto.
- I negativi evidence-complete conservano il loro percorso W1–W8; una sovrastima
  più grossolana non ne sostituisce la prova nell'unione di cut. La suite F03
  verifica anche due direzioni sorgente opposte escluse da premesse di disgiunzione.
- CLI: JSON canonico; Markdown e riepilogo `exclusionProofs` possono descrivere
  la diagnostica ricalcolata, senza trasformarla in nuovi campi wire. Gli artifact
  A/B/C completi, inclusi JSON, Markdown e Mermaid, tornano byte-identici.

Nessun nuovo input, matching SQL, tipo di lock, solver, adapter o capacità di
analisi. Nessuna modifica ai contratti T01/T02-S01 o alla certezza.

## Matrici dopo la correzione e limiti dell'interoperabilità

Per ciascuno di A/B/C, consumer pre-F02 reale e consumer aggiornato:

| Report prodotto da | Consumer pre-F02 | Consumer F03 |
|---|---|---|
| Pre-F02 | ACCEPT | ACCEPT |
| F02 storico | REJECT: campi inattesi | ACCEPT, lettura storica verificata |
| F03 canonico | ACCEPT | ACCEPT |

Il consumer F02 **storico immutato** continua a rifiutare i report pre-F02 e
F03: il suo difetto non viene riscritto retroattivamente. La matrice completa
3×3, prima/dopo e per caso, è nella ricevuta. Nessun consumer è simulato.
A senza holdings: wire F03 uguale al pre-F02, contatore 9, UNKNOWN, accettato
anche dal consumer pre-F02; F03 accetta inoltre il vecchio UNKNOWN F02.

Le quattro esclusioni recuperate B-no-pending, B-one-incomplete-cut,
REQUIRED e NESTED sono rappresentabili senza nuove informazioni: il consumer
F03 le accetta e mantiene coverage INCOMPLETE/W4 UNKNOWN. Il consumer pre-F02
le legge strutturalmente ma le respinge nel vecchio gate che richiede holdings.
Questo è un **rifiuto semantico erroneo/conservativo del vecchio consumer**,
non un errore di parsing, enum, envelope o schema. La correzione preserva il wire;
non può correggere il codice storico immutabile né garantire accettazione
semantica da parte di validatori con difetti già dimostrati.

Le quattro degradazioni A/C senza holdings, A con holding omessa e frontiera
irrisolta restano UNKNOWN. Forzarle a NO_CYCLE, anche senza campo di prova,
viene respinto prima del producer finale. Certificati inventati/incompatibili,
W4 autoattribuita, coverage falsamente completa e OBSERVED statico restano respinti.
Grafi qualificati e grafi incompleti rimangono distinti.

## Verifiche eseguite e aspettative storiche

| Gate | Esito locale |
|---|---|
| F02-R1 immutato, **prima** della correzione | FAIL riprodotto, exit 1, incompatibilità bidirezionale |
| Nuova suite wire F03 | PASS 11/11, exit 0; matrici, roundtrip, struttura, semantica, controlli negativi |
| F02 entry point storico immutato, dopo F03 | **15 PASS, 8 ERROR, 1 FAIL**, exit 1; dettagli sotto |
| Replay F02 sulla diagnostica interna | PASS 24/24, exit 0; accessor esplicito diverso, non rinomina PASS la suite storica |
| I01 immutata | PASS 22/22, exit 0 |
| Oracoli statici nel primo test I01 | PASS 31/31, 30 A–I più J05; oracoli immutati |
| F01-R1 checks immutati | PASS 19/19, exit 0 |
| I01-R1 checks immutati | PASS 27/27, exit 0; ripristinata la parità byte degli artifact |
| F01 immutata | 12 PASS / 3 FAIL, exit 1; test 11/12/15 SUPERSEDED_EXPECTATION già motivate da F02-R1 |
| Controesempi originali I01-R1 A/C | PASS 2/2, exit 0 |
| Riduzioni minime F01-R1 REQUIRED/NESTED | PASS 2/2, exit 0 |
| Quattro UNKNOWN / quattro esclusioni recuperate | PASS 4/4 e 4/4, nuovi controlli wire e replay diagnostico |
| Serializzazione CLI, hash seed 1/97 | PASS A/B/C, byte identici agli artifact originali; validazione CLI exit 0 |
| Validazione repository | PASS, exit 0 |
| Ruff check / format --check | PASS, exit 0, 13 file Python pertinenti |
| J01–J04, runtime Oracle, provider, CI, deployment | NOT_RUN |

Gli 8 ERROR F02 sono KeyError nei test 02/03/04/08/09/13/14/23 che accedono ai
campi `exclusionProof` del risultato pubblico. Il FAIL 17 esige che il contatore
**serialized** includa archi di prova ora interni. Sono aspettative della
rappresentazione F02 incompatibile, superate dalla correzione richiesta;
nessun test storico è stato riscritto o normalizzato. La nuova sottoclasse
`DiagnosticReplay` cambia esclusivamente l'accessor del helper `build` per
esercitare gli stessi 24 metodi e asserzioni sull'oggetto diagnostico privato.
Le chiamate CLI restano reali, sul wire pubblico; i budget rimangono verificati
anche tramite `build_report`. Non è una prova che l'entry point storico passi.

La suite F03 verifica direttamente le quattro esclusioni/UNKNOWN nel wire
pubblico, i vecchi consumer, falsi negativi senza certificato e rifiuti prima
della riproiezione anche con producer simulato errato. Le prove sorgente nelle
fixture usano gli oracoli manuali e la chiusura transitiva indipendente esistente.
I conteggi dei gate si sovrappongono e non sono sommati come casi unici.

## Integrità e consegna

Inventario iniziale effettivo: **1.375 file**, ossia i 1.372 di F02-R1 più i suoi
tre deliverable. Prima degli edit tutti i 1.372 hash/dimensioni/mode coincidono
con il manifest di quella review. A fine lavoro cambiano intenzionalmente solo
producer, validatore e CLI S02: **1.372/1.375 file iniziali invariati**, e
**1.369/1.372 del manifest precedente invariati**, con le tre eccezioni autorizzate
esplicitamente rendicontate. Nessuna cancellazione o variazione estranea.

Gli 11 percorsi preesistenti e i sei materiali protetti conservano byte/mode
anche rispetto ai receipt storici. CSV, report, witness, fixture, oracoli e suite
storiche non sono modificati. Manifest iniziale, hash prima/dopo, confronto dei
protetti, output integrali dei comandi e metadati Git sono nella ricevuta.
Aggiunti soltanto suite F03 e tre deliverable F03: questo rapporto, risultati e patch.

Branch, HEAD, tree, refs, indice e worktree list invariati. T01/T02-S01 canonici,
Familiar, REL-01/A, skill e superfici di attivazione non modificati.
Nessuna integrazione o nuova review autorizzata/eseguita. Arresto alla consegna
**FIX_READY_FOR_REVIEW**, con i limiti e gli esiti storici sopra dichiarati.
