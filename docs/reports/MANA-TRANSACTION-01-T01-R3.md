# MANA-TRANSACTION-01-T01-R3 — Semantic Invariants Review

Data: 20 ottobre 2026. Verdetto: **NEEDS_FIX**.

La review indipendente conferma la correzione del controesempio R2 e il comportamento
atteso della matrice richiesta. Resta però un finding HIGH sul validatore: uno
stato ACTIVE/P1 dopo la chiusura della stessa P1 viene accettato. Questo viola I5
e impedisce il consolidamento e l'integrazione della feature. Nessun commit,
merge o correzione d'implementazione è stato eseguito.

[Evidenze R3](MANA-TRANSACTION-01-T01-R3-results.json): valutazione indipendente,
comandi/output/exit code, modelli rigenerati e alterati, script di riproduzione,
ricostruzione pre-F02, verifiche PlantUML, regressioni e manifest di preservazione.

## Indipendenza e metodo

Il revisore `/root/r3_independent_review` è stato avviato dopo autorizzazione
esplicita dell'utente con `fork_turns: none`: non ha ricevuto la cronologia
implementativa F02. Ha operato in sola lettura sul repository e prodotto artefatti
soltanto in `/private/tmp/mana-t01-r3-p9fhppu3/reviewer`.

Ha letto R1, R2, F02, il receipt F02 e lo standard, esaminando direttamente motore,
helper delle alternative, validatore, fixture, oracoli e renderer. Ha rigenerato
via CLI i casi richiesti, aggiunto probe avversari di modello e sorgente, e
controllato separatamente le rappresentazioni PlantUML. I 76 test PASS non sono
stati usati come prova automatica degli invarianti.

Il coordinatore ha eseguito preflight, regressioni, controllo del diff complessivo
e integrità degli input. Ha inoltre ispezionato le evidenze e rieseguito i due
script minimi che provano il finding attuale e la sua presenza pre-F02. Il
verdetto semantico proviene dal revisore indipendente; il coordinatore non lo ha
sostituito con una nuova auto-review dell'implementazione.

## R3-F01 — HIGH, bloccante: afterState può conservare una P già terminata

Posizioni nel working tree revisionato:

- `scripts/skill_factory/transactions/model.py:662-672`: FRAME_EXIT propaga
  l'after-state dichiarato, ma il tracciamento della durata fisica non lo verifica.
- `model.py:700-705`: i frame con composizione ricevono verifiche semantiche
  dell'after-state; il loro chiamante ordinario non riceve un controllo equivalente.
- `model.py:706-726`: i controlli residui verificano forma, referenze e manager,
  senza escludere un'identità che ha già terminato la propria durata.

Il modello `required_active` rigenerato dalla sorgente R2 esatta è corretto:
F1 apre P1, F2 ha advice UNKNOWN ma conserva ACTIVE/P1, e F1 ripristina
NO_TRANSACTION dopo il proprio scope. Si modifica soltanto F1 nel modello in memoria:

```python
f1["afterState"] = copy.deepcopy(f1["duringState"])
f1["effectiveContext"]["after"] = "ACTIVE"
```

Tutti gli altri campi, compresi la composizione corretta di F2 e gli eventi,
restano invariati. `validate_model()` restituisce **True** sia prima sia dopo
questa alterazione.

| Evidenza del modello alterato | Valore |
|---|---|
| Contesto iniziale | NO_TRANSACTION |
| Proprietario di P1 | F1, beginFrame/endFrame F1 |
| Evento 7 | PHYSICAL_END_OUTCOME_UNKNOWN P1 |
| Evento 8 | FRAME_EXIT F1 |
| After-state dichiarato da F1 | TRANSACTION_PHYSICAL / P1 / tx; ACTIVE |
| Validatore | True, modello accettato |
| Risultato atteso | Rifiuto della certezza fisica incompatibile con la durata conclusa |

L'esito UNKNOWN della transazione non prolunga la sua durata simbolica. Dopo
l'evento di fine, il chiamante non può conservare la propria P1 completata come
contesto corrente. Un secondo probe ottiene la stessa accettazione indebita
quando il chiamante ha un figlio non vuoto incerto e `continuation: UNKNOWN`.
Questo dimostra anche che l'incertezza sulla continuazione non protegge la
validazione dalla falsa certezza nell'after-state del chiamante.

