# MANA-TRANSACTION-01-T01-MR00 — Piano del singolo incremento MR01

Data: 20 ottobre 2026. **Piano architetturale aggiornato alle decisioni MR00
approvate dall'utente; nessuna implementazione avviata.**

Il finding R4-F01 permette di validare effetti incompatibili con il confine
APPLIED, anche su IR completi. MR01 deve rendere il validatore capace di rifiutare
quegli IR mantenendo validi i percorsi supportati e le distinzioni F01/F02/F03.
Contratto di riferimento: [MR00](MANA-TRANSACTION-01-T01-MR00-contract.md);
specifica tabellare: [24 transizioni e 44 oracoli](MANA-TRANSACTION-01-T01-MR00-transitions.csv).

## 1. Decisioni e prerequisiti del mandato

**Esistente (E):** manager, propagation e capability già delimitati da T01;
schema v1, formati CLI e campi additivi F01/F02; lifetime F03; nessuna prova
runtime. R4 non dimostra un difetto equivalente di generazione per le capability:
non si pianifica una riscrittura preventiva del motore.

**Interpretazione (I):** apertura, durante e ritorno sono verifiche diverse;
la validità è una congiunzione di regole per riga, non la riconoscibilità dei
singoli effetti. Riferimenti e ordine temporale restano necessari ma insufficienti.

**Decisioni approvate (D1–D4 nel contratto):** D1 e D3 APPROVED; D2 e D4 APPROVED
WITH CONSTRAINT. True è premessa di compatibilità effettiva senza qualifica
runtime automatica. Il L UNKNOWN/null è solo un marcatore tentato/irrisolto:
validatore, renderer e consumer non possono trasformarlo in scope sicuramente
eseguito, transazione riuscita o fonte certa di effetti. I legacy richiedono
classificazione affidabile, senza APPLIED dalle sole annotazioni o effetti.
After U richiede continuazione effettivamente irrisolta e motivata; ogni certezza
sul lifetime fisico resta conservata separatamente e nessun invariante dimostrato
può essere cancellato. Questi vincoli rendono determinati gli oracoli.
Un'eventuale richiesta di esiti rollback/commit distinti sarebbe un altro mandato.

L'approvazione delle decisioni MR00 non autorizza MR01, modifiche di schema,
ampliamenti delle propagation, attivazione skill o T02. Al futuro avvio verificare nuovamente
branch/HEAD e working tree effettivi, senza sovrascrivere modifiche concorrenti o
assumere che i file non committati siano congelati alla lettura MR00. Gli hash
storici, receipt e verdetti R1–R4/F01–F03 restano immutabili.

## 2. Perimetro del singolo incremento

| Superficie | Lavoro proposto | Limite |
|---|---|---|
| `docs/standards/transaction-model-v1.md` | Recepire istanti, sei casi riusciti, irrisolti, V1–V12, D1–D4 e intersezione F02 | Stesso schema; chiarire semantica, senza riscrivere i report storici |
| `scripts/skill_factory/transactions/model.py`, `validate_model` | Verifica semantica APPLIED e classificazione compatibile dei legacy; integrare replay lifetime/ritorno | Non chiamare `build()` per decidere se un IR è valido |
| `scripts/skill_factory/transactions/alternatives.py` | Verificare coerenza del contratto APPLIED di ramo con quello ordinario; correggere solo divergenze dimostrate | Preservare witness e intersezione F02; niente allocazioni globali di ramo |
| `model.py`, `build` | Allineare soltanto output che le nuove regressioni dimostrino incompatibili col contratto | Nessuna nuova propagation, capability, modalità AOP o percorso di corpo |
| Suite transazioni esistenti / fixture dedicate delimitate | Aggiungere dati manuali completi e controlli positivi/negativi del CSV | Attese indipendenti dal motore; non riscrivere oracoli storici per far passare il codice |
| Renderer e consumer T01/CLI | Verificare il vincolo D2 sul marcatore UNKNOWN/null e la conservazione del lifetime D4; allineare solo le rappresentazioni/inferenze che lo violano | Nessuno scope sicuramente eseguito o effetto certo dal marcatore; nessun nuovo formato pubblico o ampliamento ai consumer T02 |

