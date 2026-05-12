# AI Data Anonymizer

AI Data Anonymizer e un'app desktop e web self-hosted per anonimizzare dati personali italiani con un motore locale ad alta precisione.

Il progetto e pensato per essere pubblicato su GitHub e usato in tre modi:

- app desktop macOS per lavorare su documenti locali;
- app desktop Windows per lavorare su documenti locali;
- web app self-hosted per ambienti controllati.

Non e necessario inviare documenti a servizi esterni.

## Cosa fa

- Incolla un testo oppure carica un documento.
- Anonimizza email, telefoni, IBAN, codice fiscale, partita IVA, indirizzi, persone con contesto forte, enti territoriali e società italiane.
- Non anonimizza le date.
- Per persone, imprese, indirizzi ed enti territoriali mantiene le iniziali invece di sostituire tutto con un placeholder.
- Permette di copiare il testo o salvare/scaricare una versione anonimizzata del documento.
- Funziona come app desktop installabile su Mac e Windows.
- Elabora il testo localmente sul computer: non invia il contenuto a servizi esterni.

Formati supportati:

- `.txt`, `.md`, `.csv`: salva un nuovo file di testo.
- `.docx`: salva un nuovo documento Word anonimizzato mantenendo la formattazione interna quando possibile.
- `.doc`: disponibile su macOS, viene convertito in `.docx`, anonimizzato e salvato come documento Word moderno. Su Windows usa prima `.docx`.
- `.pdf`: estrae il testo e salva un nuovo PDF anonimizzato. Il layout originale del PDF potrebbe non essere preservato.

## Sviluppo locale

Serve Python 3.10, 3.11, 3.12 o 3.13. Se il comando `python3 --version` mostra Python 3.9, installa una versione piu recente da python.org o con Homebrew.

```bash
git clone https://github.com/YOUR-USERNAME/ai-data-anonymizer.git
cd ai-data-anonymizer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[build]"
ai-data-anonymizer
```

Test:

```bash
python -m unittest discover -s tests -v
```

## Versione web privata

La versione web e pensata per essere self-hosted. Non usa analytics, non salva i testi, disattiva gli access log dell'app e aggiunge header `no-store` per evitare cache del browser/proxy. Il testo viene comunque inviato al server che ospita l'app: per dati sensibili, usala solo su un server controllato da te e con HTTPS.

Avvio locale:

```bash
cd ai-data-anonymizer
./scripts/run_web.sh
```

Poi apri:

```text
http://127.0.0.1:8080
```

Avvio con Docker:

```bash
cd ai-data-anonymizer
docker build -t ai-data-anonymizer .
docker run --rm -p 8080:8080 ai-data-anonymizer
```

Per pubblicarla online in modo ragionevole:

- mettila dietro HTTPS, ad esempio Caddy, Nginx o Cloudflare Tunnel;
- proteggila con password o accesso riservato;
- disattiva i log del reverse proxy per path `/api/analyze` e `/api/anonymize`;
- evita servizi di analytics, session replay o CDN che ispezionano il payload;
- non usare server di terzi se i testi contengono dati davvero sensibili.

## Creare una app macOS installabile

```bash
cd ai-data-anonymizer
./scripts/build_macos_app.sh
```

Alla fine troverai:

- `dist/AI Data Anonymizer.app`
- `dist/AI Data Anonymizer.dmg`, se `dmgbuild` riesce a creare il disco installabile

Sul Mac di destinazione: apri il `.dmg`, trascina l'app in Applicazioni e avviala. Se macOS blocca l'app perche non firmata, fai click destro sull'app, poi **Apri**.

## Creare una app Windows

Su Windows, da PowerShell:

```powershell
cd ai-data-anonymizer
.\scripts\build_windows_app.ps1
```

Alla fine troverai:

- `dist\AI Data Anonymizer\AI Data Anonymizer.exe`
- `dist\AI-Data-Anonymizer-Windows.zip`

La versione Windows base supporta `.txt`, `.md`, `.csv`, `.docx` e `.pdf`. I file `.doc` legacy non sono inclusi nella build Windows perche la conversione automatica usa `textutil`, disponibile solo su macOS.

## Release automatiche

Il workflow GitHub Actions `build-windows` crea lo zip Windows manualmente da **Actions** oppure automaticamente quando pubblichi un tag come `v0.1.0`. Se il tag corrisponde a una Release, lo zip viene allegato alla Release.

## Pubblicazione su GitHub

Prima di pubblicare:

- non caricare `.venv`, `build`, `dist`, `.dmg` o `.app`;
- scegli un nome repository, ad esempio `ai-data-anonymizer`;
- sostituisci `YOUR-USERNAME` nel comando clone qui sopra;
- aggiungi una descrizione chiara: "Italian privacy anonymizer for local desktop and self-hosted web usage".

Esempio:

```bash
git init
git add .
git commit -m "Initial open source release"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/ai-data-anonymizer.git
git push -u origin main
```

## Nota pratica

PySide e il supporto documenti rendono il pacchetto abbastanza pesante. Per distribuirla in modo professionale servono firma e notarizzazione Apple; per uso familiare il `.dmg` non firmato di solito basta.

Se il tuo Mac e quello di tua moglie hanno architetture diverse, ad esempio uno Intel e uno Apple Silicon, conviene fare la build direttamente sul Mac di destinazione o creare due pacchetti separati.
