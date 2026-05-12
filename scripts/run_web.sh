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
python -m pip install -e ".[web]"

ai-data-anonymizer-web --host 127.0.0.1 --port 8080
