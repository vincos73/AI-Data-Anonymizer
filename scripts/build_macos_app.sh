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
    echo "Serve Python 3.10, 3.11, 3.12 o 3.13. Installa uv da https://docs.astral.sh/uv/ oppure Python da python.org."
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

rm -rf build dist
python scripts/create_app_icon.py
iconutil -c icns assets/app_icon.iconset -o assets/app_icon.icns

pyinstaller \
  --name "AI Data Anonymizer" \
  --windowed \
  --clean \
  --icon assets/app_icon.icns \
  --osx-bundle-identifier "com.vincos.aidataanonymizer" \
  --collect-all docx \
  --collect-all pypdf \
  --collect-all reportlab \
  src/privacy_guardian/app.py

/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $APP_VERSION" "dist/AI Data Anonymizer.app/Contents/Info.plist"
if ! /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $APP_VERSION" "dist/AI Data Anonymizer.app/Contents/Info.plist" 2>/dev/null; then
  /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $APP_VERSION" "dist/AI Data Anonymizer.app/Contents/Info.plist"
fi

if command -v dmgbuild >/dev/null 2>&1; then
  dmgbuild -s scripts/dmg_settings.py "AI Data Anonymizer" "dist/AI Data Anonymizer.dmg"
fi

cat > "dist/LEGGIMI - AI Data Anonymizer.txt" <<'TXT'
AI Data Anonymizer

Come installare su Mac:

1. Apri "AI Data Anonymizer.dmg".
2. Trascina "AI Data Anonymizer" nella cartella Applicazioni.
3. Apri AI Data Anonymizer da Applicazioni.

Come usarla:

1. Clicca "Carica documento" per scegliere un file .txt, .md, .csv, .doc, .docx o .pdf.
2. Clicca "Anonimizza".
3. Clicca "Salva risultato" per creare la versione anonimizzata del documento.

Se macOS dice che l'app non puo essere aperta perche proviene da uno sviluppatore non identificato:

1. Fai click destro su "AI Data Anonymizer".
2. Scegli "Apri".
3. Conferma di nuovo "Apri".

Nota:
Questa versione e stata creata per Mac Apple Silicon, cioe Mac con chip M1, M2, M3, M4 o successivi.
TXT

echo "Build completata in: $PROJECT_DIR/dist"
