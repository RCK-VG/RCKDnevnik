@echo off
setlocal
rem ====================================================================
rem  RCK Nadzor - instalacija na ucenicko racunalo.
rem  Pokreni KAO ADMINISTRATOR (desni klik > Pokreni kao administrator).
rem  U istoj mapi moraju biti: nadzor.ps1, pokreni.vbs, zadatak.ps1,
rem  preskoci_procese.txt, config.json i (za HTTPS) rck-ca.crt.
rem ====================================================================

net session >nul 2>&1
if errorlevel 1 (
    echo Ovu datoteku treba pokrenuti kao administrator.
    echo Desni klik na instaliraj.bat ^> "Pokreni kao administrator".
    pause
    exit /b 1
)

set "SRC=%~dp0"
set "DEST=%ProgramData%\RCKNadzor"

for %%F in (nadzor.ps1 pokreni.vbs zadatak.ps1 preskoci_procese.txt config.json) do (
    if not exist "%SRC%%%F" (
        echo Nedostaje datoteka %%F u mapi %SRC%
        echo config.json se radi na serveru, vidi klijent\README.md.
        pause
        exit /b 1
    )
)

echo Kopiram datoteke u %DEST% ...
if not exist "%DEST%" mkdir "%DEST%"
for %%F in (nadzor.ps1 pokreni.vbs preskoci_procese.txt config.json) do (
    copy /y "%SRC%%%F" "%DEST%\" >nul || goto :greska
)

echo Postavljam dozvole (ucenici mogu samo citati) ...
rem SYSTEM i administratori: puna kontrola; korisnici: citanje i pokretanje.
icacls "%DEST%" /inheritance:r /grant:r *S-1-5-18:(OI)(CI)F *S-1-5-32-544:(OI)(CI)F *S-1-5-32-545:(OI)(CI)RX >nul || goto :greska
icacls "%DEST%\*" /reset >nul || goto :greska

if exist "%SRC%rck-ca.crt" (
    echo Uvozim HTTPS certifikat servera u pouzdane ...
    certutil -addstore -f Root "%SRC%rck-ca.crt" >nul || goto :greska
) else (
    echo Nema rck-ca.crt - preskacem certifikat ^(potreban samo za https adresu^).
)

echo Registriram pokretanje pri svakoj prijavi ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%SRC%zadatak.ps1" || goto :greska

echo.
echo Gotovo. Nadzor ce se pokrenuti pri sljedecoj prijavi korisnika na ovo racunalo.
pause
exit /b 0

:greska
echo.
echo GRESKA pri instalaciji - pogledaj poruku iznad.
pause
exit /b 1
