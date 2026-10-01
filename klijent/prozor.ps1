<#
RCK Nadzor - prozor za prijavu učenika.

Pokreće se jednom pri prijavi UČENIČKOG računa (zadatak "RCK Nadzor prozor") i
ostaje raditi cijelu prijavu. Preko cijelog zaslona traži razred, ime i prezime
kad servis (SYSTEM) javi da je potrebna prijava, a sakrije se kad je prijava
gotova. Ponovno se pojavi ako servis to zatraži - nakon buđenja računala iz
mirovanja. Sam ne zna ključ i ne razgovara sa serverom: zahtjev ostavlja u
C:\ProgramData\RCKNadzorRazmjena, a servis odgovori. Ako se učenik ne prijavi u
zadanom roku, servis ga odjavi iz Windowsa (i ako netko ugasi ovaj prozor).

Za probu (prozor se može zatvoriti tipkom Esc):
  .\prozor.ps1 -Proba -Razmjena C:\temp\razmjena
#>
[CmdletBinding()]
param(
    [string]$Razmjena = (Join-Path $env:ProgramData 'RCKNadzorRazmjena'),
    [switch]$Proba
)

$ErrorActionPreference = 'Stop'
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
$WinSid = (Get-Process -Id $PID).SessionId
$Me = "$env:USERDOMAIN\$env:USERNAME"
$StatusFile = Join-Path $Razmjena "status-$WinSid.json"
$AnswerFile = Join-Path $Razmjena "odgovor-$WinSid.json"
$ClassFile = Join-Path $Razmjena 'razredi.json'

# Samo jedan prozor po prijavi.
$created = $false
$mutex = New-Object System.Threading.Mutex($true, "Local\RCKNadzorProzor", [ref]$created)
if (-not $created) { return }

function Read-Json([string]$Path) {
    try {
        if (-not (Test-Path -LiteralPath $Path)) { return $null }
        $text = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
        if (-not $text.Trim()) { return $null }
        return ($text | ConvertFrom-Json)
    } catch { return $null }
}

function Get-Status {
    $s = Read-Json $StatusFile
    if ($s -and $s.korisnik -and ([string]$s.korisnik -ne $Me) -and -not $Proba) { return $null }  # zaostalo od drugog računa
    $s
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$font = New-Object System.Drawing.Font('Segoe UI', 12)
$form = New-Object System.Windows.Forms.Form
$form.Text = 'Prijava na računalo'
$form.FormBorderStyle = 'None'
$form.WindowState = 'Maximized'
$form.StartPosition = 'Manual'
$form.Bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$form.TopMost = $true
$form.ShowInTaskbar = $false
$form.KeyPreview = $true
$form.BackColor = [System.Drawing.Color]::FromArgb(33, 37, 41)
$form.Font = $font

# Mreža 3x3 drži bijelu ploču u sredini zaslona (i kad Windows poveća prikaz, npr. 125 %).
$layout = New-Object System.Windows.Forms.TableLayoutPanel
$layout.Dock = 'Fill'
$layout.ColumnCount = 3
$layout.RowCount = 3
foreach ($i in 0..2) {
    $type = if ($i -eq 1) { 'AutoSize' } else { 'Percent' }
    [void]$layout.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle($type, 50)))
    [void]$layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle($type, 50)))
}
$form.Controls.Add($layout)

$panel = New-Object System.Windows.Forms.Panel
$panel.Size = New-Object System.Drawing.Size(520, 430)
$panel.BackColor = [System.Drawing.Color]::White
$panel.Anchor = 'None'
$layout.Controls.Add($panel, 1, 1)

function Add-Label([string]$Text, [int]$Y, [int]$H, [float]$Size = 12, [string]$Color = 'Black', [bool]$Bold = $false, [int]$W = 460) {
    $l = New-Object System.Windows.Forms.Label
    $l.AutoSize = $false
    $l.Text = $Text
    $style = [System.Drawing.FontStyle]::Regular
    if ($Bold) { $style = [System.Drawing.FontStyle]::Bold }
    $l.Font = New-Object System.Drawing.Font('Segoe UI', $Size, $style)
    $l.ForeColor = [System.Drawing.Color]::FromName($Color)
    $l.SetBounds(30, $Y, $W, $H)
    $panel.Controls.Add($l)
    $l
}

