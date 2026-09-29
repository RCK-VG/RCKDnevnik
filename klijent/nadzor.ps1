<#
RCK Nadzor - klijent za učenička računala (Windows PowerShell 5.1).

Pokreće se pri svakoj prijavi na računalo (zadatak "RCK Nadzor", instalira ga
instaliraj.bat). Učenik odabere razred i upiše ime i prezime; skripta zatim
periodički javlja serveru (aplikacija "nadzor" u Mali e-Dnevnik):
  - INSTALIRAN PROGRAM         (registry Uninstall ključevi)
  - NOVA APLIKACIJA (AppData)  (nove mape u AppData\Roaming, Local, LocalLow)
  - NOVA IKONA/PRECAC          (radna površina korisnika i zajednička)
  - PROMJENA POZADINE
  - POKRENUTA APLIKACIJA       (jednom po aplikaciji u sesiji, uz popis preskočenih)
"Novo" = razlika u odnosu na stanje zapamćeno na ovom korisničkom profilu.
Ako server nije dostupan, zapisi čekaju u lokalnom redu i šalju se kasnije.

Postavke: config.json (adresa servera, API ključ) i preskoci_procese.txt,
u istoj mapi kao skripta. Za probu bez prozora:
  .\nadzor.ps1 -Razred 1.C -Ime Ana -Prezime Anić -JednomProvjeri
#>
[CmdletBinding()]
param(
    [string]$KonfigPutanja,
    [string]$PreskociPutanja,
    [string]$StanjePutanja = (Join-Path $env:LOCALAPPDATA 'RCKNadzor'),
    [string]$Razred,
    [string]$Ime,
    [string]$Prezime,
    [switch]$JednomProvjeri
)

$ErrorActionPreference = 'Stop'
# .NET Framework na starijim Windowsima inače ne nudi TLS 1.2 (Caddy ga traži).
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
if (-not $KonfigPutanja) { $KonfigPutanja = Join-Path $PSScriptRoot 'config.json' }
if (-not $PreskociPutanja) { $PreskociPutanja = Join-Path $PSScriptRoot 'preskoci_procese.txt' }

$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
$ApiPrefix = '/api/nadzor/v1'
$MaxQueueLines = 5000
$MaxPending = 1000
$SendBatch = 100

# --------------------------------------------------------------------------
# Pomoćne funkcije
# --------------------------------------------------------------------------

function Write-Log([string]$Message) {
    try {
        $file = Join-Path $StanjePutanja 'nadzor.log'
        if ((Test-Path -LiteralPath $file) -and (Get-Item -LiteralPath $file).Length -gt 1MB) {
            Move-Item -LiteralPath $file -Destination "$file.1" -Force
        }
        $line = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + '  ' + $Message + "`r`n"
        [System.IO.File]::AppendAllText($file, $line, $Utf8NoBom)
    } catch { }
}

