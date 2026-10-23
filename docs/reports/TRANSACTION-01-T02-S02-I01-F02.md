# MANA-T02-S02-I01-F02 — Proof-Aware Negative Claims

22 ottobre 2026. **FIX_READY_FOR_REVIEW**. Correzione implementata e verificata
localmente. I 24 test F02 e i 31 oracoli statici passano; le divergenze residue
nei runner storici sono dichiarate sotto. Nessun nuovo verdetto F01-R1, nessuna
review generale, commit, merge, push o worktree.

Baseline: `develop`, HEAD `9d3468101ccdcf40f680418955be17aec098c9e6`, indice vuoto.
Il rapporto F01-R1 concluso con NEEDS_FIX è stato usato come finding di ingresso;
i suoi deliverable e runner restano immutati. Non è stato rieseguito il runner
di review F01-R1 né rigenerato il suo receipt.

## Compatibilità con D00

**Compatibile; CONTRACT_DECISION_REQUIRED non applicabile.** D00 §4 definisce
UNKNOWN per un'«obbligazione indispensabile mancante»; §5 richiede W1–W8 per
emettere una DB_WAIT_DEPENDENCY, non per ogni prova di esclusione. O-D01/O-E01
permettono esplicitamente l'esclusione inter-P con una sola identità fisica;
W1/W6 e O-B01 permettono di escludere un circuito quando identità e prefissi
rendono impossibile la direzione inversa. §6 limita il negativo allo scenario;
§9/D08 impone di conservare incompletezza e limiti.

F02 aggiunge un certificato di derivazione al risultato, senza cambiare D00,
i 35 oracoli, il vocabolario della certezza, le categorie dei claim o i grafi.
Il certificato non certifica richieste, acquisizioni, detenzioni o attese runtime.
Non modifica gli envelope T01/S01 né accetta nuove assunzioni nel sidecar.

## Correzione

Il gate precedente rimane il percorso **EVIDENCE_COMPLETE_EXCLUSION**: ogni
candidato rilevante è qualificato da W1–W8 o escluso da una contraddizione;
nessuna premessa indispensabile al giudizio resta UNKNOWN. La completezza è
relativa alla prova, non equivale a coverage globale COMPLETE. Una contraddizione
può escludere un candidato anche se altre sue W sono sconosciute.

Quando quel percorso non basta, **STRUCTURAL_EXCLUSION** richiede una prova
separata. Per un cut coerente e risolto il motore costruisce una sovrastima:

1. Copre tutte le operazioni dell'inventario dei partecipanti; una selezione
   parziale non autorizza questo percorso.
2. Considera ogni operazione alla frontiera come possibile waiter, anche quando
   pending è omesso; considera ogni operazione pregressa come possibile holder.
3. Usa solo identità, lifetime, sospensione e posizione causale W1/W6 per
   eliminare coppie. Ignora binding, risorse, compatibilità e ipotesi di lock
   W2–W5, quindi la loro assenza non elimina archi dalla sovrastima.
4. Include le dipendenze applicative attive fra P distinte nella verifica del
   circuito. I collegamenti rimangono tipizzati nel certificato e fuori dal
   databaseGraph. Un possibile circuito REQUIRES_NEW impedisce l'esclusione.
5. Accetta l'esclusione soltanto se l'intera sovrastima è aciclica. Identità null,
   operazioni UNPLACED, frontiere irrisolte, cut contraddittori o scope non
   supportato non vengono riparati da questa prova.

La prova per identità fisica unica senza cut conserva il percorso O-D01/O-E01.
Per più cut, l'unione delle direzioni DB possibili viene controllata: direzioni
reciproche su cut distinti conservano CYCLE_FEASIBILITY_UNKNOWN.

Il negativo strutturale conserva unknowns, premessa W4 mancante e coverage
INCOMPLETE. Non riempie le holdings, non inventa archi DB e non promuove
assunzioni a MODEL_EVIDENCE. I budget comprendono anche gli archi serializzati
dei certificati e i confronti della loro costruzione/verifica; lo stop precede
la pubblicazione.

## Validatore e CLI

Il validatore ricostruisce i certificati da input T01/S01 validati e sidecar.
Non chiama il costruttore della prova strutturale per approvarli: ricostruisce
separatamente coppie e collegamenti app e usa eliminazione topologica dei nodi,
mentre il producer usa DFS. Controlla inventario, namespace, prefissi, lifetime,
completezza della sovrastima, visibilità degli unknown e budget. Anche il
percorso evidence-complete verifica indipendentemente il circuito DB/app.
La riproiezione completa finale resta attiva.

I test simulano un producer che ripete lo stesso report errato. Certificati con
archi omessi, riferimenti/prefissi alterati, circuito esatto ma ciclico, falsi
negativi C e coverage completata arbitrariamente sono rifiutati prima del
producer. Il test positivo isola il validatore sostituendo la riproiezione e
rendendo non invocabile il builder strutturale del motore.

JSON: campo additivo `exclusionProof` nei record dei cut e nell'assessment;
quest'ultimo contiene la prova solo nel caso senza cut. Valore null per gli
esiti non negativi e per la composizione globale già documentata dai cut.
Ogni prova indica kind e rule; quella strutturale conserva operationRefs,
prefixes e upperBoundEdges con provenance. I possibili archi del certificato
non sono DB_WAIT_DEPENDENCY qualificati.

CLI: espone `exclusionProofs` nel riepilogo stdout e descrive tipo di prova,
limiti e dati mancanti nel Markdown. UNKNOWN e NO_CYCLE rimangono distinti;
VALIDATED indica validità del report, non completezza delle evidenze.
Sidecar alterato dopo la generazione: exit 2. Budget esaurito: exit 2,
BUDGET_EXCEEDED/INCOMPLETE e nessuna pubblicazione.

