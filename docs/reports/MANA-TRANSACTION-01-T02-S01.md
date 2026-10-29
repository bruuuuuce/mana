# MANA-TRANSACTION-01-T02-S01 — Resource Timeline Foundation

Data: 21 ottobre 2026. Verdetto: **IMPLEMENTED_READY_FOR_REVIEW**.
Implementazione e verifica locale; review indipendente e qualificazione runtime
non eseguite. Nessuna diagnosi definitiva di deadlock.

## Preflight, classificazione e salvaguardia

Branch iniziale `develop`, HEAD
`e3537e3f8c8329a71615fe59d496757d5392c6a8`, indice vuoto: corrispondono
al mandato. Sei file locali, tutti classificati prima delle modifiche:

| Stato iniziale | Percorso | Classificazione e disposizione |
|---|---|---|
| M | `docs/roadmap/TRANSACTION-01.md` | Solo riferimento alla proposta T02; preservato byte per byte |
| ?? | `docs/roadmap/TRANSACTION-01-T02.md` | Proposta T02 preesistente; preservata byte per byte |
| M | `docs/reports/MANA-TRANSACTION-01-T01-MR00-transitions.csv` | 69 CRLF; normalizzazione virtuale uguale al blob HEAD; nessuna variazione di contenuto |
| M | `docs/reports/MANA-TRANSACTION-01-T01-MR01-coverage.csv` | 92 CRLF; normalizzazione virtuale uguale al blob HEAD; nessuna variazione di contenuto |
| ?? | `docs/reports/MANA-TRANSACTION-01-T01-MR01-R2.md` | Deliverable storico R2, escluso dall'incremento S01 |
| ?? | `docs/reports/MANA-TRANSACTION-01-T01-MR01-R2-results.json` | Receipt storico R2, escluso dall'incremento S01 |

La classificazione deriva dalla lettura dei materiali e dal confronto con HEAD,
non dai soli nomi. Nessun codice T02 preesistente è presente nei sei file. La
proposta generale lascia intenzionalmente non risolti datasource, ownership e
runtime: S01 qualifica soltanto i pattern esplicitati nello standard nuovo.

Copia persistente esterna, eseguita prima di creare il branch:
`/Users/zel/mana-evidence/MANA-TRANSACTION-01-T02-S01-preflight-20261021T172507Z`.
Contiene tutti e sei i file e `manifest.json` con byte, mode e SHA-256.
Verificata uguaglianza integrale originale/copia, poi riletti manifest e hash.
Il receipt S01 registra anche la verifica finale dei sei originali e delle copie.
Nessun CSV è stato riscritto o normalizzato; i due materiali T02 iniziali non
sono stati modificati. I report R2 restano untracked, separati dalla consegna S01.

Creato `feature/mana-transaction-02` dall'HEAD corrente mantenendo i file locali.
HEAD finale invariato, indice ancora vuoto. Nessun commit, merge, push, worktree,
stash, reset, clean o ripristino. Nessuna modifica a Familiar, REL-01/A, skill,
configurazioni di attivazione o progetti target.

## Consegna e integrazione

- [Resource Timeline Model v1](../standards/resource-timeline-model-v1.md):
  contratto, grammatica supportata, causalità, certezza e limiti.
- `scripts/mana-resource-timeline.py` e
  `scripts/skill_factory/transactions/resources.py`: CLI esplicita e proiezione
  verificabile che ingloba il Transaction Model v1 senza alterarlo.
- [Esempi strutturati](../examples/transaction-01-t02-s01/README.md):
  REQUIRES_NEW, NESTED e operazione non transazionale.
- `tests/resource-timeline.py`, fixture sorgenti e oracoli letterali indipendenti
  in `tests/fixtures/resource-timeline`.
- [Proposta T02-S02](../roadmap/TRANSACTION-01-T02-S02.md): analisi condizionale
  delle dipendenze di attesa; nessuna esecuzione S02 autorizzata o avviata.
- [Receipt S01](MANA-TRANSACTION-01-T02-S01-results.json): comandi, exit,
  output dei controlli, hash dei deliverable e verifica della conservazione.

T01 resta l'unica autorità per identità P, scope L, propagation, sospensioni,
savepoint, lifetime e intercettazione UNKNOWN. La modifica Python a T01 espone
facoltativamente anche i fatti del medesimo snapshot (`include_facts=True`);
la firma precedente continua a restituire il solo modello. L'estrattore JDK
aggiunge ai fatti delle chiamate tipo/valore letterale e posizione degli argomenti.
Nessuna modifica al composer, al validatore semantico T01 o al suo renderer.
Il controllo repository include i nuovi file Python.

