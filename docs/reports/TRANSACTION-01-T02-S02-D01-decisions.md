# MANA-TRANSACTION-01-T02-S02-D01 — Architectural decisions and I01 authority

22 ottobre 2026. Decisioni D01–D08 **APPROVED dal proprietario** mediante il
mandato di questa sessione. Preflight **PASS** sul contratto
[D00](TRANSACTION-01-T02-S02-contract.md), sui suoi
[35 oracoli A–J](TRANSACTION-01-T02-S02-oracles.csv) e sul
[piano I01](TRANSACTION-01-T02-S02-implementation-plan.md), letti integralmente.
I tre originali restano immutati, incluso il loro stato storico PROPOSED.

Baseline verificata: branch `develop`, HEAD
`9d3468101ccdcf40f680418955be17aec098c9e6`. Inventario iniziale: 1.313 file
tracciati/non ignorati e 11 percorsi locali preesistenti. Manifest iniziale
esterno: `/private/tmp/mana-s02-i01/baseline.json`. Nessun conflitto materiale
fra mandato e definizioni normative D00, nessun budget impedisce A/B/C.

| Decisione | Applicazione vincolante I01 | Compatibilità D00 |
|---|---|---|
| D01 | Sidecar versionato distinto; SHA-256 dei byte Timeline; T01 embedded validato e riferito anche tramite digest JSON canonico dichiarato | §1/3: nessuna modifica a envelope/context/sorgenti T01/S01 |
| D02 | Tupla scenario, partecipante, digest input, P originale; frame in dominio distinto; null resta UNKNOWN | §3: nessuna fusione fra istanze, nessuna P da manager/datasource |
| D03 | Premesse qualitative con provenance e dipendenze; UNKNOWN non soddisfa obbligazioni; CONTRADICTED esclude; falsificazioni respinte | §4: nessuna scala numerica o promozione di certezza |
| D04 | Solo alias opachi; database, objectMatch e lockTargetOverlap distinti; regola astratta versionata e simmetrica | §4/5: spelling/WRITE/UNKNOWN non producono lock, holder o identità |
| D05 | Grafi DB e frame distinti; relazioni EXECUTES_IN, SUSPENDS_FOR, RESUME_REQUIRES_COMPLETION fuori dagli archi DB | §6: caller→callee non è Pouter→Pinner database |
| D06 | Prefissi/cut espliciti e W1–W8 congiunte; cicli qualificati per cut, unione separata | §5/6: ciclo condizionale distinto da deadlock osservato |
| D07 | Soglia futura R1–R7 esattamente come D00 §7; nessuna ingestione runtime in I01 | §7/8: J01–J04 rinviati, J05 verifica il rifiuto di OBSERVED statico |
| D08 | Due istanze, due risorse, quattro operazioni DB selezionate, un livello di sospensione; inventario restante conservato | §9 e piano §3: incompletezza esplicita e nessuna assenza globale di rischi |

Le premessa esterne del sidecar possono essere EXPLICIT_ASSUMPTION, UNKNOWN o
CONTRADICTED. MODEL_EVIDENCE viene esclusivamente ricavata dai modelli validati;
RUNTIME_EVIDENCE non viene autoattestata da un sidecar statico. Non viene così
modificato il vocabolario D00: il consumer I01 restringe le fonti accettate in
assenza dell'adapter rinviato. STATIC_SYNTAX resta la certezza della sintassi,
CONDITIONAL quella di una dipendenza qualificata. OBSERVED non è emesso.

Budget autorizzati: T01 massimo 4 MiB, Timeline massimo 4 MiB, input combinati
massimo 8 MiB, sidecar di scenario e report S02 ciascuno massimo 2 MiB,
confronti candidati massimo 100.000, archi
serializzati complessivi massimo 5.000. Il consumer legge soltanto i byte T02
con T01 embedded: il conteggio combinato somma ogni artifact Timeline fornito
una sola volta; T01 viene anche controllato separatamente nella codifica JSON
canonica `sorted-compact-ascii-json/v1`. Non si pretende che questo sia il digest
di un file T01 originale separato non fornito. I budget aggiuntivi conservativi
di parser/rappresentazione sono documentati nell'uso, senza requisiti di release.
Superamento dei budget: arresto senza pubblicazione e coverage INCOMPLETE.
Superamento del perimetro modellabile: inventario conservato, ipotesi DB
UNSUPPORTED, coverage INCOMPLETE, nessun verdetto di assenza di cicli globale.

Implementazione autorizzata soltanto sulle nuove superfici del piano I01.
Nessun commit, merge, push, reset, worktree, adapter Oracle runtime, modifica a
Familiar/REL-01/A o attivazione skill. Gli 11 percorsi iniziali e i sei materiali
protetti devono restare identici per byte e mode. Review semantica indipendente,
runtime/provider/CI e nuova campagna QA generale non sono implicitamente eseguiti.
