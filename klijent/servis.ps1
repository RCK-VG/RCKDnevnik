<#
RCK Nadzor - servis (radi kao SYSTEM, pokreće se s računalom).

Drži ključ i postavke (config.json), red čekanja i dnevnik u mapi
C:\ProgramData\RCKNadzor do koje učenici nemaju pristup, i ne mogu ga ugasiti
bez administratorske lozinke. Za svaki prijavljeni UČENIČKI račun (popis u
racuni.json, radi ga instalacija):
  - čeka da se učenik prijavi u prozoru (prozor.ps1, radi pod učenikom i
    razgovara sa servisom preko mape C:\ProgramData\RCKNadzorRazmjena);
    ako se ne prijavi u zadanom roku, odjavi ga iz Windowsa,
  - javlja instalirane i pokrenute programe, nove AppData mape, nove ikone,
    promjenu pozadine te gašenje/paljenje mreže,
  - šalje "živ sam" (za provjeru dvostruke prijave) i odjavu,
  - postavlja ograničenja za učenički račun (Task Manager, ikona mreže...).
Ako server ne radi, sve čeka u redu i šalje se kasnije.

Za probu bez instalacije (prati trenutnog korisnika, NE odjavljuje i NE
postavlja ograničenja):
  .\servis.ps1 -Proba -Baza C:\temp\baza -Razmjena C:\temp\razmjena -Trajanje 120
#>
[CmdletBinding()]
param(
    [string]$Baza = (Join-Path $env:ProgramData 'RCKNadzor'),
    [string]$Razmjena = (Join-Path $env:ProgramData 'RCKNadzorRazmjena'),
    [switch]$Proba,
    [int]$Trajanje = 0
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
$ApiPrefix = '/api/nadzor/v1'
$FastSeconds = 2
$SendBatch = 100
$MaxQueueLines = 20000

# --------------------------------------------------------------------------
# Općenito
# --------------------------------------------------------------------------

function Write-Log([string]$Message) {
    try {
        $file = Join-Path $Baza 'nadzor.log'
        if ((Test-Path -LiteralPath $file) -and (Get-Item -LiteralPath $file).Length -gt 2MB) {
            Move-Item -LiteralPath $file -Destination "$file.1" -Force
        }
        $line = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + '  ' + $Message + "`r`n"
        [System.IO.File]::AppendAllText($file, $line, $Utf8NoBom)
    } catch { }
}

function Get-ClientTime([datetime]$When = (Get-Date)) {
    $When.ToString('yyyy-MM-ddTHH:mm:ss.fffzzz', [Globalization.CultureInfo]::InvariantCulture)
}

function Read-JsonFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $text = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
    if (-not $text.Trim()) { return $null }
    # Prvo u varijablu: PowerShell 5.1 inače JSON polje vrati kao jedan element.
    $parsed = $text | ConvertFrom-Json
    return $parsed
}

function Write-JsonFile([string]$Path, $Object) {
    [System.IO.File]::WriteAllText($Path, (ConvertTo-Json -InputObject $Object -Depth 8 -Compress), $Utf8NoBom)
}

function Read-Config {
    $cfg = Read-JsonFile (Join-Path $Baza 'config.json')
    if (-not $cfg -or -not $cfg.serverUrl -or -not $cfg.apiKey) { throw 'config.json mora imati serverUrl i apiKey.' }
    $poll = 60; if ($cfg.pollSeconds) { $poll = [Math]::Max(10, [int]$cfg.pollSeconds) }
    $timeout = 2.0; if ($cfg.loginTimeoutMinutes) { $timeout = [Math]::Max(0.1, [double]$cfg.loginTimeoutMinutes) }
    $skipWin = $true; if ($null -ne $cfg.skipWindowsDir) { $skipWin = [bool]$cfg.skipWindowsDir }
    $restrict = $true; if ($null -ne $cfg.restrictions) { $restrict = [bool]$cfg.restrictions }
    [pscustomobject]@{
        ServerUrl           = ([string]$cfg.serverUrl).TrimEnd('/')
        ApiKey              = [string]$cfg.apiKey
        PollSeconds         = $poll
        LoginTimeoutMinutes = $timeout
        SkipWindowsDir      = $skipWin
        Restrictions        = $restrict
    }
}

function Read-SkipList {
    $set = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $file = Join-Path $Baza 'preskoci_procese.txt'
    if (Test-Path -LiteralPath $file) {
        foreach ($line in [System.IO.File]::ReadAllLines($file, [System.Text.Encoding]::UTF8)) {
            $name = ($line -replace '#.*$', '').Trim()
            if ($name) { [void]$set.Add(($name -replace '\.exe$', '')) }
        }
    }
    , $set
}