[void](Add-Label 'Prijava na računalo' 22 36 18 'Black' $true)
[void](Add-Label 'Odaberi razred i upiši ime i prezime (kako su upisani u dnevniku).' 62 46 11 'DimGray')

$y = 118
[void](Add-Label 'Razred' ($y + 3) 26 12 'Black' $false 110)
$cmbClass = New-Object System.Windows.Forms.ComboBox
$cmbClass.SetBounds(150, $y, 340, 30)
$panel.Controls.Add($cmbClass)

$y += 44
[void](Add-Label 'Ime' ($y + 3) 26 12 'Black' $false 110)
$txtFirst = New-Object System.Windows.Forms.TextBox
$txtFirst.SetBounds(150, $y, 340, 30)
$panel.Controls.Add($txtFirst)

$y += 44
[void](Add-Label 'Prezime' ($y + 3) 26 12 'Black' $false 110)
$txtLast = New-Object System.Windows.Forms.TextBox
$txtLast.SetBounds(150, $y, 340, 30)
$panel.Controls.Add($txtLast)

$y += 48
$btn = New-Object System.Windows.Forms.Button
$btn.Text = 'Prijavi se'
$btn.SetBounds(150, $y, 340, 38)
$panel.Controls.Add($btn)
$form.AcceptButton = $btn

$y += 48
$lblMessage = Add-Label '' $y 50 11 'Firebrick'
$y += 52
$lblCountdown = Add-Label '' $y 26 11 'DarkOrange' $true
$y += 30
[void](Add-Label 'Na ovom računalu bilježe se instalirani i pokrenuti programi, nove ikone, promjene pozadine i isključivanje mreže.' $y 40 9 'DimGray')

$script:Shown = $false
$script:Exit = $false
$script:Request = $null
$script:RequestSent = $null
$script:HideAt = $null
$script:StartTime = Get-Date

function Set-Classes {
    $classes = @()
    $raw = Read-Json $ClassFile
    if ($raw) { $classes = @($raw | ForEach-Object { [string]$_ } | Where-Object { $_ }) }
    $current = [string]$cmbClass.Text
    $cmbClass.Items.Clear()
    if ($classes.Count -gt 0) {
        $cmbClass.DropDownStyle = 'DropDownList'
        foreach ($c in $classes) { [void]$cmbClass.Items.Add($c) }
        if ($current -and $cmbClass.Items.Contains($current)) { $cmbClass.SelectedItem = $current }
    } else {
        $cmbClass.DropDownStyle = 'DropDown'   # popis još nije stigao - razred se može upisati
        $cmbClass.Text = $current
    }
}

function Show-LoginForm {
    if ($script:Shown) { return }
    Set-Classes
    $txtFirst.Text = ''
    $txtLast.Text = ''
    $cmbClass.SelectedIndex = -1
    $lblMessage.Text = ''
    $lblCountdown.Text = ''
    $btn.Enabled = $true
    $script:Request = $null
    $script:HideAt = $null
    $script:Shown = $true
    $form.Show()
    $form.WindowState = 'Maximized'
    $form.TopMost = $true
    $form.Activate()
    [void]$cmbClass.Focus()
}

function Hide-LoginForm {
    if (-not $script:Shown) { return }
    $script:Shown = $false
    $script:Request = $null
    $script:HideAt = $null
    $form.Hide()
}

$form.Add_FormClosing({
    param($sender, $e)
    if (-not $script:Exit) { $e.Cancel = $true; $form.Hide() }
})
$form.Add_KeyDown({
    param($sender, $e)
    if ($Proba -and $e.KeyCode -eq 'Escape') { $script:Exit = $true; [System.Windows.Forms.Application]::Exit() }
    if ($e.Alt -and $e.KeyCode -eq 'F4') { $e.Handled = $true }
})
$form.Add_Resize({
    if ($script:Shown -and $form.WindowState -eq 'Minimized') { $form.WindowState = 'Maximized' }
})

