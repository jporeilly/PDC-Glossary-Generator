# ---------------------------------------------------------------------------
#  ui.ps1 - console UI, checkpoints and remote plumbing for pdc-remote.ps1
#
#  Dot-sourced by pdc-remote.ps1. Windows PowerShell 5.1 compatible:
#  no ternary, no '&&', no '??', no null-conditional. ASCII only - em-dashes
#  and box-drawing characters break 5.1 parsing and Windows consoles.
#
#  Native tools used: ssh.exe, scp.exe, ssh-keygen.exe, curl.exe. All ship
#  with Windows 10/11. Nothing here needs WSL, Git Bash or make.
# ---------------------------------------------------------------------------

$script:LogFile  = $null
$script:StateDir = $null
$script:TxtDir   = $null
$script:T0       = $null

function Initialize-Ui {
    param([string] $Root)
    $script:StateDir = Join-Path $Root '.state'
    $script:LogDir   = Join-Path $Root 'logs'
    $script:TxtDir   = Join-Path $Root 'lib\txt'
    if (-not (Test-Path $script:StateDir)) { New-Item -ItemType Directory -Path $script:StateDir -Force | Out-Null }
}

# ------------------------------- output ------------------------------------
function Write-Line {
    param([string] $Text = '', [string] $Color = $null)
    if ($Color) { Write-Host $Text -ForegroundColor $Color } else { Write-Host $Text }
    if ($script:LogFile) { Add-Content -Path $script:LogFile -Value $Text -Encoding utf8 }
}

function Write-Rule { Write-Line ('  ' + ('-' * 72)) 'DarkGray' }

function Write-Banner {
    param([string] $Text)
    Write-Line ''
    Write-Line ('=' * 77) 'Cyan'
    Write-Line ("  " + $Text) 'Cyan'
    Write-Line ('=' * 77) 'Cyan'
    Write-Line ''
}

function Write-Step {
    param([int] $N, [int] $Total, [string] $Label)
    Write-Line ''
    Write-Line ("[ STEP $N/$Total ] $Label") 'Cyan'
    Write-Rule
}

function Write-Ok    { param([string] $m) Write-Line ("  [ OK ]   " + $m) 'Green'  }
function Write-Bad   { param([string] $m) Write-Line ("  [FAIL]   " + $m) 'Red'    }
function Write-Warn  { param([string] $m) Write-Line ("  [WARN]   " + $m) 'Yellow' }
function Write-Info  { param([string] $m) Write-Line ("  [info]   " + $m) 'Blue'   }
function Write-Skip  { param([string] $m) Write-Line ("  [skip]   " + $m) 'DarkGray' }
function Write-Note  { param([string] $m) Write-Line ("  [note]   " + $m) 'Magenta' }
function Write-Hint  { param([string] $m) Write-Line ("           -> " + $m) 'DarkGray' }
function Write-Plain { param([string] $m) Write-Line ("           " + $m) }

function Write-Kv {
    param([string] $Key, [string] $Value)
    Write-Line ("  {0,-22} {1}" -f $Key, $Value)
}

# ------------------------------- logging -----------------------------------
function Start-Log {
    param([string] $Tag)
    if (-not (Test-Path $script:LogDir)) { New-Item -ItemType Directory -Path $script:LogDir -Force | Out-Null }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $script:LogFile = Join-Path $script:LogDir "$stamp-$Tag.log"
    Set-Content -Path $script:LogFile -Encoding utf8 -Value ("# pdc-remote $Tag - " + (Get-Date -Format 's') + " - host $env:COMPUTERNAME")
}

function Write-LogWhere {
    if ($script:LogFile) { Write-Line ("   full log: " + $script:LogFile) 'DarkGray' }
}

# ------------------------------- timing ------------------------------------
function Start-Timer { $script:T0 = Get-Date }
function Get-Elapsed {
    if (-not $script:T0) { return '0m00s' }
    $s = [int]((Get-Date) - $script:T0).TotalSeconds
    return ('{0}m{1:d2}s' -f [int]($s / 60), ($s % 60))
}
function Write-Lap { Write-Line ("  [time]   +" + (Get-Elapsed)) 'DarkGray' }

# --------------------------- prose rendering -------------------------------
# Long guidance lives in lib\txt\*.txt so the text reaches the console exactly
# as written. Invoke-Render substitutes @KEY@ placeholders.
function Invoke-Render {
    param([string] $Name, [hashtable] $Vars = @{})
    $f = Join-Path $script:TxtDir "$Name.txt"
    if (-not (Test-Path $f)) { Write-Warn "missing text file: $f"; return }
    $s = Get-Content -Path $f -Raw -Encoding utf8
    foreach ($k in $Vars.Keys) { $s = $s.Replace("@$k@", [string]$Vars[$k]) }
    foreach ($line in ($s -split "`r?`n")) { Write-Line $line }
}