function Read-Accounts {
    # SID-ovi učeničkih računa koje treba nadzirati (instalacija ih zapisuje).
    $set = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $list = Read-JsonFile (Join-Path $Baza 'racuni.json')
    foreach ($a in @($list)) { if ($a -and $a.sid) { [void]$set.Add([string]$a.sid) } }
    , $set
}

# --------------------------------------------------------------------------
# Komunikacija sa serverom (tijelo i odgovor izričito UTF-8)
# --------------------------------------------------------------------------

function Invoke-NadzorApi([string]$Method, [string]$Path, $Body) {
    try {
        $req = [System.Net.HttpWebRequest]::Create($script:Config.ServerUrl + $ApiPrefix + $Path)
        $req.Method = $Method
        $req.Timeout = 15000
        $req.ReadWriteTimeout = 15000
        $req.Accept = 'application/json'
        $req.UserAgent = 'RCKNadzor/2.0'
        $req.Headers.Add('X-API-Key', $script:Config.ApiKey)
        if ($null -ne $Body) {
            $bytes = [System.Text.Encoding]::UTF8.GetBytes((ConvertTo-Json -InputObject $Body -Depth 8 -Compress))
            $req.ContentType = 'application/json; charset=utf-8'
            $req.ContentLength = $bytes.Length
            $stream = $req.GetRequestStream()
            try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Close() }
        }
        $resp = $null
        try {
            $resp = $req.GetResponse()
        } catch {
            $ex = $_.Exception
            while ($ex -and -not ($ex -is [System.Net.WebException])) { $ex = $ex.InnerException }
            if ($ex -and $ex.Response) { $resp = $ex.Response } else { throw }
        }
        try {
            $status = [int]$resp.StatusCode
            $reader = New-Object System.IO.StreamReader($resp.GetResponseStream(), [System.Text.Encoding]::UTF8)
            $text = $reader.ReadToEnd()
            $reader.Close()
        } finally { $resp.Close() }
        $data = $null
        if ($text) { try { $data = $text | ConvertFrom-Json } catch { } }
        return [pscustomobject]@{ Status = $status; Data = $data; Error = $null }
    } catch {
        return [pscustomobject]@{ Status = 0; Data = $null; Error = $_.Exception.Message }
    }
}

function Test-Offline($Result) { $Result.Status -eq 0 -or $Result.Status -ge 500 -or $Result.Status -eq 429 }

function Get-ErrorText($Result, [string]$Fallback) {
    if ($Result.Data -and $Result.Data.greska) { return [string]$Result.Data.greska }
    return $Fallback
}

# --------------------------------------------------------------------------
# Zapisi o prijavama (sesije.json) i red čekanja (red.jsonl)
#
# Svaka Windows prijava učenika dobije lokalni zapis (Id) sa statusom:
#   neprijavljen    - učenik se još nije prijavio u prozoru
#   ceka            - upisao je ime dok server nije radio, provjera kasnije
#   ok              - server ga je prepoznao (Token)
#   neidentificiran - nije se prijavio ili upisano ime ne postoji
# Događaji u redu čekanja nose Id, pa se šalju tek kad se zna kome pripadaju.
# --------------------------------------------------------------------------

function Load-Records {
    $script:Records = @{}
    $raw = $null
    try { $raw = Read-JsonFile (Join-Path $Baza 'sesije.json') } catch { Write-Log "sesije.json oštećen: $($_.Exception.Message)" }
    if ($raw) {
        foreach ($p in $raw.PSObject.Properties) {
            $r = $p.Value
            $typed = @{}
            if ($r.upisano) { foreach ($q in $r.upisano.PSObject.Properties) { $typed[$q.Name] = [string]$q.Value } }
            $script:Records[$p.Name] = @{
                id            = [string]$p.Name
                kljuc         = [string]$r.kljuc
                korisnik      = [string]$r.korisnik
                pocetak       = [string]$r.pocetak
                status        = [string]$r.status
                token         = [string]$r.token
                upisano       = $typed
                zavrsena      = [bool]$r.zavrsena
                odjavaPoslana = [bool]$r.odjavaPoslana
            }
        }
    }
}

function Save-Records { Write-JsonFile (Join-Path $Baza 'sesije.json') $script:Records }

function Get-QueueFile { Join-Path $Baza 'red.jsonl' }

function Add-Event([string]$RecordId, [string]$Type, [string]$Details) {
    $entry = [ordered]@{
        sesija   = $RecordId
        racunalo = $env:COMPUTERNAME
        zapis    = [ordered]@{ vrsta = $Type; detalji = $Details; vrijeme = (Get-ClientTime) }
    }
    [System.IO.File]::AppendAllText((Get-QueueFile), (ConvertTo-Json -InputObject $entry -Depth 5 -Compress) + "`n", $Utf8NoBom)
    Write-Log "[$RecordId] $Type  $Details"
}

