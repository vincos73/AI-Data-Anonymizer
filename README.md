# OMISSIS

**OMISSIS** aiuta a preparare una versione più sicura dei documenti prima di incollarli in ChatGPT, Claude, Gemini o altri strumenti di intelligenza artificiale.

Il progetto è pensato soprattutto per utenti italiani e per un uso semplice: installi l'app desktop, carichi un documento e sostituisci localmente i dati riconosciuti. Il software non invia file o testo ad API esterne.

La web app esiste solo come opzione avanzata per sviluppatori, demo locali o installazioni self-hosted su infrastruttura controllata.

[English version](README.en.md)

## Scarica App Desktop

Versione del codice: **v0.6.14**. Le build già pubblicate possono avere un numero precedente: usa la pagina Releases e controlla il numero mostrato nell'app.

| Sistema | Download |
| --- | --- |
| Mac Apple Silicon, M1/M2/M3/M4 o successivi | [Apri l'ultima release](https://github.com/vincos73/AI-Data-Anonymizer/releases/latest) e scarica l'artefatto che inizia con `OMISSIS-macOS-Apple-Silicon` (`.dmg` o `.zip`) |
| Windows | [Apri l'ultima release](https://github.com/vincos73/AI-Data-Anonymizer/releases/latest) e scarica `OMISSIS-Setup.exe`; lo ZIP resta disponibile come versione portatile |

Tutti i file sono disponibili nella pagina [Releases](https://github.com/vincos73/AI-Data-Anonymizer/releases).

## Installazione Facile

### Mac

1. Scarica il file `.dmg` oppure `.zip`.
2. Se usi il DMG, aprilo e trascina **OMISSIS** nella cartella **Applicazioni**. Se usi lo ZIP, estrailo e sposta **OMISSIS.app** in **Applicazioni**.
3. Apri l'app da **Applicazioni**.

Le build pubblicate possono essere firmate e notarizzate quando il workflow GitHub è configurato con i secrets Apple Developer. Se scarichi una build non notarizzata e macOS mostra un avviso sullo sviluppatore non identificato:

1. fai click destro su **OMISSIS**;
2. scegli **Apri**;
3. conferma di nuovo **Apri**.

### Windows

1. Scarica `OMISSIS-Setup.exe`.
2. Apri il file e completa l'installazione guidata.
3. Avvia **OMISSIS** dal menu Start. Al termine dell'installazione puoi anche aprirla subito.

L'installer non richiede privilegi da amministratore e aggiunge automaticamente OMISSIS al menu Start. `OMISSIS-Windows.zip` resta disponibile per chi preferisce una versione portatile senza installazione.

L'installer semplifica i passaggi, ma le build non firmate possono ancora mostrare un avviso di Microsoft Defender SmartScreen. La firma digitale Authenticode è un intervento separato.

Su Windows i vecchi file `.doc` non sono supportati direttamente: convertili prima in `.docx`.

## Come Si Usa

1. Apri l'app.
2. Carica un documento, trascinalo nella finestra o incolla un testo.
3. Scegli la modalità di protezione e clicca **Analizza dati**.
4. Rivedi i dati rilevati: spuntato significa “sarà anonimizzato”, non spuntato significa “resterà visibile”. Puoi cercare, filtrare o aggiungere manualmente ciò che manca.
5. Clicca **Ho controllato, continua**, quindi **Crea copia protetta**. Il flusso laterale indica sempre il passaggio corrente.
6. Leggi il report finale con conteggi, categorie protette, modalità, formato, stato di salvataggio e avvisi di controllo. In questa fase l'elenco dei rilevamenti si chiude per lasciare spazio al confronto tra originale e copia protetta; puoi riaprirlo con **Modifica selezioni**.
7. Controlla il risultato prima di condividerlo, quindi usa **Copia per ChatGPT** per il testo oppure **Salva copia protetta** per un documento. Il file o testo originale non viene modificato.
8. Se ti serve tracciare l'operazione, apri **Strumenti > Registro attività**.
9. Se usi la modalità Reversibile, salva anche la mappa locale cifrata da **Strumenti > Salva mappa reversibile**.

Caricamento, OCR, analisi e anonimizzazione mostrano l'avanzamento e possono essere annullati. Un'operazione interrotta o fallita non sostituisce il risultato precedente. La conversione di un PDF in testo avvia automaticamente una nuova analisi sul testo normalizzato.

Per i PDF puoi mantenere il formato originale, ottenendo un PDF rasterizzato con oscuramenti permanenti, oppure trasformarlo in testo: il testo perde l'impaginazione originale ma diventa più facile da rileggere, copiare e usare con ChatGPT o altri strumenti di IA.

Scorciatoie principali: `Cmd/Ctrl+O` carica un documento, `Cmd/Ctrl+Invio` esegue il passaggio corrente, `Cmd/Ctrl+F` cerca nei dati rilevati, `Spazio` include o esclude la riga selezionata e `Cmd/Ctrl+S` salva il risultato. La guida completa è disponibile in **Aiuto > Come rivedere i dati rilevati**.

## Modalità di Protezione

### Standard

La modalità Standard mantiene più leggibile il testo. Per persone, organizzazioni e indirizzi conserva le iniziali. Negli enti territoriali e accademici mantiene in chiaro la funzione istituzionale e abbrevia soltanto il nome identificativo, così il contesto degli attori dell'atto resta comprensibile.

Esempio:

```text
Mario Rossi -> M. R.
Alfa Beta S.r.l. -> A. B. S. r. l.
Provincia di Potenza -> Provincia di P.
Università degli Studi della Basilicata -> Università degli Studi della B.
```

In modalità Standard le date non vengono anonimizzate.

### Massima Protezione

La modalità **Massima protezione** sostituisce i dati riconosciuti con segnaposto completi e anonimizza anche formati data comuni.

Esempio:

```text
Mario Rossi -> <PERSONA>
10/01/1980 -> <DATA>
mario@example.com -> <EMAIL>
```

Usa questa modalità quando devi condividere testo con chatbot o servizi esterni e vuoi ridurre al minimo i dettagli identificativi.

Seleziona questa modalità per documenti ad alto rischio o quando oscurare il maggior numero possibile di dettagli è più importante della leggibilità.

### Reversibile

La modalità **Reversibile** usa segnaposti numerati e genera una mappa locale cifrata con password.

Esempio:

```text
Mario Rossi -> <PERSONA_1>
mario@example.com -> <EMAIL_1>
10/01/1980 -> <DATA_1>
```

Il testo con segnaposti può essere incollato in ChatGPT o altri strumenti. Quando ricevi una risposta che contiene gli stessi segnaposti, puoi incollarla nell'app e usare **Strumenti > Ricostruisci testo con mappa** per reinserire localmente i valori reali.

La mappa `.omissis-map` contiene i valori originali cifrati: resta sul tuo dispositivo, va protetta come materiale sensibile e non va caricata in chatbot o servizi cloud.

Questa modalità è disponibile per testo incollato, `.txt` e `.docx` nell'app desktop. Per `.md`, `.csv` e PDF usa **Massima protezione**, perché questi formati producono output non reversibili.

## Dati Riconosciuti

OMISSIS riconosce, con regole conservative:

- indirizzi email;
- indirizzi PEC, riconosciuti separatamente dalle email ordinarie quando il dominio o il contesto li indicano;
- numeri di telefono italiani, inclusi formati con spazi, punti, trattini o slash, e numeri internazionali con prefisso `+`;
- IBAN italiani e internazionali, con verifica del checksum e della lunghezza per paese, anche scritti con spazi;
- numeri di carta di pagamento, con verifica del checksum (algoritmo di Luhn) e riconoscimento con o senza spazi/trattini;
- codice fiscale;
- partita IVA;
- codici SDI, codici destinatario e codici univoci ufficio quando indicati con contesto esplicito;
- numeri di tessera sanitaria quando indicati con contesto esplicito;
- documenti d'identità, passaporti e patenti quando indicati con contesto esplicito;
- targhe veicolo quando indicate con contesto esplicito;
- numeri di protocollo, pratica, fascicolo o istanza quando indicati con contesto esplicito;
- riferimenti catastali come foglio, particella, mappale, subalterno, sezione e categoria catastale;
- indirizzi italiani con segnali forti come via, viale, piazza, corso, anche scritti in minuscolo quando è presente il numero civico;
- CAP indicato esplicitamente (es. `CAP 85100`) o seguito dal nome di una località (es. `00185 Roma`);
- regioni, province e comuni italiani, usando l'elenco locale ISTAT aggiornato al 21 febbraio 2026 e segnali contestuali per limitare i falsi positivi;
- nomi di persone con contesto forte, per esempio nascita, residenza o intestatario di pagamento;
- aziende con forme giuridiche come `S.r.l.`, `S.p.A.`, `S.n.c.`, `S.a.s.`, cooperative e simili;
- enti territoriali come `Provincia di Potenza`, `Comune di Roma`, `Regione Basilicata`;
- date comuni in modalità Massima protezione e Reversibile.

### Nomi e località senza contesto: NER locale

Le build desktop includono già spaCy e il modello italiano leggero `it_core_news_sm`: il NER è quindi attivo senza installazioni aggiuntive.

Se avvii OMISSIS dal codice sorgente, puoi installare il riconoscimento NER locale con:

```bash
pip install "ai-data-anonymizer[ner]"
python -m spacy download it_core_news_sm
```

Il modello gira interamente sul tuo computer: nessun dato viene inviato a servizi esterni. Quando è attivo, la barra laterale mostra `Regole + NER` e i nomi o le località trovati dal modello compaiono nella tabella con origine `NER locale (spaCy)`. Le località italiane riconosciute dall'elenco integrato mostrano invece l'origine `Elenco località italiane (ISTAT)`. Per disattivare spaCy senza disinstallarlo, imposta la variabile d'ambiente `OMISSIS_NER=0`.

Il motore supporta anche `it_core_news_md` e `it_core_news_lg` quando sono installati manualmente. Il confronto ripetibile tra i modelli è disponibile con:

```bash
python scripts/benchmark_ner_models.py
```

Nel benchmark sintetico della `v0.6.3`, il modello small e il large riconoscono entrambi tutti i 25 dati attesi nei casi centrali italiani e amministrativi, senza i falsi positivi controllati. Il large resta più efficace su alcuni nomi internazionali con diacritici o più componenti: se questi documenti sono prevalenti, può essere installato manualmente. Il benchmark riduce il rischio di regressioni, ma non sostituisce la revisione umana prima di condividere un documento.

## Formati Supportati

| Formato | Supporto |
| --- | --- |
| `.txt`, `.md`, `.csv` | Legge e salva file di testo anonimizzati |
| `.docx` | Legge e salva documenti Word mantenendo struttura, stili, tabelle e immagini quando possibile |
| `.pdf` | Può salvare un PDF rasterizzato con oscuramenti permanenti oppure convertirlo in testo ricomponendo righe e sillabazioni per migliorare l'analisi e l'uso con un LLM; gestisce anche pagine miste testo/immagini usando OCR locale Tesseract quando disponibile |
| `.doc` | Supportato solo su macOS, convertito in `.docx` prima dell'anonimizzazione |

I PDF scansionati o composti solo da immagini richiedono OCR. OMISSIS può usare **Tesseract OCR locale** quando è installato sul computer; non chiama servizi OCR esterni. Se Tesseract non è disponibile o non trova testo affidabile, l'app blocca il PDF, così l'utente non scambia un file non letto per un documento già sicuro. Il PDF anonimizzato viene ricostruito come immagini di pagina redatte: questo evita di lasciare il testo originale sotto gli oscuramenti, ma il testo del PDF finale non sarà copiabile o ricercabile.

## Privacy

La versione desktop lavora localmente sul computer. Non invia testo o file a OpenAI, Google, Anthropic, servizi OCR, analytics o altre API esterne.

Per i dettagli operativi leggi la pagina [Sicurezza e privacy](SICUREZZA.md).

L'app desktop mantiene un registro attività locale consultabile dal menu **Strumenti > Registro attività**. Il registro salva solo metadati: data e ora, operazione, modalità, conteggi per categoria, estensione, dimensione e hash SHA-256 dei file quando disponibili. Non salva testo originale, testo anonimizzato, valori trovati o percorso completo dei file. Dalla stessa finestra puoi disattivarlo, scegliere quante operazioni conservare o cancellarlo.

La modalità Reversibile crea una mappa locale cifrata con password. Questa mappa è l'unico posto in cui OMISSIS conserva la corrispondenza tra segnaposto e valori reali, e viene salvata solo quando lo chiedi esplicitamente. Risultati, mappe e impostazioni locali vengono sostituiti solo dopo una scrittura completa; sui sistemi compatibili i file sensibili sono accessibili soltanto all'utente.

La web app non è necessaria per l'uso normale. Se la avvii in locale su `127.0.0.1`, resta sul tuo computer come un'interfaccia browser. Se invece la pubblichi su un server, il testo inviato alla web app arriva a quel server: per documenti sensibili usala solo su infrastruttura sotto il tuo controllo e con HTTPS.

Per i file `.docx`, l'app anonimizza il testo visibile e pulisce contenuti nascosti comuni come metadati, commenti, caselle di testo, note a piè di pagina, note di chiusura e alcune revisioni.

## Limiti Importanti

OMISSIS è uno strumento di riduzione del rischio, non una garanzia legale di anonimizzazione perfetta.

- Il motore è basato su regole ed è volutamente conservativo.
- Alcuni dati personali possono non essere riconosciuti.
- In modalità Standard alcune informazioni, come iniziali e date, possono restare utili a identificare una persona dal contesto.
- Devi sempre rileggere il risultato prima di condividerlo con chatbot, cloud, collaboratori o terze parti.

## Opzione Avanzata: Web App Self-Hosted

Per la maggior parte degli utenti è consigliata l'app desktop scaricabile dalla sezione **Scarica App Desktop**. La web app serve quando vuoi usare il motore da browser locale, in una rete interna o dentro Docker.

Per avviare la web app in locale:

```bash
pip install -e ".[web]"
ai-data-anonymizer-web
```

Poi apri:

```text
http://127.0.0.1:8080
```

La web app permette di incollare testo oppure caricare documenti supportati e scaricare il file anonimizzato. Per impostazione predefinita accetta fino a **100.000 caratteri** per il testo estratto e **10 MB** per file.

Desktop e web app partono in modalità **Standard**, scelta per mantenere più leggibili struttura, ruoli e contesto del documento. Per atti ad alto rischio o quando la priorità è oscurare il maggior numero possibile di dettagli, seleziona **Massima protezione**. La checklist finale ricorda sempre il controllo manuale prima della condivisione.

La modalità Reversibile e il ripristino tramite mappa cifrata sono disponibili solo nell'app desktop. La web app espone esclusivamente Standard e Massima protezione: questa scelta evita di inviare passphrase e mappe a un server. Una futura versione potrà aggiungere la cifratura interamente nel browser.

Con Docker:

```bash
docker build -t ai-data-anonymizer .
docker run --rm -p 8080:8080 ai-data-anonymizer
```

Per deploy non dimostrativi:

- usa HTTPS;
- richiedi autenticazione;
- disabilita log dei body HTTP nei proxy;
- evita analytics, session replay o script terzi nelle pagine che trattano documenti;
- usa limiti di upload conservativi;
- pubblica termini privacy chiari.

## Sviluppo

Requisiti:

- Python 3.10, 3.11, 3.12 o 3.13;
- Git.

Avvio desktop da sorgente:

```bash
git clone https://github.com/vincos73/AI-Data-Anonymizer.git
cd AI-Data-Anonymizer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[desktop]"
ai-data-anonymizer
```

Se vuoi sviluppare anche web app e API:

```bash
pip install -e ".[desktop,web]"
```

Test:

```bash
pip install -e ".[desktop,web]"
python -m unittest discover -s tests -v
```

La suite copre falsi positivi italiani, riconoscimento di persone e organizzazioni, enti territoriali, PEC, numeri di protocollo/pratica, identificativi strutturati, modalità Standard, Massima protezione e Reversibile desktop, mappe cifrate, anonimizzazione documenti, preservazione della struttura e della formattazione `.docx`, pulizia di contenuti nascosti `.docx`, OCR locale opzionale per PDF scansionati e pagine miste, rifiuto dei PDF non leggibili e redazione PDF rasterizzata senza testo originale estraibile.

## Build Desktop

Build macOS:

```bash
./scripts/build_macos_app.sh
```

La build produce il DMG quando macOS consente la creazione del volume. In ambienti isolati dove `hdiutil` non può montarlo, conserva la `.app` firmata e crea automaticamente uno ZIP versionato installabile.

### Firma e notarizzazione macOS

Per distribuire OMISSIS senza il blocco Gatekeeper, serve un account Apple Developer Program e un certificato **Developer ID Application**.

Il workflow GitHub supporta questi secrets:

- `APPLE_DEVELOPER_ID_CERTIFICATE_BASE64`: certificato `.p12` Developer ID Application codificato in base64;
- `APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD`: password del file `.p12`;
- `APPLE_DEVELOPER_ID_APPLICATION`: nome identità codesign, per esempio `Developer ID Application: Nome Cognome (TEAMID)`;
- `APPLE_ID`: email dell'account Apple Developer;
- `APPLE_TEAM_ID`: Team ID Apple;
- `APPLE_APP_SPECIFIC_PASSWORD`: password specifica per app generata dall'account Apple;
- `BUILD_KEYCHAIN_PASSWORD`: password temporanea per il keychain della build.

Quando questi secrets sono presenti, la build macOS firma l'app, firma il DMG, lo invia ad Apple con `notarytool`, applica lo stapling e carica su GitHub il DMG notarizzato.

Build Windows da PowerShell:

```powershell
.\scripts\install_inno_setup.ps1
.\scripts\build_windows_app.ps1
```

La build produce `dist\OMISSIS-Setup.exe` per l'installazione guidata e `dist\OMISSIS-Windows.zip` come versione portatile. Lo script di installazione di Inno Setup scarica la release ufficiale fissata nel repository e ne verifica l'hash SHA-256 prima di eseguirla.

## Stato del Progetto

OMISSIS è un progetto open source in evoluzione. Contributi utili:

- ridurre falsi positivi e falsi negativi italiani;
- migliorare la preservazione della formattazione;
- migliorare OCR locale per PDF scansionati e immagini;
- raffinare la modalità reversibile e la ricostruzione dei testi generati dall'IA;
- aggiungere nuovi riconoscitori con test accurati;
- migliorare firma e notarizzazione delle build pubblicate.

## Licenza

MIT License. Vedi [LICENSE](LICENSE).
