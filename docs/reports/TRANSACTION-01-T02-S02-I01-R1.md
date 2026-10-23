# MANA-TRANSACTION-01-T02-S02-I01-R1

22 ottobre 2026. Verdetto **NEEDS_FIX**. Review semantica indipendente **FAIL**
per F01: un cut senza ipotesi di detenzione riceve un giudizio negativo sui cicli,
pur avendo W4 mancante. Nessuna correzione dell'implementazione, consolidamento,
firma, commit, merge o push eseguiti.

La review ha letto D00, CSV, piano I01, decisioni approvate D01–D08, rapporto I01,
standard S02, motore, validatore, CLI, suite e fixture reali. Le verifiche sono
locali, statiche e bounded. I rapporti precedenti non costituiscono il verdetto
indipendente di questa review.

**F01 — Incompletezza W4 trasformata in NO_CYCLE: bloccante.**

Partire da uno degli esempi A/C, mantenere immutati input, digest, namespace,
premesse e prefissi; effettuare una sola modifica al sidecar in memoria:

```python
sidecar["cuts"][0]["holdings"] = []
```

L'assenza di un'ipotesi di acquisizione/ritenzione associata al cut lascia il
holder sconosciuto. L'oracolo indipendente richiede `UNKNOWN` per il giudizio,
zero archi DB e, in C, conservazione dell'arco app. Il risultato effettivo è:

| Proprietà | A senza holder | C senza holder |
|---|---|---|
| Assessment globale e del cut | `NO_CYCLE_IN_MODELED_SCENARIO` | `NO_CYCLE_IN_MODELED_SCENARIO` |
| Coverage | `INCOMPLETE` | `INCOMPLETE` |
| Unknown globale | `NO_ORIENTED_WAIT_HYPOTHESIS`, W4 | `NO_ORIENTED_WAIT_HYPOTHESIS`, W4 |
| Unknown nel record del cut | Lista vuota | Lista vuota |
| Archi DB / app | 0 / 0 | 0 / 1 |
| `validate_report` | Accetta | Accetta |

`globalRiskAbsence` resta correttamente `NOT_ASSERTED`: il difetto riguarda il
giudizio negativo sullo scenario/cut incompleto. Non è una promozione a
`OBSERVED` né una dichiarazione letterale di sicurezza globale. D00 §4 definisce
UNKNOWN per un'obbligazione indispensabile mancante; §5/W4 richiede holder e
ritenzione separati; O-C02 richiede `UNKNOWN — DATABASE_WAIT_UNPROVEN` senza
detenzione provata o assunta; §9/D08 vieta di trasformare l'incompletezza in un
verdetto negativo completo. Nessuna insufficienza del contratto è necessaria per
spiegare F01: è un difetto locale del calcolo e della validazione dell'esito.

La causa è in
[`wait_dependencies.py`](../../scripts/skill_factory/transactions/wait_dependencies.py):
righe 1075–1084 registrano W4 mancante nella sola lista globale `unknowns`;
senza holdings il ciclo dei candidati non produce record. Alle righe 1217–1230
il giudizio considera gli unresolved del cut e i candidati UNKNOWN, senza
includere quel W4 globale: cade in `NO_CYCLE_IN_MODELED_SCENARIO`. Le righe
1251–1254 propagano il risultato all'assessment globale.

Il [validatore](../../scripts/skill_factory/transactions/wait_validation.py),
righe 215–224, controlla i limiti globali e confronta il report con una nuova
esecuzione dello stesso producer. Manca un invariante sull'assessment in presenza
di W4 indispensabile non risolta; la riproiezione replica F01. Le mutazioni
arbitrarie dell'assessment sono respinte, ma il giudizio errato originato dal
producer è accettato. L'accettazione non costituisce quindi una verifica
semantica sufficiente di questo caso.

La CLI reale ha pubblicato C senza holder e successivamente lo ha validato:
entrambi i comandi hanno exit **0**, assessment negativo e coverage incompleta.
Il report Markdown mostra lo stesso assessment. Evidenza completa nella
[ricevuta R1](TRANSACTION-01-T02-S02-I01-R1-results.json).

Riproduzione persistente, senza scrivere gli input o il motore:

```sh
python3 docs/reports/TRANSACTION-01-T02-S02-I01-R1-counterexamples.py
```

Il [riproduttore minimo](TRANSACTION-01-T02-S02-I01-R1-counterexamples.py)
termina con exit **1**, con due FAIL sullo stesso difetto. Le fixture I01
O-A02/O-C02 passano perché `clear_lock_scenario` elimina anche tutti i cut
(`scenarios.py:148`); non esercitano la combinazione cut presente/holder assente.
Nessuna aspettativa storica è stata modificata.

**Risultati indipendenti sul modello e sui grafi.**

| Area | Evidenza e risultato nel perimetro esaminato |
|---|---|
| Envelope e input | Sidecar distinto; digest Timeline sui byte e T01 embedded canonico dichiarato; input invalidi e witness alterati respinti. Nessuna modifica ai modelli canonici |
| Identità | Namespace scenario/partecipante/digest/P; P1 di due istanze resta distinto; null F02 resta sconosciuto. REQUIRED/NESTED non genera una seconda P o self-loop DB nelle fixture |
| Lock e risorse | WRITE non crea automaticamente richieste/acquisizioni; FOR UPDATE conserva acquisizione UNKNOWN. Overlap, binding, indipendenza e ritenzione mancanti impediscono gli archi; spelling e datasource non risolvono l'identità |
| A: ciclo compatibile | Due archi a→b[Y], b→a[X] al cut comune; `CONDITIONAL_CYCLE_RISK`, con W1–W8 e premesse. END nel suffix futuro non elimina il rischio |
| B: scenari incompatibili | Due orientamenti su cut esclusivi producono `CYCLE_FEASIBILITY_UNKNOWN`. Un unico cut con entrambe le prime operazioni già ritornate e holdings esclusive incompatibili esclude gli archi per W8; nessun ciclo qualificato |
| C: tempi incompatibili | Holder P1 terminato al prefisso 9 e waiter al proprio prefisso 5: W1 CONTRADICTED, zero archi. Il test isola END senza affidarsi a un errore di posizione del pending |
| D: misto DB/app | P1 viva/sospesa, P2 viva/corrente; DB P2→P1 e app F1→F2; `CONDITIONAL_CROSS_LAYER_COMPLETION_RISK`. Nessun ciclo nel solo grafo DB |
| Prefissi e incertezze | Pending non alla frontiera, ritorni incompatibili e frontiere irrisolte escludono le qualificazioni; inventario UNPLACED e limiti T01/S01 conservati nelle prove |
| Input/output contraffatti | MODEL_EVIDENCE e RUNTIME_EVIDENCE autoattestati nel sidecar, digest e witness falsi respinti; mutazioni di certezza, direzione/cut e assessment respinte. F01 resta accettato perché condiviso dal producer |
| Incompletezza | Overflow di scope conserva inventario e UNKNOWN; F01 impedisce il PASS complessivo del comportamento in presenza di premesse mancanti |

Gli oracoli indipendenti sono scritti nel
[runner R1](TRANSACTION-01-T02-S02-I01-R1-checks.py), senza importare il builder
degli scenari o le aspettative della suite I01. Usano i byte degli esempi come
input e mutazioni manuali in memoria. Il runner verifica 27 controlli: **26 PASS,
1 FAIL**; il FAIL sulla variante WRITE senza ipotesi holder ha portato alla
riduzione ai due controesempi minimi sopra. L'assenza di richieste/archi in tale
variante è corretta; l'asserzione che fallisce riguarda l'assessment atteso UNKNOWN.

**Esecuzioni e limiti della prova.**