function Send-Queue {
    $file = Get-QueueFile
    $remaining = New-Object 'System.Collections.Generic.HashSet[string]'
    if (-not (Test-Path -LiteralPath $file)) { return , $remaining }
    $lines = @([System.IO.File]::ReadAllLines($file, [System.Text.Encoding]::UTF8) | Where-Object { $_.Trim() })
    if ($lines.Count -gt $MaxQueueLines) {
        Write-Log "Red čekanja prevelik ($($lines.Count)), odbacujem najstarije."
        $lines = $lines[($lines.Count - $MaxQueueLines)..($lines.Count - 1)]
    }
    $entries = New-Object System.Collections.ArrayList
    foreach ($l in $lines) { try { [void]$entries.Add(($l | ConvertFrom-Json)) } catch { } }

    $keep = New-Object System.Collections.ArrayList
    $serverDown = $false
    foreach ($group in @($entries | Group-Object -Property sesija)) {
        $rec = $script:Records[$group.Name]
        $items = @($group.Group)
        # Kome pripadaju? Ako se još ne zna, čekaju.
        $body = $null
        if ($rec -and $rec.status -eq 'ok' -and $rec.token) {
            $body = [ordered]@{ token = $rec.token }
        } elseif (-not $rec -or $rec.status -eq 'neidentificiran' -or ($rec.status -eq 'neprijavljen' -and $rec.zavrsena)) {
            if ($rec -and $rec.status -ne 'neidentificiran') { $rec.status = 'neidentificiran'; Save-Records }
            $typed = @{}
            if ($rec) { $typed = $rec.upisano }
            $body = [ordered]@{ neidentificiran = $typed }
        }
        if ($null -eq $body -or $serverDown) {
            foreach ($c in $items) { [void]$keep.Add($c) }
            continue
        }
        for ($i = 0; $i -lt $items.Count; $i += $SendBatch) {
            $chunk = @($items[$i..([Math]::Min($i + $SendBatch, $items.Count) - 1)])
            if ($serverDown) { foreach ($c in $chunk) { [void]$keep.Add($c) }; continue }
            $events = New-Object System.Collections.ArrayList
            foreach ($c in $chunk) { [void]$events.Add($c.zapis) }
            $payload = [ordered]@{}
            foreach ($k in $body.Keys) { $payload[$k] = $body[$k] }
            $payload['racunalo'] = $env:COMPUTERNAME
            $payload['zapisi'] = $events.ToArray()
            $r = Invoke-NadzorApi 'POST' '/zapisi/' $payload
            if ($r.Status -eq 201) { continue }
            if (Test-Offline $r) {
                $serverDown = $true
                foreach ($c in $chunk) { [void]$keep.Add($c) }
            } else {
                Write-Log "Odbačeno $($chunk.Count) zapisa: HTTP $($r.Status) $(Get-ErrorText $r '')"
            }
        }
    }

    if ($keep.Count -eq 0) {
        Remove-Item -LiteralPath $file -Force
    } else {
        $out = foreach ($k in $keep) { ConvertTo-Json -InputObject $k -Depth 5 -Compress; [void]$remaining.Add([string]$k.sesija) }
        [System.IO.File]::WriteAllText($file, (($out -join "`n") + "`n"), $Utf8NoBom)
    }
    return , $remaining
}

# --------------------------------------------------------------------------
# Windows prijave učenika
# --------------------------------------------------------------------------

$script:Sessions = @{}          # "<id Windows sesije>|<korisnik>" -> stanje u memoriji
$script:SidCache = @{}

function Get-UserSid([string]$Account) {
    if (-not $script:SidCache.ContainsKey($Account)) {
        try {
            $script:SidCache[$Account] = (New-Object System.Security.Principal.NTAccount($Account)).Translate(
                [System.Security.Principal.SecurityIdentifier]).Value
        } catch { $script:SidCache[$Account] = '' }
    }
    $script:SidCache[$Account]
}

function Get-ProfilePath([string]$Sid) {
    try {
        $key = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey("SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\$Sid")
        if ($key) { try { return [string]$key.GetValue('ProfileImagePath') } finally { $key.Close() } }
    } catch { }
    return $null
}

