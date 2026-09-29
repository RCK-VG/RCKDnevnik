@echo off
setlocal
rem RCK Nadzor - uklanjanje s racunala. Pokreni s administratorskog racuna
rem (desni klik > Pokreni kao administrator). Uklanja zadatke, datoteke i
rem ogranicenja ucenickih racuna (Task Manager, mreza, Postavke).

net session >nul 2>&1
if errorlevel 1 (
    echo Ovu datoteku treba pokrenuti kao administrator.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalacija.ps1" -Ukloni
if errorlevel 1 (
    echo.
    echo GRESKA pri uklanjanju - pogledaj poruku iznad.
)
echo.
pause
