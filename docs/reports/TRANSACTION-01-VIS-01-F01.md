# MANA-TRANSACTION-01-VIS-01-F01 — R6 Label Layout Fix

Verdetto: **FIX_READY_FOR_REVIEW**. Data: 2026-10-23.

Corretto esclusivamente il layout dell'etichetta R6 nel renderer PlantUML della
vista mixed. Il tipo resta `RESUME_REQUIRES_COMPLETION`, visualizzato su due
righe `RESUME_REQUIRES_` / `COMPLETION`, senza abbreviazioni. La relazione rimane
R6, da a/P1 ad a/P2; evidenze, classificazioni e modelli T01/S01/S02 invariati.
La verifica visiva librsvg del risultato finale è **PASS**; una nuova review
indipendente della correzione resta **NOT_RUN**.

## Baseline e ambito

Branch verificato: `feature/mana-transaction-visualization`.
HEAD prima e dopo: `a222018fa50a3e1286a01f6da6c224a4dea242ed`.
Letti report VIS-01/R1, standard visualization-v1 e README degli esempi.
La riproduzione usa sorgente e SVG consegnati in R1, non un PNG PlantUML.
SHA-256 SVG iniziale:
`7c199e8586f5c481a94d8d3a82ea989faa4229850d91a6f4c373ed056282a796`.

I 13 materiali preesistenti, inclusi i sei protetti, coincidono per SHA-256 e
mode con l'inventario R1: [preservation.json](TRANSACTION-01-VIS-01-F01/preservation.json).
Confrontato anche lo snapshot iniziale dei file esistenti sotto docs/scripts/tests:
le sole quattro variazioni sono renderer, test VIS, sorgente C mixed e suo SVG.
Le evidenze R1 e VIS-01 precedenti sono preservate come documentazione storica.
Nessun commit, staging, merge, push, nuovo worktree o cambio branch. Indice vuoto.
Nessuna modifica a Familiar, REL-01/A, motori semantici o attivazioni di skill.

## Diagnosi con evidenza

Ambiente equivalente a R1: rsvg-convert/librsvg 2.61.3, cairo 1.18.4,
pango 1.57.0, harfbuzz 14.3.1, fontconfig 2.18.3.
Rasterizzazione nativa con `rsvg-convert --background-color=white`.

Il contenitore originale ha width=876px, height=889px e viewBox=`0 0 876 889`;
anche lo style dichiara le medesime dimensioni. Non contiene clip-path.
R6 inizia a x=607.99, baseline y=503.3366, sans-serif 13;
textLength=260.9331 e lengthAdjust=spacing. Il termine nominale è 868.9231,
quindi la sola geometria dichiarata non spiega il difetto.

Una sonda isola lo stesso elemento text su un canvas ampio e ne misura i pixel
non bianchi: bbox relativa alla baseline `(0,-10,275,2)`, cioè termine destro
stimato 882.99 nel diagramma, oltre il viewport di circa 7 px. La misura isolata
è rasterizzata a coordinate intere; eventuali frazioni subpixel non cambiano
questa conclusione. La rimozione di textLength e lengthAdjust dà PNG identici
byte per byte: questi attributi non vincolano la larghezza nel percorso librsvg
eseguito. Una copia diagnostica con viewport e width portati a 1100, senza
spostare il grafo, mostra il suffisso prima nascosto. Questa copia è solo prova
della causa e non la soluzione consegnata.

La sonda Pango sans-serif 13px riporta Helvetica 9.75pt, advance logico 278px;
il bbox osservato librsvg resta la misura decisiva. `fc-match sans-serif`
restituisce invece Verdana: il risultato del comando fontconfig non basta a
stabilire il font usato da Pango su questo host. Non è stato identificato il
font fisico interno della JVM; non si attribuisce il difetto a uno specifico
file font Java. L'evidenza dimostra una differenza tra la metrica incorporata
nell'SVG PlantUML e il testo effettivamente rasterizzato, con assenza di
adeguamento a textLength nel percorso eseguito e conseguente clipping al bordo
radice. Non è una perdita di dati S02 né un clip-path locale.

[Metriche e versione](TRANSACTION-01-VIS-01-F01/diagnosis.json),
[sonda riproducibile](TRANSACTION-01-VIS-01-F01/diagnose.py),
[viewport diagnostico ampliato](TRANSACTION-01-VIS-01-F01/expanded.png).

## Correzione minima

Nel solo ramo del tipo `RESUME_REQUIRES_COMPLETION`, `graph_source` emette
`MIXED / RESUME_REQUIRES_\nCOMPLETION\nCONDITIONAL / R6 / evidence.json`.
La sanitizzazione degli altri tipi, gli alias, gli endpoint, lo stile delle
frecce e l'indice delle relazioni rimangono invariati. Il test C esistente ora
richiede il wrapping completo e il riferimento R6. Nessuna modifica manuale
all'SVG: sorgente e SVG finali provengono dal renderer e PlantUML 1.2024.8.

