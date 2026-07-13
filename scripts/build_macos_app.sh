#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 14) else 1)
PY
    then
      PYTHON_BIN="$candidate"
      break
    fi
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  if [ -x "$HOME/.local/bin/uv" ]; then
    "$HOME/.local/bin/uv" python install 3.12
    PYTHON_BIN="$("$HOME/.local/bin/uv" python find 3.12)"
  elif command -v uv >/dev/null 2>&1; then
    uv python install 3.12
    PYTHON_BIN="$(uv python find 3.12)"
  else
    cat <<'MSG'
Serve Python 3.10, 3.11, 3.12 o 3.13 per la build (PySide6 e PyInstaller non supportano ancora versioni più recenti come 3.14), ma non è stato trovato nessun interprete compatibile e uv non è installato.

Per risolvere:

  1. Installa uv (non tocca il Python di sistema):
     curl -LsSf https://astral.sh/uv/install.sh | sh

  2. Riapri il terminale (o esegui: source "$HOME/.local/bin/env")
     in modo che il comando "uv" sia disponibile nel PATH.

  3. Rilancia questo script:
     ./scripts/build_macos_app.sh

     Lo script userà automaticamente uv per installare Python 3.12 in locale
     e creare l'ambiente virtuale della build, senza modificare o sostituire
     il Python già presente sul sistema.
MSG
    exit 1
  fi
fi

if [ ! -d ".venv" ]; then
  "$PYTHON_BIN" -m venv .venv
elif ! .venv/bin/python - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 14) else 1)
PY
then
  echo "Ricreo .venv per usare una versione Python supportata."
  rm -rf .venv
  "$PYTHON_BIN" -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[build]"
APP_VERSION="$(python - <<'PY'
from privacy_guardian import __version__
print(__version__)
PY
)"
SIGN_IDENTITY="${APPLE_DEVELOPER_ID_APPLICATION:-}"
APPLE_ID_VALUE="${APPLE_ID:-}"
APPLE_TEAM_ID_VALUE="${APPLE_TEAM_ID:-}"
APPLE_APP_PASSWORD_VALUE="${APPLE_APP_SPECIFIC_PASSWORD:-}"
NOTARIZE_DMG=false

if [ -n "$SIGN_IDENTITY" ] && [ -n "$APPLE_ID_VALUE" ] && [ -n "$APPLE_TEAM_ID_VALUE" ] && [ -n "$APPLE_APP_PASSWORD_VALUE" ]; then
  NOTARIZE_DMG=true
fi

rm -rf build dist
python scripts/create_app_icon.py
iconutil -c icns assets/app_icon.iconset -o assets/app_icon.icns

pyinstaller \
  --name "OMISSIS" \
  --windowed \
  --clean \
  --icon assets/app_icon.icns \
  --osx-bundle-identifier "com.vincos.aidataanonymizer" \
  --collect-data privacy_guardian \
  --collect-all docx \
  --collect-all pypdf \
  --collect-all pypdfium2 \
  --collect-all reportlab \
  --collect-all cryptography \
  src/privacy_guardian/app.py

/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $APP_VERSION" "dist/OMISSIS.app/Contents/Info.plist"
if ! /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $APP_VERSION" "dist/OMISSIS.app/Contents/Info.plist" 2>/dev/null; then
  /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $APP_VERSION" "dist/OMISSIS.app/Contents/Info.plist"
fi

# Attributi estesi residui (resource fork, quarantine) sui file appena scritti da
# PyInstaller possono far fallire "codesign --deep" in modo intermittente, lasciando
# una firma incoerente con l'Info.plist appena modificato sopra: li rimuoviamo prima
# di firmare, per entrambi i rami.
xattr -cr "dist/OMISSIS.app"

if [ -n "$SIGN_IDENTITY" ]; then
  echo "Firma Developer ID dell'app macOS..."
  codesign --force --deep --options runtime --timestamp --sign "$SIGN_IDENTITY" "dist/OMISSIS.app"
else
  echo "APPLE_DEVELOPER_ID_APPLICATION non impostato: creo una firma ad-hoc non notarizzabile."
  codesign --force --deep --sign - "dist/OMISSIS.app"
fi
codesign --verify --deep --strict --verbose=2 "dist/OMISSIS.app"

if command -v dmgbuild >/dev/null 2>&1; then
  dmgbuild -s scripts/dmg_settings.py "OMISSIS" "dist/OMISSIS.dmg"

  if [ -n "$SIGN_IDENTITY" ]; then
    echo "Firma del DMG macOS..."
    codesign --force --timestamp --sign "$SIGN_IDENTITY" "dist/OMISSIS.dmg"
  fi

  if [ "$NOTARIZE_DMG" = true ]; then
    echo "Invio del DMG ad Apple per la notarizzazione..."
    xcrun notarytool submit "dist/OMISSIS.dmg" \
      --apple-id "$APPLE_ID_VALUE" \
      --password "$APPLE_APP_PASSWORD_VALUE" \
      --team-id "$APPLE_TEAM_ID_VALUE" \
      --wait
    xcrun stapler staple "dist/OMISSIS.dmg"
    spctl -a -t open --context context:primary-signature -v "dist/OMISSIS.dmg"
  else
    echo "Notarizzazione saltata: servono APPLE_ID, APPLE_TEAM_ID, APPLE_APP_SPECIFIC_PASSWORD e APPLE_DEVELOPER_ID_APPLICATION."
  fi

  cp "dist/OMISSIS.dmg" "dist/OMISSIS-macOS-Apple-Silicon.dmg"
fi

cat > "dist/LEGGIMI - OMISSIS.txt" <<'TXT'
OMISSIS

Come installare su Mac:

1. Apri "OMISSIS.dmg".
2. Trascina "OMISSIS" nella cartella Applicazioni.
3. Apri OMISSIS da Applicazioni.

Come usarla:

1. Clicca "Carica documento" per scegliere un file .txt, .md, .csv, .doc, .docx o .pdf.
2. Clicca "Analizza dati" o "Anonimizza".
3. Clicca "Salva risultato" per creare la versione anonimizzata del documento.

Nota sui PDF:
I PDF con testo selezionabile vengono esportati come PDF rasterizzato con oscuramenti permanenti. Il testo originale non resta selezionabile nel file finale. I PDF scansionati o composti solo da immagini richiedono prima OCR.

Nota sulla modalita reversibile:
Se usi "Reversibile con mappa locale", salva anche la mappa da Strumenti > Salva mappa reversibile. La mappa e cifrata con la password scelta da te e serve per ricostruire localmente le risposte generate dall'IA.

Se macOS dice che l'app non puo essere aperta perche proviene da uno sviluppatore non identificato, stai usando una build non notarizzata:

1. Fai click destro su "OMISSIS".
2. Scegli "Apri".
3. Conferma di nuovo "Apri".

Nota:
Questa versione e stata creata per Mac Apple Silicon, cioe Mac con chip M1, M2, M3, M4 o successivi.
TXT

echo "Build completata in: $PROJECT_DIR/dist"