function Get-ClientTime {
    (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss.fffzzz', [Globalization.CultureInfo]::InvariantCulture)
}

function Read-Config {
    if (-not (Test-Path -LiteralPath $KonfigPutanja)) { throw "Nema datoteke s postavkama: $KonfigPutanja" }
    $cfg = [System.IO.File]::ReadAllText($KonfigPutanja, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    if (-not $cfg.serverUrl -or -not $cfg.apiKey) { throw 'config.json mora imati serverUrl i apiKey.' }
    $poll = 60
    if ($cfg.pollSeconds) { $poll = [Math]::Max(10, [int]$cfg.pollSeconds) }
    $remind = 5
    if ($cfg.reminderMinutes) { $remind = [Math]::Max(1, [int]$cfg.reminderMinutes) }
    $skipWin = $true
    if ($null -ne $cfg.skipWindowsDir) { $skipWin = [bool]$cfg.skipWindowsDir }
    [pscustomobject]@{
        ServerUrl       = ([string]$cfg.serverUrl).TrimEnd('/')
        ApiKey          = [string]$cfg.apiKey
        PollSeconds     = $poll
        ReminderMinutes = $remind
        SkipWindowsDir  = $skipWin
    }
}

function Read-SkipList {
    $set = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    if (Test-Path -LiteralPath $PreskociPutanja) {
        foreach ($line in [System.IO.File]::ReadAllLines($PreskociPutanja, [System.Text.Encoding]::UTF8)) {
            $name = ($line -replace '#.*$', '').Trim()
            if ($name) { [void]$set.Add(($name -replace '\.exe$', '')) }
        }
    }
    , $set
}

# HTTP poziv prema serveru. Vraća Status (0 = server nedostupan), Data i Error.
# Tijelo se šalje i odgovor čita izričito kao UTF-8 (PowerShell 5.1 inače
# kvari č, ć, š, ž, đ).
function Invoke-NadzorApi([string]$Method, [string]$Path, $Body) {
    try {
        $req = [System.Net.HttpWebRequest]::Create($script:Config.ServerUrl + $ApiPrefix + $Path)
        $req.Method = $Method
        $req.Timeout = 15000
        $req.ReadWriteTimeout = 15000
        $req.Accept = 'application/json'
        $req.UserAgent = 'RCKNadzor/1.0'
        $req.Headers.Add('X-API-Key', $script:Config.ApiKey)
        if ($null -ne $Body) {
            $bytes = [System.Text.Encoding]::UTF8.GetBytes((ConvertTo-Json -InputObject $Body -Depth 6 -Compress))
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

function Get-ErrorText($Result, [string]$Fallback) {
    if ($Result.Data -and $Result.Data.greska) { return [string]$Result.Data.greska }
    return $Fallback
}

# --------------------------------------------------------------------------
# Red čekanja (zapisi se nikad ne gube zbog pada mreže)
# --------------------------------------------------------------------------

$script:Token = $null
$script:Pending = New-Object System.Collections.ArrayList   # zapisi prije uspješne prijave

function Get-QueueFile { Join-Path $StanjePutanja 'red.jsonl' }

function Add-Event([string]$Type, [string]$Details) {
    $event = [ordered]@{ vrsta = $Type; detalji = $Details; vrijeme = (Get-ClientTime) }
    if ($script:Token) {
        Add-ToQueue $script:Token $event
    } else {
        # Još nema prijave: čuva se u memoriji i pridruži prijavi kad uspije.
        [void]$script:Pending.Add($event)
        if ($script:Pending.Count -gt $MaxPending) { $script:Pending.RemoveAt(0) }
    }
    Write-Log "$Type  $Details"
}

function Add-ToQueue([string]$Token, $Event) {
    $entry = [ordered]@{ token = $Token; racunalo = $env:COMPUTERNAME; zapis = $Event }
    $line = ConvertTo-Json -InputObject $entry -Depth 5 -Compress
    [System.IO.File]::AppendAllText((Get-QueueFile), $line + "`n", $Utf8NoBom)
}

function Send-Queue {
    $file = Get-QueueFile
    if (-not (Test-Path -LiteralPath $file)) { return }
    $lines = @([System.IO.File]::ReadAllLines($file, [System.Text.Encoding]::UTF8) | Where-Object { $_.Trim() })
    if ($lines.Count -eq 0) { Remove-Item -LiteralPath $file -Force; return }
    if ($lines.Count -gt $MaxQueueLines) {
        Write-Log "Red čekanja prevelik ($($lines.Count)), odbacujem najstarije."
        $lines = $lines[($lines.Count - $MaxQueueLines)..($lines.Count - 1)]
    }

    $entries = New-Object System.Collections.ArrayList
    foreach ($l in $lines) { try { [void]$entries.Add(($l | ConvertFrom-Json)) } catch { } }

    $keep = New-Object System.Collections.ArrayList
    $serverDown = $false
    $groups = $entries | Group-Object -Property token
    foreach ($group in $groups) {
        $items = @($group.Group)
        for ($i = 0; $i -lt $items.Count; $i += $SendBatch) {
            $chunk = @($items[$i..([Math]::Min($i + $SendBatch, $items.Count) - 1)])
            if ($serverDown) { foreach ($c in $chunk) { [void]$keep.Add($c) }; continue }
            $events = New-Object System.Collections.ArrayList
            foreach ($c in $chunk) { [void]$events.Add($c.zapis) }
            $body = [ordered]@{ token = $group.Name; racunalo = $chunk[0].racunalo; zapisi = $events.ToArray() }
            $r = Invoke-NadzorApi 'POST' '/zapisi/' $body
            if ($r.Status -eq 201) {
                continue
            } elseif ($r.Status -eq 0 -or $r.Status -ge 500 -or $r.Status -eq 429) {
                $serverDown = $true
                foreach ($c in $chunk) { [void]$keep.Add($c) }
            } else {
                # 401 (token istekao), 400, 403... - ponavljanje ne bi pomoglo.
                Write-Log "Odbačeno $($chunk.Count) zapisa: HTTP $($r.Status) $(Get-ErrorText $r '')"
                if ($r.Status -eq 401 -and $group.Name -eq $script:Token) { $script:Token = $null; $script:NeedLogin = $true }
            }
        }
    }

    if ($keep.Count -eq 0) {
        Remove-Item -LiteralPath $file -Force
    } else {
        $out = foreach ($k in $keep) { ConvertTo-Json -InputObject $k -Depth 5 -Compress }
        [System.IO.File]::WriteAllText($file, (($out -join "`n") + "`n"), $Utf8NoBom)
    }
}

# --------------------------------------------------------------------------
# Prijava učenika
# --------------------------------------------------------------------------

$script:NeedLogin = $true
$script:OfflineLogin = $null   # podaci upisani dok server nije bio dostupan
$script:LastLoginError = ''
$script:NextReminder = [DateTime]::MinValue

function Get-Classes {
    $cache = Join-Path $StanjePutanja 'razredi.json'
    $r = Invoke-NadzorApi 'GET' '/razredi/' $null
    if ($r.Status -eq 200 -and $r.Data) {
        $list = @($r.Data.razredi)
        [System.IO.File]::WriteAllText($cache, (ConvertTo-Json -InputObject $list -Compress), $Utf8NoBom)
        return $list
    }
    if (Test-Path -LiteralPath $cache) {
        try {
            # Prvo u varijablu: PowerShell 5.1 inače cijelo JSON polje vrati kao jedan element.
            $parsed = [System.IO.File]::ReadAllText($cache, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
            return @($parsed)
        } catch { }
    }
    return @()
}

# Vraća: ok | notfound | offline | error
function Invoke-Login([string]$ClassName, [string]$FirstName, [string]$LastName) {
    $body = [ordered]@{ razred = $ClassName; ime = $FirstName; prezime = $LastName; racunalo = $env:COMPUTERNAME }
    $r = Invoke-NadzorApi 'POST' '/prijava/' $body
    if ($r.Status -eq 200 -and $r.Data.token) {
        $script:Token = [string]$r.Data.token
        $script:NeedLogin = $false
        $script:OfflineLogin = $null
        foreach ($e in $script:Pending) { Add-ToQueue $script:Token $e }
        $script:Pending.Clear()
        Write-Log "Prijava: $($r.Data.ucenik), $($r.Data.razred)"
        return 'ok'
    }
    if ($r.Status -eq 0 -or $r.Status -ge 500) {
        $script:LastLoginError = 'Server trenutno nije dostupan.'
        return 'offline'
    }
    $script:LastLoginError = Get-ErrorText $r "Greška pri prijavi (HTTP $($r.Status))."
    if ($r.Status -eq 404) { return 'notfound' }
    return 'error'
}

function Show-LoginWindow {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    [System.Windows.Forms.Application]::EnableVisualStyles()

    $classes = Get-Classes
    $font = New-Object System.Drawing.Font('Segoe UI', 10)

    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'Prijava na računalo'
    $form.StartPosition = 'CenterScreen'
    $form.FormBorderStyle = 'FixedDialog'
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.TopMost = $true
    $form.Font = $font
    $form.ClientSize = New-Object System.Drawing.Size(380, 320)

    $y = 15
    $intro = New-Object System.Windows.Forms.Label
    $intro.AutoSize = $false
    $intro.Text = 'Odaberi razred i upiši ime i prezime (točno kako su u dnevniku).'
    $intro.SetBounds(15, $y, 350, 40)
    $form.Controls.Add($intro)
    $y += 45

    $lblClass = New-Object System.Windows.Forms.Label
    $lblClass.Text = 'Razred'
    $lblClass.SetBounds(15, $y, 100, 22)
    $form.Controls.Add($lblClass)
    $cmbClass = New-Object System.Windows.Forms.ComboBox
    $cmbClass.SetBounds(120, $y, 245, 26)
    if ($classes.Count -gt 0) {
        $cmbClass.DropDownStyle = 'DropDownList'
        foreach ($c in $classes) { [void]$cmbClass.Items.Add([string]$c) }
    } else {
        $cmbClass.DropDownStyle = 'DropDown'   # nema popisa - razred se može upisati
    }
    $form.Controls.Add($cmbClass)
    $y += 36

    $lblFirst = New-Object System.Windows.Forms.Label
    $lblFirst.Text = 'Ime'
    $lblFirst.SetBounds(15, $y, 100, 22)
    $form.Controls.Add($lblFirst)
    $txtFirst = New-Object System.Windows.Forms.TextBox
    $txtFirst.SetBounds(120, $y, 245, 26)
    $form.Controls.Add($txtFirst)
    $y += 36

    $lblLast = New-Object System.Windows.Forms.Label
    $lblLast.Text = 'Prezime'
    $lblLast.SetBounds(15, $y, 100, 22)
    $form.Controls.Add($lblLast)
    $txtLast = New-Object System.Windows.Forms.TextBox
    $txtLast.SetBounds(120, $y, 245, 26)
    $form.Controls.Add($txtLast)
    $y += 40

    $btn = New-Object System.Windows.Forms.Button
    $btn.Text = 'Prijavi se'
    $btn.SetBounds(120, $y, 245, 32)
    $form.Controls.Add($btn)
    $form.AcceptButton = $btn
    $y += 40

    $status = New-Object System.Windows.Forms.Label
    $status.AutoSize = $false
    $status.ForeColor = [System.Drawing.Color]::Firebrick
    $status.SetBounds(15, $y, 350, 40)
    $status.Text = $script:LastLoginError
    $form.Controls.Add($status)
    $y += 42

    $notice = New-Object System.Windows.Forms.Label
    $notice.AutoSize = $false
    $notice.Text = 'Na ovom računalu bilježe se instalirani i pokrenuti programi, nove ikone i promjene pozadine.'
    $notice.ForeColor = [System.Drawing.Color]::DimGray
    $notice.Font = New-Object System.Drawing.Font('Segoe UI', 8)
    $notice.SetBounds(15, $y, 350, 32)
    $form.Controls.Add($notice)

    if ($script:OfflineLogin) {
        $cmbClass.Text = $script:OfflineLogin.Razred
        $txtFirst.Text = $script:OfflineLogin.Ime
        $txtLast.Text = $script:OfflineLogin.Prezime
    }

    $btn.Add_Click({
        $cls = $cmbClass.Text.Trim()
        $first = $txtFirst.Text.Trim()
        $last = $txtLast.Text.Trim()
        if (-not $cls -or -not $first -or -not $last) {
            $status.Text = 'Odaberi razred i upiši ime i prezime.'
            return
        }
        $btn.Enabled = $false
        $status.Text = 'Prijava...'
        $form.Refresh()
        $result = Invoke-Login $cls $first $last
        $btn.Enabled = $true
        if ($result -eq 'ok') {
            $form.Close()
        } elseif ($result -eq 'offline') {
            $script:OfflineLogin = [pscustomobject]@{ Razred = $cls; Ime = $first; Prezime = $last }
            [System.Windows.Forms.MessageBox]::Show(
                'Server trenutno nije dostupan. Prijava će se poslati automatski čim proradi.',
                'Prijava na računalo') | Out-Null
            $form.Close()
        } else {
            $status.Text = $script:LastLoginError
        }
    })

    # Provjere nastavljaju raditi i dok je prozor otvoren.
    $timer = New-Object System.Windows.Forms.Timer
    $timer.Interval = $script:Config.PollSeconds * 1000
    $timer.Add_Tick({ Invoke-Checks })
    $timer.Start()

    [void]$form.ShowDialog()
    $timer.Stop()
    $timer.Dispose()
    $form.Dispose()
    $script:NextReminder = (Get-Date).AddMinutes($script:Config.ReminderMinutes)
}

function Invoke-OfflineLoginRetry {
    # Ponovni pokušaj prijave upisane dok server nije radio (bez prozora).
    if (-not ($script:NeedLogin -and $script:OfflineLogin)) { return }
    $o = $script:OfflineLogin
    $result = Invoke-Login $o.Razred $o.Ime $o.Prezime
    if ($result -eq 'notfound' -or $result -eq 'error') {
        $script:OfflineLogin = $null          # npr. ime nije pronađeno - pitaj ponovno
        $script:NextReminder = [DateTime]::MinValue
    }
}

# --------------------------------------------------------------------------
# Provjere
# --------------------------------------------------------------------------

function Get-InstalledPrograms {
    $result = @{}
    $paths = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
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

function Get-AppDataFolders {
    $result = @{}
    $roots = [ordered]@{
        'Roaming'  = $env:APPDATA
        'Local'    = $env:LOCALAPPDATA
        'LocalLow' = (Join-Path $env:USERPROFILE 'AppData\LocalLow')
    }
    foreach ($label in $roots.Keys) {
        $root = $roots[$label]
        if (-not $root -or -not (Test-Path -LiteralPath $root)) { continue }
        foreach ($dir in @(Get-ChildItem -LiteralPath $root -Directory -Force -ErrorAction SilentlyContinue)) {
            if ($dir.Name -in @('Temp', 'RCKNadzor')) { continue }
            $key = "$label\$($dir.Name)"
            $result[$key] = $key
        }
    }
    $result
}

function Get-DesktopItems {
    $result = @{}
    $shell = $null
    $desktops = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('CommonDesktopDirectory'))
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

function Get-Wallpaper {
    try { [string](Get-ItemProperty -Path 'HKCU:\Control Panel\Desktop' -Name WallPaper).WallPaper } catch { '' }
}

function Get-UserProcesses {
    $result = @{}
    $session = (Get-Process -Id $PID).SessionId
    foreach ($p in @(Get-Process -ErrorAction SilentlyContinue)) {
        if ($p.SessionId -ne $session) { continue }
        if ($script:Skip.Contains($p.ProcessName)) { continue }
        $path = $null
        try { $path = $p.Path } catch { }
        if (-not $path) { continue }   # bez putanje = sistemski/tuđi proces
        if ($script:Config.SkipWindowsDir -and $path.StartsWith($env:windir, [StringComparison]::OrdinalIgnoreCase)) { continue }
        if (-not $result.ContainsKey($p.ProcessName)) { $result[$p.ProcessName] = $path }
    }
    $result
}

function Read-State {
    $file = Join-Path $StanjePutanja 'stanje.json'
    if (-not (Test-Path -LiteralPath $file)) { return $null }
    try {
        $raw = [System.IO.File]::ReadAllText($file, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
        $state = @{ programi = @{}; appdata = @{}; ikone = @{}; pozadina = [string]$raw.pozadina }
        foreach ($section in @('programi', 'appdata', 'ikone')) {
            if ($raw.$section) {
                foreach ($prop in $raw.$section.PSObject.Properties) { $state[$section][$prop.Name] = [string]$prop.Value }
            }
        }
        return $state
    } catch {
        Write-Log "stanje.json oštećen, radim novo početno stanje: $($_.Exception.Message)"
        return $null
    }
}

function Save-State {
    $file = Join-Path $StanjePutanja 'stanje.json'
    [System.IO.File]::WriteAllText($file, (ConvertTo-Json -InputObject $script:State -Depth 4 -Compress), $Utf8NoBom)
}

function Compare-AndReport([string]$Section, [hashtable]$Current, [string]$EventType) {
    $known = $script:State[$Section]
    foreach ($key in $Current.Keys) {
        if (-not $known.ContainsKey($key)) { Add-Event $EventType $Current[$key] }
    }
    $script:State[$Section] = $Current
}

function Invoke-Checks {
    try {
        Compare-AndReport 'programi' (Get-InstalledPrograms) 'INSTALIRAN PROGRAM'
        Compare-AndReport 'appdata' (Get-AppDataFolders) 'NOVA APLIKACIJA (AppData)'
        Compare-AndReport 'ikone' (Get-DesktopItems) 'NOVA IKONA/PRECAC'
        $wallpaper = Get-Wallpaper
        if ($wallpaper -ne $script:State.pozadina) {
            Add-Event 'PROMJENA POZADINE' $wallpaper
            $script:State.pozadina = $wallpaper
        }
        Save-State
    } catch { Write-Log "Greška u provjeri: $($_.Exception.Message)" }

    try {
        $procs = Get-UserProcesses
        foreach ($name in $procs.Keys) {
            if ($script:SeenProcesses.Add($name)) { Add-Event 'POKRENUTA APLIKACIJA' "$name ($($procs[$name]))" }
        }
    } catch { Write-Log "Greška kod procesa: $($_.Exception.Message)" }

    try {
        Invoke-OfflineLoginRetry
        Send-Queue
    } catch { Write-Log "Greška pri slanju: $($_.Exception.Message)" }
}

# --------------------------------------------------------------------------
# Glavni tok
# --------------------------------------------------------------------------

New-Item -ItemType Directory -Path $StanjePutanja -Force | Out-Null

$created = $false
$mutex = New-Object System.Threading.Mutex($true, 'Local\RCKNadzor', [ref]$created)
if (-not $created) { Write-Log 'Već radi u ovoj sesiji - izlazim.'; return }

try {
    $script:Config = Read-Config
    $script:Skip = Read-SkipList
} catch {
    Write-Log "Ne mogu pokrenuti: $($_.Exception.Message)"
    throw
}
Write-Log "Pokrenuto na $env:COMPUTERNAME ($env:USERNAME), server $($script:Config.ServerUrl)"

# Početno stanje: pri prvom pokretanju na profilu ništa se ne javlja, samo
# se zapamti što već postoji.
$script:State = Read-State
if ($null -eq $script:State) {
    $script:State = @{
        programi = Get-InstalledPrograms
        appdata  = Get-AppDataFolders
        ikone    = Get-DesktopItems
        pozadina = Get-Wallpaper
    }
    Save-State
    Write-Log 'Zapamćeno početno stanje profila.'
}

# Procesi koji su već radili pri pokretanju (npr. autostart) se ne javljaju.
$script:SeenProcesses = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
foreach ($name in (Get-UserProcesses).Keys) { [void]$script:SeenProcesses.Add($name) }

if ($Razred -and $Ime -and $Prezime) {
    $result = Invoke-Login $Razred $Ime $Prezime
    if ($result -eq 'offline') {
        $script:OfflineLogin = [pscustomobject]@{ Razred = $Razred; Ime = $Ime; Prezime = $Prezime }
    }
    Write-Log "Prijava iz parametara: $result $script:LastLoginError"
} else {
    Show-LoginWindow
}

while ($true) {
    Invoke-Checks
    if ($JednomProvjeri) { break }
    # Učenik je zatvorio prozor bez prijave: ponovno ga pokaži nakon nekoliko minuta.
    if ($script:NeedLogin -and -not $script:OfflineLogin -and (Get-Date) -ge $script:NextReminder) {
        Show-LoginWindow
    }
    Start-Sleep -Seconds $script:Config.PollSeconds
}

$mutex.ReleaseMutex()
