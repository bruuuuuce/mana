# MANA-TRANSACTION-01-T01-R2 — Independent Review & Integration

Data: 20 ottobre 2026. Verdetto: **NEEDS_FIX**.

Il controesempio storico R1-F01 è corretto: ASPECTJ senza weaving dimostrato non
riceve più il bypass PROXY. Rimane però un difetto bloccante rispetto al requisito
R2 sul contesto già noto: UNKNOWN dell'intercettazione impone UNKNOWN del contesto
fisico anche quando le alternative applicabile/bypassata conservano entrambe P1.
Nessun commit o integrazione è stato eseguito. Nessuna correzione implementata.

[Evidenze R2](MANA-TRANSACTION-01-T01-R2-results.json): comandi, exit code e output
integrali, modelli/PlantUML rigenerati, sorgente e contesto del controesempio,
probe del validatore, hash degli input, manifest di preservazione e stato Git.
Le prove nuove sono state prodotte in questa sessione di review, distinta dalla
remediation F01, esaminando codice e oracoli effettivi. I receipt precedenti sono
stati usati come input da verificare, senza sostituirli con risultati nuovi.

## R2-F01 — HIGH, bloccante: UNKNOWN dell'advice cancella un contesto deducibile

Posizioni nel working tree revisionato:

- `scripts/skill_factory/transactions/model.py:176-182`: `uncertain()` imposta
  sempre `duringState = unknown()`.
- `model.py:276-277,365-366`: una forma AspectJ non modellata entra in quel percorso.
- `model.py:565-566`: anche il contesto dopo il frame diventa UNKNOWN.
- `model.py:648-649`: il validatore vieta qualsiasi UNKNOWN dell'intercettazione
  accompagnato da un contesto fisico conosciuto.

Riproduzione indipendente su una copia esterna della fixture AspectJ F01:

1. Copiare `tests/fixtures/transaction-self-invocation/aspectj` fuori dal repository.
2. Nel solo metodo `required()`, aggiungere `final`, lasciando annotazione e corpo
   vuoto invariati. Il chiamante rimane `activeRequired()`:

```java
@Transactional public void activeRequired() { this.required(); }
@Transactional public final void required() {}
```

3. Usare il contesto seguente, salvato fuori dal target:

```json
{
  "schema": "mana.transaction-context/v1",
  "initialState": "NO_TRANSACTION",
  "entryThroughProxy": false,
  "aspectjWeaving": "ASSUMED_APPLIED",
  "managerCapabilities": {"tx": {"suspend": true, "savepoints": true}}
}
```

4. Eseguire `python3 scripts/mana-transaction.py --project-root <copia>
   --context <contesto> --entry 'selftest.Calls#activeRequired()'
   --output-dir <directory-esterna-nuova>`.

CLI exit 0, modello accettato dal validatore; target immutato:

| Osservazione | Risultato effettivo |
|---|---|
| F1 `activeRequired()` | APPLIED, durante ACTIVE/P1, manager tx |
| F2 `required()` | propagation REQUIRED, interception UNKNOWN / ASPECTJ_METHOD_SHAPE_NOT_MODELED |
| F2 prima | ACTIVE/P1, manager tx |
| F2 durante e dopo | UNKNOWN, physicalId null, manager null |
| Identità / eventi | Una sola P1, nessuna sospensione o savepoint; P1 termina nel frame F1 |
| Diagramma F2 | Regione rossa `METHOD_EXECUTION UNKNOWN`, `interception=UNKNOWN; context=UNKNOWN; UNKNOWN` |

Il modello conserva `previousState`; il difetto riguarda la perdita del contesto
**effettivo durante/dopo**, non la cancellazione del dato storico di ingresso.
Non viene inventato uno stato INACTIVE, ma si perde informazione che R2 richiede
di mantenere separata dall'incertezza sull'advice.

Sotto le stesse premesse condizionali usate dal motore per stabilire P1 nel
chiamante, un advice REQUIRED applicato usa P1 dello stesso manager; se l'advice
non si applica, il corpo vuoto eredita P1. Nessuna alternativa modellata sospende
P1 o crea P2. È quindi possibile mantenere l'intercettazione UNKNOWN e il contesto
ACTIVE/P1, senza affermare weaving runtime, un nuovo scope logico certo o l'esito
della transazione. Il trattamento conservativo delle forme AspectJ fuori dal
sottoinsieme può restare UNKNOWN: non occorre estenderne il supporto per conservare
l'informazione comune alle alternative.

Come controllo separato dal generatore, la review ha sostituito nel solo modello
in memoria `duringState` di F2 con il suo `previousState` e aggiornato
`effectiveContext.during` ad ACTIVE, mantenendo UNKNOWN dell'intercettazione.
Il validatore rifiuta il risultato con
`unknown advice asserted an effective context`: i due assi sono ancora accoppiati
per contratto, oltre che nel generatore. Il probe non è una patch al codice.

