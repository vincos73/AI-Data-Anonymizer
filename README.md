# AI Data Anonymizer

**AI Data Anonymizer** aiuta a preparare una versione più sicura dei documenti prima di incollarli in ChatGPT, Claude, Gemini o altri strumenti di intelligenza artificiale.

Il progetto è pensato soprattutto per utenti italiani e per un uso semplice: installi l'app desktop, carichi un documento, anonimizza tutto sul tuo computer. Il software non invia file o testo ad API esterne.

La web app esiste solo come opzione avanzata per sviluppatori, demo locali o installazioni self-hosted su infrastruttura controllata.

[English version](README.en.md)

## Scarica App Desktop

Ultima versione: **v0.2.0**

| Sistema | Download |
| --- | --- |
| Mac Apple Silicon, M1/M2/M3/M4 o successivi | [Scarica DMG per macOS](https://github.com/vincos73/AI-Data-Anonymizer/releases/download/v0.2.0/AI-Data-Anonymizer-macOS-Apple-Silicon.dmg) |
| Windows | [Scarica ZIP per Windows](https://github.com/vincos73/AI-Data-Anonymizer/releases/download/v0.2.0/AI-Data-Anonymizer-Windows.zip) |

Tutti i file sono disponibili nella pagina [Releases](https://github.com/vincos73/AI-Data-Anonymizer/releases).

## Installazione Facile

### Mac

1. Scarica il file `.dmg`.
2. Aprilo.
3. Trascina **AI Data Anonymizer** nella cartella **Applicazioni**.
4. Apri l'app da **Applicazioni**.

Le build attuali non sono ancora firmate/notarizzate. Se macOS mostra un avviso sullo sviluppatore non identificato:

1. fai click destro su **AI Data Anonymizer**;
2. scegli **Apri**;
3. conferma di nuovo **Apri**.

### Windows

1. Scarica il file `.zip`.
2. Estrai lo zip in una cartella.
3. Apri **AI Data Anonymizer.exe**.

Su Windows i vecchi file `.doc` non sono supportati direttamente: convertili prima in `.docx`.

## Come Si Usa

1. Apri l'app.
2. Carica un documento o incolla un testo.
3. Clicca **Analizza** per vedere quali dati sono stati riconosciuti.
4. Scegli la modalità di protezione.
5. Clicca **Anonimizza**.
6. Leggi il report finale con modalità usata, numero di dati riconosciuti e avvisi di controllo.
7. Controlla il risultato prima di condividerlo.
8. Salva o copia il testo anonimizzato.

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
Mario Rossi -> <PERSON>
10/01/1980 -> <DATE>
mario@example.com -> <EMAIL_ADDRESS>
```

Usa questa modalità quando devi condividere testo con chatbot o servizi esterni e vuoi ridurre al minimo i dettagli identificativi.

## Dati Riconosciuti

AI Data Anonymizer riconosce, con regole conservative:

- indirizzi email;
- numeri di telefono italiani, inclusi formati con spazi, punti, trattini o slash;
- IBAN italiani, anche scritti con spazi;
- codice fiscale;
- partita IVA;
- indirizzi italiani con segnali forti come via, viale, piazza, corso;
- nomi di persone con contesto forte, per esempio nascita, residenza o intestatario di pagamento;
- aziende con forme giuridiche come `S.r.l.`, `S.p.A.`, `S.n.c.`, `S.a.s.`, cooperative e simili;
- enti territoriali come `Provincia di Potenza`, `Comune di Roma`, `Regione Basilicata`;
- date comuni in modalità Massima protezione.

## Formati Supportati

| Formato | Supporto |
| --- | --- |
| `.txt`, `.md`, `.csv` | Legge e salva file di testo anonimizzati |
| `.docx` | Legge e salva documenti Word preservando il più possibile la formattazione |
| `.pdf` | Estrae il testo e crea un nuovo PDF anonimizzato; il layout originale può non essere preservato |
| `.doc` | Supportato solo su macOS, convertito in `.docx` prima dell'anonimizzazione |

I PDF scansionati o composti solo da immagini devono essere convertiti con OCR prima dell'uso. L'app li blocca quando non riesce a estrarre testo selezionabile, così l'utente non scambia un PDF non letto per un documento già sicuro.

## Privacy

La versione desktop lavora localmente sul computer. Non invia testo o file a OpenAI, Google, Anthropic, servizi OCR, analytics o altre API esterne.

La web app non è necessaria per l'uso normale. Se la avvii in locale su `127.0.0.1`, resta sul tuo computer come un'interfaccia browser. Se invece la pubblichi su un server, il testo inviato alla web app arriva a quel server: per documenti sensibili usala solo su infrastruttura sotto il tuo controllo e con HTTPS.

Per i file `.docx`, l'app anonimizza il testo visibile e pulisce contenuti nascosti comuni come metadati, commenti, caselle di testo, note a piè di pagina, note di chiusura e alcune revisioni.

## Limiti Importanti

AI Data Anonymizer è uno strumento di riduzione del rischio, non una garanzia legale di anonimizzazione perfetta.

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

La suite copre falsi positivi italiani, riconoscimento di persone e organizzazioni, enti territoriali, identificativi strutturati, modalità Standard e Massima protezione, anonimizzazione documenti, preservazione della formattazione `.docx`, pulizia di contenuti nascosti `.docx` e rifiuto dei PDF scansionati/non leggibili.

## Build Desktop

Build macOS:

```bash
./scripts/build_macos_app.sh
```

Build Windows da PowerShell:

```powershell
.\scripts\build_windows_app.ps1
```

## Stato del Progetto

Questa è una release open source iniziale. Contributi utili:

- ridurre falsi positivi e falsi negativi italiani;
- migliorare la preservazione della formattazione;
- aggiungere nuovi riconoscitori con test accurati;
- migliorare packaging, firma delle app e automazione delle release.

## Licenza

MIT License. Vedi [LICENSE](LICENSE).
