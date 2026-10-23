# MANA-TRANSACTION-01-T02-S02-I01-F01-R1

22 ottobre 2026. Verdetto **NEEDS_FIX**. F01 corregge i due falsi negativi
originali A/C, ma rende W4 un requisito assoluto per ogni cut negativo e perde
prove di aciclicità che non dipendono da W4. Nessuna modifica al prodotto,
remediation, staging, commit, switch, merge o push.

Review locale indipendente: letti D00, 35 oracoli, I01-R1, rapporto/receipt/witness
F01; esaminati direttamente motore, validatore, CLI, fixture e suite. Le attese
nuove derivano da D00 e da una prova sui riferimenti sorgente, non dal producer.
Il vecchio motore è stato estratto in memoria da I01.patch, verificato contro
SHA-256 `6b95d22c0aafcbd443c1d53f894caaca7cc86197305a358119217696c2453cd1`,
senza applicare patch al checkout. Le otto assessment prima/dopo sono state
rieseguite e coincidono esattamente con il receipt F01.

## Finding bloccante R1-F01 — W4 non indispensabile trattata come indispensabile

In `wait_dependencies.py:712–713`, pending o holdings vuoti aggiungono sempre
un unresolved W4. Il ramo a righe 1285–1299 dà priorità a UNKNOWN e alle holdings
mancanti senza distinguere la possibilità di un arco da quella di un ciclo.
La prova di identità unica è limitata ai casi senza cut dal ramo finale
`if not s.cuts and single_physical_scope(selected)`.
`wait_validation.py:85–93` replica il vincolo assoluto: richiede pending e
holdings anche quando nessuna coppia può soddisfare W1. La CLI pubblica e valida
questi UNKNOWN con exit 0, coerentemente con i due moduli ma non con l'oracolo.

**Controesempio minimo REQUIRED:** un solo partecipante, un solo input T01/S01
valido, una sola P1, O1 nel frame F2 alla sequence 6, O2 nel frame F1 alla sequence
9. Il cut a 9 lascia O2 pendente; holdings vuote; nessuna frontiera o
contraddizione. P1 inizia a 2 e termina soltanto a 11. Senza cut il motore
restituisce NO_CYCLE; aggiungendo quel cut restituisce UNKNOWN per W4.
**NESTED:** stessa prova, O1 a 7, O2/cut a 11, END P1 a 13; SP1 non è una P.

W1 richiede endpoint P distinti: con una sola P ogni arco inter-P è impossibile
indipendentemente da richiesta, acquisizione e ritenzione. O-D01/O-E01 autorizzano
precisamente questo negativo limitato. L'ignoranza sui lock resta esposta e la
coverage può restare INCOMPLETE; non serve promuoverla a completa né affermare
l'assenza di attese o di deadlock reali. D08 non cancella una prova nel perimetro
modellato per la mancanza di dati irrilevanti a quella prova. D00 §4 parla di
obbligazioni **indispensabili**, non di tutte le obbligazioni per ogni conclusione.

Anche i due casi B sono degradazioni non necessarie. Nei loro prefissi a=5/b=4,
l'unica operazione selezionata strettamente precedente al proprio cut è a1 a 4.
b1 è a 4 e b2 a 5: nessuna acquisizione di b precede il cut b=4. Considerando
come possibili waiter tutte le operazioni alla frontiera, anche se pending è
omesso, e ignorando tutte le restrizioni W2–W5, W1/W6 permettono al massimo
`b/P1 → a/P1`. Non esiste l'arco inverso né un grafo app nei due input. Questa
sovrastima aciclica prova l'assenza di cicli nel perimetro chiuso O-B01, senza
certificare la detenzione di a1 o lo stato reale delle richieste.

La prova non richiede un solver generale o un cambiamento D00. È un difetto
locale della condizione di qualificazione negativa, condiviso dal validatore.
**ARCHITECTURAL_DECISION_REQUIRED non applicabile.** Il requisito di review
positiva non è soddisfatto; consolidamento e integrazione non sono autorizzati
a procedere in questo stato.

Riproduzione minima persistente (exit atteso corrente 1, due FAIL):

```sh
python3 docs/reports/TRANSACTION-01-T02-S02-I01-F01-R1-counterexamples.py
```

Il [runner completo](TRANSACTION-01-T02-S02-I01-F01-R1-checks.py) restituisce exit
1 con 13 PASS e 6 FAIL: quattro degradazioni non necessarie più due loro riduzioni
minime REQUIRED/NESTED. I sei FAIL non sono sei difetti diversi. Include
riproduzione storica, prove sorgente, controlli API e CLI e rifiuti pre-producer.

## Matrice delle otto degradazioni