Ogni osservazione distingue metodo/call site, API, sintassi SQL, identificatore
lessicale, contesto P/manager, datasource, certezza ed evidenze con hash/offset.
Il datasource e l'enlistment restano UNKNOWN in S01. Una P contestuale non prova
la partecipazione del JDBC a quella transazione. READ/WRITE non sono lock mode;
FOR UPDATE è una richiesta osservata nel sorgente, non un lock acquisito.
Granularità riga/tabella e identità runtime restano UNKNOWN.

La timeline avvolge tutti gli eventi T01 senza cambiarli e inserisce le operazioni
posizionabili immediatamente prima della frontiera UNRESOLVED_CALL di T01.
Il seguito resta UNKNOWN. Corpi non attraversati, async e suffissi irrisolti
possono conservare sintassi JDBC come UNPLACED, senza P, manager o evento
cronologico. Non vengono attraversati nuovi corpi per completare il percorso.

La proiezione usa il contesto T01 aggiornato dopo i figli risolti: dopo la fine
di un REQUIRES_NEW vuoto, una successiva operazione usa P1 ripristinata, mai P2
terminata. Durante REQUIRES_NEW P1 rimane viva ma sospesa; l'operazione interna
usa P2. NESTED mantiene P1 e il savepoint non ne termina il lifetime. Non sono
dedotti commit, rollback o rilasci di lock dai marcatori condizionali T01.

## Verifica locale

| Controllo | Risultato |
|---|---|
| Nuova suite S01 | **22 PASS**, zero skipped |
| T01 boundary | **16 PASS** |
| T01 self-invocation F01 | **16 PASS** |
| T01 context alternatives F02 | **21 PASS** |
| T01 physical lifetime F03 | **19 PASS** |
| T01 transition contract MR01 | **64 PASS** |
| T01 AOP / causal order | **26 PASS** |
| Factory | **23 PASS** |
| Totale | **207 PASS**, zero skipped |
| Ruff check / format --check | PASS sui quattro Python interessati |
| `scripts/validate-repo.sh` | PASS, exit 0 |
| Tre esempi CLI esterni | Generati, validati e copiati nella documentazione |

Le suite T01/factory sono tutte conservate; quelle che invocano il PlantUML
locale hanno completato i propri controlli, senza skip. Non è stata avviata una
campagna QA globale o una nuova qualificazione renderer T02. CI remota, runtime
Spring/database e acquisizione di lock: **NOT RUN**.

Gli oracoli positivi sono dichiarazioni letterali del sorgente e del contratto
T01, non snapshot degli output del motore. La nuova suite verifica tutti gli otto
casi richiesti: REQUIRED/P1, REQUIRES_NEW/P2 indipendente, NESTED/SP1 su P1,
assenza di transazione, contesto UNKNOWN, datasource/manager ambiguo, rifiuto
dell'operazione dopo terminazione e lifetime di P1 durante sospensione.
Controlli negativi separati spostano l'operazione dopo PHYSICAL_END, assegnano
P2 già terminata o P1 sospesa, inventano acquisizione/granularità e tentano di
inserire sintassi UNPLACED nella timeline. Tutti vengono rifiutati.

Verificati inoltre SQL dinamico e non supportato, incompatibilità API/SQL,
commenti, identità/hash e span sorgenti, assenza di continuazione dopo frontiere
irrisolte, uguaglianza del modello T01 prodotto dalle due API, round-trip JSON,
immutabilità del target e rifiuto della sovrascrittura degli output.

## Limiti e giudizio

Il sottoinsieme qualificato è limitato a campi JdbcTemplate diretti con injection
non qualificata, tre API a un argomento stringa letterale e cinque forme SQL
chiuse documentate. Non c'è risoluzione datasource, connessioni, alias SQL,
risorse JPA o altri driver, né prova di esecuzione, ownership, attesa o concorrenza.
I fatti relativi a corpi non attraversati non diventano operazioni cronologiche.

Il validatore verifica coerenza interna dei fatti forniti, hash dichiarati,
causalità e lifetime T01. Non autentica un JSON importato mediante reparse
indipendente dei sorgenti; una fabbricazione coordinata dei fatti e degli hash
richiede un nuovo confronto con il progetto tramite CLI read-only. Questo limite
è esplicito e non viene promosso a prova runtime o completezza semantica.

**IMPLEMENTED_READY_FOR_REVIEW** riguarda questa fondazione statica e i controlli
locali elencati. La consegna non qualifica il motore di attese o il rilevatore di
deadlock. Arresto alla consegna S01.
