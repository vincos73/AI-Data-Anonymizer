# Piano della closed beta di OMISSIS

## Obiettivo

Verificare se persone esterne riescono a installare OMISSIS, proteggere documenti di ambiti diversi, controllare il risultato ed esportarlo senza assistenza. La beta deve far emergere dati non rilevati, oscuramenti eccessivi, problemi di formato e passaggi poco comprensibili.

## Durata e gruppo

- Durata operativa: 14 giorni.
- Numero consigliato: 8-12 tester.
- Impegno richiesto: 45-60 minuti complessivi per persona.
- Sistemi da coprire: almeno 4 installazioni Windows 11 e 4 installazioni macOS Apple Silicon; se disponibile, aggiungere un Mac Intel come verifica separata.
- Profili: amministrazione/contabilità, HR, sanità o servizi alla persona, scuola/università, consulenza o professioni, piccola impresa, privacy/compliance e almeno due persone non tecniche.

## Condizioni per iniziare

La beta esterna parte quando:

1. la suite automatica del progetto è verde;
2. il corpus multi-settore è stato eseguito in modalità Massima protezione;
3. non restano perdite già note classificate come bloccanti;
4. le build distribuite hanno versione e hash identificabili;
5. ogni build è stata installata su un computer pulito;
6. su macOS è documentato chiaramente se la build è notarizzata o richiede l'apertura manuale da Sicurezza e privacy.

La baseline v0.6.22 del corpus non rileva perdite, classificazioni non conformi o falsi positivi sui controlli dichiarati. Il corpus è quindi pronto per la verifica umana; prima del reclutamento restano da produrre e installare le build candidate identificate da versione e hash.

## Assegnazione dei casi

Ogni tester riceve tre documenti sintetici:

- uno vicino al proprio ambito di lavoro;
- uno di un ambito diverso;
- un PDF, preferibilmente scansionato per almeno due tester.

Tutti provano Massima protezione. Almeno metà del gruppo confronta lo stesso documento anche in modalità Standard. Quattro tester provano il flusso Reversibile con un file TXT o DOCX.

## Sessione richiesta al tester

1. Installare e aprire OMISSIS annotando eventuali avvisi del sistema operativo.
2. Caricare i tre documenti sintetici assegnati.
3. Controllare ciò che OMISSIS ha evidenziato prima di esportare.
4. Salvare la copia protetta e riaprirla con l'applicazione abituale.
5. Per i PDF, provare a selezionare e cercare uno dei valori originali.
6. Provare, facoltativamente, uno o due documenti propri senza inviarli al team.
7. Compilare una scheda per ogni problema distinto.

## Regole per i documenti personali

- I file originali restano sul computer del tester.
- Non devono essere caricati in moduli, email, chat o cartelle condivise.
- Nel feedback si indica soltanto il tipo di documento e la categoria del dato sfuggito.
- Un esempio può essere allegato solo dopo aver sostituito ogni dato reale con valori inventati.
- Le mappe reversibili e le relative password non devono essere condivise.

## Classificazione delle segnalazioni

- **B0 - Bloccante privacy:** un valore sensibile resta leggibile o recuperabile nell'output; la mappa reversibile viene persa, esposta o associata al documento sbagliato.
- **B1 - Bloccante d'uso:** crash, documento corrotto, impossibilità di installare, aprire o salvare.
- **M2 - Malfunzionamento:** riconoscimento errato importante, formattazione compromessa o flusso poco chiaro che richiede assistenza.
- **M3 - Miglioria:** testo, etichetta, dettaglio visivo o suggerimento che non impedisce il completamento.

## Criteri di uscita

La beta può chiudersi con una release candidate quando:

- non ci sono segnalazioni B0 o B1 aperte;
- almeno l'80% dei tester completa installazione, anonimizzazione, controllo ed esportazione senza assistenza diretta;
- almeno il 98% dei valori dichiarati in `expected_remove` viene rimosso nel corpus;
- almeno il 98% dei controlli `must_remain` resta leggibile;
- tutti i PDF protetti superano il controllo di selezione e ricerca del testo originale;
- i problemi M2 sono risolti oppure accettati con una motivazione documentata.

## Calendario suggerito

- Giorno 0: build candidata, controllo su macchine pulite e assegnazione dei casi.
- Giorni 1-7: prima sessione dei tester e raccolta delle segnalazioni.
- Giorno 8: triage, correzione dei bloccanti e nuova build se necessaria.
- Giorni 9-12: verifica mirata delle correzioni.
- Giorni 13-14: riepilogo, decisione sulla release candidate e archivio dei risultati.

## Dati da conservare

Conservare soltanto ID del tester, sistema operativo, versione OMISSIS, ID del caso sintetico, esito, gravità e descrizione. Non archiviare documenti originali, testo anonimizzato proveniente da casi reali, mappe reversibili, password o percorsi locali completi.