Per tutte le righe: precedente `NO_CYCLE_IN_MODELED_SCENARIO`, attuale `UNKNOWN`.
La [matrice CSV](TRANSACTION-01-T02-S02-I01-F01-R1-degradations.csv) contiene anche
questi campi espliciti. Le prove e le assessment complete sono nei
[risultati indipendenti](TRANSACTION-01-T02-S02-I01-F01-R1-results.json).

| Scenario originale / variante | W4 richiesta e dati disponibili | Evidenza mancante | Classificazione e giustificazione normativa |
|---|---|---|---|
| A-R1-no-holdings: X→Y / Y→X, cut a5/b5, entrambe le seconde richieste pendenti | Richieste a2/b2 e acquisizioni/ritenzioni separate a1/b1. Ordini, P distinte vive, richieste e regole presenti | Nessuna holding associata al cut; a1/b1 possono essere holder reciproci | **JUSTIFIED_DEGRADATION**. D00 §§4–5/W4, O-A01/A02: la mancanza può nascondere il circuito |
| C-R1-no-holdings: REQUIRES_NEW, cut inner a9 | Richiesta inner a2; acquisizione/ritenzione outer a1. P1 viva/sospesa, P2 corrente e arco app presenti | Detenzione outer al cut | **JUSTIFIED_DEGRADATION**. O-C02, §§5–6: arco DB non provato e rischio di completamento misto irrisolto; preservare l'arco app |
| A-partial-holder-omission: A con sola holding a1 | W4 per entrambe le direzioni; a1 qualificata, b1 pregressa, un arco DB supportato | Acquisizione/ritenzione b1 collegata al cut | **JUSTIFIED_DEGRADATION**. §§4–6: il secondo arco potrebbe chiudere il ciclo; non inferire assenza dall'omissione |
| B-no-pending: X→Y / X→Y, cut a5/b4, holding a1 | W4 serve per orientare un'attesa; a1 detenuta, posizioni e identità complete | Richieste dichiarate pendenti | **UNNECESSARY_DEGRADATION**. O-B01, W1/W6, §6: anche ammettendo ogni richiesta alla frontiera, il solo arco possibile è b→a; W4 non serve alla prova di aciclicità |
| B-one-incomplete-cut: B più un cut identico senza holdings | Primo cut qualificato; secondo a5/b4, pending a2/b1; unica acquisizione pregressa possibile a1 | Holding a1 al secondo cut | **UNNECESSARY_DEGRADATION**. O-B01, W1/W6: entrambi i cut e la loro unione ammettono al massimo b→a; la presenza dell'arco resta UNKNOWN, l'assenza di ciclo è dimostrabile |
| required-incomplete-cut: REQUIRED, cut a9/O2, nessuna holding | Unica P1 in due frame, tutte le operazioni posizionate. W4 necessaria solo per una dipendenza che W1 già esclude | Richiesta di lock, acquisizione/ritenzione, altri dati lock non qualificati | **UNNECESSARY_DEGRADATION**. O-D01, W1, §§4/6: impossibilità di archi inter-P; l'aggiunta del cut coerente non introduce una seconda P |
| nested-incomplete-cut: NESTED, cut a11/O2, nessuna holding | Unica P1 e SP1, due frame, posizioni note. W4 non necessaria alla prova per identità | Come REQUIRED; il savepoint non prova lock | **UNNECESSARY_DEGRADATION**. O-E01, W1, §§4/6: SP1 non è una P; nessun self-loop DB ammesso |
| frontier-incomplete-cut: prefisso oltre UNRESOLVED_CALL | Ipotesi richiesta/holding presenti, ma il modello autorevole non qualifica il suffisso | Continuazione, raggiungibilità e compatibilità W8; non una carenza W4 isolata | **JUSTIFIED_DEGRADATION**. O-G02, §5/W8 e §9: contraddizione del prefisso non certifica il suffisso non modellato |

Totale: **4 JUSTIFIED_DEGRADATION, 4 UNNECESSARY_DEGRADATION,
0 INSUFFICIENT_EVIDENCE**. I numeri riguardano le otto varianti nominate, non una
ricerca esaustiva sul dominio di tutti i sidecar.

## Contratto W4 e conclusioni positive

- A/C senza holdings producono UNKNOWN; i report originali pre-F01 sono ora
  respinti. I due witness salvati sono stati verificati contro gli SHA degli
  input e rigenerati con contenuto JSON identico ai rispettivi report after.
- W4 nel ledger, coverage COMPLETE o un producer simulato che ripete il falso
  report non bastano: il gate negativo rifiuta prima della riproiezione.
  I riferimenti alle premesse, il DAG e i dati T01/S01 vengono ricontrollati.
