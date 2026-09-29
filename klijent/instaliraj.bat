@echo off
setlocal
rem ====================================================================
rem  RCK Nadzor - instalacija na ucenicko racunalo.
rem  Pokreni s ADMINISTRATORSKOG racuna: desni klik > Pokreni kao administrator.
rem  U istoj mapi moraju biti: instalacija.ps1, servis.ps1, prozor.ps1,
rem  pokreni_prozor.vbs, preskoci_procese.txt, config.json i rck-ca.crt.
rem  Moze se pokrenuti ponovno (npr. nakon izmjene config.json) - to je nadogradnja.
rem ====================================================================

net session >nul 2>&1
if errorlevel 1 (
    echo Ovu datoteku treba pokrenuti kao administrator.
    echo Desni klik na instaliraj.bat ^> "Pokreni kao administrator".
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalacija.ps1" %*
if errorlevel 1 (
    echo.
    echo GRESKA pri instalaciji - pogledaj poruku iznad.
    pause
    exit /b 1
)
echo.
pause
