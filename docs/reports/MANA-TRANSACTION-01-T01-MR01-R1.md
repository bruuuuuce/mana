# MANA-TRANSACTION-01-T01-MR01-R1 — Contract Conformance Review

Data: 20 ottobre 2026. Verdetto: **NEEDS_FIX**. **T01 non integrato.**

I tre positivi storici R4 sono tutti **LEGITIMATELY_REJECTED**. Non è stata
riscontrata una falsa restrizione nei positivi MR00 esaminati. La review ha però
isolato due false accettazioni del validatore: premesse proxy incompatibili con
AspectJ in un frame UNKNOWN e una chiamata figlia affermata dopo la perdita
dell'ordine di esecuzione. Questi controesempi impediscono la conformance MR00,
anche se tutte le suite consegnate passano. Nessuna correzione implementata.

Risultati e ricevuta Git: [receipt indipendente](MANA-TRANSACTION-01-T01-MR01-R1-results.json).
Input, sorgenti sintetiche e riproduzione: [evidenze](MANA-TRANSACTION-01-T01-MR01-R1-evidence/independent-replay.json),
[script](MANA-TRANSACTION-01-T01-MR01-R1-evidence/replay.py).

## Indipendenza, autorità e metodo

Review svolta in un nuovo contesto, senza partecipazione all'implementazione MR01.
Tre contesti read-only separati hanno esaminato input R4, oracoli e coerenza
motore/validatore; il coordinatore ha letto codice e fonti e riprodotto i finding.
Le conclusioni non sono ricavate dal solo handoff o dal conteggio dei test.

Letti contratto e CSV MR00, report/receipt/coverage MR01 e report/receipt R4;
esaminati direttamente `model.py`, `alternatives.py`, `plantuml.py`, CLI, fixture,
test e collegamenti ai controlli repository. Le attese derivano dalle regole MR00
e dallo standard v1 incorporato da MR00, non dall'output del motore. I nuovi
witness sono IR sintetici forniti: nessuna pretesa di parsing o esecuzione Java.
Per il secondo finding sono stati aggiornati sorgente, span e hash concordanti.

Il confronto AST di `build`, ricostruendo in una copia temporanea esterna la
versione precedente tramite il patch MR01 consegnato, conferma che il corpo del
generatore è invariato. Questo controllo non sostituisce la review del validatore.

## Finding bloccanti

### R1-F01 — Premesse proxy contraddittorie accettate in UNKNOWN

Partire separatamente dai positivi coerenti **O27/O28/O29**, rispettivamente
REQUIRED/REQUIRES_NEW/NESTED. In F2 cambiare soltanto la coppia:

```python
model['frames'][1]['proxy'].update(
    crossed=True, reason='SCENARIO_PROXY_CALL')
```

Lo scenario resta ASPECTJ/ASSUMED_APPLIED. F2 resta UNKNOWN con witness F02.
Attesa indipendente: **REJECT**. Esito effettivo: **ACCEPT in tutti e tre i casi**;
le baseline valide sono accettate. I tre diagrammi risultano byte-identici alle
rispettive baseline, nascondendo la premessa incompatibile.