È un solo incremento MR01 con contratto, validatore e regressioni coerenti. Nessun
framework generale di state machine, abstract interpretation, event sourcing,
nuova API, nuova dipendenza o infrastruttura di prova runtime. Non servono nuovi
timestamp, campi owner, capability o eventi: i dati necessari sono già nel v1.

## 3. Ordine del lavoro proposto

1. Fissare i dati e le attese manuali del CSV prima della correzione. Trascrivere
   le nove varianti R4 (`finding.variants`) e i controlli temporali richiesti;
   affiancare a ogni negativo il modello positivo completo corrispondente.
   I 44 oracoli sono casi/varianti, non un numero obbligatorio di funzioni test.
2. Delimitare una classificazione locale del frame: bypass, composizione F02,
   APPLIED riuscito T01–T06, APPLIED irrisolto T07–T12 o continuazione incerta T23.
   Con campi F01 espliciti rispettarne la semantica; nei legacy applicare D3 dalle
   osservazioni disponibili, senza inventare prova d'intercettazione. L'omissione
   dei campi opzionali non deve creare un percorso per saltare i vincoli.
3. Per ogni APPLIED ordinario selezionare il manager e confrontare le capability
   con l'input, poi determinare obblighi/vietati dalla propagation e dal prior.
   Contare tutte le entità attribuite al frame, non soltanto quelle puntate dal
   suo logicalScope: rifiutare scope orfani, entità aggiuntive e combinazioni
   miste anche se i riferimenti sono validi.
4. Integrare questi obblighi nel replay già esistente: previous prima di ingresso;
   prefisso completo prima di verificare during; operazioni dei figli con stack;
   chiusure e terminali autorizzati; ripristino e after anche se N. Conservare i
   set di P iniziate/vive/terminate e le sospensioni, senza sostituirli con il solo
   snapshot fisico del frame. Verificare proprietà e cardinalità degli eventi,
   oltre a coppie begin/end, ownership, ordine e contesto corrente.
5. Confrontare i sei casi con APPLIED nei witness F02. Piccole funzioni di
   selezione manager o lettura capability possono essere condivise; il validatore
   deve controllare la relazione direttamente, senza usare `build`, `compose` o
   `applied_boundary` come unica fonte dell'attesa. Evitare che generatore e
   controllo si approvino reciprocamente sulla stessa tabella di output.
6. Toccare il motore solo per un caso concreto ora fallente contro l'oracolo.
   Conservare D2 senza trasformarlo in scope riuscito, anche nelle rappresentazioni
   del renderer e negli usi dei consumer T01. Applicare D4 separando l'incertezza
   della continuazione dai fatti certi di lifetime; la sola etichetta UNKNOWN non
   giustifica after U. Se il motore già genera l'IR corretto, lasciare invariata
   quella transizione.
7. Recepire lo standard, eseguire soltanto le verifiche pertinenti sotto descritte
   e produrre evidenza nuova distinta. Arrestarsi all'esito del mandato MR01;
   nessun avvio automatico di integrazione o T02.

Questi sono passi di implementazione futura. Nessuna di queste modifiche è stata
eseguita durante MR00.

## 4. Regressioni indipendenti e criteri di accettazione

I test nuovi devono poter invocare **solo il validatore** su payload completi
forniti manualmente, senza passare prima dal generatore per correggerli o ricavare
le aspettative. JSON sintetici devono dichiarare tale origine; le copie storiche
mantengono envelope, evidence e provenance originali. Le mutazioni negative non
devono fallire soltanto perché manca un campo additivo o due capability discordano
per errore: includere le versioni concordanti incompatibili di R4.

