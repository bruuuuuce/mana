# MANA-TRANSACTION-01-T02-S02-I01-F01 — Negative Claim Evidence Gate

22 ottobre 2026. **FIX_READY_FOR_REVIEW**. Remediation locale verificata;
nuova review indipendente della correzione **NOT RUN**. Nessuna qualifica runtime.

Baseline: `develop`, HEAD `9d3468101ccdcf40f680418955be17aec098c9e6`.
Letti integralmente contratto D00, 35 oracoli CSV, piano, rapporto I01,
review I01-R1 e riproduttore dei due controesempi. Esaminati anche decisioni D01,
moduli reali, CLI, fixture e controlli indipendenti R1. Nessun cambio normativo,
di schema, certezza o perimetro I01.

## Difetto ricostruito e witness

W4 significa esattamente: «Richiesta candidata del waiter; richiesta/acquisizione
pregressa del blocker e detenzione al cut, con provenance separata» (D00 §5).
Non significa presenza generica di una P viva, SQL WRITE o semplice richiesta;
non è soddisfatta quando manca la detenzione. Una dichiarazione libera di W4
non sostituisce i riferimenti strutturati alle ipotesi e ai dati sorgente.

Nel codice iniziale `obligations()` verificava richiesta, acquisizione e ritenzione
per ogni coppia pending/holding. Con `holdings = []` non veniva valutata nessuna
coppia: W4 era annotata solo negli unknown globali, fuori dal risultato del cut.
Il ramo finale del calcolo scambiava l'assenza di candidati per assenza di cicli.
Il validatore controllava categoria, archi e riproiezione, ma mancava un'invariante
semantica indipendente sull'esito negativo. Ripetendo lo stesso producer accettava
lo stesso errore. La CLI pubblicava il risultato e lo validava con exit 0.

I due witness originali sono stati catturati **prima degli edit**. Gli unici
cambiamenti agli scenari sono in memoria: `cuts[0].holdings = []`; input originali,
digest, namespace, prefissi e premesse rimangono identici.

| Witness | Prima: cut/globale | Dopo: cut/globale | Archi DB/app dopo | Validazione del vecchio report dopo il fix |
|---|---|---|---|---|
| A senza holdings | NO_CYCLE / NO_CYCLE | UNKNOWN / UNKNOWN | 0 / 0 | Rifiutato per W4 mancante |
| C senza holdings | NO_CYCLE / NO_CYCLE | UNKNOWN / UNKNOWN | 0 / 1 | Rifiutato per W4 mancante |

Prima: coverage INCOMPLETE, unknown globale W4, unknown del cut vuoto, validatore
accettante. Dopo: W4 visibile anche nel cut; coverage INCOMPLETE; nessun claim
negativo certificato. I grafi vuoti restano strutturalmente aciclici, ma tale
proprietà non prova la completezza delle dipendenze rappresentate.
`globalRiskAbsence` resta `NOT_ASSERTED` in tutti i casi.

[Witness completi prima/dopo](TRANSACTION-01-T02-S02-I01-F01-witnesses.json),
con percorsi e SHA-256 dei Timeline originali, senza duplicarli.

## Regola implementata

- Un cut privo di pending o holdings conserva W4 mancante e restituisce UNKNOWN.
- Una detenzione pregressa potenziale omessa non diventa implicitamente assente:
  si riusano le obbligazioni W esistenti per distinguere coppie escluse da coppie
  ancora irrisolte. Gli archi già supportati restano disponibili; il giudizio
  negativo esaustivo viene impedito. Nessun holder o nuovo arco è inventato.
- Una continuazione oltre UNRESOLVED_CALL conserva la contraddizione del prefisso
  e rende esplicita l'incompletezza: non può autorizzare NO_CYCLE.
- L'esclusione per identità fisica unica di O-D01/O-E01 resta ammessa senza cut;
  non può più sovrascrivere un cut esplicitamente incompleto e richiede operazioni
  posizionate. Non è una prova di assenza di lock.
- Scope e budget conservano i limiti esistenti: UNKNOWN per scope non supportato;
  stop prima della pubblicazione per budget. Nessun nuovo algoritmo di grafo.

I negativi autorizzati da D00 rimangono: B qualificato aciclico, stessa P nei casi
D/E, disgiunzione esplicita, P terminata, cut contraddittorio secondo gli oracoli
storici. Una premessa contraddetta può escludere un candidato; una premessa
indispensabile UNKNOWN non può farlo. Non si richiedono W1–W8 tutte positive per
escludere una coppia già dimostrata impossibile.

La coverage generale comprende inventario e candidati esclusi; può essere
INCOMPLETE anche in B. Il gate controlla la completezza delle evidenze necessarie
al claim nel suo perimetro, non la sola stringa coverage. Non trasforma pertanto
ogni coverage INCOMPLETE in un UNKNOWN indiscriminato.

## Validatore e CLI

[Validatore](../../scripts/skill_factory/transactions/wait_validation.py): il nuovo
controllo negativo ricostruisce scenario, dipendenze delle premesse, posizioni e
obbligazioni dagli input originali validati. Controlla tutti i cut, scope, W4,
frontiere, coppie irrisolte e cicli strutturali prima della riproiezione finale.
Non usa lo stato W4 dichiarato nel ledger come prova. La riproiezione completa e
i controlli precedenti sugli archi/cicli positivi restano attivi.

