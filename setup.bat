@echo off
echo Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo FAILURE: Could not install dependencies.
    echo Please right-click this file and select "Run as Administrator".
    echo If that fails, your Antivirus (Avast/AVG) is blocking Python.
    pause
    exit /b
)
echo.
echo Success! Starting App...
python app.py
pause