# --------------------------- checkpoint store ------------------------------
# One stamp file per checkpoint: .state\ck.<name> holding "<status> <epoch> <detail>".
# Same on-disk format the earlier Makefile used, so existing state carries over.
$script:CkNames = @('cfg','ssh','priv','dir','up','run','os','app','http','kc')
$script:CkDesc  = @{
    cfg  = 'Configuration loaded (pdc-remote.env)'
    ssh  = 'Passwordless SSH to the VM'
    priv = 'Remote privileges (docker + sudo)'
    dir  = 'PDC deployment directory located'
    up   = 'pdc-reset.sh uploaded to the VM'
    run  = 'Reset script completed on the VM'
    os   = 'OpenSearch security index initialised'
    app  = 'App tier Up (fe + public-api)'
    http = 'HTTPS front door answers (not 404)'
    kc   = 'Keycloak realm reachable'
}

function Get-CkPath { param([string] $Name) return (Join-Path $script:StateDir "ck.$Name") }

function Set-Ck {
    param([string] $Name, [string] $Status, [string] $Detail = '')
    # ToUnixTimeSeconds returns a long directly - Get-Date -UFormat %s yields a
    # culture-dependent decimal string that fails to parse under some locales.
    $epoch = [datetimeoffset]::UtcNow.ToUnixTimeSeconds()
    Set-Content -Path (Get-CkPath $Name) -Encoding ascii -Value "$Status $epoch $Detail"
}
function Set-CkPass { param([string] $Name, [string] $Detail = '') Set-Ck $Name 'pass' $Detail; Write-Ok "checkpoint '$Name' passed" }
function Set-CkFail {
    param([string] $Name, [string] $Detail = '')
    Set-Ck $Name 'fail' $Detail
    if ($Detail) { Write-Bad "checkpoint '$Name' FAILED - $Detail" } else { Write-Bad "checkpoint '$Name' FAILED" }
}
function Get-CkStatus {
    param([string] $Name)
    $p = Get-CkPath $Name
    if (-not (Test-Path $p)) { return 'none' }
    return ((Get-Content $p -First 1) -split ' ')[0]
}
function Get-CkWhen {
    param([string] $Name)
    $p = Get-CkPath $Name
    if (-not (Test-Path $p)) { return '' }
    $parts = (Get-Content $p -First 1) -split ' '
    if ($parts.Count -lt 2) { return '' }
    $epoch = 0
    if (-not [int]::TryParse($parts[1], [ref]$epoch)) { return '' }
    return ([datetimeoffset]::FromUnixTimeSeconds($epoch).LocalDateTime.ToString('yyyy-MM-dd HH:mm'))
}
function Clear-Ck {
    Get-ChildItem -Path $script:StateDir -Filter 'ck.*' -ErrorAction SilentlyContinue | Remove-Item -Force
}
function Show-Ck {
    Write-Line ''
    Write-Line '  CHECKPOINTS'
    Write-Rule
    foreach ($n in $script:CkNames) {
        $st = Get-CkStatus $n
        switch ($st) {
            'pass' { $mark = '[ OK ]'; $col = 'Green'    }
            'fail' { $mark = '[FAIL]'; $col = 'Red'      }
            'warn' { $mark = '[WARN]'; $col = 'Yellow'   }
            default{ $mark = '[ -- ]'; $col = 'DarkGray' }
        }
        Write-Line ("  {0} {1,-6} {2,-42} {3}" -f $mark, $n, $script:CkDesc[$n], (Get-CkWhen $n)) $col
    }
    Write-Rule
}
function Get-FirstIncomplete {
    foreach ($n in $script:CkNames) { if ((Get-CkStatus $n) -ne 'pass') { return $n } }
    return ''
}

# ------------------------------- prompts -----------------------------------
function Read-Answer {
    param([string] $Prompt, [string] $Default = '')
    if ($Default) { $p = "  $Prompt [$Default]" } else { $p = "  $Prompt" }
    $a = Read-Host -Prompt $p
    if ([string]::IsNullOrWhiteSpace($a)) { return $Default }
    return $a
}