- Un sidecar non può autodichiarare MODEL_EVIDENCE/RUNTIME_EVIDENCE. Le
  EXPLICIT_ASSUMPTION ammissibili restano ipotesi condizionali: la provenance
  dichiarata e i digest non autenticano fatti runtime. Questo è previsto da D00,
  non una certificazione arbitraria di acquisizioni osservate.
- B completo conserva NO_CYCLE con un arco; A completo conserva due archi
  compatibili e CONDITIONAL_CYCLE_RISK. Cut mutuamente esclusivi restano distinti;
  due holdings esclusive incompatibili non producono un ciclo candidato.
- REQUIRES_NEW conserva app outer→inner e, solo con W1–W8, DB inner→outer e
  CONDITIONAL_CROSS_LAYER_COMPLETION_RISK. REQUIRED/NESTED non introducono P
  aggiuntive. Archi app, archi DB e collegamenti tipizzati rimangono separati.
- UNKNOWN viene esposto in JSON e Markdown. Budget esaurito: exit 2,
  BUDGET_EXCEEDED/INCOMPLETE, nessuna pubblicazione. Sidecar cambiato dopo la
  generazione: la CLI rifiuta il vecchio report con exit 2.
- Nessun ciclo statico viene dichiarato deadlock confermato. Il negativo rimane
  limitato allo scenario; globalRiskAbsence=NOT_ASSERTED e runtime=NOT_RUN.

Il difetto è dunque nella distinzione fra **premessa ignota per un arco** e
**premessa indispensabile per escludere un ciclo**. Le protezioni contro i falsi
negativi originali sono efficaci, ma non sufficienti per accettare F01.

## Verifiche eseguite

| Gate | Risultato corrente |
|---|---|
| 22 test I01 | PASS, 22/22, exit 0 |
| 31 oracoli statici | PASS nel primo test I01; 30 A–I e J05; nessuna modifica alle attese |
| 27 controlli R1 | PASS, 27/27, exit 0 |
| 15 regressioni F01 | PASS, 15/15, exit 0; le attese conservative dei test 11/12/15 non sono un oracolo indipendente della loro correttezza |
| Due controesempi originali A/C | PASS, 2/2, exit 0 |
| Nuovi controlli indipendenti | 13 PASS / 6 FAIL, exit 1; quattro varianti e due riduzioni del finding sopra |
| Nuovo riproduttore minimo | 2 FAIL, exit 1 |
| Validazione repository | PASS, exit 0; governance skill/agent/metadata/output/story trace/developer choice log |
| Ruff check e format --check | PASS sui dieci Python I01/R1/F01 e della review corrente |
| Integrità | PASS, tutti i 1.361 file iniziali identici per SHA-256/dimensione/mode; 11 percorsi e 6 protetti confrontati anche con receipt storici |
| Git | PASS: HEAD, branch, refs, indice vuoto e worktree list invariati |
| J01–J04 | NOT_RUN: richiedono evidenze runtime |

I conteggi si sovrappongono e non vanno sommati come test indipendenti unici.
Ruff/repository validation non sostituiscono la review semantica. Nessuna nuova
qualificazione generale, prova provider/CI o rendering Mermaid esterno.

## Ricevuta Git, preservazione e limiti

HEAD iniziale/finale e `develop`:
`9d3468101ccdcf40f680418955be17aec098c9e6`.
Indice iniziale/finale senza staged changes. Le tre modifiche tracked iniziali
e tutti gli untracked iniziali sono preservati. Il manifest dei file iniziali,
le ricevute Git e il confronto storico dei protetti sono nel JSON indipendente.

Sono aggiunti soltanto cinque deliverable della review: questo rapporto,
risultati JSON, matrice CSV e due runner Python. Motore, validatore, CLI, D00,
fixture, attese e rapporti storici restano immutati. Familiar, REL-01/A e superfici
di attivazione delle skill non sono modificati.

SHA commit I01: **non creato**. Consolidamento del diff, selezione degli artifact
per commit, firma/parent/tree e merge ff-only: **NOT_RUN**, perché la review è
NEEDS_FIX. Non è READY_FOR_INTEGRATION: il blocco è semantico, non uno switch Git
fallito. Nessun reset, stash, clean, force, nuovo worktree o push.

Restano fuori scope runtime Oracle/J01–J04, R1–R7 osservati, deployment, provider,
CI e qualifica generale. La prova di sovrastima usata nella review è delimitata
alle fixture chiuse con al massimo due P e prefissi risolti; non certifica un
algoritmo universale né l'autenticità esterna degli input. Nessuna correzione
implementata. Arresto alla consegna.
