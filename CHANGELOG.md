# Changelog

Tutte le modifiche rilevanti a questo progetto sono documentate in questo file.

## [In sviluppo]

## [0.6.21] - 2026-08-04

### Migliorato
- Un selettore `Documento: Scuro / Carta chiara` cambia insieme i tre pannelli di lettura e ricorda localmente la preferenza.
- La modalità Carta chiara usa inchiostro, selezione ed evidenziazioni ad alto contrasto senza modificare l'interfaccia scura circostante.
- Il marchio nell'interfaccia e l'icona dell'app hanno una resa piatta e nitida, senza l'alone sfocato attorno al simbolo OMISSIS.

## [0.6.20] - 2026-08-04

### Migliorato
- Il selettore del tipo di dato mostra una freccia coerente e visibile su macOS e negli altri ambienti Qt.
- Il testo nei pannelli Originale, Risposta dell'IA e risultato anonimizzato usa una dimensione più leggibile con maggiore interlinea.
- La conferma per scartare lavoro non salvato usa un dialogo OMISSIS scuro, con avviso e azione distruttiva riconoscibili anche senza affidarsi soltanto al colore.

## [0.6.19] - 2026-08-04

### Migliorato
- Tutte le sostituzioni sono evidenziate da subito anche nell'anteprima anonimizzata; la selezione corrente resta distinguibile con un'evidenziazione più intensa.
- Il disclaimer dell'anteprima è più breve e affiancato al titolo, così testo originale e anteprima iniziano alla stessa altezza.
- Il dialogo per classificare un dato aggiunto manualmente adotta il tema OMISSIS, mostra la selezione e usa azioni esplicite e accessibili.

## [0.6.18] - 2026-08-04

### Migliorato
- Il dato attivo viene evidenziato anche nella posizione corrispondente dell'anteprima anonimizzata, compresi iniziali e segnaposto numerati della modalità Reversibile.
- Le evidenziazioni nel testo originale sono più nette sullo sfondo scuro, mantenendo il testo bianco leggibile per tutte le categorie.

## [0.6.17] - 2026-08-04

### Migliorato
- Il testo originale e il testo anonimizzato scorrono insieme, in entrambe le direzioni, mantenendo la posizione relativa anche quando l'anteprima viene aggiornata.

### Corretto
- Il NER locale non interpreta più come località comuni espressioni giuridiche e istituzionali quali `Difetto di Motivazione`, `Istituto Professionale`, `Mancata Pronuncia` e `Giudice delle Leggi`.
- I nomi delle Corti di appello non vengono più inglobati in un'unica località: `Potenza` e `Firenze` restano riconosciute separatamente come toponimi reali.
- `Autorità Giudiziaria` e le altre locuzioni giuridiche controllate non vengono più interpretate come persone quando il modello spaCy cambia etichetta in base al contesto.

## [0.6.16] - 2026-08-04

### Migliorato
- Un dato aggiunto manualmente viene propagato a tutte le varianti di maiuscole e minuscole, conservando la grafia originale per la ricostruzione reversibile.

### Corretto
- Le espressioni `Via Gradata` e `Via Preliminare` non vengono più interpretate come indirizzi.
- Le parole `Comparsa` e `Note`, quando seguono etichette come `Località` o `Frazione`, non vengono più interpretate come località.

## [0.6.15] - 2026-08-04

### Migliorato
- La modalità Reversibile guida l'utente attraverso salvataggio del File di ripristino, condivisione della copia protetta e inserimento della risposta dell'IA.
- Dopo il ripristino, la risposta dell'IA con i segnaposti e il testo ricostruito sono mostrati affiancati; il documento originale resta disponibile con un comando secondario e il risultato sensibile ha un avviso persistente.

### Corretto
- La creazione della password del File di ripristino usa un'unica finestra coerente per inserimento e conferma, evitando la doppia richiesta con dimensioni diverse.

## [0.6.7] - 2026-07-31

### Corretto
- Su Windows il testo originale e il risultato mantengono esplicitamente testo chiaro su fondo scuro, senza dipendere dalla palette nativa di Qt o dai colori incorporati nel testo incollato.

### Migliorato
- Le parole rilevate nel testo originale usano evidenziazioni più luminose e distinguono con maggiore decisione il dato attivo, conservando testo bianco leggibile.

## [0.6.6] - 2026-07-28

