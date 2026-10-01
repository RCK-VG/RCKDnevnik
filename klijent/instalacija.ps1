<#
RCK Nadzor - instalacija i deinstalacija na učeničkom računalu.
Pokreću ga instaliraj.bat i deinstaliraj.bat (kao administrator).

Što radi:
  1. pronađe UČENIČKE račune (omogućeni lokalni računi koji nisu
     administratori) i pita je li popis točan,
  2. kopira datoteke:
       C:\ProgramData\RCKNadzor          servis, config.json, zapisi - samo SYSTEM i administratori
       C:\ProgramData\RCKNadzorProzor    prozor za prijavu - učenici smiju samo pokrenuti
       C:\ProgramData\RCKNadzorRazmjena  razgovor prozora i servisa
  3. uveze HTTPS certifikat servera (rck-ca.crt) u pouzdane,
  4. registrira zadatke "RCK Nadzor servis" (SYSTEM, pri pokretanju računala)
     i "RCK Nadzor prozor" (pri prijavi učeničkih računa),
  5. učeničkim računima isključi Task Manager, ikonu mreže, Postavke i
     Centar za akcije. Administratorski račun ostaje netaknut.

  .\instalacija.ps1 -SamoProvjera   pokaže što bi napravio, ništa ne mijenja
  .\instalacija.ps1 -Ukloni         deinstalacija
#>
[CmdletBinding()]
param(
    [switch]$Ukloni,
    [switch]$SamoProvjera,
    [string[]]$Racuni,
    [switch]$Da
)

$ErrorActionPreference = 'Stop'
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false

$Src = $PSScriptRoot
$Baza = Join-Path $env:ProgramData 'RCKNadzor'
$ProzorDir = Join-Path $env:ProgramData 'RCKNadzorProzor'
$Razmjena = Join-Path $env:ProgramData 'RCKNadzorRazmjena'
$ServiceTask = 'RCK Nadzor servis'
$WindowTask = 'RCK Nadzor prozor'
$OldTask = 'RCK Nadzor'   # stara verzija (radila pod učenikom)

# Isti popis je u servis.ps1.
$RestrictionValues = @(
    @('Software\Microsoft\Windows\CurrentVersion\Policies\System', 'DisableTaskMgr'),
    @('Software\Microsoft\Windows\CurrentVersion\Policies\Explorer', 'HideSCANetwork'),
    @('Software\Microsoft\Windows\CurrentVersion\Policies\Explorer', 'NoControlPanel'),
    @('Software\Policies\Microsoft\Windows\Explorer', 'DisableNotificationCenter')
)

function Say([string]$Text, [string]$Color = 'Gray') { Write-Host $Text -ForegroundColor $Color }

function Get-AccountName([string]$Sid) {
    (New-Object System.Security.Principal.SecurityIdentifier $Sid).Translate([System.Security.Principal.NTAccount]).Value
}

function Invoke-Native([string]$Exe, [string[]]$Arguments) {
    $out = & $Exe @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "$Exe $($Arguments -join ' ') nije uspio: $out" }
}

# --------------------------------------------------------------------------
# Učenički računi
# --------------------------------------------------------------------------

