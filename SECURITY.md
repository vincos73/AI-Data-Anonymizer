# Sicurezza e Privacy

AI Data Anonymizer è progettato prima di tutto per funzionare in locale sul computer dell'utente tramite app desktop. Questa è la modalità consigliata per la maggior parte delle persone.

La versione desktop non chiama API esterne di intelligenza artificiale, OCR, analytics o trattamento documentale. La web app è un'opzione avanzata per uso locale da browser o self-hosting; in quel caso elabora il testo sul computer o server in cui viene installata.

La web app applica limiti predefiniti di **100.000 caratteri** per il testo estratto e **10 MB** per file caricato. I file caricati vengono elaborati in una cartella temporanea rimossa al termine della richiesta.

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

## Web App Locale, Pubblica o Self-Hosted

La web app non è necessaria per usare il prodotto come anonimizzatore locale: l'app desktop resta la scelta consigliata.

Se esponi la web app su Internet o in una rete condivisa, il testo incollato dagli utenti arriva al server che la ospita. Questo può creare responsabilità legali, tecniche e organizzative.

Per deploy non dimostrativi:

- usa HTTPS;
- richiedi autenticazione;
- disabilita i log dei body HTTP in proxy, server applicativi e strumenti di osservabilità;
- non aggiungere analytics, session replay o script terzi nelle pagine che trattano documenti;
- mantieni limiti di upload conservativi;
- elimina immediatamente eventuali file temporanei se personalizzi gli endpoint di upload;
- pubblica termini privacy chiari per gli utenti.

## Segnalare Problemi

Per bug non sensibili puoi aprire una issue pubblica su GitHub.

Per segnalazioni che includono dati personali, documenti riservati o dettagli di sicurezza, usa un canale privato configurato nel repository prima di condividere esempi reali.
