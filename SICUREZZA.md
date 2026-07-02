# Sicurezza e privacy di OMISSIS

OMISSIS nasce per preparare documenti italiani prima di usarli con ChatGPT, Claude, Gemini o altri strumenti di IA, riducendo il rischio di condividere dati personali.

Questa pagina spiega cosa fa l'app, cosa non fa e quali limiti devi conoscere.

## Elaborazione locale

La versione desktop lavora sul tuo computer.

Non invia documenti, testo, dati rilevati o risultati anonimizzati a:

- OpenAI;
- Google;
- Anthropic;
- servizi OCR esterni;
- analytics;
- server del progetto;
- altre API esterne.

Il progetto non include telemetria, session replay o tracciamenti di utilizzo.

## Registro attività locale

OMISSIS mantiene un registro attività locale pensato per chi vuole documentare le operazioni fatte su un documento.

Il registro salva solo metadati:

- data e ora dell'operazione;
- tipo di operazione: analisi, anonimizzazione o salvataggio;
- modalità usata: Standard, Massima protezione o Reversibile;
- numero totale di dati riconosciuti;
- conteggi per categoria, per esempio persone, email, IBAN;
- estensione e dimensione del file, quando è stato caricato un documento;
- hash SHA-256 del file originale e del risultato, quando disponibili;
- versione dell'app.

Il registro non salva:

- testo originale;
- testo anonimizzato;
- valori trovati;
- anteprime dei dati rilevati;
- percorso completo dei file.

Su macOS il registro viene salvato in:

```text
~/Library/Application Support/OMISSIS/activity-log.jsonl
```

Su Windows viene salvato nella cartella dati applicazione dell'utente:

```text
%APPDATA%\OMISSIS\activity-log.jsonl
```

Il registro resta sul dispositivo. Dall'app desktop puoi consultarlo ed esportarlo in CSV.

## Mappe reversibili

La modalità Reversibile crea segnaposti numerati come:

```text
Mario Rossi -> <PERSONA_1>
mario@example.com -> <EMAIL_1>
```

Per ricostruire una risposta generata dall'IA, OMISSIS ha bisogno della corrispondenza tra segnaposto e valore reale. Questa corrispondenza viene salvata solo se scegli **Strumenti > Salva mappa reversibile**.

La mappa:

- resta sul tuo dispositivo;
- viene cifrata con una password scelta da te;
- non viene scritta nel registro attività;
- non viene inviata a server o API esterne;
- contiene dati reali e quindi va trattata come un file sensibile.

Se perdi la password o elimini la mappa, OMISSIS non può ricostruire automaticamente i valori reali.

## Web app

La web app non è necessaria per l'uso normale. Serve per demo locali, sviluppo o installazioni self-hosted.

Se la avvii su `127.0.0.1`, resta sul tuo computer come interfaccia browser locale.

Se la pubblichi su un server, i documenti inviati alla web app arrivano a quel server. In quel caso devi proteggerla come qualunque servizio che tratta documenti sensibili:

- HTTPS;
- autenticazione;
- niente log dei body HTTP nei proxy;
- niente analytics o script terzi sulle pagine che trattano documenti;
- limiti di upload conservativi;
- backup e retention coerenti con le tue policy.

## DOCX

Per i file `.docx`, OMISSIS anonimizza il testo visibile e prova a pulire contenuti nascosti comuni:

- metadati del documento;
- commenti;
- caselle di testo;
- intestazioni e piè di pagina;
- note a piè di pagina;
- note di chiusura;
- alcune revisioni e parti XML testuali.

La formattazione viene preservata quando possibile, ma devi sempre controllare il risultato prima di condividerlo.

## PDF

Per i PDF con testo selezionabile, OMISSIS:

1. estrae il testo;
2. rileva i dati personali;
3. calcola le coordinate dei dati nel PDF;
4. ricostruisce il PDF come immagini di pagina con oscuramenti permanenti.

Questo evita il problema tipico dei finti oscuramenti, cioè testo ancora recuperabile sotto un rettangolo nero.

Limite importante: il PDF finale non mantiene testo selezionabile o ricercabile, perché viene rasterizzato.

## PDF scansionati e OCR locale

I PDF scansionati o composti solo da immagini non contengono testo selezionabile. OMISSIS può leggerli con **Tesseract OCR locale** quando Tesseract è installato sul computer.

Questo OCR resta locale: non vengono chiamati servizi esterni.

Se Tesseract non è disponibile o non trova testo affidabile, OMISSIS blocca il PDF, così non puoi scambiare un file non letto per un documento già sicuro.

Puoi indicare un percorso Tesseract personalizzato con la variabile:

```text
OMISSIS_TESSERACT_PATH
```

Puoi indicare lingue OCR diverse con:

```text
OMISSIS_TESSERACT_LANG
```

Il valore predefinito è:

```text
ita+eng
```

## Modalità di protezione

### Standard

La modalità Standard mantiene il testo più leggibile e conserva iniziali per alcune categorie.

Esempio:

```text
Mario Rossi -> M. R.
```

Questa modalità non è consigliata quando devi incollare il testo in chatbot o servizi esterni.

### Massima protezione

La modalità Massima protezione usa segnaposto completi.

Esempio:

```text
Mario Rossi -> <PERSONA>
mario@example.com -> <EMAIL>
10/01/1980 -> <DATA>
```

È la modalità consigliata per preparare testi da condividere con strumenti di IA.

### Reversibile

La modalità Reversibile usa segnaposti numerati e include anche le date comuni.

Esempio:

```text
Mario Rossi -> <PERSONA_1>
10/01/1980 -> <DATA_1>
```

È utile quando vuoi far lavorare un assistente IA su un testo mascherato e poi ricostruire localmente la risposta. Per i PDF resta consigliata Massima protezione, perché l'output PDF viene redatto in modo permanente e non è ricostruibile.

## Limiti

OMISSIS riduce il rischio, ma non garantisce anonimizzazione perfetta.

- Il motore è basato su regole locali.
- Alcuni dati possono non essere riconosciuti.
- Alcuni testi possono contenere identificatori indiretti, per esempio eventi, ruoli, sedi, numeri pratica o combinazioni rare.
- Il contesto può rendere riconoscibile una persona anche dopo la sostituzione dei dati evidenti.
- Devi sempre rileggere il risultato prima di condividerlo.

## Cosa controllare prima di condividere

Prima di incollare un risultato in un chatbot o inviarlo a terzi:

1. usa Massima protezione o Reversibile, in base al flusso di lavoro;
2. controlla il report e i dati rilevati;
3. rileggi il testo anonimizzato;
4. verifica nomi, luoghi, date, importi, ruoli e riferimenti indiretti;
5. se usi Reversibile, salva la mappa cifrata e non condividerla;
6. per i PDF, apri il file finale e controlla visivamente gli oscuramenti.