### Corretto
- Le build NER dichiarano esplicitamente `click`, necessario all'interfaccia da riga di comando di spaCy: gli ambienti puliti macOS e Windows possono ora scaricare e includere il modello italiano senza dipendere da pacchetti preesistenti.

## [0.6.5] - 2026-07-28

### Modificato
- Desktop e web app selezionano ora **Standard** come modalità iniziale, per mantenere più leggibili struttura, ruoli e contesto dei documenti destinati a un LLM.
- Testi di aiuto e checklist distinguono con maggiore chiarezza la modalità Standard dalla Massima protezione, consigliata per documenti ad alto rischio.

## [0.6.4] - 2026-07-28

### Corretto
- Enti territoriali e riferimenti catastali ora terminano prima dell'etichetta successiva: espressioni come `Provincia di Potenza. CAP 85100` e `subalterno 6. Email:` non inglobano più `CAP` o `Email` nel dato precedente.
- Nel testo originale, Tab sposta il focus e `Cmd/Ctrl+Invio` esegue il passaggio corrente senza inserire caratteri nel documento.
- Nomi, descrizioni e avvisi esposti alle tecnologie assistive seguono ora lo stato reale dell'analisi, della conferma e del risultato.
- La tabella di revisione non forza più focus e scorrimento sulla prima riga: VoiceOver e le API di accessibilità macOS possono leggerla senza arresti, mentre la selezione resta sotto il controllo dell'utente.

### Migliorato
- Dopo l'analisi la revisione dei dati diventa l'area principale e il pulsante finale rende esplicita la conferma delle spunte, senza sottrarre il focus al testo.
- Eliminata la seconda azione visibile di copia; il report finale presenta conteggi, modalità, formato e stato di salvataggio in una struttura più leggibile.
- I filtri mostrano solo categorie presenti nel documento e distinguono Persone, Contatti, Finanziari, Documenti, Luoghi, Date ed Enti senza nasconderli sotto “Altro”.
- La barra laterale concentra lo stato locale di regole e NER in un solo avviso e mostra la sezione della mappa esclusivamente quando è pertinente.
- Aggiunta una guida in-app alla revisione con significato delle spunte, affidabilità, origine, selezione manuale e scorciatoie.

## [0.6.3] - 2026-07-28

### Migliorato
- Le build desktop includono il modello italiano spaCy `it_core_news_sm` al posto di `it_core_news_lg`, mantenendo il NER locale pronto all'uso con un download molto più leggero.
- Aggiunto un benchmark end-to-end ripetibile tra modello small e large: entrambi coprono 25/25 casi centrali italiani e amministrativi senza i falsi positivi controllati; il large resta migliore sui nomi internazionali più complessi.

### Corretto
- Gli script di build preparano esplicitamente `pip`, `setuptools` e `wheel` nei nuovi ambienti virtuali e interrompono subito la build Windows quando un comando nativo fallisce.
- Il workflow di release usa Python 3.12 anche su macOS e accetta lo ZIP firmato come alternativa al DMG quando il runner non può creare il volume.

## [0.6.2] - 2026-07-28

### Aggiunto
- Riconoscimento dei riferimenti catastali relativi a foglio, particella, mappale, subalterno, sezione e categoria catastale, comprese le abbreviazioni comuni.
- L'anonimizzazione conserva le etichette catastali per mantenere comprensibile il contesto dell'atto e sostituisce soltanto codici e numeri con `<DATO_CATASTALE>`.
- Le espressioni ambigue come un semplice “foglio 12” vengono riconosciute solo in presenza di contesto catastale o di altri componenti catastali vicini.

## [0.6.1] - 2026-07-28

### Corretto
- Finestre di errore e conferma leggibili su macOS: i messaggi ora definiscono esplicitamente uno sfondo chiaro e testo scuro ad alto contrasto, evitando che il testo chiaro del tema principale venga mostrato sulla superficie chiara nativa.

## [0.6.0] - 2026-07-28

### Sicurezza
- I risultati, i CSV del registro, le impostazioni locali e le mappe reversibili vengono scritti in modo atomico: un errore durante il salvataggio non sostituisce il file precedente con un contenuto parziale.
- Le mappe reversibili e i file applicativi locali ricevono permessi riservati all'utente sui sistemi compatibili.
- Il registro attività può essere disattivato, limitato nel numero di operazioni conservate e cancellato dall'interfaccia.

