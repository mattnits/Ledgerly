#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3.11 or newer is required for source setup."
    echo "Download the Linux release ZIP to run without Python."
    exit 1
fi

if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
    echo "Python 3.11 or newer is required for source setup."
    exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

echo "Installing runtime packages..."
.venv/bin/python -m pip install -r requirements.txt
echo "Setup complete. Run: .venv/bin/python -m app"
