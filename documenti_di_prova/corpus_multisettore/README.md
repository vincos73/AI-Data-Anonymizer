# Corpus sintetico multi-settore OMISSIS

Il corpus contiene **35 documenti interamente fittizi**. Non contiene dati personali reali e può essere usato in demo, test automatici e sessioni con beta tester.

## Come usarlo

1. Aprire un documento con OMISSIS.
2. Eseguire prima il test in modalità **Massima protezione**.
3. Confrontare il risultato con `manifest.json`: `expected_remove` deve sparire, `must_remain` deve restare leggibile.
4. Per i PDF, salvare la copia protetta e verificare che i valori originali non siano selezionabili o estraibili.
5. Eseguire `PYTHONPATH=src python3 scripts/evaluate_multisector_corpus.py` per produrre una baseline ripetibile.

## Copertura dei formati

- CSV: 6
- DOCX: 11
- PDF: 9
- PDF scansionato: 2
- TXT: 7

## Copertura dei settori

- Amministrazione e finanza: 1
- Assicurazioni: 1
- Assistenza clienti: 1
- Banca: 1
- Commercio: 1
- Commercio elettronico: 1
- Condominio: 1
- Energia: 1
- Eventi: 1
- Fornitori: 1
- Immobiliare: 1
- Lavoro e HR: 4
- Legale: 1
- Logistica: 1
- Marketing e CRM: 1
- Media: 1
- Professionisti: 1
- Psicologia: 1
- Pubblica amministrazione: 1
- Sanità: 3
- Scuola: 1
- Servizi sociali: 1
- Sport: 1
- Tecnologia: 1
- Telecomunicazioni: 1
- Terzo settore: 1
- Trasporti: 1
- Turismo: 1
- Università: 1
- Viaggi: 1

## Regole di sicurezza

- Non sostituire i dati fittizi con dati reali nel repository.
- I tester esterni possono usare propri documenti localmente, ma non devono inviare gli originali al team.
- Nei report descrivere il tipo di dato sfuggito; allegare soltanto estratti già anonimizzati o ricreati con valori inventati.
- Un risultato senza segnalazioni non equivale a garanzia assoluta: resta obbligatorio il controllo umano.