function Get-LiveSessions {
    # Svaka interaktivna prijava ima explorer.exe; po njemu znamo tko je gdje.
    $result = @{}
    if ($Proba) {
        $wsid = (Get-Process -Id $PID).SessionId
        $account = "$env:USERDOMAIN\$env:USERNAME"
        $result["$wsid|$account"] = [pscustomobject]@{ WinSid = $wsid; Account = $account; Sid = (Get-UserSid $account) }
        return $result
    }
    foreach ($p in @(Get-Process -Name explorer -IncludeUserName -ErrorAction SilentlyContinue)) {
        if (-not $p.UserName) { continue }
        $sid = Get-UserSid $p.UserName
        if (-not $sid -or -not $script:Accounts.Contains($sid)) { continue }
        $key = "$($p.SessionId)|$($p.UserName)"
        if (-not $result.ContainsKey($key)) {
            $result[$key] = [pscustomobject]@{ WinSid = $p.SessionId; Account = $p.UserName; Sid = $sid }
        }
    }
    $result
}

function Update-Sessions {
    $live = Get-LiveSessions
    $now = Get-Date

    foreach ($key in $live.Keys) {
        if ($script:Sessions.ContainsKey($key)) { $script:Sessions[$key].LastSeen = $now; continue }
        $info = $live[$key]
        # Isti zapis nakon ponovnog pokretanja servisa (npr. nadogradnja) - ne pitaj ponovno.
        $rec = $null
        foreach ($r in $script:Records.Values) { if ($r.kljuc -eq $key -and -not $r.zavrsena) { $rec = $r; break } }
        if (-not $rec) {
            $id = [guid]::NewGuid().ToString('N').Substring(0, 12)
            $rec = @{ id = $id; kljuc = $key; korisnik = $info.Account; pocetak = (Get-ClientTime $now)
                      status = 'neprijavljen'; token = ''; upisano = @{}; zavrsena = $false; odjavaPoslana = $false }
            $script:Records[$id] = $rec
            Save-Records
            Write-Log "Nova Windows prijava: $($info.Account) (sesija $($info.WinSid))"
        }
        $deadline = $null
        if ($rec.status -eq 'neprijavljen') { $deadline = $now.AddMinutes($script:Config.LoginTimeoutMinutes) }
        $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
        $s = [pscustomobject]@{
            Key = $key; WinSid = $info.WinSid; Account = $info.Account; Sid = $info.Sid
            Profile = (Get-ProfilePath $info.Sid); RecordId = $rec.id; Deadline = $deadline
            LoggedOff = $false; LastSeen = $now; Seen = $seen
        }
        foreach ($name in (Get-SessionProcesses $s).Keys) { [void]$seen.Add($name) }
        $script:Sessions[$key] = $s
        if (-not $Proba) { Set-Restrictions $info.Sid $script:Config.Restrictions }
        Write-Status $s
    }

    foreach ($key in @($script:Sessions.Keys)) {
        $s = $script:Sessions[$key]
        if ($live.ContainsKey($key)) { continue }
        if (($now - $s.LastSeen).TotalSeconds -lt 20) { continue }   # explorer se možda samo ponovno pokreće
        $rec = $script:Records[$s.RecordId]
        if ($rec) { $rec.zavrsena = $true; Save-Records }
        Write-Log "Kraj Windows prijave: $($s.Account)"
        foreach ($f in @("status-$($s.WinSid).json", "odgovor-$($s.WinSid).json")) {
            Remove-Item -LiteralPath (Join-Path $Razmjena $f) -Force -ErrorAction SilentlyContinue
        }
        $script:Sessions.Remove($key)
    }

    # Zapisi koji su ostali "otvoreni" (npr. računalo je ugašeno) - zatvori ih.
    $liveKeys = @($script:Sessions.Keys)
    foreach ($r in @($script:Records.Values)) {
        if (-not $r.zavrsena -and $liveKeys -notcontains $r.kljuc) { $r.zavrsena = $true; Save-Records }
    }
}

function Write-Status($Session) {
    $rec = $script:Records[$Session.RecordId]
    $deadline = $null
    if ($Session.Deadline) { $deadline = Get-ClientTime $Session.Deadline }
    $obj = [ordered]@{ korisnik = $Session.Account; stanje = $rec.status; rok = $deadline; sada = (Get-ClientTime) }
    Write-JsonFile (Join-Path $Razmjena "status-$($Session.WinSid).json") $obj
}