# Reads with echo off and returns plain text. Used only at the moment a
# credential is needed; never written to disk, never placed in history.
function Read-Secret {
    param([string] $Prompt)
    $sec = Read-Host -Prompt "  $Prompt" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

function Confirm-Typed {
    param([string] $Word)
    Write-Line ''
    $got = Read-Host -Prompt "  Type '$Word' to continue (anything else aborts)"
    if ($got -ne $Word) {
        Write-Line ''
        Write-Warn 'Aborted - nothing was changed.'
        return $false
    }
    return $true
}

# ------------------------------- network -----------------------------------
function Test-TcpPort {
    param([string] $HostName, [int] $Port, [int] $TimeoutMs = 3000)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch { return $false }
    finally { $client.Close() }
}

# curl.exe with --resolve, so PDC's vhost works without a hosts entry and
# without tripping PowerShell 5.1's certificate handling on the self-signed cert.
function Invoke-PdcHttp {
    param([string] $Url, [int] $TimeoutSec = 15)
    $code = & curl.exe -sk -o NUL -w '%{http_code}' --max-time $TimeoutSec `
        --resolve "$($script:Cfg.PDC_FQDN):443:$($script:Cfg.VM_HOST)" $Url
    return [string]$code
}

# ------------------------------- ssh / scp ---------------------------------
function Get-SshArgs {
    return @(
        '-o','BatchMode=yes'
        '-o','StrictHostKeyChecking=accept-new'
        '-o','ConnectTimeout=8'
        '-o','ServerAliveInterval=15'
        '-o','ServerAliveCountMax=8'
        '-p',[string]$script:Cfg.SSH_PORT
        '-i',$script:Cfg.SSH_KEY
    )
}
function Get-SshTarget { return ("{0}@{1}" -f $script:Cfg.VM_USER, $script:Cfg.VM_HOST) }

# Wrap a remote command as a single quote-free token.
#
# PowerShell 5.1 does not escape embedded double quotes when it hands arguments
# to a native exe, so any remote command containing quotes, pipes or || arrives
# at bash mangled ("syntax error near unexpected token"). Base64 sidesteps the
# whole problem: the argument becomes [A-Za-z0-9+/=] and nothing can chew on it.
#
# The 2>&1 is applied to bash on the LINUX side, never on the PowerShell side:
# 5.1 wraps a native exe's stderr in ErrorRecords and reports failure even on
# exit 0.
function Get-RemotePayload {
    param([string] $Command, [switch] $Merge)
    $b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Command))
    if ($Merge) { return "echo $b64 | base64 -d | bash 2>&1" }
    return "echo $b64 | base64 -d | bash"
}

# Runs a command on the VM and returns its stdout lines. $script:LastRemoteExit
# carries the exit code.
function Invoke-Remote {
    param([string] $Command, [switch] $Merge)
    $a = Get-SshArgs
    $a += (Get-SshTarget)
    $a += (Get-RemotePayload -Command $Command -Merge:$Merge)
    $out = & ssh.exe @a
    $script:LastRemoteExit = $LASTEXITCODE
    return $out
}

# Same, but streams to the console (and the log) as output arrives.
function Invoke-RemoteStreaming {
    param([string] $Command, [string] $Prefix = '  | ')
    $a = Get-SshArgs
    $a += (Get-SshTarget)
    $a += (Get-RemotePayload -Command $Command -Merge)
    & ssh.exe @a | ForEach-Object { Write-Line ($Prefix + $_) }
    $script:LastRemoteExit = $LASTEXITCODE
    return $script:LastRemoteExit
}

# Quiet true/false test of a remote condition.
function Test-Remote {
    param([string] $Command)
    Invoke-Remote -Command $Command | Out-Null
    return ($script:LastRemoteExit -eq 0)
}

function Copy-ToRemote {
    param([string] $LocalPath, [string] $RemotePath)
    $a = @(
        '-o','BatchMode=yes'
        '-o','StrictHostKeyChecking=accept-new'
        '-P',[string]$script:Cfg.SSH_PORT
        '-i',$script:Cfg.SSH_KEY
        $LocalPath
        ((Get-SshTarget) + ':' + $RemotePath)
    )
    & scp.exe @a | Out-Null
    return ($LASTEXITCODE -eq 0)
}

# ssh.exe writes its version banner to stderr, and PowerShell 5.1 turns a
# native exe's stderr into ErrorRecords that trip $ErrorActionPreference='Stop'.
# Read the version off the binary instead.
function Get-SshVersion {
    $c = Get-Command ssh.exe -ErrorAction SilentlyContinue
    if (-not $c) { return 'unknown' }
    return (Get-Item $c.Source).VersionInfo.ProductVersion
}

function Set-Clip {
    param([string] $Text)
    try { Set-Clipboard -Value $Text; return $true } catch { return $false }
}
