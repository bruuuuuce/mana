# MANA-TRANSACTION-01-T01-R1 — Independent Review & Integration

Data: 20 ottobre 2026. Verdetto: **NEEDS_FIX**.

La review indipendente ha confermato un difetto bloccante nella gestione delle
configurazioni AspectJ fuori perimetro. Le regressioni richieste passano, ma non
coprono questo percorso. Al primo blocco confermato l'attività di review è stata
fermata, senza modificare l'implementazione. Nessun commit o merge è stato creato.

Evidenze riproducibili, comandi, exit code, output integrali delle regressioni,
hash degli input e modello del controesempio sono conservati in
[MANA-TRANSACTION-01-T01-R1-results.json](MANA-TRANSACTION-01-T01-R1-results.json).
Il precedente rapporto T01 e le sue evidenze sono rimasti immutati.

## R1-F01 — HIGH, bloccante: AspectJ riceve la semantica di bypass dei proxy

Posizioni: `scripts/skill_factory/transactions/model.py:80`, `:280`, `:311`.

Una configurazione esplicita `AdviceMode.ASPECTJ` lascia `proxy_mode` a `UNKNOWN`.
Tuttavia `crossing is False` abilita incondizionatamente il bypass delle annotazioni.
La verifica di modalità/visibilità si trova soltanto nel ramo `conf and not bypass`.
Un'entry non annotata che chiama un proprio metodo annotato può quindi attraversare
questi controlli senza alcuna incertezza e ottenere uno stato `NO_TRANSACTION`.

Riproduzione effettuata su una copia esterna della fixture, senza modificare il
repository o la fixture originale:

1. Copiare `tests/fixtures/transaction-boundaries` in una directory esterna.
2. In `Scenario.java`, sostituire
   `@EnableTransactionManagement(proxyTargetClass = true)` con
   `@EnableTransactionManagement(mode = org.springframework.context.annotation.AdviceMode.ASPECTJ, proxyTargetClass = true)`.
3. In `context.json`, impostare `entryThroughProxy` a `false`, mantenendo
   `initialState: NO_TRANSACTION` e le capability originali. L'assenza di un proxy
   è coerente con la configurazione AspectJ e non dimostra l'assenza di advice.
4. Invocare la CLI con entry `fixture.A#selfOutside()` e output esterno nuovo.

Il sorgente attraversato è già presente nella fixture:

```java
public void selfOutside() { this.localNew(); }
@Transactional(propagation = Propagation.REQUIRES_NEW) public void localNew() {}
```

Risultato effettivo, exit code 0:

| Campo | Risultato |
|---|---|
| status | CONDITIONAL_STATIC_SCENARIO |
| proxyMode | UNKNOWN |
| F1 selfOutside | CONDITIONAL, NO_TRANSACTION |
| F2 localNew | CONDITIONAL, NO_TRANSACTION, SELF_OR_DIRECT_CALL |
| uncertainties | array vuoto |
| logicalScopes / physicalTransactions | entrambi vuoti |

Anche il diagramma dichiara `CONDITIONAL_CALL` e `NO_TRANSACTION`, senza una regione
di incertezza per AspectJ. La sola proprietà globale `proxyMode: UNKNOWN` non limita
le conclusioni dei frame e non spiega che il bypass è inapplicabile.

Spring distingue le chiamate interne non intercettate dai proxy dall'advice tramite
weaving AspectJ, che può applicarsi anche alle self-invocation. Il risultato atteso
per T01 è un esito esplicitamente `UNKNOWN`/`UNSUPPORTED` sul confine interessato,
senza dedurre il bypass dei proxy. Non è richiesto implementare AspectJ o affermare
che una transazione runtime sia effettivamente avvenuta: classpath e weaving non
sono provati da questa analisi. Riferimento primario consultato:
[Spring, Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).

Il caso viola il requisito R1 di limitare esplicitamente le configurazioni fuori
perimetro e il contratto locale che assegna `UNKNOWN` alle impostazioni proxy non
risolte. Le condizioni dichiarate non giustificano la conclusione non transazionale.

Per la chiusura del finding serve una correzione autorizzata distinta e una
regressione indipendente per entry non annotata → self-invocation annotata con
AspectJ, mantenendo il controllo positivo equivalente in modalità PROXY. Non è
stata applicata alcuna correzione né aggiunto un test al repository durante R1.

