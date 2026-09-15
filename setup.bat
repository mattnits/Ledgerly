@echo off

echo Setting up finance app...

if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

echo Activating virtual environment...

call .venv\Scripts\activate

echo Upgrading pip...

python -m pip install --upgrade pip

echo Installing requirements...

pip install -r requirements.txt

echo.
echo Setup complete.
echo.
echo To activate the environment later, run:
echo.
echo .venv\Scripts\activate