| Criterio per MR01 | Evidenza attesa |
|---|---|
| Sei confini positivi | T01–T06, stati a ingresso/ritorno, conteggi per frame ed eventi letterali; NESTED e NEW senza P anche con capability non usate false/null |
| R4 capability | Rifiuto SP/S con false/null, copie context/manager concordi; separato controllo copie discordanti |
| R4 propagation | Rifiuto NESTED con S/P2 e NEW con SP/P1, pur con entrambe capability true e trace ben ordinata |
| R4 stato di ritorno | Rifiuto N dopo END L2 soltanto, con P1 viva; sia legacy senza F01 sia IR moderno con effectiveContext coerente |
| Effetti completi | Rifiuto L/SP obbligatori assenti, P/S/SP aggiuntivi e termine fisico senza evento o senza ownership giustificativa |
| F03 | Rifiuto resume anticipato, P terminata in after/previous/during, riapertura dello stesso simbolo; conservazione dei tre payload R3 archiviati |
| F01 | PROXY bypass eredita; AspectJ senza premessa resta UNKNOWN; ASSUMED_APPLIED non diventa prova runtime; UNKNOWN prior non diventa N |
| F02 | REQUIRED/P1 e NESTED/P1 comuni; NEW con attività/manager noti e identità null; niente perdita delle proprietà comuni; niente effetti di ramo incondizionati |
| D2 su validatore, renderer e consumer | L UNKNOWN/null ammesso soltanto come marcatore tentato/irrisolto; nessuna etichetta, conteggio o inferenza di scope sicuramente eseguito, transazione riuscita o fonte certa di effetti |
| D4 e limiti ammessi | After U solo con continuazione effettivamente irrisolta e motivo verificabile; conservazione separata di ogni informazione certa sul lifetime; rifiuto di effetti incompatibili e cancellazione di invarianti anche con UNKNOWN. Capability non true senza SP/S; nessuna qualifica del rollback |
| Compatibilità | Otto modelli storici ancora leggibili/validi se semanticamente coerenti; le stesse alterazioni R4 sono rifiutate anche senza campi additivi |

Per F01/F02/F03 mantenere i test esistenti e aggiungere verifiche sui dati
contrattuali necessari. Non sostituire il rifiuto indipendente con il solo
confronto «il generatore produce il medesimo JSON». La validazione semantica è
congiunta: un lifetime ben formato non sana una capability incompatibile.

Verifiche locali pertinenti **proposte per MR01**, non eseguite in MR00:

- Le quattro suite `tests/transaction-boundaries.py`,
  `transaction-self-invocation.py`, `transaction-context-alternatives.py`,
  `transaction-physical-lifetime.py`, comprensive delle regressioni nuove.
- Regressioni factory/profili e controlli repository/Ruff già pertinenti a T01;
  controlli rendering locali già previsti per gli output eventualmente cambiati.
  Un tool assente produce NOT RUN, mai PASS.
- Confronto finale del diff e dei manifest di input/artefatti storici; annotare
  distintamente il rifiuto atteso di un negativo e il risultato della suite.

Non si richiedono nuove campagne generali, benchmark, ambienti Spring/AspectJ,
provider, CI remota o piattaforme ulteriori. I 95 test e i replay citati da R4
restano evidenza storica; non sono un risultato MR00 né un futuro PASS automatico.

## 5. Chiusura MR00 e arresto

MR00 fornisce una relazione che distingue le transizioni valide dalle invalide,
con effetti chiusi, istanti definiti e oracoli indipendenti. Lo schema v1 è
sufficiente per questo perimetro. D1–D4 sono decisioni architetturali approvate
dall'utente, con i vincoli D2/D4 espliciti;
gli esiti runtime e i percorsi rollback non modellati restano limiti dichiarati,
senza richiedere un nuovo schema nel singolo incremento.

Controlli di consegna MR00: sola lettura degli input, consistenza dei riferimenti
Txx/Oxx, sintassi/tabellarità CSV, integrità dei file preesistenti e stato Git.
Non costituiscono una nuova campagna QA dell'engine. Stato correzione R4-F01:
**NOT IMPLEMENTED**. Suite/replay/rendering nuovi: **NOT RUN**. MR01: **NOT STARTED**.

Sono aggiunti soltanto i tre deliverable MR00 in `docs/reports/`. Nessun codice,
test o standard preesistente modificato; nessun commit, merge, push, worktree,
modifica a Familiar, skill attivata o implementazione T02. Fermarsi alla consegna.