Le regressioni contraffanno assessment, coverage e ledger e simulano un producer
che restituisce lo stesso falso report: il gate rifiuta **prima** di chiamarlo.
Sono respinti anche promozioni positive senza holdings e MODEL_EVIDENCE
arbitrariamente dichiarata nel sidecar. Gli EXPLICIT_ASSUMPTION validamente
referenziati restano ipotesi condizionali ammesse da D00, non fatti autenticati.

[CLI](../../scripts/mana-wait-dependencies.py): mantiene JSON/Markdown/Mermaid ed
exit code esistenti. Il Markdown UNKNOWN spiega l'insufficienza e mostra le
obbligazioni mancanti. Il JSON distingue assessment e coverage; `VALIDATED`
significa validità del report, anche quando l'assessment è UNKNOWN.

| Caso CLI | Esito | Exit |
|---|---|---|
| B qualificato | NO_CYCLE_IN_MODELED_SCENARIO | 0 |
| A/C senza holdings, generazione e validazione | UNKNOWN, INCOMPLETE | 0 |
| Vecchio report o negativo falsificato con W4 assente | REJECTED_INPUT, motivo W4; nessun risultato accettato su stdout | 2 |
| Budget superato | BUDGET_EXCEEDED, INCOMPLETE, published false | 2 |

Gli artifact A/B/C originali, inclusi Markdown e Mermaid, si rigenerano
byte-identici. Nessun nuovo formato o renderer.

## Verifiche

| Gate | Risultato corrente |
|---|---|
| `python3 tests/wait-dependencies.py -v` | PASS, 22/22, exit 0; suite e aspettative immutate |
| Oracoli storici nel primo test I01 | PASS, 31/31 statici (30 A–I e J05); 35 righe immutate |
| Riproduttore minimo I01-R1 | PASS, 2/2, exit 0 dopo; 2 FAIL prima |
| Controlli indipendenti I01-R1 esistenti | PASS, 27/27, exit 0; runner immutato |
| `python3 tests/wait-dependencies-negative-evidence.py -v` | PASS, 15/15, exit 0; include le dieci regressioni richieste |
| `bash scripts/validate-repo.sh` | PASS, exit 0 |
| Ruff check e format --check | PASS, exit 0, otto Python delimitati I01/R1/F01 |
| Isolamento, hash, mode, refs e indice | PASS; dettagli nella ricevuta |
| J01–J04 | DEFERRED / NOT RUN; adapter runtime fuori scope |
| Database reali, provider, CI e renderer esterni | NOT RUN |

La nuova [suite mirata](../../tests/wait-dependencies-negative-evidence.py) usa
attese manuali da D00 §§4–6/9 e O-B01/B03/C02/D01/E01/F05/G02. Riusa gli esempi
esistenti e le fixture parse-only I01; non genera gli oracoli dal producer.
I conteggi 22, 31, 2, 27 e 15 descrivono gate differenti, con coperture sovrapposte.
Una prima iterazione aveva spostato la frontiera fuori dalle contraddizioni attese
dal test I01-19: corretta preservando quel controllo e aggiungendo l'incompletezza,
senza modificare test o oracoli storici.

## Conclusioni degradate e preservazione

Nel corpus mirato confrontato prima/dopo, otto risultati globali passano da
NO_CYCLE_IN_MODELED_SCENARIO a UNKNOWN: A senza holdings; C senza holdings;
A con un holder omesso; B senza pending; B con un ulteriore cut senza holdings;
REQUIRED e NESTED con cut incompleto; prefisso oltre frontiera irrisolta.
I risultati per cut, conteggi degli archi e confronti sono nella ricevuta.
È un inventario delle varianti esercitate, non una ricerca esaustiva su ogni
possibile scenario. Nessun verdetto dei 31 oracoli storici cambia.

Inventario effettivo iniziale: **1.356 file**, ossia i 1.352 della review più i
quattro deliverable R1. Solo tre file preesistenti sono modificati intenzionalmente:
motore S02, validatore S02 e CLI S02; gli altri **1.353** restano identici per
SHA-256, dimensione e mode. I sei protetti coincidono anche con gli hash storici.
T01/S01 canonici, originali D00, 35 oracoli, fixture, suite I01, report/esempi
storici e runner R1 sono preservati. Le tre modifiche tracked iniziali restano
identiche. Branch, HEAD, refs, indice e worktree list invariati.

[Diff incrementale](TRANSACTION-01-T02-S02-I01-F01.patch): confrontato con i byte
I01 presenti all'avvio, non con HEAD che non contiene ancora quelle superfici.
Include solo i tre moduli modificati e la nuova suite; rapporto, ricevuta e
witness sono deliverable separati. Nessun commit, merge, push, nuovo worktree,
clone o backup del repository. Nessuna modifica a Familiar, REL-01/A o skill.

## Rischi residui e consegna

Il validatore condivide le primitive di lettura e valutazione W con il motore,
ma il gate negativo non dipende dalla sua conclusione o dalla sola uguaglianza
di riproiezione. Gli oracoli manuali e il producer simulato errato ne verificano
l'indipendenza rispetto al difetto F01; non costituiscono una seconda review
indipendente della remediation.

Premesse di scenario, overlap opaco e compatibilità restano ipotesi; digest e
snapshot non autenticano il mondo runtime. Nessun claim deadlock-free, nessuna
cattura DB, correlazione R1–R7, nuova forma di resource matching o solver.
Le guardie per confronti/archi sono testate con budget ridotti; i byte anche alle
soglie effettive. Non è un benchmark ai massimi numerici di complessità.

[Ricevuta completa](TRANSACTION-01-T02-S02-I01-F01-results.json): comandi, exit,
log, witness, degradazioni, hash e integrità. **Arresto alla consegna.**