I report precedenti sono snapshot storici: per la nuova validazione occorre
rigenerarli dagli input preservati, perché manca il nuovo certificato. Non
vengono normalizzati o aggiornati automaticamente. I diagrammi A/B/C restano
byte-identici; il contenuto JSON precedente si recupera rimuovendo i soli campi
additivi di prova. Il test F02-23 verifica tale equivalenza senza riscrivere
alcun artifact storico.

## Otto varianti richieste

| Variante | Esito F02 | Prova o limite |
|---|---|---|
| A senza holdings | UNKNOWN | Sovrastima DB reciproca; W4 indispensabile |
| C senza holdings | UNKNOWN | Possibile DB inner→outer più app outer→inner |
| A con una holding omessa | UNKNOWN | La dipendenza mancante può chiudere il ciclo |
| Prefisso oltre UNRESOLVED_CALL | UNKNOWN | Causalità W8 non qualificata |
| B senza pending | NO_CYCLE_IN_MODELED_SCENARIO | STRUCTURAL_EXCLUSION: al massimo b→a |
| B con secondo cut senza holdings | NO_CYCLE_IN_MODELED_SCENARIO | Primo cut evidence-complete, secondo strutturale; nessun ciclo nell'unione |
| REQUIRED con cut senza holdings | NO_CYCLE_IN_MODELED_SCENARIO | STRUCTURAL_EXCLUSION: unica P1 |
| NESTED con cut senza holdings | NO_CYCLE_IN_MODELED_SCENARIO | STRUCTURAL_EXCLUSION: unica P1, SP1 distinta da P |

[Matrice CSV](TRANSACTION-01-T02-S02-I01-F02-outcomes.csv) e
[witness F02](TRANSACTION-01-T02-S02-I01-F02-witnesses.json): scenari, digest,
assessment, premesse mancanti, coverage e prove dell'oracolo indipendente.
I quattro UNKNOWN e i quattro recuperi sono verificati in F02-01/F02-02.
Le riduzioni minime REQUIRED/NESTED senza alcuna assunzione sono F02-13.

## Verifiche e divergenze storiche

| Gate eseguito sul codice F02 | Risultato |
|---|---|
| Nuova suite F02 | **PASS, 24/24**, exit 0 |
| Suite I01 immutata | **PASS, 22/22**, exit 0 |
| Oracoli statici nel primo test I01 | **PASS, 31/31**; 30 A–I e J05; quattro runtime differiti |
| Due controesempi originali A/C (I01-R1) | **PASS, 2/2**, exit 0 |
| Runner regressioni I01-R1 immutato | **26 PASS / 1 FAIL**, exit 1; solo confronto byte dei vecchi artifact JSON |
| Suite F01 immutata | **12 PASS / 3 FAIL**, exit 1; aspettative superate dei test 11, 12 e 15 |
| Validazione repository | **PASS**, exit 0, inclusi controlli di governance |
| Ruff check e format --check | **PASS**, exit 0, nove Python I01/R1/F01/F02 delimitati |
| Preservazione e Git | **PASS**; dettagli nel receipt F02 |
| J01–J04, runtime/provider/CI, qualifica generale | **NOT_RUN** |

I tre FAIL F01 richiedono UNKNOWN rispettivamente per B senza pending, B con cut
senza holdings e REQUIRED/NESTED senza holdings: sono le aspettative che il
mandato F02 chiede di correggere nel prodotto. Non sono stati modificati quei
test per ottenere PASS. F02-02 verifica le nuove attese; F02-01/F02-15 mantengono
le guardie di frontiera e di dipendenza delle premesse contenute negli stessi
test storici. Il FAIL I01-R1 confronta byte del vecchio JSON privo dei campi di
prova; F02-23 verifica equivalenza semantica e identità Mermaid. Questi runner
storici restano **FAIL**, non sono conteggiati come PASS complessivi.

L'oracolo nuovo legge direttamente osservazioni/eventi/frame e calcola la
chiusura transitiva, senza chiamare inventory, builder delle prove o rilevatore
di cicli del prodotto. È un controllo indipendente delle fixture delimitate;
non costituisce una nuova review indipendente completa della correzione.

## Consegna e preservazione

Modificati intenzionalmente solo motore S02, validatore S02 e CLI S02. Aggiunti
suite F02 e cinque deliverable F02: rapporto, risultati, witness, matrice e
[patch incrementale](TRANSACTION-01-T02-S02-I01-F02.patch). Il diff è riferito ai
byte pre-F02, non a HEAD che non contiene ancora queste superfici untracked.

I 1.366 file iniziali sono inventariati: 1.363 restano identici per
SHA-256/dimensione/mode; le sole tre variazioni sono autorizzate sopra. Gli 11
percorsi locali originali e i sei protetti coincidono anche con i receipt
storici. Nessun materiale F01-R1, D00, oracolo, fixture o suite preesistente è
stato modificato. Nessuna modifica a Familiar, REL-01/A o attivazione skill.

HEAD/branch/refs/indice/worktree list invariati. Nessun commit, merge, push,
reset, stash, clean, force o nuovo worktree. La correzione resta locale e pronta
per la successiva review autorizzata. Digest e provenance non autenticano eventi
runtime; globalRiskAbsence resta NOT_ASSERTED e runtime resta NOT_RUN.
I limiti di scope e l'assenza dell'adapter Oracle rimangono quelli I01.

[Risultati e ricevuta completa](TRANSACTION-01-T02-S02-I01-F02-results.json).
Fermata alla consegna F02.
