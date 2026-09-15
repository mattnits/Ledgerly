#!/usr/bin/env bash

set -e

echo "Setting up finance app..."

if ! command -v python3 &> /dev/null
then
    echo "Python 3 is not installed."
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

echo "Activating virtual environment..."

source .venv/bin/activate

echo "Upgrading pip..."

python -m pip install --upgrade pip

echo "Installing requirements..."

pip install -r requirements.txt

echo ""
echo "Setup complete."
echo "To activate the environment later, run:"
echo ""
echo "source .venv/bin/activate"