function Invoke-StudentLogin($Session, $Typed) {
    $rec = $script:Records[$Session.RecordId]
    if ($rec.status -eq 'ok' -or $rec.status -eq 'ceka') { return @{ stanje = 'ok'; poruka = 'Već si prijavljen/a.' } }

    $body = [ordered]@{ razred = $Typed.razred; ime = $Typed.ime; prezime = $Typed.prezime; racunalo = $env:COMPUTERNAME }
    $r = Invoke-NadzorApi 'POST' '/prijava/' $body
    if ($r.Status -eq 200 -and $r.Data.token) {
        $rec.status = 'ok'; $rec.token = [string]$r.Data.token; $rec.upisano = $Typed
        $Session.Deadline = $null
        Save-Records
        Write-Log "Prijava učenika: $($r.Data.ucenik), $($r.Data.razred)"
        return @{ stanje = 'ok'; poruka = "Prijavljen/a: $($r.Data.ucenik), $($r.Data.razred)" }
    }
    if (Test-Offline $r) {
        $rec.status = 'ceka'; $rec.upisano = $Typed
        $Session.Deadline = $null
        Save-Records
        Write-Log "Server nedostupan, prijava prihvaćena za kasniju provjeru: $($Typed.ime) $($Typed.prezime) $($Typed.razred)"
        return @{ stanje = 'ok'; poruka = 'Server trenutno nije dostupan. Prijava će se provjeriti kasnije.' }
    }
    return @{ stanje = 'greska'; poruka = (Get-ErrorText $r "Greška pri prijavi (HTTP $($r.Status)).") }
}

function Receive-LoginRequests {
    foreach ($file in @(Get-ChildItem -LiteralPath $Razmjena -Filter 'prijava-*.json' -File -ErrorAction SilentlyContinue)) {
        if ($file.Name -notmatch '^prijava-(\d+)-(\w+)\.json$') {
            Remove-Item -LiteralPath $file.FullName -Force -ErrorAction SilentlyContinue; continue
        }
        $wsid = [int]$Matches[1]; $request = $Matches[2]
        $session = $null
        foreach ($s in $script:Sessions.Values) { if ($s.WinSid -eq $wsid) { $session = $s; break } }
        $typed = $null
        try {
            $data = Read-JsonFile $file.FullName
            $typed = @{ razred = [string]$data.razred; ime = [string]$data.ime; prezime = [string]$data.prezime }
        } catch {
            if (((Get-Date) - $file.LastWriteTime).TotalSeconds -lt 5) { continue }  # možda se još piše
        }
        $owner = ''
        try { $owner = (Get-Acl -LiteralPath $file.FullName).Owner } catch { }
        Remove-Item -LiteralPath $file.FullName -Force -ErrorAction SilentlyContinue
        if (-not $session -or -not $typed) { continue }
        # Zahtjev mora doći od učenika te Windows sesije.
        if (-not $Proba -and $owner -and $owner -ne $session.Account) {
            Write-Log "Odbijen zahtjev iz tuđe sesije ($owner)"; continue
        }
        $answer = Invoke-StudentLogin $session $typed
        $answer['zahtjev'] = $request
        Write-JsonFile (Join-Path $Razmjena "odgovor-$wsid.json") $answer
        Write-Status $session
    }
}

function Invoke-Deadlines {
    $now = Get-Date
    foreach ($s in @($script:Sessions.Values)) {
        if ($s.LoggedOff -or -not $s.Deadline -or $now -lt $s.Deadline) { continue }
        $rec = $script:Records[$s.RecordId]
        if ($rec.status -ne 'neprijavljen') { $s.Deadline = $null; continue }
        $s.LoggedOff = $true
        $rec.status = 'neidentificiran'
        Save-Records
        Add-Event $s.RecordId 'ODJAVA - NIJE SE PRIJAVIO' "Učenik se nije prijavio u $($script:Config.LoginTimeoutMinutes) min ($($s.Account))."
        if ($Proba) {
            Write-Log "PROBA: ovdje bi odjavio Windows sesiju $($s.WinSid)"
        } else {
            try { & (Join-Path $env:windir 'System32\logoff.exe') $s.WinSid } catch { Write-Log "Odjava nije uspjela: $($_.Exception.Message)" }
        }
    }
}

# --------------------------------------------------------------------------
# Ograničenja za učenički račun (upisuje se u njegov dio registryja)
# --------------------------------------------------------------------------

# Isti popis je u instalacija.ps1 (postavlja ih odmah i briše pri deinstalaciji).
$RestrictionValues = @(
    @('Software\Microsoft\Windows\CurrentVersion\Policies\System', 'DisableTaskMgr'),       # Task Manager
    @('Software\Microsoft\Windows\CurrentVersion\Policies\Explorer', 'HideSCANetwork'),     # ikona mreže
    @('Software\Microsoft\Windows\CurrentVersion\Policies\Explorer', 'NoControlPanel'),     # Postavke i Upravljačka ploča
    @('Software\Policies\Microsoft\Windows\Explorer', 'DisableNotificationCenter')          # Centar za akcije (Wi-Fi, zrakoplov)
)