| Gate | Esito corrente |
|---|---|
| `python3 tests/wait-dependencies.py -v` | PASS, 22/22 test, exit 0; 4,828 s riportati da unittest |
| Oracoli statici della suite I01 | PASS, 31/31 (30 A–I e J05); eseguiti dentro il primo test, non 31 test aggiuntivi |
| Runner R1 | 26 PASS / 1 FAIL, exit 1 |
| Controesempi minimi R1 | 2 FAIL, exit 1; stesso difetto F01, entrambi accettati dal validatore |
| `bash scripts/validate-repo.sh` | PASS, exit 0; include validazioni skill/agent, metadata, output, story trace e developer choice log; nessuna attivazione |
| Ruff check e format --check | PASS sui 5 Python I01 e sui 2 riproduttori R1, exit 0 |
| Isolamento/preservazione | PASS per byte, dimensione e mode dei 1.352 file iniziali inventariati; sei protetti verificati anche contro il receipt storico S01 |
| Mermaid/JSON | PASS per rigenerazione esatta degli artifact A/B/C, numero/direzione archi, separazione layer e cut |
| Renderer Mermaid esterno | NOT_RUN: `mmdc` assente; non è un FAIL applicativo del contratto |
| J01–J04, runtime Oracle, provider, CI | NOT_RUN; adapter runtime assente |

R1–R7 rimangono esattamente la soglia futura D00 §7: origine e semantica della
capture; identità runtime temporali; dominio/risorsa; attesa effettiva; episodio
comune; correlazione statica quando rivendicata; separazione proprietà/copertura.
I01 rifiuta l'autorità runtime autoattestata e non implementa ingestione o
qualificazione di questi sette requisiti. Il rifiuto statico J05 non rende PASS
J01–J04 e non prova la correttezza di un adapter futuro.

Budget letti nel codice e verificati: 4 MiB Timeline, 4 MiB T01 embedded canonico,
8 MiB combinati Timeline, 2 MiB sidecar/report, 100.000 confronti, 5.000 archi
inclusi i collegamenti tipizzati. La suite esercita soglie byte effettive su
Timeline, sidecar e report; i controlli isolati delle sei guardie usano soglie
ridotte. Nessuna pretesa di carico reale da 100.001 confronti o 5.001 archi.
Gli stop verificati sono espliciti e precedono la pubblicazione; nessun
troncamento silenzioso. Scope oltre due istanze/due risorse/quattro operazioni/
un livello di sospensione è dichiarato incompleto; nessun solver generale aggiunto.

**Stato Git e arresto.**

Branch iniziale e finale `develop`; HEAD e ref locale `develop`:
`9d3468101ccdcf40f680418955be17aec098c9e6`.
Tree HEAD: `d653a29de2823722b6753fcdf619410d4c5d8817`.
Indice senza modifiche staged; refs invariate. Il rapporto ahead 3 è relativo
al tracking ref locale: nessun fetch o controllo remoto.

Restano le tre modifiche tracked preesistenti (due CSV storici con CRLF e
`docs/roadmap/TRANSACTION-01.md`) e tutto il materiale untracked iniziale.
Le sole aggiunte R1 sono questo rapporto, la ricevuta JSON e i due runner Python.
I sei protetti, conservati integralmente, sono:

- `docs/reports/MANA-TRANSACTION-01-T01-MR00-transitions.csv`
- `docs/reports/MANA-TRANSACTION-01-T01-MR01-coverage.csv`
- `docs/reports/MANA-TRANSACTION-01-T01-MR01-R2-results.json`
- `docs/reports/MANA-TRANSACTION-01-T01-MR01-R2.md`
- `docs/roadmap/TRANSACTION-01-T02.md`
- `docs/roadmap/TRANSACTION-01.md`

SHA del commit I01: **non creato**. Verifica firma/parent, consolidamento del diff,
switch al branch feature, controllo writer per integrazione e merge ff-only:
**NOT_RUN**, poiché manca il prerequisito della review positiva. Nessun nuovo
worktree, reset, stash, clean, force, modifica a Familiar/REL-01/A, attivazione
skill o adapter Oracle. Nessuna nuova campagna QA generale.

Per la visualizzazione integrata resta necessario distinguere UNKNOWN,
contraddizione del cut e assenza di ciclo nel perimetro qualificato; F01 blocca
l'accettazione di tale giudizio. Sono verificati i sorgenti Mermaid locali,
mentre rendering esterno e integrazione in un prodotto restano NOT_RUN. Gli
artifact temporanei di esecuzione sono in `/private/tmp/mana-s02-i01-r1`; la
ricevuta e i riproduttori persistenti conservano gli esiti necessari alla review.
Arresto alla consegna, senza remediation automatica.
