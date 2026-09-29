<#
Registrira (ili uz -Ukloni briše) zadatak "RCK Nadzor" koji pri prijavi SVAKOG
korisnika pokrene nadzor.ps1 pod računom tog korisnika (mora, jer prikazuje
prozor i gleda korisnikovu radnu površinu i AppData). Poziva ga instaliraj.bat.
#>
param([switch]$Ukloni)

$ErrorActionPreference = 'Stop'
$taskName = 'RCK Nadzor'

if ($Ukloni) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    return
}

$installDir = Join-Path $env:ProgramData 'RCKNadzor'
$action = New-ScheduledTaskAction -Execute (Join-Path $env:windir 'System32\wscript.exe') `
    -Argument ('"' + (Join-Path $installDir 'pokreni.vbs') + '"')
$trigger = New-ScheduledTaskTrigger -AtLogOn

# Grupa "Korisnici"/"Users" preko SID-a, da radi i na hrvatskom i na engleskom Windowsu.
$usersGroup = (New-Object System.Security.Principal.SecurityIdentifier 'S-1-5-32-545').Translate(
    [System.Security.Principal.NTAccount]).Value
$principal = New-ScheduledTaskPrincipal -GroupId $usersGroup -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances Parallel

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null