## Risultati delle regressioni rieseguite

| Verifica | Risultato corrente |
|---|---|
| `python3 tests/transaction-boundaries.py -v` | PASS, 16 test, nessuno skipped, exit 0 |
| `python3 tests/mana-skill-factory.py -v` | PASS, 23 test, exit 0 |
| `scripts/validate-repo.sh` | PASS, exit 0 |
| `tests/profile-skill-activation.sh` | PASS, exit 0 |
| `ruff check scripts/mana-transaction.py scripts/skill_factory tests/mana-skill-factory.py tests/transaction-boundaries.py` | PASS, exit 0 |
| `ruff format --check` sugli stessi percorsi | PASS, 10 file, exit 0 |
| `git diff --check` | PASS, exit 0 |
| PlantUML sulle otto fixture generate dai test | PASS, sintassi/SVG e controllo negativo |
| PlantUML sugli otto `.puml` consegnati | PASS, `-checkonly`, `-tsvg`, `-tpng`, tutti exit 0 |
| Controesempio indipendente AspectJ | FAIL semantico: risultato non limitato; CLI exit 0 |

Rendering eseguito con il jar locale `/Applications/plantuml-1.2024.8.jar`, hash
SHA-256 `b88519d2f37c089a470ee7044ec011a72d130e70a61f7fcaa424179f1c1f4641`.
Nessun download. Il rendering PNG ha emesso un warning JVM CodeCache non fatale;
tutti gli otto PNG e SVG sono stati prodotti. I PNG sono stati aperti e ispezionati.
Le copie di rendering sono esterne, in
`/private/tmp/mana-t01-r1-20261020/rendered`, e non sono aggiunte al versionamento.

## Modello e diagrammi: evidenze raccolte prima dello stop

Sono stati letti il rapporto T01, lo standard del modello, entrambe le roadmap,
il motore, il parser JDK, il renderer, il punto d'ingresso CLI e l'adapter factory.
La review ha esaminato codice effettivo, fixture e output, senza affidarsi al solo
rapporto precedente.

Gli oracoli contengono valori attesi letterali e riferimenti a espressioni/callee
del sorgente; non invocano il motore per produrre le aspettative. I casi principali
sono stati confrontati anche manualmente con il sorgente e le regole di propagazione
documentate da [Spring](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html).
I test basati su mutazioni dei facts restano controlli aggiuntivi, non sostituiscono
gli oracoli. La regressione AspectJ dimostra comunque che la copertura è incompleta.

| Diagramma | Confronto semantico e visivo con fixture/oracolo |
|---|---|
| required | L1/L2 distinti, P1 condivisa, nessuna seconda apertura fisica |
| requires_new | P1/P2 distinti; SUSPEND P1 prima di BEGIN P2, END P2 prima di RESUME P1 |
| nested | SP1 sulla stessa P1; nessuna P2 |
| outside | Entry NO_TRANSACTION; P1 nasce nella chiamata a B REQUIRED |
| inherited | B non annotato eredita P1 senza aggiungere L |
| self_invocation | In modalità PROXY, localNew eredita P1, senza L/P nuovi |
| unsupported_propagation | SUPPORTS esplicitamente non modellata, corpo/continuazione incerti |
| capability_unknown | NESTED con capability mancante resta UNKNOWN, senza savepoint inventato |

Per tutti gli otto modelli consegnati sono stati rieseguiti il validatore, il
confronto delle identità L/P e dei conteggi SP/S con gli oracoli e il confronto
esatto fra `.puml` e rendering del relativo JSON. Gli eventi del JSON compaiono
nel diagramma nel rispettivo ordine. Sono stati ispezionati chiamate, gruppi,
legende, note di sospensione/ripristino e savepoint nelle immagini renderizzate.

I gruppi rappresentano l'annidamento dei metodi; le note descrivono la durata
fisica e la sovrapposizione della P1 sospesa con P2. Questo limite geometrico è
esplicito e leggibile. Le identità restano simboliche e l'esito commit/rollback
UNKNOWN; non emerge una prova runtime dalle fixture.