function Set-Restrictions([string]$Sid, [bool]$Enable = $true) {
    foreach ($v in $RestrictionValues) {
        try {
            $path = "Registry::HKEY_USERS\$Sid\$($v[0])"
            if ($Enable) {
                if (-not (Test-Path -LiteralPath $path)) { New-Item -Path $path -Force | Out-Null }
                New-ItemProperty -LiteralPath $path -Name $v[1] -Value 1 -PropertyType DWord -Force | Out-Null
            } else {
                Remove-ItemProperty -LiteralPath $path -Name $v[1] -ErrorAction SilentlyContinue
            }
        } catch { Write-Log "Ograničenje $($v[1]) nije promijenjeno: $($_.Exception.Message)" }
    }
}

# --------------------------------------------------------------------------
# Provjere (izvode se za svakog prijavljenog učenika)
# --------------------------------------------------------------------------

function Get-InstalledPrograms([string]$Sid) {
    $result = @{}
    $paths = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
        "Registry::HKEY_USERS\$Sid\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    foreach ($p in $paths) {
        foreach ($item in @(Get-ItemProperty -Path $p -ErrorAction SilentlyContinue)) {
            if (-not $item.DisplayName) { continue }
            if ($item.SystemComponent -eq 1) { continue }
            $label = [string]$item.DisplayName
            if ($item.DisplayVersion) { $label += " $($item.DisplayVersion)" }
            if ($item.Publisher) { $label += " ($($item.Publisher))" }
            $result[[string]$item.PSPath] = $label
        }
    }
    $result
}

function Get-AppDataFolders([string]$ProfilePath) {
    $result = @{}
    if (-not $ProfilePath) { return $result }
    foreach ($label in @('Roaming', 'Local', 'LocalLow')) {
        $root = Join-Path $ProfilePath "AppData\$label"
        if (-not (Test-Path -LiteralPath $root)) { continue }
        foreach ($dir in @(Get-ChildItem -LiteralPath $root -Directory -Force -ErrorAction SilentlyContinue)) {
            if ($dir.Name -in @('Temp')) { continue }
            $key = "$label\$($dir.Name)"
            $result[$key] = $key
        }
    }
    $result
}