### Architettura
- Separati dall'interfaccia i job in background, i workflow di analisi/anonimizzazione, la provenienza dell'output e le primitive di persistenza.
- Unificata la pipeline GitHub per tag: verifica l'allineamento della versione, costruisce macOS e Windows, genera i checksum SHA-256 e pubblica la release solo quando entrambi gli artefatti sono disponibili.
- Aggiunti al CI test desktop reali con PySide6 su macOS, Windows e Linux.
- La build macOS produce uno ZIP versionato della `.app` già firmata quando l'ambiente non consente a `hdiutil` di creare il DMG.

## [0.5.9] - 2026-07-28

### Migliorato
- Le caselle della revisione dichiarano esplicitamente che una riga spuntata sarà anonimizzata e quando la scelta si applica a tutte le occorrenze uguali.
- La colonna tecnica “Confidenza” è diventata “Affidabilità”, con giudizi leggibili e una spiegazione che chiarisce che non si tratta di probabilità statistiche.
- Aggiunti nomi accessibili, ordine di tabulazione, focus visibile e scorciatoie per caricamento, salvataggio, ricerca ed esecuzione del passaggio corrente.
- La barra degli strumenti si dispone su due righe nelle finestre più strette e i filtri possono scorrere orizzontalmente.
- Lo stato della mappa reversibile è sempre visibile nella barra laterale.
- Aumentato il contrasto dei testi secondari e ridotta la dimensione minima della finestra.

## [0.5.8] - 2026-07-28

### Aggiunto
- Caricamento documenti, OCR, analisi e anonimizzazione vengono eseguiti fuori dal thread dell'interfaccia, con avanzamento per fase o pagina e comando di annullamento.
- I job producono risultati immutabili che vengono applicati alla finestra solo dopo il completamento; annullamenti, errori o risultati riferiti a uno stato superato non modificano il lavoro precedente.

### Migliorato
- Durante un'operazione vengono temporaneamente bloccati testo, modalità e selezioni che potrebbero rendere incoerente il risultato.
- Lettura e rasterizzazione PDF controllano l'annullamento tra una pagina e la successiva.

## [0.5.7] - 2026-07-28

### Sicurezza
- Un risultato già generato viene ora marcato come obsoleto quando cambiano il testo sorgente, la modalità di protezione, le esclusioni o le selezioni manuali. L'anteprima resta visibile ma non può essere copiata o salvata finché non viene rianalizzata e rigenerata.
- Caricamento, pulizia, conversione in testo, sostituzione della mappa e chiusura chiedono conferma quando eliminerebbero testo, selezioni, risultati o mappe reversibili non salvati.
- Il registro attività associa salvataggi e anonimizzazioni alla modalità realmente usata per generare il risultato.

### Aggiunto
- Report finale visibile con modalità effettiva, dati anonimizzati ed esclusi, formato prodotto, uso dell'OCR, modifiche manuali e stato di salvataggio della mappa reversibile.
- Provenienza locale dell'output basata su revisione e impronte non reversibili di sorgente e selezioni.

## [0.5.6] - 2026-07-28

### Corretto
- Riconoscimento nei PDF di comuni come Rotondella e delle località minori presenti nel documento, come Parrutta.
- Riconoscimento degli elenchi in forma “cognome nome”, per esempio “Cresci Nicola”, anche senza NER.
- Le ragioni sociali estratte con spaziatura irregolare, come `GEO -S. S. r. l`, vengono rilevate per intero e in modalità Standard mantengono la forma giuridica (`G. S. r. l.`).

## [0.5.5] - 2026-07-28

### Migliorato
- Rafforzati i filtri del NER locale per evitare che indirizzi, enti, email, righe isolate o testo attraversato da interruzioni di paragrafo vengano classificati come persone o località.
- La rianalisi del testo estratto dai PDF combina NER, dizionari locali e regole specifiche per gli elenchi.

## [0.5.4] - 2026-07-28

### Aggiunto
- Il comando “Converti PDF in testo” normalizza righe, sillabazioni e spaziature orientandole all'analisi e all'uso con un LLM.
- Dopo la conversione viene avviata automaticamente una nuova analisi; il pulsante principale passa direttamente alla revisione/anonimizzazione.

## [0.5.3] - 2026-07-28

