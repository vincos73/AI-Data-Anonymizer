# Baseline corpus multi-settore - OMISSIS v0.6.21

- Modalità: Massima protezione
- NER locale attivo: sì
- Casi analizzati: 35
- Valori sensibili rilevati e rimossi: 160
- Valori presenti ma rimasti nell'output: 6
- Tipo o intervallo non conforme: 9
- Valori non estratti dal documento/OCR: 0
- Controlli innocui preservati: 68
- Possibili falsi positivi sui controlli: 1
- Tasso di rimozione verificabile: 96.6%
- Tasso di preservazione dei controlli: 98.6%

## Anomalie da esaminare

- **SAN-01** (`SAN-01_referto_laboratorio.docx`): leaked: ADDRESS = Via delle Magnolie 17
- **SAN-02** (`SAN-02_lettera_dimissione.pdf`): wrong_type_or_span: LOCATION = Bologna
- **SAN-04** (`SAN-04_nota_colloquio_scansione.pdf`): leaked: ADDRESS = Via del Glicine 9
- **LAV-02** (`LAV-02_distinta_pagamenti.csv`): leaked: CODICE_FISCALE = RSSMRC88A01H501T
- **LAV-04** (`LAV-04_idoneita_mansione.docx`): false_positive: controllo = DIP-00427
- **IST-01** (`IST-01_comunicazione_famiglia.pdf`): wrong_type_or_span: LOCATION = Bari
- **FIN-01** (`FIN-01_fattura.pdf`): wrong_type_or_span: ORGANIZATION = Aurora Digitale S.r.l.
- **IMM-02** (`IMM-02_scheda_catastale.docx`): leaked: ADDRESS = Via dei Pini 6; wrong_type_or_span: CATASTO = 7
- **SOC-01** (`SOC-01_relazione_sociale.pdf`): wrong_type_or_span: LOCATION = Salerno
- **LOG-01** (`LOG-01_documento_consegna.pdf`): leaked: VEHICLE_PLATE = CD456EF
- **TEC-01** (`TEC-01_incidente_sicurezza.docx`): wrong_type_or_span: ORGANIZATION = Rete Sicura S.p.A.
- **LEG-01** (`LEG-01_promemoria_pratica.docx`): wrong_type_or_span: PROTOCOL_CASE_NUMBER = RG 4567/2026
- **FOR-01** (`FOR-01_onboarding_fornitore.docx`): wrong_type_or_span: ORGANIZATION = Officina del Sud S.n.c.; leaked: ADDRESS = Via delle Industrie 5
- **MED-01** (`MED-01_liberatoria_intervista.pdf`): wrong_type_or_span: LOCATION = Matera

## Lettura corretta dei risultati

`not_extracted` indica un problema di estrazione o OCR, non necessariamente del riconoscitore. `wrong_type_or_span` richiede un controllo manuale: il valore potrebbe essere stato coperto da un finding più ampio. La baseline non sostituisce la verifica visiva dei documenti esportati.