Riproduzione minima già eseguita dal revisore e ripetuta dal coordinatore:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 /private/tmp/mana-t01-r3-p9fhppu3/reviewer/validate_after_probe.py
```

Output rilevante:

```text
unmodified generated model: True
initial context: NO_TRANSACTION
forged model accepted: True
```

Il processo termina con exit 0 perché riproduce correttamente il difetto: non è
un PASS semantico. Il receipt conserva anche modello corretto, modello alterato
e script, permettendo di ripetere il controllo senza dipendere dai temporanei.
Nessun modello del repository è stato alterato durante questi probe.

### Attribuzione storica verificata

La lacuna **precede F02**: non è una regressione introdotta dalla correzione.
Il revisore ha ricostruito esternamente il solo `model.py` pre-F02 invertendo la
sua sezione del patch F02. SHA-256 della ricostruzione:
`45bface47f53ebea6dbd12332dd40a0be9d2e0674e39f479bf65d0a10ad721fe`,
identico al `beforeSha256` nel receipt F02. Il vecchio validatore accetta la
stessa alterazione dell'after-state radice su un modello PROXY.

Comando, patch isolato, modello ricostruito, hash e output del replay sono nel
receipt. Il coordinatore ha ripetuto questo replay con exit 0 e verificato
l'hash contro il receipt F02. Nessun file del repository è stato ricostruito o
ripristinato. Il difetto resta rilevante per R3 perché I5 è un requisito della
feature da integrare, anche se la composizione introdotta da F02 è corretta nei
casi mirati.

Per la chiusura serve una correzione autorizzata distinta che verifichi la
coerenza temporale degli stati fisici prima/durante/dopo anche nei frame ordinari
e nei chiamanti, con oracoli negativi su P terminata e continuazione incerta.
Non è stata implementata alcuna correzione in R3.

## Invarianti e matrice indipendente

| Invariante | Esito e perimetro |
|---|---|
| I1 — Indipendenza | PASS sui casi generati mirati: UNKNOWN advice non impone UNKNOWN fisico |
| I2 — Conservazione | PASS sulle alternative ammissibili della matrice richiesta |
| I3 — Prudenza | PASS su identità divergenti ed effetti di ramo dei casi mirati |
| I4 — Identità | PASS sul controesempio R2 esatto e sui probe di conservazione del chiamante |
| I5 — Validazione | **FAIL**, R3-F01: after-state fisicamente impossibile accettato |
| I6 — Rappresentazione | PASS sui diagrammi dei modelli corretti rigenerati, con verifica distinta del renderer |

I PASS sono circoscritti alle evidenze indicate; non sono una prova universale
che il modello rispetti sempre gli invarianti. I5 è sufficiente per NEEDS_FIX.

| Scenario rigenerato via CLI | Risultato indipendente |
|---|---|
| REQUIRED, P1 attiva, advice UNKNOWN | ACTIVE/P1/tx; scope logico IF_APPLIED, nessuna nuova P |
| REQUIRED, nessuna TX iniziale, advice UNKNOWN | Contesto durante UNKNOWN; nessuna transazione comune inventata |
| REQUIRES_NEW, P1 attiva, advice UNKNOWN | ACTIVE/tx, identità corrente null; P1 e identità fresca alternative |
| NESTED, P1 attiva, manager compatibile, advice UNKNOWN | ACTIVE/P1/tx, savepoint IF_APPLIED sulla stessa P1 |
| NESTED, capability ignota | APPLIED irrisolto; nessuna certezza sul savepoint o sull'esito |
| Manager non determinabile | Nessuna identità fisica comune inventata |
| PROXY self-invocation con P1 | BYPASSED, P1 ereditata, nessun nuovo confine |

Verificati inoltre continuazione con chiamata successiva, `return` vuoto,
corpo non vuoto, hazard e async. Sorgente e contesto della regressione R2
corrispondono esattamente al receipt R2 immutabile. Tre controlli negativi separati
vengono correttamente rifiutati: P1 inventata nel caso REQUIRES_NEW, alternativa
BYPASSED mancante e witness di composizione mancante. Questi risultati positivi
non coprono la lacuna nel frame chiamante.

Un probe supplementare sull'accettazione di `outcome: COMMITTED` è conservato nel
receipt del revisore come osservazione non sviluppata né attribuita storicamente.
Non è stato usato per definire un secondo finding o ampliare la review: il
verdetto si fonda sul controesempio R3-F01 completo e riprodotto.

## Renderer ed evidenze PlantUML

Il revisore ha confrontato separatamente le distinzioni dell'IR con il testo
PlantUML degli otto casi rigenerati (sette della matrice più la continuazione).
REQUIRED/P1 mantiene il contesto noto con advice UNKNOWN e scope condizionale;
REQUIRES_NEW mostra PHYSICAL_ID_UNKNOWN e sospensione/ripristino IF_ADVICE_APPLIED;
NESTED mostra il savepoint condizionale sulla stessa P1. La presenza dichiarativa
AspectJ non diventa prova runtime di weaving.

Tutti gli otto diagrammi passano `-checkonly`, SVG e PNG con exit 0; i file
attesi esistono e non contengono Syntax Error. Il revisore ha ispezionato
visivamente REQUIRED/P1, REQUIRES_NEW e NESTED. La JVM ha emesso un warning
CodeCache nel rendering PNG, senza impedire gli otto output; il warning è
conservato integralmente nelle evidenze.

Jar locale `/Applications/plantuml-1.2024.8.jar`, SHA-256
`b88519d2f37c089a470ee7044ec011a72d130e70a61f7fcaa424179f1c1f4641`.
Nessun download o campagna generale. I6 PASS riguarda i modelli corretti:
non trasforma in valido il modello impossibile accettato da I5.

Le regole semantiche sono state confrontate dal revisore con le fonti primarie
[Spring, Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
e [Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).
Queste fonti non dimostrano il runtime dei target analizzati.

## Regressioni e governance

| Verifica rieseguita | Risultato corrente |
|---|---|
| F02 | PASS, 21 test, zero skipped, exit 0 |
| F01 | PASS, 16 test, zero skipped, exit 0 |
| T01 originale | PASS, 16 test, zero skipped, exit 0 |
| Skill Factory | PASS, 23 test, zero skipped, exit 0 |
| Validazione repository e profili | PASS, exit 0 |
| Ruff check e format --check | PASS, exit 0 |
| `git diff --check` | PASS, exit 0 |
| Verifica inversa patch F02 | PASS, exit 0, nessuna applicazione |
| Validazione candidata consegnata | PASS strutturale, exit 0 |
| Matrice indipendente, probe sorgente e rendering mirato | PASS con il perimetro descritto |
| R3-F01, replay corrente e pre-F02 | **FAIL semantico**, modello alterato accettato; replay exit 0 |

Gli hash dei 15 file d'implementazione indicati nel receipt F02 e del rapporto
F02 corrispondono al working tree. La candidata resta generated,
trusted/registered/executable false, approval pending; nessuna attivazione.
Nessuna nuova qualifica runtime Spring/AspectJ, CI remota o altra piattaforma.

## Diff complessivo, preservazione e decisione Git

Il coordinatore ha inventariato il diff rispetto alla baseline, inclusi gli
untracked: nove file tracked modificati e 68 untracked correnti, compresi i due
deliverable R3. Il perimetro è T01 (engine, test, esempi, evidenze, standard,
adapter/template e workflow) con la proposta T02 preesistente; nessuna
implementazione T02 o artefatto temporaneo è stato selezionato per il repository.
Questa verifica di perimetro non equivale all'approvazione semantica del diff.

Branch iniziale e finale: `feature/mana-transaction-01`.
HEAD e develop locale: `378243883adb101a7a41feef71e2a66b76e7f508`.
Tree HEAD: `d5b7ae2cf2625ab6a788eb31f5fc62cbe0d39ee4`. Indice vuoto.

I 1.219 file iniziali tracked/untracked non ignorati conservano contenuti SHA-256
e mode; nessuno è rimosso. Sono aggiunti soltanto questo rapporto e il receipt R3.
Le modifiche T01 precedenti a F02, F02 stessa e tutte le evidenze storiche restano
presenti e immutate. Working tree intenzionalmente non pulito e non staged.
Il receipt conserva stato Git completo e manifest prima/dopo.

Poiché manca la review positiva, staging, commit atomico firmato, verifica della
nuova firma/SHA/parent/tree, verifica finale dei writer per integrazione, checkout
develop e merge `--ff-only` sono **NOT RUN**. SHA del nuovo commit: **nessuno**.
Integrazione: **non eseguita**. Nessun tentativo di firma, rebase, reset, force o
push; nessun nuovo worktree, modifica a Familiar/REL-01/A o attivazione di skill.

T02 non deve assumere validato l'after-state del chiamante o usarlo come prova
di ritenzione/rilascio di una risorsa. Serve prima chiudere R3-F01 e ripetere la
review pertinente. Identità runtime, esiti, risorse/lock, concorrenza e deadlock
rimangono fuori dalle evidenze statiche T01. R3 termina con questa consegna.