### Aggiunto
- Elenco locale ISTAT di comuni, province e regioni italiane, con riconoscimento contestuale di località come Basilicata, Venosa e Potenza e protezioni per i termini ambigui.
- Riconoscimento dei CAP esplicitamente etichettati o associati a una località; Standard usa il segnaposto `<CAP>` invece di conservarne le cifre.
- Trattamento contestuale degli enti in modalità Standard: `Provincia di Potenza` diventa `Provincia di P.` e `Università degli Studi della Basilicata` diventa `Università degli Studi della B.`, mentre un Dipartimento non qualificato resta leggibile.

## [0.5.2]

### Corretto
- Selezione manuale estesa a tutte le occorrenze: aggiungendo una selezione (es. "Potenza") su un testo incollato veniva redatta solo l'occorrenza evidenziata, mentre le altre uguali restavano in chiaro. Ora una selezione manuale viene applicata a ogni occorrenza letterale del valore nel testo, in modo coerente con quanto già avveniva su DOCX e PDF.

## [0.5.1]

### Corretto
- Selezioni manuali non redatte su DOCX e PDF: un dato aggiunto con "Aggiungi selezione" compariva nel pannello come "sarà anonimizzato" ma restava visibile nel documento esportato, perché la pipeline DOCX/PDF ri-analizza il testo per parte (nodi XML o pagine) e non teneva conto delle selezioni manuali. Ora ogni occorrenza letterale del valore selezionato viene redatta ovunque compaia nel documento, sia in modalità normale sia reversibile. Il bottone "Aggiungi selezione" è quindi ora disponibile anche su DOCX e PDF (resta escluso solo il formato legacy .doc).
- Titolo abbreviato "Sig." (o "Sig") non riconosciuto: "Il Sig. Mario Rossi" non faceva scattare il rilevamento della persona e il nome restava in chiaro; funzionavano solo "signor", "sig.ra" e simili.
- La "e commerciale" (&) spezzava le ragioni sociali: di "Rossi & Figli S.r.l." veniva anonimizzata solo la parte dopo la &, lasciando leggibile metà del nome aziendale.
- Collisione dei segnaposto in modalità Reversibile: se il testo conteneva già una stringa come `<PERSONA_1>`, lo stesso segnaposto veniva assegnato a un dato reale e la ricostruzione sostituiva entrambe le occorrenze, producendo un testo diverso dall'originale. Ora gli indici già presenti nel testo vengono saltati.
- OCR non funzionante su Windows: il file immagine temporaneo veniva riaperto per nome mentre era ancora bloccato dal sistema; ora viene scritto e riletto in modo compatibile con Windows.
- "Salva risultato" scartava le correzioni fatte a mano nel pannello di output per i risultati testuali; ora salva ciò che si vede nel pannello.
- I file `.csv` anonimizzati venivano salvati come `.txt`; ora mantengono l'estensione `.csv`.
- Doppia registrazione nel registro attività: l'anonimizzazione di testo incollato registrava anche una voce "Analisi" oltre a quella "Anonimizzazione".

### Aggiunto
- Riconoscimento del codice fiscale preceduto dall'etichetta "C.F." o "codice fiscale" anche quando i 16 caratteri sono separati da spazi (es. "C.F. RSS MRA 80A01 H501U"), anche se il checksum formale non è valido: la presenza dell'etichetta è considerata un contesto sufficientemente forte.
- Riconoscimento di enti/amministrazioni territoriali legati a un luogo: "amministrazione provinciale/comunale/regionale", prefettura, questura, procura (della Repubblica), tribunale e camera di commercio, ad esempio "amministrazione provinciale di Potenza" o "Prefettura di Matera".
- Riconoscimento degli IBAN internazionali (70 paesi), con verifica del checksum mod-97 e della lunghezza ufficiale per paese; prima venivano rilevati solo gli IBAN italiani.
- Riconoscimento dei numeri di telefono internazionali con prefisso `+` (es. +44, +1), validati sulla lunghezza E.164; nessun falso positivo su temperature, importi o percentuali.
- Riconoscimento degli indirizzi scritti in minuscolo (es. "via giuseppe garibaldi 12") quando è presente il numero civico, con lista di esclusione per i modi di dire come "in via preliminare".
- Riconoscimento NER locale opzionale basato su spaCy per i nomi senza contesto: si installa con l'extra `ner` più un modello italiano, gira interamente offline e si disattiva con `OMISSIS_NER=0`.

### Sicurezza
- Web app: aggiunti gli header `Content-Security-Policy` e `X-Frame-Options`; le richieste API senza `Content-Length` (body chunked) vengono rifiutate per non aggirare il limite di dimensione.