Le regole semantiche confrontate sono quelle primarie di
[Spring, Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
e [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html),
consultate durante R2. La deduzione sul controesempio è una conclusione della
review sotto le premesse statiche dichiarate, non una prova runtime Spring.

Per chiudere il finding occorre distinguere incertezza dell'intercettazione,
incertezza del corpo/continuazione e conoscenza del contesto; conservare soltanto
le informazioni valide in tutte le alternative ammesse. Non va applicata una
regola generale UNKNOWN → ACTIVE: REQUIRES_NEW, manager irrisolti, chiamate
programmatiche e altre incertezze possono richiedere risultati differenti.
Servono un oracolo indipendente con P1 già stabilita, un controllo del validatore
e un diagramma che mostri contemporaneamente advice incerto e contesto ereditato.
Questa review non implementa tali cambiamenti.

## Review semantica e degli oracoli

| Area | Esito circoscritto |
|---|---|
| PROXY REQUIRED senza transazione | BYPASSED/INACTIVE; nessun L o P |
| PROXY con P1 ereditata, REQUIRED e REQUIRES_NEW dichiarate | BYPASSED/ACTIVE/P1; nessun L/P aggiuntivo, sospensione o savepoint |
| ASPECTJ REQUIRED condizionale | P1 nasce da assenza iniziale; con chiamante attivo si hanno L1/L2 su P1 |
| ASPECTJ REQUIRES_NEW condizionale | P2 distinta da P1; sospensione/ripristino di P1 con capability esplicita |
| ASPECTJ NESTED condizionale | SP1 sulla stessa P1; nessuna P2 |
| Capability assenti/false | Nessuna sospensione o savepoint inventato; limiti espliciti |
| Weaving non dimostrato | UNKNOWN / ASPECTJ_WEAVING_NOT_ESTABLISHED, nessun falso bypass PROXY |
| Modalità sconosciuta | Resta UNKNOWN anche con ASSUMED_APPLIED |
| UNKNOWN advice con contesto già deducibile | FAIL, R2-F01 |

Sono stati letti R1, F01, il receipt e l'intero delta F01, lo standard, la CLI,
il modello/validatore, il renderer, il parser e gli oracoli di entrambe le suite.
Gli otto oracoli F01 sono aspettative letterali: non vengono generati dal motore.
I test confrontano identità L/P, eventi ordinati, S/SP, siti di chiamata reali e
stati prima/durante/dopo. La copertura UNKNOWN parte però da un chiamante senza
P1: non rileva R2-F01. Il test BYPASSED con contesto iniziale UNKNOWN controlla
un'altra direzione e non colma questa lacuna.

Gli hash dei file elencati nel receipt F01 e del relativo rapporto coincidono con
i file reali; `git apply --reverse --check` sul delta F01 passa senza applicarlo.
Gli otto nuovi modelli coincidono con quelli del receipt salvo `contextEvidence`
(hash diverso della serializzazione JSON esterna); tutti gli otto testi PlantUML
coincidono esattamente. Questa concordanza prova riproducibilità, non completezza.
Le identità P restano simboliche/condizionali e runtimeApplication resta UNKNOWN.
La sola dichiarazione ASPECTJ non abilita il percorso positivo.

## Diagrammi e renderer

Rigenerati otto diagrammi F01, riletti/renderizzati otto modelli storici T01,
aggiunto il diagramma del controesempio: 17 file PlantUML. Tutti passano
`-checkonly`, SVG e PNG; nessun SVG contiene `Syntax Error`. Ispezione visiva degli
otto F01 nel riepilogo e dei dettagli REQUIRES_NEW, NESTED e controesempio.

Le regioni PROXY attive riportano INHERITED P1 anche con REQUIRES_NEW dichiarata;
quelle senza transazione riportano NO_TRANSACTION. REQUIRED AspectJ condizionale
apre P1 quando necessario; REQUIRES_NEW ordina SUSPEND P1 prima di BEGIN P2 ed END
P2 prima di RESUME P1; NESTED usa SP1/P1. Le premesse weaving sono presenti nelle
note e nella legenda. Il caso non dimostrato è rosso/UNKNOWN, senza P inventata.
Il controesempio propaga invece nel diagramma la perdita d'informazione R2-F01.

I gruppi seguono l'annidamento dei metodi; le note BEGIN/END e SUSPEND/RESUME
rappresentano la durata simbolica. La durata trattenuta di P1 sospesa si sovrappone
alla P2, senza implicare un savepoint o esecuzione contemporanea di entrambe.
Il modello di eventi resta il riferimento per l'ordine temporale preciso.

Nelle nuove etichette F01 i valori passano per la whitelist/budget di `label()`;
le direttive strutturali e gli alias sono costruiti dal renderer. Passa il
controllo originale di injection e un probe aggiuntivo sui campi F01: newline,
include e delimitatori di link/immagine non diventano direttive attive. La
whitelist conserva caratteri di URL come testo; questo probe non certifica un
renderer per report arbitrari fuori schema né un motore PlantUML ostile. Nel
percorso CLI reale i nuovi status, reason e weaving sono valori del motore/enumerati.
Non sono emerse nuove possibilità di injection nel delta F01 esaminato.

Jar locale `/Applications/plantuml-1.2024.8.jar`, SHA-256
`b88519d2f37c089a470ee7044ec011a72d130e70a61f7fcaa424179f1c1f4641`.
Nessun download. Rendering, copie target e script della review sono in
`/private/tmp/mana-t01-r2-20261020`; non sono artefatti da integrare nel repository.
Il receipt conserva modelli, PlantUML, sorgente e comandi per riprodurre il finding.

## Verifiche rieseguite

| Verifica | Risultato |
|---|---|
| `python3 tests/transaction-self-invocation.py -v` | PASS, 16 test, zero skipped, exit 0 |
| `python3 tests/transaction-boundaries.py -v` | PASS, 16 test, zero skipped, exit 0 |
| `python3 tests/mana-skill-factory.py -v` | PASS, 23 test, zero skipped, exit 0 |
| `bash scripts/validate-repo.sh` | PASS, exit 0 |
| `bash tests/profile-skill-activation.sh` | PASS, exit 0 |
| Ruff check sui percorsi engine/factory e tre suite | PASS, exit 0 |
| Ruff format --check sugli stessi percorsi | PASS, 11 file, exit 0 |
| `git diff --check` | PASS, exit 0 |
| Verifica inversa del patch F01, senza applicazione | PASS, exit 0 |
| PlantUML interessato, 17 diagrammi | PASS sintassi/SVG/PNG, tutti exit 0 |
| Validazione candidata T01 consegnata | PASS strutturale, exit 0 |
| Controesempio indipendente e probe validatore | FAIL semantico R2-F01; CLI exit 0, modello errato accettato |

La candidata consegnata è stata validata direttamente contro la fixture originale.
Rimane `trustOrigin: generated`, `trusted: false`, `registered: false`,
`executable: false`, approval `pending`. Le regressioni factory/profili verificano
anche mancata discovery/attivazione e rifiuto delle alterazioni di fiducia. Nessuna
candidata è stata attivata. L'analisi usa l'helper JDK parse-only e snapshot esterni;
nessun build/wrapper, processor o classe target è stato eseguito.

## Decisione e stato Git

Branch iniziale e finale: `feature/mana-transaction-01`.
HEAD e `develop` locale: `378243883adb101a7a41feef71e2a66b76e7f508`.
Tree HEAD: `d5b7ae2cf2625ab6a788eb31f5fc62cbe0d39ee4`.
Indice vuoto; working tree intenzionalmente non pulito con il lavoro preesistente
e i soli due nuovi deliverable R2, non staged.

Confrontati contenuti SHA-256 e mode dei 1.204 file iniziali tracked/untracked non
ignorati: nessun file preesistente modificato o rimosso. Anche rapporti R1/F01,
fixture, candidata, roadmap T02 e superfici di discovery restano invariati.
Le cache ignorate eventualmente prodotte dalle validazioni non sono deliverable.
Lo stato Git completo iniziale/finale è nel receipt.

Il diff tracked rispetto alla baseline è stato letto per il contesto della review;
non è stata selezionata una lista di staging o approvato il diff complessivo T01
per l'integrazione. La review positiva è una precondizione non soddisfatta.
Staging, commit firmato, verifica firma/SHA/parent/tree del nuovo commit, controllo
finale dei writer per integrazione, checkout develop e merge `--ff-only`:
**NOT RUN**. SHA del nuovo commit: **nessuno**. Integrazione: **non eseguita**.
Nessun tentativo di firma, rebase, reset, force o push; nessun nuovo worktree.

Nessuna modifica a Familiar o REL-01/A, nessuna implementazione T02. La review
termina con questi deliverable. I PASS delle regressioni mantengono il perimetro
locale e non superano il finding bloccante.

## Limiti per T02

T02 non deve assumere chiuso R2-F01 o usare la perdita del contesto come evidenza
di rilascio/assenza di una risorsa. Occorre prima una correzione autorizzata e una
nuova review del contesto preservato, compresi validatore e diagramma.

Qualunque lavoro futuro deve mantenere distinti scope logici, identità fisiche
simboliche, sospensione, savepoint, intercettazione e stato effettivo. Associazione
manager/risorse, aliasing, acquisizione/ritenzione/rilascio e assunzioni di
concorrenza richiedono un mandato e oracoli propri. Presenza JDBC/JPA o annotazioni
non provano connessioni, lock, blocchi o deadlock runtime. Identità, outcome e
weaving effettivo restano UNKNOWN senza evidenza adeguata; lifecycle candidate e
approvazione umana restano separati dalla validazione tecnica.

Runtime Spring/AspectJ, CI remota, altre piattaforme e campagna generale di
qualificazione: **NOT RUN**. Le evidenze locali non certificano T02/T03 o rilascio.