function Get-AdminSids {
    # Preko ADSI jer Get-LocalGroupMember zna pasti na "siroče" SID-ovima.
    $sids = New-Object 'System.Collections.Generic.HashSet[string]'
    $groupName = (Get-AccountName 'S-1-5-32-544').Split('\')[-1]
    $group = [ADSI]"WinNT://$env:COMPUTERNAME/$groupName,group"
    foreach ($m in @($group.Invoke('Members'))) {
        try {
            $bytes = $m.GetType().InvokeMember('objectSid', 'GetProperty', $null, $m, $null)
            [void]$sids.Add((New-Object System.Security.Principal.SecurityIdentifier($bytes, 0)).Value)
        } catch { }
    }
    , $sids
}

function Find-StudentAccounts {
    $admins = Get-AdminSids
    $builtin = @('500', '501', '503', '504')   # Administrator, Guest, DefaultAccount, WDAGUtilityAccount
    @(Get-LocalUser | Where-Object {
        $_.Enabled -and -not $admins.Contains($_.SID.Value) -and ($builtin -notcontains $_.SID.Value.Split('-')[-1])
    } | ForEach-Object { [pscustomobject]@{ Ime = $_.Name; Sid = $_.SID.Value } })
}

function Resolve-Accounts([string[]]$Names) {
    $admins = Get-AdminSids
    foreach ($n in $Names) {
        $name = $n.Trim()
        if (-not $name) { continue }
        $user = Get-LocalUser -Name $name -ErrorAction SilentlyContinue
        if (-not $user) { throw "Račun '$name' ne postoji na ovom računalu." }
        if ($admins.Contains($user.SID.Value)) { throw "Račun '$name' je administrator - njega se ne nadzire." }
        [pscustomobject]@{ Ime = $user.Name; Sid = $user.SID.Value }
    }
}

function Select-Accounts {
    if ($Racuni) { return @(Resolve-Accounts ($Racuni -split ',')) }
    $found = @(Find-StudentAccounts)
    Say ''
    if ($found.Count -gt 0) {
        Say 'Pronađeni učenički računi (NISU administratori) - njih će se nadzirati:' 'Cyan'
        foreach ($a in $found) { Say "   - $($a.Ime)" 'White' }
        Say 'Administratorski računi se ne diraju.'
        if ($Da -or $SamoProvjera) { return $found }
        $answer = Read-Host 'Je li popis točan? (D = da, N = upisat ću sam)'
        if ($answer -match '^\s*[dDyY]') { return $found }
    } else {
        Say 'Nije pronađen nijedan učenički račun (svi omogućeni računi su administratori).' 'Yellow'
        if ($SamoProvjera) { return @() }
    }
    $typed = Read-Host 'Upiši imena učeničkih računa, odvojena zarezom (npr. Učenik)'
    @(Resolve-Accounts ($typed -split ','))
}

# --------------------------------------------------------------------------
# Ograničenja u registryju učeničkih računa
# --------------------------------------------------------------------------

function Set-AccountRestrictions([string]$Sid, [bool]$Enable) {
    $hive = $null
    $loaded = $false
    if (Test-Path -LiteralPath "Registry::HKEY_USERS\$Sid") {
        $hive = "HKU\$Sid"                    # račun je upravo prijavljen
    } else {
        $profilePath = (Get-ItemProperty -LiteralPath "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\$Sid" -ErrorAction SilentlyContinue).ProfileImagePath
        $ntuser = if ($profilePath) { Join-Path $profilePath 'NTUSER.DAT' } else { $null }
        if (-not $ntuser -or -not (Test-Path -LiteralPath $ntuser)) {
            return 'profil još ne postoji - servis postavlja pri prvoj prijavi'
        }
        $hive = 'HKU\RCKNadzorTmp'
        Invoke-Native 'reg.exe' @('load', $hive, $ntuser)
        $loaded = $true
    }
    try {
        foreach ($v in $RestrictionValues) {
            if ($Enable) {
                Invoke-Native 'reg.exe' @('add', "$hive\$($v[0])", '/v', $v[1], '/t', 'REG_DWORD', '/d', '1', '/f')
            } else {
                & reg.exe delete "$hive\$($v[0])" /v $v[1] /f 2>&1 | Out-Null
            }
        }
    } finally {
        if ($loaded) {
            [GC]::Collect(); Start-Sleep -Milliseconds 300
            & reg.exe unload $hive 2>&1 | Out-Null
        }
    }
    return 'u redu'
}

# --------------------------------------------------------------------------
# Zadaci i procesi
# --------------------------------------------------------------------------

function Stop-Monitoring {
    foreach ($t in @($ServiceTask, $WindowTask, $OldTask)) {
        if (Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue) {
            Stop-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskName $t -Confirm:$false
        }
    }
    foreach ($p in @(Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" -ErrorAction SilentlyContinue)) {
        if ($p.CommandLine -and $p.CommandLine -match 'RCKNadzor(Prozor)?\\(servis|prozor|nadzor)\.ps1') {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Seconds 1
}

function Register-Tasks($Accounts) {
    $system = Get-AccountName 'S-1-5-18'
    $users = Get-AccountName 'S-1-5-32-545'
    $ps = Join-Path $env:windir 'System32\WindowsPowerShell\v1.0\powershell.exe'

    # Servis: pri pokretanju računala + svakih 5 minuta provjera da još radi
    # (ako radi, novi primjerak se odmah ugasi).
    $action = New-ScheduledTaskAction -Execute $ps `
        -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + (Join-Path $Baza 'servis.ps1') + '"')
    # Ponavljanje svake minute: ako servis nije živ (pao ili se sam ugasio radi
    # nadogradnje), sljedeća minuta ga ponovno pokrene. Ako već radi, novi
    # primjerak odmah iziđe (mutex + MultipleInstances IgnoreNew).
    $triggers = @(
        (New-ScheduledTaskTrigger -AtStartup),
        (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1))
    )
    $principal = New-ScheduledTaskPrincipal -UserId $system -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $ServiceTask -Action $action -Trigger $triggers -Principal $principal `
        -Settings $settings -Description 'RCK Nadzor: bilježi aktivnost na učeničkim računima.' -Force | Out-Null

    # Prozor: pri prijavi svakog učeničkog računa, pod tim računom. Ostaje raditi
    # cijelu prijavu (sam se pokaže/sakrije po potrebi), pa ne treba ponavljanje.
    $action = New-ScheduledTaskAction -Execute (Join-Path $env:windir 'System32\wscript.exe') `
        -Argument ('"' + (Join-Path $ProzorDir 'pokreni_prozor.vbs') + '"')
    $triggers = @($Accounts | ForEach-Object { New-ScheduledTaskTrigger -AtLogOn -User (Get-AccountName $_.Sid) })
    $principal = New-ScheduledTaskPrincipal -GroupId $users -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances Parallel `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $WindowTask -Action $action -Trigger $triggers -Principal $principal `
        -Settings $settings -Description 'RCK Nadzor: prozor za prijavu učenika.' -Force | Out-Null
}

function Set-Folder([string]$Path, [string[]]$Grants) {
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
    Invoke-Native 'icacls.exe' (@($Path, '/inheritance:r', '/grant:r') + $Grants)
    Invoke-Native 'icacls.exe' @((Join-Path $Path '*'), '/reset', '/T', '/C', '/Q')
}

# --------------------------------------------------------------------------
# Deinstalacija
# --------------------------------------------------------------------------

function Uninstall {
    $accounts = @()
    try { $accounts = @(Get-Content -LiteralPath (Join-Path $Baza 'racuni.json') -Raw -Encoding UTF8 | ConvertFrom-Json) } catch { }
    Say 'Zaustavljam i brišem zadatke ...'
    Stop-Monitoring
    foreach ($a in $accounts) {
        if (-not $a.sid) { continue }
        try { $r = Set-AccountRestrictions ([string]$a.sid) $false; Say "Ograničenja uklonjena: $($a.ime) ($r)" }
        catch { Say "Ograničenja za $($a.ime) nisu uklonjena: $($_.Exception.Message)" 'Yellow' }
    }
    foreach ($d in @($Baza, $ProzorDir, $Razmjena)) {
        if (Test-Path -LiteralPath $d) { Remove-Item -LiteralPath $d -Recurse -Force }
    }
    Say ''
    Say 'Nadzor je uklonjen s ovog računala.' 'Green'
    Say 'Certifikat servera ostaje među pouzdanima (ne smeta). Ukloniti ga se može u certmgr.msc.'
}

# --------------------------------------------------------------------------
# Instalacija
# --------------------------------------------------------------------------

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin -and -not $SamoProvjera) { throw 'Pokreni kao administrator (desni klik > Pokreni kao administrator).' }

if ($Ukloni) { Uninstall; return }

foreach ($f in @('servis.ps1', 'prozor.ps1', 'pokreni_prozor.vbs', 'preskoci_procese.txt', 'preskoci_domene.txt', 'config.json')) {
    if (-not (Test-Path -LiteralPath (Join-Path $Src $f))) {
        throw "Nedostaje datoteka $f u mapi $Src (config.json se radi na serveru, vidi klijent\README.md)."
    }
}
$cfg = Get-Content -LiteralPath (Join-Path $Src 'config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $cfg.serverUrl -or -not $cfg.apiKey) { throw 'config.json mora imati serverUrl i apiKey.' }
$hasCert = Test-Path -LiteralPath (Join-Path $Src 'rck-ca.crt')

Say "Računalo: $env:COMPUTERNAME     server: $($cfg.serverUrl)" 'Cyan'
$accounts = @(Select-Accounts)
if ($accounts.Count -eq 0) { throw 'Nema učeničkih računa za nadzor - ništa nije instalirano.' }

if ($SamoProvjera) {
    Say ''
    Say 'SAMO PROVJERA - ništa nije promijenjeno. Instalacija bi:' 'Yellow'
    Say "  - kopirala datoteke u $Baza, $ProzorDir i $Razmjena"
    Say "  - $(if ($hasCert) { 'uvezla rck-ca.crt u pouzdane' } else { 'preskočila certifikat (nema rck-ca.crt)' })"
    Say "  - registrirala zadatke '$ServiceTask' i '$WindowTask'"
    Say "  - postavila ograničenja za: $(($accounts | ForEach-Object { $_.Ime }) -join ', ')"
    return
}

Say ''
Say 'Zaustavljam prethodnu verziju (ako postoji) ...'
Stop-Monitoring
# Stara verzija je ovdje držala i skripte za učenika - više ne trebaju.
foreach ($old in @('nadzor.ps1', 'pokreni.vbs', 'zadatak.ps1')) {
    Remove-Item -LiteralPath (Join-Path $Baza $old) -Force -ErrorAction SilentlyContinue
}

Say 'Kopiram datoteke i postavljam dozvole ...'
$S = '*S-1-5-18'; $A = '*S-1-5-32-544'; $U = '*S-1-5-32-545'
# Servis i postavke: učenici ne smiju ni čitati.
Set-Folder $Baza @("${S}:(OI)(CI)F", "${A}:(OI)(CI)F")
foreach ($f in @('servis.ps1', 'config.json', 'preskoci_procese.txt', 'preskoci_domene.txt')) { Copy-Item -LiteralPath (Join-Path $Src $f) -Destination $Baza -Force }
$list = @($accounts | ForEach-Object { [ordered]@{ ime = $_.Ime; sid = $_.Sid } })
[System.IO.File]::WriteAllText((Join-Path $Baza 'racuni.json'), (ConvertTo-Json -InputObject $list -Compress), $Utf8NoBom)
Invoke-Native 'icacls.exe' @((Join-Path $Baza '*'), '/reset', '/T', '/C', '/Q')

# Prozor: učenici ga smiju pokrenuti, ali ne i mijenjati.
Set-Folder $ProzorDir @("${S}:(OI)(CI)F", "${A}:(OI)(CI)F", "${U}:(OI)(CI)RX")
foreach ($f in @('prozor.ps1', 'pokreni_prozor.vbs')) { Copy-Item -LiteralPath (Join-Path $Src $f) -Destination $ProzorDir -Force }
Invoke-Native 'icacls.exe' @((Join-Path $ProzorDir '*'), '/reset', '/T', '/C', '/Q')

# Razmjena: učenici čitaju popis razreda i stanje te ostavljaju zahtjev za prijavu.
if (Test-Path -LiteralPath $Razmjena) { Get-ChildItem -LiteralPath $Razmjena -Force | Remove-Item -Force -Recurse }
Set-Folder $Razmjena @("${S}:(OI)(CI)F", "${A}:(OI)(CI)F", "${U}:(OI)(CI)RX")
Invoke-Native 'icacls.exe' @($Razmjena, '/grant', "${U}:(WD)")

if ($hasCert) {
    Say 'Uvozim HTTPS certifikat servera u pouzdane ...'
    Invoke-Native 'certutil.exe' @('-addstore', '-f', 'Root', (Join-Path $Src 'rck-ca.crt'))
} else {
    Say 'Nema rck-ca.crt - preskačem certifikat (potreban samo za https adresu).' 'Yellow'
}

Say 'Ograničenja za učeničke račune (Task Manager, mreža, Postavke) ...'
foreach ($a in $accounts) {
    try { Say "   $($a.Ime): $(Set-AccountRestrictions $a.Sid $true)" }
    catch { Say "   $($a.Ime): nije uspjelo ($($_.Exception.Message)) - servis će pokušati pri prijavi" 'Yellow' }
}

Say 'Registriram zadatke i pokrećem servis ...'
Register-Tasks $accounts
Start-ScheduledTask -TaskName $ServiceTask

Say ''
Say 'Gotovo. Odjavi se i prijavi na učenički račun - trebao bi se pojaviti prozor za prijavu.' 'Green'
Say "Dnevnik servisa: $Baza\nadzor.log"