Il codice e le regressioni coprono inoltre NESTED senza transazione precedente
(apertura di P senza SP), capability savepoint false rispetto a sconosciute,
contesto iniziale UNKNOWN, annotazione di metodo rispetto alla classe, manager
ambigui, dispatch irrisolto, visibilità, async e controllo di flusso fuori perimetro.
La distinzione NO_TRANSACTION/UNKNOWN non regge però nel controesempio R1-F01;
queste osservazioni positive non costituiscono accettazione globale del motore.

## Governance, isolamento e stringhe PlantUML

Nel percorso esaminato la factory mantiene il lifecycle nel proprio host e
l'adapter espone il contratto di dominio. Generazione/validazione non chiamano
l'analizzatore. La candidata consegnata conserva `trustOrigin: generated`,
`trusted: false`, `registered: false`, `executable: false`, approvazione `pending`.
I 23 test factory passano anche per separazione dalle superfici di discovery,
contratti di output e rifiuto di alterazioni della fiducia.

L'analizzatore usa snapshot esterni e compila soltanto l'helper Mana fisso.
L'helper chiama `JavacTask.parse()`, senza attribution, generazione, caricamento
di classi target o processor; non invoca build/wrapper del target. Sono passati
i controlli di argomenti subprocess, directory temporanee, mancata esecuzione
wrapper e osservazione delle scritture. La copia target del controesempio ha
mantenuto identici tutti gli hash prima/dopo l'analisi.

Il renderer costruisce alias dei partecipanti autonomamente e tratta i valori
derivati dai sorgenti con una whitelist e un limite di lunghezza. La whitelist
rimuove newline, virgolette, `!`, `@` e delimitatori di link/markup. Le direttive
del documento sono costanti; i tipi di evento provengono dal motore. Nel percorso
CLI esaminato non è emerso un canale per introdurre direttive PlantUML, include o
riferimenti esterni attivi tramite i dati sorgente. La CLI non avvia PlantUML.
La qualifica non copre un report arbitrario passato direttamente a `render()` da
un chiamante esterno: l'oggetto esaminato è quello costruito dal motore.

Queste verifiche assumono tool JDK/framework fidati e filesystem stabile, come
dichiarato dal contratto; non qualificano una sandbox contro tool ostili. Non è
stata introdotta infrastruttura di sicurezza.

## Git e consolidamento

Branch iniziale e finale: `feature/mana-transaction-01`.

HEAD e `develop` locale sono rimasti entrambi a
`378243883adb101a7a41feef71e2a66b76e7f508`.
Tree del commit HEAD: `d5b7ae2cf2625ab6a788eb31f5fc62cbe0d39ee4`.
L'indice è rimasto vuoto. Il working tree resta intenzionalmente non pulito:
contiene tutte le modifiche T01 preesistenti, più questo rapporto e il relativo
file risultati R1, entrambi non staged.

Il confronto SHA-256 dei 1.190 file inventariati prima delle regressioni conferma
che nessun contenuto preesistente è stato alterato. Il manifest iniziale include
file tracked e untracked non ignorati; gli hash degli input modificati/untracked
sono nel receipt R1. Le validazioni possono produrre cache Python ignorate.

Consolidamento, selezione dello staging, commit atomico firmato, verifica della
nuova firma/SHA/parent/tree, merge `--ff-only` e verifica del working tree integrato
pulito: **NOT RUN**, perché la review positiva richiesta come precondizione non è
stata ottenuta. SHA del nuovo commit: **nessuno**. Nessun tentativo di firma.

Non sono stati creati worktree, effettuati push, modificati Familiar o REL-01/A,
attivate candidate o implementati T02/T03. Lo stato Git finale completo è nel
receipt R1.

## Limiti residui e indicazioni per T02

La review è terminata al primo difetto bloccante; non certifica assenza di altri
difetti. Suite zero-token completa, CI remota, altre piattaforme e runtime
Spring/AspectJ: **NOT RUN**. Il PASS locale delle regressioni conserva il proprio
perimetro e non diventa accettazione dell'engine o della candidata.

Prima di fondare T02 su questo modello occorre chiudere R1-F01 e ripetere la review
del confine AOP. Per T02 restano da concordare API risorse, aliasing, associazione
manager/risorse e assunzioni di concorrenza. Le osservazioni statiche non devono
diventare certezze su lock, connessioni runtime o deadlock. La roadmap T02 resta
una proposta separata, senza implementazione o autorizzazione implicita da R1.
