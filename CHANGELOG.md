# Changelog

Tutte le modifiche rilevanti a questo progetto sono documentate in questo file.

## [In sviluppo]

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
