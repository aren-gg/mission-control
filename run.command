#!/bin/bash
set -e
cd -- "$(dirname -- "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.11 or newer is required. Install it from https://www.python.org/downloads/"
  read -r -p "Press Enter to close."
  exit 1
fi
if ! python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
  echo "Please install Python 3.11 or newer."
  read -r -p "Press Enter to close."
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -m pip install -r requirements.txt; then
  echo "Dependency setup failed. Check the connection and the error above."
  read -r -p "Press Enter to close."
  exit 1
fi
.venv/bin/python main.py "$@"