## [0.5.0]

### Aggiunto
- Riconoscimento dei nomi di persona anche senza titoli o contesto: frasi comuni come "la pratica di Mario Rossi" o "Mario Rossi ha richiesto..." ora vengono rilevate grazie a un dizionario locale di oltre 1200 nomi propri italiani, integrato nell'app. Funziona anche nelle build desktop (macOS/Windows) senza componenti aggiuntivi da installare, colmando il buco di sicurezza per cui questi nomi passavano inosservati quando non preceduti da un titolo (sig., dott., ...) o seguiti da un indizio come "nato a" o "codice fiscale".
- Esclusione dei dati rilevati anche su documenti DOCX e PDF: le caselle del pannello "Dati rilevati" ora funzionano con un documento caricato, mantenendo il formato in uscita (DOCX resta formattato, PDF resta redatto). Su questi formati l'esclusione vale per tutte le occorrenze dello stesso valore; sui PDF scansionati (OCR) un'esclusione non riconosciuta lascia comunque il dato anonimizzato, per sicurezza.
- Guida all'installazione di Tesseract OCR: quando un PDF contiene immagini e serve l'OCR locale per controllarle in sicurezza, l'app non mostra più solo un avviso in fondo alla finestra ma apre una finestra di dialogo con istruzioni specifiche per macOS (comando Homebrew copiabile), Windows (link alla pagina di download ufficiale) e Linux (comando apt copiabile), più un pulsante "Ho installato, riprova" che ricarica subito il documento.

### Corretto
- Indirizzi con CAP a 5 cifre: "Via Garibaldi 45, 00185 Roma" veniva rilevato solo fino a "0018", lasciando "5 Roma" in chiaro dopo l'anonimizzazione.
- Testo del comando illeggibile (bianco su bianco) nella finestra di dialogo per l'installazione di Tesseract OCR.
- Build macOS: la firma ad-hoc dell'app poteva risultare incoerente con l'Info.plist dopo l'impostazione della versione, lasciando la build senza DMG in modo silenzioso; ora lo script verifica sempre la firma e rimuove gli attributi estesi residui prima di firmare.

## [0.4.0] - Redesign Dark Pro

### Aggiunto
- Nuovo tema visivo "Dark Pro" per l'app desktop: rail di navigazione laterale, stepper verticale, radio card per la modalità di protezione, primaria step-aware, font IBM Plex.
- Pannello "Dati rilevati" riscritto: vista ad albero con badge per tipo, barra di confidenza, pill di filtro per categoria, campo di ricerca.
- Vista raggruppata automatica oltre i 30 risultati, con checkbox tri-state per gruppo.
- Sincronizzazione bidirezionale tra testo ed elenco dati rilevati (click su una riga muove il cursore nel testo e viceversa).
- Avviso inline per documenti PDF/DOCX con pulsante "Estrai come testo".
- Splitter verticale regolabile tra editor e pannello dati rilevati.

### Corretto
- Popup del combobox "Tipo di dato" illeggibile (testo chiaro su sfondo chiaro).
- Sovrapposizione tra il cerchietto numerato e il bordo arrotondato nello stepper.
- Colonna laterale (rail) troppo stretta, ora allargata per dare più respiro agli stepper.

## [0.3.3]
### Corretto
- Export PDF e testo modificato.

## [0.3.2]
### Corretto
- Mantenuto il formato PDF nel salvataggio.

## [0.3.1]
### Aggiunto
- Sicurezza OCR e modalità reversibile.
- Notarizzazione macOS.
### Migliorato
- Rafforzato il riconoscimento dei dati sensibili.

## [0.3.0]
### Aggiunto
- Report finale di anonimizzazione.
- Upload documenti nella web app.
- Riconoscimento documenti di identità e targhe.
- Riconoscimento codici SDI e tessere sanitarie.
- Riconoscimento PEC e numeri di protocollo pratica.
- Anonimizzazione valori nelle tabelle DOCX.
### Migliorato
- Documentazione principale in italiano.
- Esperienza desktop per utenti non tecnici.
- Etichette dei risultati più leggibili.
- Segnaposto italiani nell'anonimizzazione.
- Web app alleggerita e allineata alla desktop.

## [0.2.0]
### Aggiunto
- Build desktop per Windows.
### Migliorato
- Rafforzata la sicurezza dell'anonimizzazione di documenti italiani.

## [0.1.0]
- Prima release.
