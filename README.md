# OMISSIS

**OMISSIS** aiuta a preparare una versione più sicura dei documenti prima di incollarli in ChatGPT, Claude, Gemini o altri strumenti di intelligenza artificiale.

Il progetto è pensato soprattutto per utenti italiani e per un uso semplice: installi l'app desktop, carichi un documento, anonimizza tutto sul tuo computer. Il software non invia file o testo ad API esterne.

La web app esiste solo come opzione avanzata per sviluppatori, demo locali o installazioni self-hosted su infrastruttura controllata.

[English version](README.en.md)

## Scarica App Desktop

Ultima versione: **v0.4.0**

| Sistema | Download |
| --- | --- |
| Mac Apple Silicon, M1/M2/M3/M4 o successivi | [Scarica DMG per macOS](https://github.com/vincos73/AI-Data-Anonymizer/releases/download/v0.4.0/OMISSIS-macOS-Apple-Silicon.dmg) |
| Windows | [Scarica ZIP per Windows](https://github.com/vincos73/AI-Data-Anonymizer/releases/download/v0.4.0/OMISSIS-Windows.zip) |

Tutti i file sono disponibili nella pagina [Releases](https://github.com/vincos73/AI-Data-Anonymizer/releases).

## Installazione Facile

### Mac

1. Scarica il file `.dmg`.
2. Aprilo.
3. Trascina **OMISSIS** nella cartella **Applicazioni**.
4. Apri l'app da **Applicazioni**.

Le build pubblicate possono essere firmate e notarizzate quando il workflow GitHub è configurato con i secrets Apple Developer. Se scarichi una build non notarizzata e macOS mostra un avviso sullo sviluppatore non identificato:

1. fai click destro su **OMISSIS**;
2. scegli **Apri**;
3. conferma di nuovo **Apri**.

### Windows

1. Scarica il file `.zip`.
2. Estrai lo zip in una cartella.
3. Apri **OMISSIS.exe**.

Su Windows i vecchi file `.doc` non sono supportati direttamente: convertili prima in `.docx`.

## Come Si Usa

1. Apri l'app.
2. Carica un documento, trascinalo nella finestra o incolla un testo.
3. Clicca **Analizza** per vedere quali dati sono stati riconosciuti.
4. Scegli la modalità di protezione.
5. Clicca **Anonimizza**.
6. Leggi il report finale con modalità usata, numero di dati riconosciuti e avvisi di controllo.
7. Se ti serve tracciare l'operazione, apri **Strumenti > Registro attività**.
8. Se usi la modalità Reversibile, salva anche la mappa locale cifrata da **Strumenti > Salva mappa reversibile**.
9. Controlla il risultato prima di condividerlo.
10. Salva o copia il testo anonimizzato.

## Modalità di Protezione

### Standard

La modalità Standard mantiene più leggibile il testo. Per persone, organizzazioni, indirizzi ed enti territoriali conserva le iniziali.

Esempio:

```text
Mario Rossi -> M. R.
Alfa Beta S.r.l. -> A. B. S. r. l.
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

Nell'app desktop è la modalità predefinita e consigliata per l'uso con ChatGPT e altri strumenti di IA.

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
- indirizzi italiani con segnali forti come via, viale, piazza, corso, anche scritti in minuscolo quando è presente il numero civico;
- CAP seguito da nome di località (es. `00185 Roma`);
- nomi di persone con contesto forte, per esempio nascita, residenza o intestatario di pagamento;
- aziende con forme giuridiche come `S.r.l.`, `S.p.A.`, `S.n.c.`, `S.a.s.`, cooperative e simili;
- enti territoriali come `Provincia di Potenza`, `Comune di Roma`, `Regione Basilicata`;
- date comuni in modalità Massima protezione e Reversibile.

### Nomi senza contesto: NER locale opzionale

Di base i nomi di persona vengono riconosciuti solo con contesto forte, per mantenere alta la precisione. Se vuoi riconoscere anche i nomi senza contesto (per esempio `Mario Rossi ha inviato la relazione`), puoi installare il riconoscimento NER locale basato su spaCy:

```bash
pip install "ai-data-anonymizer[ner]"
python -m spacy download it_core_news_lg
```

Il modello gira interamente sul tuo computer: nessun dato viene inviato a servizi esterni. Quando è attivo, lo stato del motore mostra `NER locale attivo` e i nomi trovati dal modello compaiono nella tabella con origine `NER locale (spaCy)`. Per disattivarlo senza disinstallare, imposta la variabile d'ambiente `OMISSIS_NER=0`.

## Formati Supportati

| Formato | Supporto |
| --- | --- |
| `.txt`, `.md`, `.csv` | Legge e salva file di testo anonimizzati |
| `.docx` | Legge e salva documenti Word mantenendo struttura, stili, tabelle e immagini quando possibile |
| `.pdf` | Estrae il testo per analisi e salva un PDF rasterizzato con oscuramenti permanenti; gestisce anche pagine miste testo/immagini usando OCR locale Tesseract quando disponibile |
| `.doc` | Supportato solo su macOS, convertito in `.docx` prima dell'anonimizzazione |

I PDF scansionati o composti solo da immagini richiedono OCR. OMISSIS può usare **Tesseract OCR locale** quando è installato sul computer; non chiama servizi OCR esterni. Se Tesseract non è disponibile o non trova testo affidabile, l'app blocca il PDF, così l'utente non scambia un file non letto per un documento già sicuro. Il PDF anonimizzato viene ricostruito come immagini di pagina redatte: questo evita di lasciare il testo originale sotto gli oscuramenti, ma il testo del PDF finale non sarà copiabile o ricercabile.

## Privacy

La versione desktop lavora localmente sul computer. Non invia testo o file a OpenAI, Google, Anthropic, servizi OCR, analytics o altre API esterne.

Per i dettagli operativi leggi la pagina [Sicurezza e privacy](SICUREZZA.md).

L'app desktop mantiene un registro attività locale consultabile dal menu **Strumenti > Registro attività**. Il registro salva solo metadati: data e ora, operazione, modalità, conteggi per categoria, estensione, dimensione e hash SHA-256 dei file quando disponibili. Non salva testo originale, testo anonimizzato, valori trovati o percorso completo dei file.

La modalità Reversibile crea una mappa locale cifrata con password. Questa mappa è l'unico posto in cui OMISSIS conserva la corrispondenza tra segnaposto e valori reali, e viene salvata solo quando lo chiedi esplicitamente.

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

Anche la web app parte in **Massima protezione** e mostra una breve checklist finale per ricordare il controllo manuale prima della condivisione.

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
.\scripts\build_windows_app.ps1
```

## Stato del Progetto

Questa è una release open source iniziale. Contributi utili:

- ridurre falsi positivi e falsi negativi italiani;
- migliorare la preservazione della formattazione;
- migliorare OCR locale per PDF scansionati e immagini;
- raffinare la modalità reversibile e la ricostruzione dei testi generati dall'IA;
- aggiungere nuovi riconoscitori con test accurati;
- migliorare packaging Windows, firma delle app e automazione delle release.

## Licenza

MIT License. Vedi [LICENSE](LICENSE).
