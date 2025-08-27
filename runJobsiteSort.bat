@echo off
REM ========= Fleet Operations – Geo-only Clustering (UI) =========
REM Paths -- adjust to your environment

REM 1) Python executable (Replace "YOURPATH" with your file path)
set "PY=C:\Users\YOURPATH\AppData\Local\Programs\Python\Python312\python.exe"

REM 2) Working directory (where Jobsite_List.xlsx and script live) (Replace "YOURPATH" with your file path)
set "WORKDIR=C:\Users\YOURPATH\Desktop\Jobsite Sort v.3"

REM 3) Script path
set "SCRIPT=%WORKDIR%\JobsiteSortv3.py"

REM -------- Environment variables --------
REM Your Google Maps Geocoding API key:
set "GOOGLE_API_KEY=PASTE_YOUR_KEY_HERE"

REM Optional: Shop address override (Replace "SHOP_ADDRESS" with your desired address)
REM set "SHOP_ADDRESS=SHOP_ADDRESS"

REM ===============================================================

cd /d "%WORKDIR%"
if not exist "%PY%" (
  echo Could not find Python at: %PY%
  echo Trying 'py -3' launcher...
  set "PY=py -3"
)

echo Installing dependencies from requirements.txt ...
"%PY%" -m pip install -r requirements.txt

echo Running script with interactive K picker (entry box). Press Cancel in the dialog to exit.
"%PY%" "%SCRIPT%"
echo.
echo Done. Press any key to close this window.
pause >nul