[Diff rispetto al worktree pre-F01](TRANSACTION-01-VIS-01-F01/layout.diff)
(renderer, sorgente e test; SVG prima/dopo separati per evitare una riga XML enorme).
Il diff rispetto a HEAD include anche il lavoro VIS-01 preesistente e non misura
la sola correzione F01.

## Verifica visiva finale

Ispezionati direttamente i PNG librsvg dei file SVG prima/dopo, con fondo bianco
a dimensione nativa. Il risultato finale è 838×889px, senza ingrandimento globale
e senza variazioni dei font. Il wrapping mantiene l'identificatore completo e
leggibile. Le tre righe R6 terminano circa a x=820.16, 762.50 e 813.99: tutte
entro 838px. Nessuna sovrapposizione nuova, testo troncato, elemento fuori dal
contenitore o associazione ambigua osservati. C7, C8, R1–R6, nodi frame/P,
premesse e legenda rimangono leggibili. Verifica desktop a scala 1:1: **PASS**.

| Controllo | Risultato |
|---|---|
| R6 completa e comprensibile | PASS, underscore conservato al punto di wrapping |
| Assenza clipping/sovrapposizioni/elementi fuori contenitore | PASS, ispezione del PNG finale |
| Identità archi e informazioni | PASS, sorgente uguale salvo wrapping; JSON identici |
| Browser aggiuntivo | NOT_RUN: `cua.getBrowser` restituisce `No browser is available` |
| Secondo renderer SVG | NOT_RUN: resvg e Inkscape non disponibili nel PATH |

- [SVG prima](TRANSACTION-01-VIS-01-F01/before.svg) / [SVG dopo](TRANSACTION-01-VIS-01-F01/after.svg).
- [PlantUML prima](TRANSACTION-01-VIS-01-F01/before.puml) / [PlantUML dopo](TRANSACTION-01-VIS-01-F01/after.puml).
- [PNG prima](TRANSACTION-01-VIS-01-F01/before.png) / [PNG dopo](TRANSACTION-01-VIS-01-F01/after.png).
- [SVG finale nell'esempio](../examples/transaction-01-vis-01/C/mixed-replacement.svg).

## Regressioni e determinismo

Tutti i controlli sotto sono stati eseguiti dopo il wrapping finale, exit 0.
Comandi ed esiti in [checks.json](TRANSACTION-01-VIS-01-F01/checks.json);
log integrali nella stessa cartella. Nessuna nuova campagna generale.

| Verifica | Esito |
|---|---|
| transaction-visualization | PASS, 13 test, nessuno skip, rendering PlantUML effettivo |
| transaction-boundaries | PASS, 16 |
| transaction-physical-lifetime | PASS, 19 |
| transaction-context-alternatives | PASS, 21 |
| resource-timeline | PASS, 22 |
| wait-dependencies | PASS, 22 |
| Pacchetto VIS-01 | **113 PASS**, nessuno skip |
| PlantUML -checkonly / -tsvg | PASS, 14 sorgenti, due rigenerazioni complete |
| SVG finali e ripetuti | PASS, XML valido e identità byte per byte su 14/14 |
| Altri diagrammi rigenerati | 13 SVG identici ai consegnati; solo C mixed cambia |
| Source/evidence deterministici, input non mutati | PASS, tre scenari; 3 evidence.json identici |
| bash scripts/validate-repo.sh | PASS |
| Ruff check / format --check sui tre Python VIS | PASS |

[Riscontri mirati](TRANSACTION-01-VIS-01-F01/targeted.json) e
[script dell'esecuzione](TRANSACTION-01-VIS-01-F01/verify.py).
Lo script dell'esecuzione documenta il confronto col worktree iniziale e usa
lo snapshot temporaneo `/private/tmp/mana-vis-f01/before.json`; non è un nuovo
runner pubblico. I log e i manifest consegnati conservano i risultati anche se
la directory temporanea viene eliminata. La sonda diagnose.py si riesegue dalla
root usando gli SVG prima/dopo consegnati e la directory temporanea indicata.

## Rischi residui

Il PASS visivo riguarda librsvg e i font di questo ambiente; nessun Browser PASS,
nessuna garanzia trasversale a versioni/font non eseguiti. Il wrapping locale
risolve il caso riprodotto; non qualifica ogni futura etichetta arbitraria.
La stringa continua resta nel JSON originale, mentre nel diagramma si legge su
due righe senza eliminare caratteri. Nessuna semantica runtime Spring/Oracle,
lock acquisito o deadlock è stata verificata o promossa: resta NOT_RUN.
Consegna terminata in attesa di review, senza consolidamento Git.
