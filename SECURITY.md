# Sicurezza e Privacy

AI Data Anonymizer è progettato per funzionare in locale sul computer dell'utente o su infrastruttura controllata dall'utente.

La versione desktop non chiama API esterne di intelligenza artificiale, OCR, analytics o trattamento documentale. La web app self-hosted elabora il testo sul server in cui viene installata.

## Cosa Significa Anonimizzazione

AI Data Anonymizer riduce il rischio prima di condividere documenti con chatbot, cloud, collaboratori o sistemi esterni. Non è un prodotto di conformità legale e non garantisce anonimizzazione perfetta.

- In modalità Standard conserva le iniziali per alcune entità e mantiene visibili le date.
- In modalità Massima protezione sostituisce le entità riconosciute con segnaposto completi e anonimizza anche formati data comuni.
- L'utente deve sempre rileggere il risultato prima di condividerlo.
- I PDF scansionati o composti solo da immagini vengono rifiutati quando non è possibile estrarre testo selezionabile. Prima va eseguito OCR.
- I file `.docx` vengono puliti sia nel testo visibile sia in contenuti nascosti comuni come metadati, commenti, caselle di testo, note e alcune revisioni.

## Uso Desktop

La versione desktop lavora in locale. I documenti non vengono inviati ad API esterne dal software.

Attenzione: se copi manualmente il risultato in un chatbot o lo carichi su un servizio cloud, quel servizio riceverà il testo che hai scelto di condividere. Controlla sempre il risultato prima di farlo.

## Web App Pubblica o Self-Hosted

Se esponi la web app su Internet, il testo incollato dagli utenti arriva al server che la ospita. Questo può creare responsabilità legali, tecniche e organizzative.

Per deploy non dimostrativi:

- usa HTTPS;
- richiedi autenticazione;
- disabilita i log dei body HTTP in proxy, server applicativi e strumenti di osservabilità;
- non aggiungere analytics, session replay o script terzi nelle pagine che trattano documenti;
- usa limiti di upload conservativi;
- tratta i documenti in memoria quando possibile;
- elimina immediatamente file temporanei se aggiungi endpoint di upload;
- pubblica termini privacy chiari per gli utenti.

## Segnalare Problemi

Per bug non sensibili puoi aprire una issue pubblica su GitHub.

Per segnalazioni che includono dati personali, documenti riservati o dettagli di sicurezza, usa un canale privato configurato nel repository prima di condividere esempi reali.
