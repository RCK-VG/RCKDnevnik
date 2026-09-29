@echo off
setlocal
rem RCK Nadzor - uklanjanje s racunala. Pokreni KAO ADMINISTRATOR.

net session >nul 2>&1
if errorlevel 1 (
    echo Ovu datoteku treba pokrenuti kao administrator.
    pause
    exit /b 1
)

echo Uklanjam zadatak "RCK Nadzor" ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0zadatak.ps1" -Ukloni

echo Brisem %ProgramData%\RCKNadzor ...
if exist "%ProgramData%\RCKNadzor" rmdir /s /q "%ProgramData%\RCKNadzor"

echo.
echo Gotovo. Skripta koja vec radi zaustavit ce se kad se korisnik odjavi.
echo Uvezeni certifikat ostaje u pouzdanima; ukloni ga rucno ako treba (certlm.msc).
pause
