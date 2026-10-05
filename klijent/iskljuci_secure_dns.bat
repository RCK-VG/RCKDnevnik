@echo off
rem ============================================================
rem  RCK Nadzor - iskljuci "Secure DNS" (DoH) u Chromeu i Edgeu,
rem  da se posjecene stranice vide u nadzoru.
rem
rem  Nije nuzno rucno pokretati: servis (SYSTEM) to radi sam na
rem  svakom racunalu. Ovo je za ODMAH / rucno (npr. preko Veyona).
rem  Pokreni kao administrator. Vrijedi nakon ponovnog pokretanja
rem  preglednika.
rem ============================================================

rem --- osiguraj administratorske ovlasti (HKLM trazi elevaciju) ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Trazim administratorske ovlasti...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

reg add "HKLM\SOFTWARE\Policies\Google\Chrome" /v DnsOverHttpsMode /t REG_SZ /d off /f
reg add "HKLM\SOFTWARE\Policies\Microsoft\Edge"  /v DnsOverHttpsMode /t REG_SZ /d off /f

echo.
echo Gotovo. Zatvori i ponovno otvori Chrome/Edge da promjena uhvati.
echo.
rem --- Ako zelis da uhvati ODMAH, makni "rem" ispred ove dvije linije.
rem     PAZI: zatvara otvorene preglednike SVIH korisnika na racunalu. ---
rem taskkill /F /IM chrome.exe >nul 2>&1
rem taskkill /F /IM msedge.exe >nul 2>&1

timeout /t 3 >nul
