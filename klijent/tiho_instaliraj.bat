@echo off
rem ============================================================
rem  RCK Nadzor - TIHA instalacija za masovno pokretanje
rem  (npr. preko Veyona, "Pokreni program").
rem
rem  - sam trazi administratorske ovlasti (UAC),
rem  - ne postavlja pitanja: -Da prihvaca ucenicke racune koje
rem    sam pronadje na TOM racunalu (svi omoguceni ne-admin racuni),
rem  - nema "pause" na kraju.
rem
rem  Mapa "klijent" (s config.json i rck-ca.crt) mora biti dostupna,
rem  npr. na dijeljenoj mapi \\admin-pc\klijent, pa odatle pokreni ovu
rem  datoteku. Za prvu instalaciju; nije potrebno za kasnije izmjene
rem  (one se sire same auto-updateom).
rem ============================================================

net session >nul 2>&1
if errorlevel 1 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalacija.ps1" -Da