$btn.Add_Click({
    $cls = $cmbClass.Text.Trim()
    $first = $txtFirst.Text.Trim()
    $last = $txtLast.Text.Trim()
    if (-not $cls -or -not $first -or -not $last) {
        $lblMessage.ForeColor = [System.Drawing.Color]::Firebrick
        $lblMessage.Text = 'Odaberi razred i upiši ime i prezime.'
        return
    }
    $script:Request = [DateTime]::UtcNow.Ticks.ToString()
    $script:RequestSent = Get-Date
    $body = ConvertTo-Json -InputObject ([ordered]@{ razred = $cls; ime = $first; prezime = $last }) -Compress
    try {
        [System.IO.File]::WriteAllText((Join-Path $Razmjena "prijava-$WinSid-$($script:Request).json"), $body, $Utf8NoBom)
    } catch {
        $lblMessage.ForeColor = [System.Drawing.Color]::Firebrick
        $lblMessage.Text = 'Prijava se ne može poslati. Javi nastavniku.'
        $script:Request = $null
        return
    }
    $btn.Enabled = $false
    $lblMessage.ForeColor = [System.Drawing.Color]::DimGray
    $lblMessage.Text = 'Provjeravam...'
})

function Update-Countdown($Status) {
    if ($Status -and $Status.rok) {
        $left = [DateTimeOffset]::Parse([string]$Status.rok) - [DateTimeOffset]::Now
        if ($left.TotalSeconds -gt 0) {
            $lblCountdown.Text = 'Ako se ne prijaviš, odjava s računala za {0}:{1:00}' -f [int][Math]::Floor($left.TotalMinutes), $left.Seconds
        } else {
            $lblCountdown.Text = 'Odjava s računala...'
        }
    } else {
        $lblCountdown.Text = ''
    }
}

function Handle-Answer {
    if (-not $script:Request) { return }
    $answer = Read-Json $AnswerFile
    if ($answer -and [string]$answer.zahtjev -eq $script:Request) {
        $script:Request = $null
        $btn.Enabled = $true
        if ($answer.stanje -eq 'ok') {
            $lblMessage.ForeColor = [System.Drawing.Color]::DarkGreen
            $lblMessage.Text = [string]$answer.poruka
            $lblCountdown.Text = ''
            $script:HideAt = (Get-Date).AddSeconds(2)   # sakrij nakon kratke potvrde
        } else {
            $lblMessage.ForeColor = [System.Drawing.Color]::Firebrick
            $lblMessage.Text = [string]$answer.poruka
        }
    } elseif (((Get-Date) - $script:RequestSent).TotalSeconds -gt 40) {
        $script:Request = $null
        $btn.Enabled = $true
        $lblMessage.ForeColor = [System.Drawing.Color]::Firebrick
        $lblMessage.Text = 'Nema odgovora. Pokušaj ponovno.'
    }
}

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 1000
$timer.Add_Tick({
  try {
    $st = Get-Status
    $identified = $st -and ($st.stanje -eq 'ok' -or $st.stanje -eq 'ceka')
    if ($st) {
        $needLogin = ($st.stanje -eq 'neprijavljen')
    } else {
        # Servis još/ne javlja: nakon kratke milosti ipak zatraži prijavu
        # (da se računalo ne koristi bez nadzora).
        $needLogin = (((Get-Date) - $script:StartTime).TotalSeconds -gt 60)
    }

    if ($script:HideAt -and (Get-Date) -ge $script:HideAt) { Hide-LoginForm; return }
    if ($identified -and -not $script:Request -and -not $script:HideAt) { Hide-LoginForm; return }
    if ($needLogin) { Show-LoginForm }

    if ($script:Shown) {
        if ($cmbClass.Items.Count -eq 0) { Set-Classes }   # popis je u međuvremenu stigao
        if (-not $form.ContainsFocus) { $form.TopMost = $true; $form.Activate() }
        Handle-Answer
        if (-not $script:HideAt) { Update-Countdown $st }
    }
  } catch { }
})
$timer.Start()

[System.Windows.Forms.Application]::Run()
$timer.Stop()
$mutex.ReleaseMutex()
