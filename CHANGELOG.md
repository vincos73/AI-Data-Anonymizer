# Changelog

Tutte le modifiche rilevanti a questo progetto sono documentate in questo file.

## [In sviluppo]

### Aggiunto
- Esclusione dei dati rilevati anche su documenti DOCX e PDF: le caselle del pannello "Dati rilevati" ora funzionano con un documento caricato, mantenendo il formato in uscita (DOCX resta formattato, PDF resta redatto). Su questi formati l'esclusione vale per tutte le occorrenze dello stesso valore; sui PDF scansionati (OCR) un'esclusione non riconosciuta lascia comunque il dato anonimizzato, per sicurezza.
- Guida all'installazione di Tesseract OCR: quando un PDF contiene immagini e serve l'OCR locale per controllarle in sicurezza, l'app non mostra più solo un avviso in fondo alla finestra ma apre una finestra di dialogo con istruzioni specifiche per macOS (comando Homebrew copiabile), Windows (link alla pagina di download ufficiale) e Linux (comando apt copiabile), più un pulsante "Ho installato, riprova" che ricarica subito il documento.

### Corretto
- Indirizzi con CAP a 5 cifre: "Via Garibaldi 45, 00185 Roma" veniva rilevato solo fino a "0018", lasciando "5 Roma" in chiaro dopo l'anonimizzazione.

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