function Get-UserDesktop([string]$Sid, [string]$ProfilePath) {
    # REG_EXPAND_SZ čitamo neproširen: kao SYSTEM bi %USERPROFILE% bio pogrešan.
    try {
        $key = [Microsoft.Win32.Registry]::Users.OpenSubKey("$Sid\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
        if ($key) {
            try {
                $raw = [string]$key.GetValue('Desktop', $null, [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
                if ($raw) { return ($raw -replace '%USERPROFILE%', $ProfilePath) }
            } finally { $key.Close() }
        }
    } catch { }
    if ($ProfilePath) { return (Join-Path $ProfilePath 'Desktop') }
    return $null
}

function Get-DesktopItems([string]$Sid, [string]$ProfilePath) {
    $result = @{}
    $shell = $null
    $desktops = @((Get-UserDesktop $Sid $ProfilePath), [Environment]::GetFolderPath('CommonDesktopDirectory'))
    foreach ($d in $desktops) {
        if (-not $d -or -not (Test-Path -LiteralPath $d)) { continue }
        foreach ($f in @(Get-ChildItem -LiteralPath $d -File -Force -ErrorAction SilentlyContinue)) {
            if ($f.Extension -notin @('.lnk', '.url', '.exe', '.appref-ms')) { continue }
            $label = $f.Name
            if ($f.Extension -eq '.lnk') {
                try {
                    if (-not $shell) { $shell = New-Object -ComObject WScript.Shell }
                    $target = $shell.CreateShortcut($f.FullName).TargetPath
                    if ($target) { $label += " -> $target" }
                } catch { }
            }
            $result[$f.FullName] = $label
        }
    }
    $result
}

function Get-Wallpaper([string]$Sid) {
    try {
        [string](Get-ItemProperty -LiteralPath "Registry::HKEY_USERS\$Sid\Control Panel\Desktop" -Name WallPaper).WallPaper
    } catch { '' }
}

function Get-SessionProcesses($Session) {
    $result = @{}
    foreach ($p in @(Get-Process -ErrorAction SilentlyContinue)) {
        if ($p.SessionId -ne $Session.WinSid) { continue }
        if ($script:Skip.Contains($p.ProcessName)) { continue }
        $path = $null
        try { $path = $p.Path } catch { }
        if (-not $path) { continue }
        if ($script:Config.SkipWindowsDir -and $path.StartsWith($env:windir, [StringComparison]::OrdinalIgnoreCase)) { continue }
        if (-not $result.ContainsKey($p.ProcessName)) { $result[$p.ProcessName] = $path }
    }
    $result
}

$script:States = @{}

function Get-StateFile([string]$Sid) { Join-Path (Join-Path $Baza 'stanje') "$Sid.json" }

function Get-State([string]$Sid, [string]$ProfilePath) {
    if ($script:States.ContainsKey($Sid)) { return $script:States[$Sid] }
    $state = $null
    try {
        $raw = Read-JsonFile (Get-StateFile $Sid)
        if ($raw) {
            $state = @{ programi = @{}; appdata = @{}; ikone = @{}; pozadina = [string]$raw.pozadina }
            foreach ($section in @('programi', 'appdata', 'ikone')) {
                if ($raw.$section) { foreach ($p in $raw.$section.PSObject.Properties) { $state[$section][$p.Name] = [string]$p.Value } }
            }
        }
    } catch { Write-Log "Stanje za $Sid oštećeno, radim novo: $($_.Exception.Message)" }
    if (-not $state) {
        # Prvi put za ovaj račun: samo zapamti što postoji, ništa ne javljaj.
        $state = @{
            programi = Get-InstalledPrograms $Sid
            appdata  = Get-AppDataFolders $ProfilePath
            ikone    = Get-DesktopItems $Sid $ProfilePath
            pozadina = Get-Wallpaper $Sid
        }
        Write-JsonFile (Get-StateFile $Sid) $state
        Write-Log "Zapamćeno početno stanje računa $Sid."
    }
    $script:States[$Sid] = $state
    $state
}

function Compare-AndReport($State, [string]$Section, [hashtable]$Current, [string]$EventType, [string]$RecordId) {
    $known = $State[$Section]
    foreach ($key in $Current.Keys) {
        if (-not $known.ContainsKey($key)) { Add-Event $RecordId $EventType $Current[$key] }
    }
    $State[$Section] = $Current
}

function Invoke-Scans {
    foreach ($s in @($script:Sessions.Values)) {
        try {
            $state = Get-State $s.Sid $s.Profile
            Compare-AndReport $state 'programi' (Get-InstalledPrograms $s.Sid) 'INSTALIRAN PROGRAM' $s.RecordId
            Compare-AndReport $state 'appdata' (Get-AppDataFolders $s.Profile) 'NOVA APLIKACIJA (AppData)' $s.RecordId
            Compare-AndReport $state 'ikone' (Get-DesktopItems $s.Sid $s.Profile) 'NOVA IKONA/PRECAC' $s.RecordId
            $wallpaper = Get-Wallpaper $s.Sid
            if ($wallpaper -ne $state.pozadina) {
                Add-Event $s.RecordId 'PROMJENA POZADINE' $wallpaper
                $state.pozadina = $wallpaper
            }
            Write-JsonFile (Get-StateFile $s.Sid) $state
        } catch { Write-Log "Greška u provjeri ($($s.Account)): $($_.Exception.Message)" }
        try {
            $procs = Get-SessionProcesses $s
            foreach ($name in $procs.Keys) {
                if ($s.Seen.Add($name)) { Add-Event $s.RecordId 'POKRENUTA APLIKACIJA' "$name ($($procs[$name]))" }
            }
        } catch { Write-Log "Greška kod procesa ($($s.Account)): $($_.Exception.Message)" }
    }
}

$script:NetworkUp = $null

function Test-Network {
    $up = @()
    try { $up = @(Get-NetAdapter -Physical -ErrorAction Stop | Where-Object { $_.Status -eq 'Up' }) } catch { return }
    $isUp = $up.Count -gt 0
    if ($null -ne $script:NetworkUp -and $isUp -ne $script:NetworkUp) {
        $type = 'MREŽA UKLJUČENA'
        $details = ($up | ForEach-Object { $_.Name }) -join ', '
        if (-not $isUp) { $type = 'MREŽA ISKLJUČENA'; $details = 'Nijedan mrežni adapter nije spojen (Wi-Fi isključen, način rada u zrakoplovu ili kabel).' }
        foreach ($s in @($script:Sessions.Values)) { Add-Event $s.RecordId $type $details }
    }
    $script:NetworkUp = $isUp
}

# --------------------------------------------------------------------------
# Razgovor sa serverom u pozadini
# --------------------------------------------------------------------------

function Update-Classes {
    $r = Invoke-NadzorApi 'GET' '/razredi/' $null
    if ($r.Status -eq 200 -and $r.Data) {
        $list = @($r.Data.razredi)
        Write-JsonFile (Join-Path $Razmjena 'razredi.json') $list
    }
}

function Resolve-PendingLogins {
    # Prijave upisane dok server nije radio: provjeri ih sad.
    foreach ($rec in @($script:Records.Values)) {
        if ($rec.status -ne 'ceka') { continue }
        $t = $rec.upisano
        $body = [ordered]@{ razred = $t.razred; ime = $t.ime; prezime = $t.prezime; racunalo = $env:COMPUTERNAME
                            naknadno = $true; zavrsena = [bool]$rec.zavrsena }
        $r = Invoke-NadzorApi 'POST' '/prijava/' $body
        if (Test-Offline $r) { return }
        if ($r.Status -eq 200 -and $r.Data.token) {
            $rec.status = 'ok'; $rec.token = [string]$r.Data.token
            if ($rec.zavrsena) { $rec.odjavaPoslana = $true }
            Write-Log "Naknadno potvrđena prijava: $($t.ime) $($t.prezime) $($t.razred)"
        } else {
            $rec.status = 'neidentificiran'
            Write-Log "Naknadno NIJE potvrđena prijava ($($t.ime) $($t.prezime) $($t.razred)): $(Get-ErrorText $r $r.Status)"
        }
        Save-Records
    }
}

function Send-Heartbeats {
    foreach ($s in @($script:Sessions.Values)) {
        $rec = $script:Records[$s.RecordId]
        if ($rec.status -ne 'ok') { continue }
        $r = Invoke-NadzorApi 'POST' '/zivost/' ([ordered]@{ token = $rec.token })
        if (Test-Offline $r) { return }
    }
}

function Send-Logoffs {
    foreach ($rec in @($script:Records.Values)) {
        if (-not $rec.zavrsena -or $rec.status -ne 'ok' -or $rec.odjavaPoslana) { continue }
        $r = Invoke-NadzorApi 'POST' '/odjava/' ([ordered]@{ token = $rec.token })
        if (Test-Offline $r) { return }
        $rec.odjavaPoslana = $true
        Save-Records
    }
}

function Remove-OldRecords($StillQueued) {
    $changed = $false
    foreach ($rec in @($script:Records.Values)) {
        if (-not $rec.zavrsena -or $StillQueued.Contains($rec.id)) { continue }
        $done = ($rec.status -eq 'neidentificiran') -or ($rec.status -eq 'ok' -and $rec.odjavaPoslana) -or ($rec.status -eq 'neprijavljen')
        if ($done) { $script:Records.Remove($rec.id); $changed = $true }
    }
    if ($changed) { Save-Records }
}

# --------------------------------------------------------------------------
# Glavni tok
# --------------------------------------------------------------------------

foreach ($dir in @($Baza, $Razmjena, (Join-Path $Baza 'stanje'))) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

$created = $false
$mutexName = 'Global\RCKNadzorServis'
if ($Proba) { $mutexName = 'Local\RCKNadzorServisProba' }
$mutex = New-Object System.Threading.Mutex($true, $mutexName, [ref]$created)
if (-not $created) { Write-Log 'Servis već radi - izlazim.'; return }

try {
    $script:Config = Read-Config
    $script:Skip = Read-SkipList
    $script:Accounts = Read-Accounts
} catch {
    Write-Log "Ne mogu pokrenuti servis: $($_.Exception.Message)"
    throw
}
Load-Records
Write-Log "Servis pokrenut na $env:COMPUTERNAME, server $($script:Config.ServerUrl), nadzire se računa: $($script:Accounts.Count)$(if ($Proba) { ' (PROBA)' })"

$start = Get-Date
$nextSlow = Get-Date
$nextNetwork = Get-Date
$nextClasses = Get-Date

while ($true) {
    try { Update-Sessions } catch { Write-Log "Greška (sesije): $($_.Exception.Message)" }
    try { Receive-LoginRequests } catch { Write-Log "Greška (prijava): $($_.Exception.Message)" }
    try { Invoke-Deadlines } catch { Write-Log "Greška (rok prijave): $($_.Exception.Message)" }
    foreach ($s in @($script:Sessions.Values)) { try { Write-Status $s } catch { } }

    $now = Get-Date
    if ($now -ge $nextNetwork) {
        try { Test-Network } catch { Write-Log "Greška (mreža): $($_.Exception.Message)" }
        $nextNetwork = $now.AddSeconds(10)
    }
    if ($now -ge $nextClasses) {
        try { Update-Classes } catch { }
        $nextClasses = $now.AddMinutes(10)
    }
    if ($now -ge $nextSlow) {
        try { Invoke-Scans } catch { Write-Log "Greška (provjere): $($_.Exception.Message)" }
        try {
            Resolve-PendingLogins
            Send-Heartbeats
            Send-Logoffs
            $stillQueued = Send-Queue
            Remove-OldRecords $stillQueued
        } catch { Write-Log "Greška (slanje): $($_.Exception.Message)" }
        $nextSlow = (Get-Date).AddSeconds($script:Config.PollSeconds)
    }

    if ($Trajanje -gt 0 -and ((Get-Date) - $start).TotalSeconds -ge $Trajanje) { break }
    Start-Sleep -Seconds $FastSeconds
}

$mutex.ReleaseMutex()