Norma: [standard v1, Bounded Resolution](../standards/transaction-model-v1.md#bounded-resolution),
righe 198–208: in uno scenario AspectJ `proxy.crossed` è false e il motivo è
`NOT_APPLICABLE_ASPECTJ`. La regola preesiste a MR01. MR00 §§1/5/6 incorpora lo
standard, distingue le premesse AOP e richiede tutti i vincoli, inclusi i campi
additivi (V1). Non basta verificare correttamente l'intersezione fisica F02.

Causa: `model.py:691` verifica le premesse APPLIED, mentre il percorso con
`contextComposition` ritorna a `model.py:756` senza controllare la coppia proxy
del frame UNKNOWN. `validate_composition` verifica modalità/reason dell'advice,
non quella coppia. I payload sono salvati come `O27/O28/O29-aspectj-proxy-contradiction.json`.
Gravità **HIGH per conformance/provenienza**; non è dimostrato un effetto fisico
transazionale errato da questa sola mutazione.

### R1-F02 — Figlio affermato dopo una chiamata irrisolta

Partire da O02. Nel sorgente sintetico di F1 inserire `System.gc();` prima di
`other.inner();`, ricalcolando hash e span. Registrare il corrispondente
`UNRESOLVED_CALL` F1 dopo l'apertura L1 e prima di FRAME_ENTER F2, con uncertainty
source-linked. Impostare continuazione e after di F1 a UNKNOWN, conservando il
figlio F2 e il suo previous certo P1.

Attesa indipendente: **REJECT**. Esito effettivo: **ACCEPT**. Il renderer scrive
«remaining order NOT ASSERTED» e poi disegna proprio F2 come chiamata condizionale
eseguita con P1 ereditata. Il witness contiene entrambe le chiamate nel sorgente;
non dipende da hash mancanti o da un evento inserito senza riscontro sorgente.
Non si sostiene che `System.gc()` modifichi una transazione: il limite è quello
esplicitamente dichiarato dall'IR e dal sottoinsieme statico.

Norma: MR00 §2 (continuazioni irrisolte), §4 D4 e §6 V4/V10; standard v1,
Bounded Resolution, mantiene UNKNOWN per chiamate irrisolte e interrompe la
continuazione certa. Il motore effettivo a `model.py:535–554` interrompe il
traversal alla prima chiamata irrisolta. Il validatore a `model.py:738–750` usa
quell'evento per giustificare after UNKNOWN, ma a `model.py:922–942` controlla
soltanto che chiamate e figli stiano tra apertura e chiusura, senza vietare figli
successivi alla perdita dell'ordine. UNKNOWN finale nasconde così una certezza
intermedia ingiustificata. Payload:
[O02-child-after-unresolved-call.json](MANA-TRANSACTION-01-T01-MR01-R1-evidence/O02-child-after-unresolved-call.json).
Gravità **HIGH**. Questo caso dimostra che il validatore può accettare un errore
di traversal che il motore attuale evita; non è provata una regressione del motore.

Riproduzione di entrambi i finding, dalla root, con output esterno nuovo:

```sh
python3 docs/reports/MANA-TRANSACTION-01-T01-MR01-R1-evidence/replay.py "$PWD" /private/tmp/mana-mr01-r1-replay
```

Lo script stampa quattro false accettazioni: tre varianti R1-F01 e una R1-F02.
Queste sono evidenze di FAIL della review, non test/oracoli modificati per passare.

## Disposizione dei tre positivi R4

Recuperati i JSON originali da `R4-results.json#/reviewArtifacts`, senza riparare
gli input. La serializzazione indent=2 con newline coincide per byte count e
SHA-256 con `reviewExternalManifest`. Copie e sorgente storico `Review.java` sono
nelle evidenze R1; il receipt storico rimane immutato.

| Input originale | SHA-256 originale verificato | Disposizione |
|---|---|---|
| hand-unknown-REQUIRED.json | `25e58405e3094bd0268167b51595907d1e843e70510993cc5fe8f91808d5ddc7` | LEGITIMATELY_REJECTED |
| hand-unknown-NESTED.json | `a3d99613bef23b6d636434405b343427ab8b4a946923416bdc6ccff8217a8850` | LEGITIMATELY_REJECTED |
| hand-unknown-REQUIRES_NEW.json | `5187c67b23a1c2764fc0834bdb3ad81efbd9729d29dbcbc4cce09b01b6a9cf2f` | LEGITIMATELY_REJECTED |

In **ciascuno** dei tre input le premesse dichiarate sono:

- Scenario globale `interceptionMode=ASPECTJ`, weaving `ASSUMED_APPLIED`.
- F1: `APPLIED/SCENARIO_PROXY_CALL`, `proxy.mode=CLASS`, `crossed=true` e motivo
  `SCENARIO_PROXY_CALL`.
- F2: advice UNKNOWN per forma AspectJ non modellata, con le alternative F02
  della rispettiva propagation; anch'esso conserva metadati proxy incompatibili.

Per ciascun caso il rifiuto corrente avviene su **F1** con
`applied interception lacks compatible scenario evidence`. La contraddizione è
reale nella premessa AOP del caller: lo stesso scenario T01 non può dichiarare
applicazione proxy di F1 come prova in modalità globale AspectJ. Non è un rifiuto
della proprietà fisica comune REQUIRED/NESTED o della distinzione NEW di F2.
O27/O28/O29 coerenti verificano positivamente queste tre configurazioni.

Riferimento normativo per tutti e tre: standard v1, righe 198–208; MR00 §1,
§5 e D3. La [documentazione ufficiale Spring](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
conferma la distinzione tra modalità proxy e weaving AspectJ. Configurazioni
Spring più generali con advisor multipli non sono una configurazione positiva
aggiunta al sottoinsieme T01 a singola modalità: non rendono coerenti questi IR.
Il piccolo `Review.java` storico non fornisce una prova runtime AOP alternativa.

Nessun caso è classificato VALID_CASE_REGRESSED o CONTRACT_AMBIGUITY. Le tre
vecchie attese positive restano tre divergenze storiche esplicite; non sono
riscritte né contate come tre regressioni PASS. R1-F01 è un finding distinto,
ottenuto da input MR00 coerenti con una mutazione isolata del figlio.

## Oracoli e coerenza semantica

I 44 oracoli contengono **18 ACCEPT e 26 REJECT**; O13 ha anche una variante
legacy. Attese, ID, transizione e delta coincidono con il CSV normativo. Il loader
passa IR forniti direttamente a `validate_model`, verifica la diagnostica
semantica e l'immutabilità dell'input; non usa build/compose/renderer per l'attesa.
I 26 negativi e la variante legacy falliscono per capability, effetti,
ownership, lifetime, intersezione o intercettazione pertinenti, non per errori
accidentali di forma. Gli otto positivi supplementari coprono le righe non
esemplificate positivamente dai 44: **24/24 transizioni** hanno un input pertinente.

| Vincoli | Esito circoscritto della review |
|---|---|
| V1 | FAIL complessivo: envelope e riferimenti dei casi passano, ma R1-F01 ammette premesse additive AOP contraddittorie |
| V2/V3 | PASS sui casi: capability concordi, manager selezionato, insieme chiuso di effetti; nessuna capability inutilizzata richiesta da N |
| V4/V10 | FAIL complessivo per R1-F02; prefisso, chiusure e ritorni dei casi normativi passano |
| V5/V8/V9 | PASS sui witness: ownership, terminali, divieto di riuso e conservazione della P antenata |
| V6 | PASS sul replay esaminato e sul nuovo positivo a tre frame con S1/S2, ripristino S2 poi S1; prova limitata a quel witness |
| V7 | PASS: NESTED usa SP sulla stessa P; NEW crea P distinta e sospende/riprende; scambi rifiutati |
| V11 | PASS sulle intersezioni dei casi F02; non sana il difetto di premesse AOP di V1 |
| V12 | PASS sui controlli mirati: identità simboliche e outcome/weaving runtime UNKNOWN |
| D2/D3 | Marcatore UNKNOWN/null distinto da scope eseguito; legacy non certificato dalla sola annotazione/effetti |
| D4 | Bare UNKNOWN e effetti fisici impossibili dei test sono rifiutati; insufficiente sul seguito della continuazione in R1-F02 |

I sei confini APPLIED T01–T06 sono coerenti nei positivi: REQUIRED condiviso
chiude soltanto L; NEW separa S/P2/resume; NESTED conserva P1 con SP; i casi da N
aprono/terminano la P posseduta senza capability non usate. Il validatore non
richiama il generatore per decidere questi esiti. R1-F02 resta la divergenza
bloccante tra le due superfici.

Due precisazioni non bloccanti sul materiale MR01: la riga V6 della coverage
attribuisceva prova LIFO a fixture con al massimo una sospensione; il nuovo
witness R1 a tre frame la esercita direttamente. La descrizione O17 menziona un
frame successivo, mentre il payload duplica BEGIN nello stesso frame: verifica
comunque il divieto di riuso, senza provare da sola quel testo più ampio.
Nessuna coverage o fixture storica è stata corretta retroattivamente.

## Verifiche eseguite

| Controllo indipendente corrente | Risultato |
|---|---|
| MR01 | PASS, 64 test, zero skipped |
| T01/F01/F02/F03/factory | PASS, 16 + 16 + 21 + 19 + 23; totale richiesto **159**, zero skipped |
| Nove controesempi HIGH R4 originali | PASS del rifiuto atteso, 9/9; diagnostiche semantiche nel receipt |
| 44 oracoli + otto positivi supplementari | 52 righe / 53 payload con variante legacy, tutte le attese soddisfatte |
| Repository / profili | PASS, exit 0 per entrambi |
| Ruff check / format --check | PASS, exit 0, 15 file formattati |
| PlantUML pertinente | PASS: O02/O04/O06/O28/O29/O33/O42, sette sintassi + sette SVG + sette PNG |
| Ispezione PNG diretta | O04 NEW, O06 NESTED, O28 alternative NEW, O33 D2; nessun difetto distinto su questi diagrammi validi |
| Governance candidata | PASS strutturale: generated; trusted/registered/executable false; approval pending; profili PASS |
| Positivo NEW a tre frame | ACCEPT: P1/P2/P3, S1/S2, termine P3 prima di resume P2, termine P2 prima di resume P1 |
| Nuovi witness di review | **FAIL semantico**: quattro accettazioni indebite, due finding |
| Preservazione / whitespace | Manifest iniziale invariato; `git diff --check` PASS |

Jar locale `/Applications/plantuml-1.2024.8.jar`, hash nel receipt. Nessun download,
nuova campagna QA generale o runtime Spring richiesto. Rendering corretto sui
positivi non qualifica gli IR contraddittori. CI remota e runtime restano NOT RUN.

## Git, integrazione e arresto

Branch iniziale/finale `feature/mana-transaction-01`; HEAD e develop locale
invariati a `378243883adb101a7a41feef71e2a66b76e7f508`; tree HEAD
`d5b7ae2cf2625ab6a788eb31f5fc62cbe0d39ee4`. Indice vuoto e invariato.
Il manifest dei **1.237 file iniziali** tracked/untracked non ignorati conserva
hash e mode: tutto il lavoro preesistente, inclusi MR00/MR01/R4, candidata e
proposta T02, è preservato. Aggiunti soltanto questo rapporto, receipt e witness R1.

Review positiva non ottenuta: selezione finale del diff completo d'integrazione,
precondizioni develop pulito/writer, commit firmato, verifica firma/parent/nuovo
tree e merge ff-only sono **NOT RUN per condizione non soddisfatta**. Nessun nuovo
commit SHA né ricevuta di integrazione positiva. La ricevuta Git registra invece
branch, HEAD, develop, tree, indice e manifest invariati. Nessun checkout,
staging, merge, push, force, reset, rebase o nuovo worktree.

Nessuna skill candidata attivata; nessuna modifica a Familiar, REL-01/A o T02.
Prima di fondare T02 sul validatore occorre correggere e riesaminare questi due
finding. Identità/outcome runtime, weaving effettivo, driver, commit/rollback,
percorsi d'eccezione, risorse/lock/concorrenza/deadlock restano fuori da questa
prova statica. T02 non è implementato. **Arresto alla consegna R1.**
