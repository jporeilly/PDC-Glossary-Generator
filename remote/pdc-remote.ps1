# =============================================================================
#  pdc-remote 2.0.0 - drive pdc-reset.sh on the PDC VM from this Windows box
# =============================================================================
#
#  WHY THIS EXISTS
#    pdc-reset.sh has to run *on* the VM: it force-removes containers, deletes
#    pdc_* volumes, docker-execs into the OpenSearch node and re-runs pdc.sh.
#    None of that is reachable over PDC's 443 front door. This script is the
#    remote-control layer: it proves the path is sane, uploads the current copy
#    of the script, streams the run back to your console, then INDEPENDENTLY
#    verifies the result instead of trusting the script's own exit code.
#
#  Pure Windows PowerShell 5.1. No WSL, no Git Bash, no make. Uses ssh.exe,
#  scp.exe, ssh-keygen.exe and curl.exe, all of which ship with Windows.
#  ASCII only - em-dashes break 5.1 parsing.
#
#  USAGE
#    .\pdc-remote.ps1                    -> help
#    .\pdc-remote.ps1 doctor
#    .\pdc-remote.ps1 logs SVC=fe N=500
#    .\pdc-remote.ps1 reset
#
#  Any KEY=VALUE argument overrides configuration for that run.
# =============================================================================

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string] $Command = 'help',

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $Rest
)

$ErrorActionPreference = 'Stop'
$script:Here = $PSScriptRoot
. (Join-Path $script:Here 'lib\ui.ps1')
Initialize-Ui -Root $script:Here

$Version = '2.0.0'

# ---------------------------------------------------------------------------
#  Configuration. Precedence: KEY=VALUE argument > pdc-remote.env > defaults.
# ---------------------------------------------------------------------------
$script:Cfg = @{
    VM_HOST          = '192.168.1.200'
    VM_USER          = ''
    SSH_PORT         = '22'
    SSH_KEY          = (Join-Path $env:USERPROFILE '.ssh\id_ed25519_pdc')
    PDC_DIR          = '/opt/pentaho/pdc-docker-deployment'
    PDC_HOST         = 'https://pentaho.io'
    VOLUME_PREFIX    = 'pdc_'
    CONTAINER_PREFIX = 'pdc-'
    RESET_SCRIPT     = (Join-Path $script:Here '..\pdc-reset.sh')
    REMOTE_SCRIPT    = '/tmp/pdc-reset.sh'
    LICENSE_BIN      = ''
    DEVICE_ID        = 'pdc-demo'
    KC_REALM         = 'pdc'
    KC_CLIENT        = 'pdc-client'
    PDC_ADMIN_USER   = 'admin'
    # Routing verified on the 11.0.0 demo build 2026-08-06: the /api/public/
    # prefix returns 404 (Traefik has no router for it) while /api/ and
    # /swagger/ are routed. Keep in step with pdc-reset.sh.
    SWAGGER_PATH     = '/swagger/'
    LICENSE_PATH     = '/api/v2/licensing/uploadLicense'
    WAIT_TIMEOUT     = '600'
    ENROLL_PORT      = '8099'
    RESET_FLAGS      = ''
    SVC              = 'fe'
    N                = '200'
}

$script:ConfigFile = Join-Path $script:Here 'pdc-remote.env'

function Import-Config {
    if (-not (Test-Path $script:ConfigFile)) { return }
    foreach ($line in (Get-Content $script:ConfigFile -Encoding utf8)) {
        $t = $line.Trim()
        if ($t -eq '' -or $t.StartsWith('#')) { continue }
        $i = $t.IndexOf('=')
        if ($i -lt 1) { continue }
        $k = $t.Substring(0, $i).Trim()
        $v = $t.Substring($i + 1).Trim()
        $v = [Environment]::ExpandEnvironmentVariables($v)
        if ($script:Cfg.ContainsKey($k)) { $script:Cfg[$k] = $v } else { $script:Cfg[$k] = $v }
    }
}

function Import-Overrides {
    param([string[]] $Args)
    if (-not $Args) { return }
    foreach ($a in $Args) {
        $i = $a.IndexOf('=')
        if ($i -lt 1) { continue }
        $script:Cfg[$a.Substring(0, $i)] = $a.Substring($i + 1)
    }
}

Import-Config
Import-Overrides -Args $Rest

# Derived
$script:Cfg.PDC_FQDN = ($script:Cfg.PDC_HOST -replace '^https?://', '')
if ($script:Cfg.RESET_SCRIPT -and -not [IO.Path]::IsPathRooted($script:Cfg.RESET_SCRIPT)) {
    $script:Cfg.RESET_SCRIPT = Join-Path $script:Here $script:Cfg.RESET_SCRIPT
}
function Get-Target { return ("{0}@{1}" -f $script:Cfg.VM_USER, $script:Cfg.VM_HOST) }

function Assert-VmUser {
    if ([string]::IsNullOrWhiteSpace($script:Cfg.VM_USER)) {
        Write-Bad 'VM_USER is not set'
        Write-Hint 'run: .\pdc-remote.ps1 config'
        return $false
    }
    return $true
}

# ===========================================================================
#  HELP
# ===========================================================================
function Invoke-Help {
    Write-Banner "pdc-remote $Version - reset the PDC VM from Windows"
    Invoke-Render 'help'
    Write-Line ''
}

function Invoke-Version {
    Write-Info "pdc-remote $Version"
    Write-Plain ("PowerShell " + $PSVersionTable.PSVersion)
    Write-Plain (Get-SshVersion)
    Write-Plain (& curl.exe --version | Select-Object -First 1)
}

# ===========================================================================
#  CONFIGURATION
# ===========================================================================
function Invoke-Config {
    Write-Banner 'Configure pdc-remote'
    Invoke-Render 'config-intro'
    Write-Line ''
    if (Test-Path $script:ConfigFile) {
        Write-Warn "$($script:ConfigFile) exists - current values are offered as defaults."
        Write-Line ''
    }
    $h = Read-Answer 'VM IP address or hostname' $script:Cfg.VM_HOST
    Write-Line ''
    Write-Info 'The LINUX username on the VM - not a PDC or Keycloak login.'
    Write-Hint "If the console auto-logs-in and you do not know it, type 'whoami' there."
    $u = Read-Answer 'VM Linux username' $script:Cfg.VM_USER
    Write-Line ''
    $d = Read-Answer 'PDC deployment directory on the VM' $script:Cfg.PDC_DIR
    $p = Read-Answer 'PDC base URL' $script:Cfg.PDC_HOST

    $lines = @(
        "# pdc-remote configuration - generated $(Get-Date -Format 's')",
        '# Safe to edit by hand. Never commit: this file is gitignored.',
        "VM_HOST=$h",
        "VM_USER=$u",
        "SSH_PORT=$($script:Cfg.SSH_PORT)",
        "SSH_KEY=$($script:Cfg.SSH_KEY)",
        "PDC_DIR=$d",
        "PDC_HOST=$p",
        "VOLUME_PREFIX=$($script:Cfg.VOLUME_PREFIX)",
        "CONTAINER_PREFIX=$($script:Cfg.CONTAINER_PREFIX)",
        "RESET_SCRIPT=$($script:Cfg.RESET_SCRIPT)",
        "LICENSE_BIN=$($script:Cfg.LICENSE_BIN)",
        "DEVICE_ID=$($script:Cfg.DEVICE_ID)",
        "KC_REALM=$($script:Cfg.KC_REALM)",
        "KC_CLIENT=$($script:Cfg.KC_CLIENT)",
        "PDC_ADMIN_USER=$($script:Cfg.PDC_ADMIN_USER)",
        "SWAGGER_PATH=$($script:Cfg.SWAGGER_PATH)",
        "LICENSE_PATH=$($script:Cfg.LICENSE_PATH)",
        "WAIT_TIMEOUT=$($script:Cfg.WAIT_TIMEOUT)"
    )
    Set-Content -Path $script:ConfigFile -Value $lines -Encoding utf8
    Write-Line ''
    Write-Ok "wrote $($script:ConfigFile)"
    if ([string]::IsNullOrWhiteSpace($u)) {
        Set-Ck 'cfg' 'warn' 'VM_USER empty'
        Write-Warn 'VM_USER is still empty - SSH cannot work until you set it.'
        Write-Hint "run 'whoami' at the VM console, then re-run: .\pdc-remote.ps1 config"
    } else {
        Set-CkPass 'cfg' "$u@$h"
    }
    Write-Line ''
    Write-Info 'Next: .\pdc-remote.ps1 probe'
}

function Invoke-ShowConfig {
    Write-Banner 'Effective configuration'
    $cfgNote = '  (MISSING - run: .\pdc-remote.ps1 config)'
    if (Test-Path $script:ConfigFile) { $cfgNote = '  (present)' }
    $keyNote = '  (not generated - run: .\pdc-remote.ps1 enroll)'
    if (Test-Path $script:Cfg.SSH_KEY) { $keyNote = '  (present)' }
    $scrNote = '  (MISSING)'
    if (Test-Path $script:Cfg.RESET_SCRIPT) { $scrNote = '  (present)' }
    $user = $script:Cfg.VM_USER
    if (-not $user) { $user = '(unset - run: .\pdc-remote.ps1 config)' }
    $lic = $script:Cfg.LICENSE_BIN
    if (-not $lic) { $lic = '(unset - license step skipped)' }

    Write-Kv 'config file'      ($script:ConfigFile + $cfgNote)
    Write-Kv 'VM_HOST'          $script:Cfg.VM_HOST
    Write-Kv 'VM_USER'          $user
    Write-Kv 'SSH_PORT'         $script:Cfg.SSH_PORT
    Write-Kv 'SSH_KEY'          ($script:Cfg.SSH_KEY + $keyNote)
    Write-Kv 'PDC_DIR'          $script:Cfg.PDC_DIR
    Write-Kv 'PDC_HOST'         $script:Cfg.PDC_HOST
    Write-Kv 'container prefix' $script:Cfg.CONTAINER_PREFIX
    Write-Kv 'volume prefix'    $script:Cfg.VOLUME_PREFIX
    Write-Kv 'local script'     ($script:Cfg.RESET_SCRIPT + $scrNote)
    Write-Kv 'remote script'    $script:Cfg.REMOTE_SCRIPT
    Write-Kv 'LICENSE_BIN'      $lic
    Write-Kv 'swagger path'     $script:Cfg.SWAGGER_PATH
    Write-Kv 'licence path'     $script:Cfg.LICENSE_PATH
    Write-Kv 'Keycloak realm'   ("$($script:Cfg.KC_REALM) / client $($script:Cfg.KC_CLIENT)")
    Write-Kv 'logs'             (Join-Path $script:Here 'logs')
    Write-Kv 'state'            (Join-Path $script:Here '.state')
    Write-Line ''
}

# ===========================================================================
#  CONNECTIVITY AND ENROLLMENT
# ===========================================================================
function Invoke-Probe {
    Start-Log 'probe'
    Write-Banner "Port probe - $($script:Cfg.VM_HOST)"
    # A plain array, not [ordered]@{}: indexing an OrderedDictionary with an
    # integer is a POSITIONAL lookup, so $ports[22] would silently return $null.
    $ports = @(
        @{ Port = 22;   Desc = 'SSH (required by this script)' },
        @{ Port = 443;  Desc = 'PDC front door' },
        @{ Port = 5433; Desc = 'lab Postgres' },
        @{ Port = 9000; Desc = 'MinIO S3 API' },
        @{ Port = 9001; Desc = 'MinIO console' },
        @{ Port = 2376; Desc = 'Docker TLS socket (not required)' }
    )
    foreach ($e in $ports) {
        if (Test-TcpPort -HostName $script:Cfg.VM_HOST -Port $e.Port) {
            Write-Ok ("{0,-5} open    - {1}" -f $e.Port, $e.Desc)
        } elseif ($e.Port -eq 22) {
            Write-Bad ("{0,-5} CLOSED  - {1}" -f $e.Port, $e.Desc)
        } else {
            Write-Skip ("{0,-5} closed  - {1}" -f $e.Port, $e.Desc)
        }
    }
    Write-Line ''
    if (-not (Test-TcpPort -HostName $script:Cfg.VM_HOST -Port 22)) {
        Write-Warn 'Port 22 is closed. Nothing else here can work yet.'
        Write-Hint 'run: .\pdc-remote.ps1 enable-ssh'
    }
    Write-LogWhere
}

function Invoke-EnableSsh {
    Write-Banner 'Turn on SSH - this part happens at the VM console'
    Invoke-Render 'enable-ssh'
    Write-Line ''
}

function Invoke-WaitSsh {
    Write-Banner "Waiting for $($script:Cfg.VM_HOST):$($script:Cfg.SSH_PORT)"
    Write-Info 'Polling every 3s for up to 5 minutes. Ctrl-C to give up.'
    Start-Timer
    for ($i = 0; $i -lt 100; $i++) {
        if (Test-TcpPort -HostName $script:Cfg.VM_HOST -Port ([int]$script:Cfg.SSH_PORT) -TimeoutMs 2000) {
            Write-Host ''
            Write-Ok "port $($script:Cfg.SSH_PORT) is OPEN after $(Get-Elapsed)"
            Write-Info 'Next: .\pdc-remote.ps1 enroll'
            return
        }
        Write-Host '.' -NoNewline
        Start-Sleep -Seconds 3
    }
    Write-Host ''
    Write-Bad "port $($script:Cfg.SSH_PORT) never opened"
    Write-Hint 're-check the console steps: .\pdc-remote.ps1 enable-ssh'
}

function Invoke-Keygen {
    if (Test-Path $script:Cfg.SSH_KEY) {
        Write-Ok "key already exists: $($script:Cfg.SSH_KEY)"
        return
    }
    Write-Info 'Generating a dedicated ed25519 key (no passphrase - this is a lab VM).'
    $dir = Split-Path -Parent $script:Cfg.SSH_KEY
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    & ssh-keygen.exe -t ed25519 -N '""' -C "pdc-remote@$env:COMPUTERNAME" -f $script:Cfg.SSH_KEY | Out-Null
    Write-Ok "created $($script:Cfg.SSH_KEY)"
    Protect-KeyFile
}

# Windows OpenSSH refuses a private key that other principals can read. Strip
# inheritance and grant only the current user.
function Protect-KeyFile {
    if (-not (Test-Path $script:Cfg.SSH_KEY)) { return }
    & icacls.exe $script:Cfg.SSH_KEY /inheritance:r | Out-Null
    & icacls.exe $script:Cfg.SSH_KEY /grant:r ("$env:USERNAME" + ':R') | Out-Null
    Write-Info 'key ACLs tightened to the current user only'
}

# Reuse a key that already lives in a WSL home, so an already-enrolled key does
# not have to be enrolled a second time.
function Invoke-ImportWslKey {
    Write-Banner 'Import an existing key from WSL'
    $distro = $script:Cfg.WSL_DISTRO
    if (-not $distro) { $distro = 'Ubuntu-24.04' }
    $wslUser = $script:Cfg.WSL_USER
    if (-not $wslUser) { $wslUser = 'chatbot' }
    $src = "\\wsl$\$distro\home\$wslUser\.ssh\id_ed25519_pdc"
    Write-Info "source: $src"
    if (-not (Test-Path $src)) {
        Write-Bad 'not found - nothing to import'
        Write-Hint 'override with WSL_DISTRO=... WSL_USER=... or just run: .\pdc-remote.ps1 enroll'
        return
    }
    $dir = Split-Path -Parent $script:Cfg.SSH_KEY
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    Copy-Item $src $script:Cfg.SSH_KEY -Force
    if (Test-Path "$src.pub") { Copy-Item "$src.pub" ($script:Cfg.SSH_KEY + '.pub') -Force }
    Write-Ok "copied to $($script:Cfg.SSH_KEY)"
    Protect-KeyFile
    Write-Info 'Next: .\pdc-remote.ps1 ssh-test'
}

function Invoke-Enroll {
    Invoke-Keygen
    Start-Log 'enroll'
    Write-Banner "Enroll this workstation's key on the VM"
    if ([string]::IsNullOrWhiteSpace($script:Cfg.VM_USER)) {
        Write-Warn 'VM_USER is not set yet - the paste below still works, it enrols the'
        Write-Warn "key for whichever account the console is logged in as. Run 'whoami'"
        Write-Warn 'there too, then run: .\pdc-remote.ps1 config'
        Write-Line ''
    }
    $pub = (Get-Content ($script:Cfg.SSH_KEY + '.pub') -Raw).Trim()
    $cmd = "mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo '$pub' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && echo ENROLLED"
    Set-Content -Path (Join-Path $script:Here '.state\enroll-command.txt') -Value $cmd -Encoding ascii
    Invoke-Render 'enroll'
    Write-Line ''
    if (Set-Clip $cmd) { Write-Ok 'copied to the Windows clipboard' } else { Write-Warn 'could not reach the clipboard - copy it from below' }
    Write-Info "also saved to: .state\enroll-command.txt"
    Write-Line ''
    Write-Line '  --- paste at the VM console -----------------------------------------'
    Write-Line ''
    Write-Line $cmd
    Write-Line ''
    Write-Line '  ---------------------------------------------------------------------'
    Write-Line ''
    Write-Note 'Console has no clipboard? Use: .\pdc-remote.ps1 enroll-http'
    Write-Line ''
    Write-Info 'When it prints ENROLLED, run: .\pdc-remote.ps1 ssh-test'
}

function Invoke-EnrollHttp {
    Invoke-Keygen
    Write-Banner 'Key delivery fallback - serve the public key over HTTP'
    $pubDir = Join-Path $script:Here '.state\pub'
    if (-not (Test-Path $pubDir)) { New-Item -ItemType Directory -Path $pubDir -Force | Out-Null }
    Copy-Item ($script:Cfg.SSH_KEY + '.pub') (Join-Path $pubDir 'pdc.pub') -Force
    $hostIp = (Get-NetIPAddress -AddressFamily IPv4 |
               Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
               Sort-Object -Property InterfaceMetric |
               Select-Object -First 1).IPAddress
    if (-not $hostIp) { $hostIp = '<this-host-LAN-ip>' }
    Invoke-Render 'enroll-http' @{
        PUBDIR = $pubDir
        WINDIR = $pubDir
        PORT   = $script:Cfg.ENROLL_PORT
        HOSTIP = $hostIp
    }
}

function Invoke-SshTest {
    Write-Banner 'SSH smoke test'
    if (-not (Assert-VmUser)) { return }
    Write-Info ("target: " + (Get-Target) + ":" + $script:Cfg.SSH_PORT)
    Write-Info ("key   : " + $script:Cfg.SSH_KEY)
    $out = Invoke-Remote -Command 'echo OK; id -un; id -nG; . /etc/os-release 2>/dev/null && echo "$PRETTY_NAME"' -Merge
    foreach ($l in $out) { Write-Plain $l }
    Write-Line ''
    if ($script:LastRemoteExit -ne 0) {
        Set-CkFail 'ssh' "exit $($script:LastRemoteExit)"
        $joined = ($out -join ' ')
        if ($joined -match 'Permission denied')  { Write-Hint 'the key is not in ~/.ssh/authorized_keys yet - run: .\pdc-remote.ps1 enroll' }
        if ($joined -match 'Connection refused') { Write-Hint 'sshd is not running - run: .\pdc-remote.ps1 enable-ssh' }
        if ($joined -match 'No route to host|timed out') { Write-Hint 'wrong IP or a firewall in between - run: .\pdc-remote.ps1 probe' }
        return
    }
    Set-CkPass 'ssh' (Get-Target)
    Write-Info 'Next: .\pdc-remote.ps1 doctor'
}

function Invoke-PrivTest {
    Write-Banner 'Remote privilege check'
    if (-not (Assert-VmUser)) { return }
    $dockerOk = Test-Remote 'docker ps >/dev/null 2>&1'
    if ($dockerOk) {
        Write-Ok 'docker works without sudo'
    } else {
        Write-Bad "cannot run 'docker ps' as $($script:Cfg.VM_USER)"
        Write-Hint "on the VM: sudo usermod -aG docker $($script:Cfg.VM_USER)   (then log out and back in)"
    }
    $sudoOk = Test-Remote 'sudo -n true 2>/dev/null'
    if ($sudoOk) {
        Write-Ok 'passwordless sudo available'
    } else {
        Write-Warn 'sudo needs a password - that is fine, see: .\pdc-remote.ps1 sudo-help'
    }
    if ($dockerOk) { Set-CkPass 'priv' "docker=yes nopasswd-sudo=$sudoOk" }
    else { Set-CkFail 'priv' 'docker unavailable' }
}

function Invoke-Shell {
    Write-Info ("opening an interactive session on " + (Get-Target) + " (exit to return)")
    $a = @(
        '-o','StrictHostKeyChecking=accept-new'
        '-p',[string]$script:Cfg.SSH_PORT
        '-i',$script:Cfg.SSH_KEY
        (Get-Target)
    )
    & ssh.exe @a
}

# ===========================================================================
#  SUDO
# ===========================================================================
function Invoke-SudoHelp {
    Write-Banner 'Your VM asks for a sudo password. Here are the options.'
    $u = $script:Cfg.VM_USER
    if (-not $u) { $u = '<vm-user>' }
    Invoke-Render 'sudo-help' @{ VM_USER = $u; PDC_DIR = $script:Cfg.PDC_DIR }
    Write-Line ''
    Write-Info 'check the docker group from here with: .\pdc-remote.ps1 priv-test'
}

function Invoke-EnvCheck {
    Write-Banner 'conf/.env - LICENSING_OFFLINE_INSTALL'
    if (-not (Assert-VmUser)) { return }
    $cmd = 'F=' + $script:Cfg.PDC_DIR + '/conf/.env; if [ -r "$F" ]; then grep -E "^LICENSING_OFFLINE_INSTALL=" "$F" || echo __ABSENT__; else echo __UNREADABLE__; fi'
    $out = (Invoke-Remote -Command $cmd) -join ''
    switch -Regex ($out) {
        '^LICENSING_OFFLINE_INSTALL=true$' {
            Write-Ok 'already true - a reset will never need sudo'
            Write-Hint 'ensure_env_kv() short-circuits on an exact match'
            break
        }
        '^LICENSING_OFFLINE_INSTALL=' {
            Write-Warn "found: $out"
            Write-Hint 'set it to true at the console: .\pdc-remote.ps1 env-fix'
            break
        }
        '__ABSENT__' {
            Write-Warn 'the key is not present in conf/.env'
            Write-Hint 'the reset would try to append it, which needs sudo: .\pdc-remote.ps1 env-fix'
            break
        }
        '__UNREADABLE__' {
            Write-Warn "conf/.env is not readable as $($script:Cfg.VM_USER) - expected, it is root-owned"
            Write-Hint "check at the console: sudo grep LICENSING_OFFLINE_INSTALL $($script:Cfg.PDC_DIR)/conf/.env"
            break
        }
        default { Write-Warn "unexpected result: $out" }
    }
    Write-Line ''
}

function Invoke-EnvFix {
    Write-Banner 'Fix conf/.env at the VM console'
    Write-Note 'this needs root and your sudo password, so it cannot be driven from here'
    $f = $script:Cfg.PDC_DIR + '/conf/.env'
    $one = 'F=' + $f + '; sudo cp -n "$F" "$F.bak"; if sudo grep -q "^LICENSING_OFFLINE_INSTALL=" "$F"; then sudo sed -i "s/^LICENSING_OFFLINE_INSTALL=.*/LICENSING_OFFLINE_INSTALL=true/" "$F"; else echo "LICENSING_OFFLINE_INSTALL=true" | sudo tee -a "$F" >/dev/null; fi; sudo grep LICENSING_OFFLINE_INSTALL "$F"'
    Write-Line ''
    Write-Line '  --- paste at the VM console -----------------------------------------'
    Write-Line ''
    Write-Line $one
    Write-Line ''
    Write-Line '  ---------------------------------------------------------------------'
    Write-Line ''
    if (Set-Clip $one) { Write-Ok 'copied to the Windows clipboard' }
    Write-Info 'afterwards, confirm from here: .\pdc-remote.ps1 env-check'
}

# ===========================================================================
#  DOCTOR
# ===========================================================================
function Invoke-Doctor {
    Start-Log 'doctor'
    Write-Banner 'Preflight - 16 checks'
    $script:Pass = 0; $script:WarnC = 0; $script:FailC = 0
    function P { param($m) Write-Ok   $m; $script:Pass  = $script:Pass  + 1 }
    function W { param($m, $h = '') Write-Warn $m; if ($h) { Write-Hint $h }; $script:WarnC = $script:WarnC + 1 }
    function F { param($m, $h = '') Write-Bad  $m; if ($h) { Write-Hint $h }; $script:FailC = $script:FailC + 1 }

    Write-Step 1 5 'Local workstation'
    if (Get-Command ssh.exe -ErrorAction SilentlyContinue) { P ('ssh client present (' + (Get-SshVersion) + ')') } else { F 'no ssh client' }
    if (Get-Command scp.exe -ErrorAction SilentlyContinue) { P 'scp present' } else { F 'no scp' }
    if (Get-Command curl.exe -ErrorAction SilentlyContinue) { P ('curl present (' + ((& curl.exe --version | Select-Object -First 1) -split ' ')[1] + ')') } else { F 'no curl.exe' }
    if (Test-Path $script:Cfg.RESET_SCRIPT) {
        $n = (Get-Content $script:Cfg.RESET_SCRIPT).Count
        P "local pdc-reset.sh found ($n lines)"
    } else {
        F "pdc-reset.sh not found at $($script:Cfg.RESET_SCRIPT)" 'set RESET_SCRIPT in pdc-remote.env'
    }

    Write-Step 2 5 'Configuration'
    if (Test-Path $script:ConfigFile) { P 'pdc-remote.env present' } else { F 'no pdc-remote.env' 'run: .\pdc-remote.ps1 config' }
    if ($script:Cfg.VM_USER) { P "VM_USER = $($script:Cfg.VM_USER)" } else { F 'VM_USER is empty' "run 'whoami' at the VM console, then: .\pdc-remote.ps1 config" }
    if (Test-Path $script:Cfg.SSH_KEY) { P 'ssh key present' } else { F "no ssh key at $($script:Cfg.SSH_KEY)" 'run: .\pdc-remote.ps1 enroll' }

    Write-Step 3 5 "Network path to $($script:Cfg.VM_HOST)"
    if (Test-TcpPort -HostName $script:Cfg.VM_HOST -Port ([int]$script:Cfg.SSH_PORT)) { P "port $($script:Cfg.SSH_PORT) open" } else { F "port $($script:Cfg.SSH_PORT) CLOSED" 'run: .\pdc-remote.ps1 enable-ssh' }
    if (Test-TcpPort -HostName $script:Cfg.VM_HOST -Port 443) { P 'port 443 open (PDC front door)' } else { W 'port 443 closed - PDC is down or not installed yet' }

    Write-Step 4 5 'Authentication and remote host'
    $haveSsh = $false
    if ($script:Cfg.VM_USER -and (Test-Remote 'true')) {
        $haveSsh = $true
        P 'passwordless SSH works'
        Set-Ck 'ssh' 'pass' (Get-Target)
        $who = (Invoke-Remote -Command 'id -un') -join ''
        $os  = (Invoke-Remote -Command '. /etc/os-release; echo $PRETTY_NAME') -join ''
        P "remote identity: $who on $os"
        if (Test-Remote 'docker ps >/dev/null 2>&1') { P 'docker usable without sudo' }
        else { F "docker needs sudo for $($script:Cfg.VM_USER)" "sudo usermod -aG docker $($script:Cfg.VM_USER) on the VM, then re-login. See: sudo-help" }
        if (Test-Remote 'sudo -n true 2>/dev/null') { P 'passwordless sudo' }
        else { W 'sudo needs a password' 'not fatal - see: .\pdc-remote.ps1 sudo-help (Option A removes the need entirely)' }
    } else {
        F 'passwordless SSH failed' 'run: .\pdc-remote.ps1 enroll, then ssh-test'
    }

    Write-Step 5 5 'PDC deployment on the VM'
    if ($haveSsh) {
        if (Test-Remote ('[ -d "' + $script:Cfg.PDC_DIR + '" ]')) {
            P "$($script:Cfg.PDC_DIR) exists"
            if (Test-Remote ('[ -x "' + $script:Cfg.PDC_DIR + '/pdc.sh" ]')) {
                P 'pdc.sh is executable'
                Set-Ck 'dir' 'pass' $script:Cfg.PDC_DIR
            } else {
                F 'pdc.sh missing or not executable' 'wrong PDC_DIR? run: .\pdc-remote.ps1 config'
            }
        } else {
            F "$($script:Cfg.PDC_DIR) not found on the VM" 'find it: .\pdc-remote.ps1 shell, then sudo find / -name pdc.sh'
        }
        $nct = (Invoke-Remote -Command ('docker ps -a --format "{{.Names}}" | grep -c "^' + $script:Cfg.CONTAINER_PREFIX + '"')) -join ''
        $nvl = (Invoke-Remote -Command ('docker volume ls -q | grep -c "^' + $script:Cfg.VOLUME_PREFIX + '"')) -join ''
        P "$nct $($script:Cfg.CONTAINER_PREFIX)* containers, $nvl $($script:Cfg.VOLUME_PREFIX)* volumes"
        $mmc = [int](((Invoke-Remote -Command 'sysctl -n vm.max_map_count') -join '') -replace '\D', '')
        if ($mmc -ge 262144) { P "vm.max_map_count = $mmc (OpenSearch OK)" }
        else { W "vm.max_map_count = $mmc is below 262144" 'OpenSearch will fail to start: sudo sysctl -w vm.max_map_count=262144' }
        $free = [int](((Invoke-Remote -Command 'df -BG --output=avail /var/lib/docker | tail -1') -join '') -replace '\D', '')
        if ($free -ge 20) { P "${free}G free on /var/lib/docker" }
        else { W "only ${free}G free on /var/lib/docker" 'OpenSearch trips its flood-stage watermark when disk gets tight' }
        # grep + arithmetic here rather than a remote awk: quoting an awk
        # program through PowerShell's native-argument handling is a losing game.
        $memKb = [int64](((Invoke-Remote -Command 'grep MemTotal /proc/meminfo') -join '') -replace '\D', '')
        $mem = [int]($memKb / 1048576)
        if ($mem -ge 16) { P "${mem}G RAM" } else { W "${mem}G RAM - PDC 11 wants 16G or more" }
    } else {
        Write-Skip 'remote checks skipped - no SSH'
        $script:FailC = $script:FailC + 1
    }

    Write-Line ''
    Write-Rule
    Write-Line ("  RESULT   $($script:Pass) passed   $($script:WarnC) warnings   $($script:FailC) failures")
    Write-Rule
    Write-Line ''
    if ($script:FailC -eq 0) { Write-Ok 'Ready. Next: .\pdc-remote.ps1 plan' }
    else { Write-Bad 'Fix the failures above before attempting a reset.' }
    Write-LogWhere
}

# ===========================================================================
#  DAY TO DAY
# ===========================================================================
function Invoke-Status {
    Write-Banner 'PDC service status'
    if (-not (Assert-VmUser)) { return }
    $out = Invoke-Remote -Command ('cd "' + $script:Cfg.PDC_DIR + '" && ./pdc.sh ps') -Merge
    foreach ($l in $out) { Write-Line ('  ' + $l) }
    Write-Line ''
    Write-Info 'state tally:'
    $tally = Invoke-Remote -Command ('docker ps -a --format "{{.Names}} {{.Status}}" | grep "^' + $script:Cfg.CONTAINER_PREFIX + '" | awk ''{print $2}'' | sort | uniq -c | sort -rn')
    foreach ($l in $tally) { Write-Line ('  ' + $l) }
    Write-Line ''
    Write-Note "anything in 'Created' means an init container failed -> .\pdc-remote.ps1 unstick"
}

function Invoke-Health {
    Write-Banner "HTTP health - $($script:Cfg.PDC_HOST)"
    Write-Info 'using curl --resolve, so this works without a hosts entry on this machine'
    # 302 (oauth2-proxy redirect) and 401 both prove the route exists. A 404 is
    # the red flag: Traefik has no router for that prefix.
    $checks = @(
        @{ Url = $script:Cfg.PDC_HOST + '/'; Label = 'front door (fe)' },
        @{ Url = $script:Cfg.PDC_HOST + $script:Cfg.SWAGGER_PATH; Label = 'Swagger UI (302 to Keycloak = healthy)' },
        @{ Url = $script:Cfg.PDC_HOST + '/keycloak/realms/' + $script:Cfg.KC_REALM + '/.well-known/openid-configuration'; Label = "Keycloak realm $($script:Cfg.KC_REALM)" },
        @{ Url = $script:Cfg.PDC_HOST + '/css-admin-api/api/internal/css-auth-proxy/v1/provider/' + $script:Cfg.PDC_FQDN; Label = 'css-admin-api (401 = healthy)' }
    )
    foreach ($c in $checks) {
        $code = Invoke-PdcHttp -Url $c.Url -TimeoutSec 12
        if ($code -match '^(200|301|302|303|307|401|403)$') { Write-Ok "$code  $($c.Label)" }
        elseif ($code -eq '404') { Write-Bad "404  $($c.Label)   <- Traefik is up but has no backend" }
        elseif ($code -eq '000') { Write-Bad "---  $($c.Label)   <- no response at all" }
        else { Write-Warn "$code  $($c.Label)" }
    }
    Write-Line ''
}

function Invoke-Logs {
    $svc = $script:Cfg.SVC
    $n   = $script:Cfg.N
    Write-Banner "Logs - $($script:Cfg.CONTAINER_PREFIX)$svc, last $n lines"
    if (-not (Assert-VmUser)) { return }
    $cmd = 'C=$(docker ps -a --format "{{.Names}}" | grep -E "^' + $script:Cfg.CONTAINER_PREFIX + $svc + '(-[0-9]+)?$" | head -1); if [ -z "$C" ]; then echo "no container matching ' + $script:Cfg.CONTAINER_PREFIX + $svc + '"; exit 1; fi; echo "== $C =="; docker logs --tail ' + $n + ' "$C"'
    $out = Invoke-Remote -Command $cmd -Merge
    foreach ($l in $out) { Write-Line $l }
    Write-Line ''
    Write-Note 'try: fe public-api glossary keycloak traefik opensearch um-css-admin-api-init'
}

function Invoke-Unstick {
    Start-Log 'unstick'
    Write-Banner "Re-running 'pdc.sh up' to start services stranded in Created"
    if (-not (Assert-VmUser)) { return }
    Write-Info 'When an init container fails everything downstream sits in Created and'
    Write-Info 'Traefik answers every URL with 404. Re-running up is the documented fix'
    Write-Info 'and is non-destructive - no volumes are touched.'
    Write-Line ''
    Invoke-RemoteStreaming -Command ('cd "' + $script:Cfg.PDC_DIR + '" && ./pdc.sh up') -Prefix '  ' | Out-Null
    Write-Line ''
    Invoke-Verify
    Write-LogWhere
}

# ===========================================================================
#  RESET
# ===========================================================================
function Invoke-Plan {
    Write-Banner 'Reset plan - nothing is being changed'
    $flags = $script:Cfg.RESET_FLAGS
    if (-not $flags) { $flags = '(none - full wipe including OpenSearch)' }
    $keep = ''
    if ($script:Cfg.RESET_FLAGS -eq '--keep-opensearch') { $keep = '    - EXCEPT the opensearch volumes (--keep-opensearch)' }
    Invoke-Render 'plan' @{
        TARGET        = (Get-Target)
        SSH_PORT      = $script:Cfg.SSH_PORT
        RESET_SCRIPT  = $script:Cfg.RESET_SCRIPT
        REMOTE_SCRIPT = $script:Cfg.REMOTE_SCRIPT
        PDC_DIR       = $script:Cfg.PDC_DIR
        PDC_HOST      = $script:Cfg.PDC_HOST
        CPREFIX       = $script:Cfg.CONTAINER_PREFIX
        VPREFIX       = $script:Cfg.VOLUME_PREFIX
        FLAGS         = $flags
        KEEPNOTE      = $keep
    }
    Show-Ck
    Write-Line ''
    Write-Info 'Happy with this? Run: .\pdc-remote.ps1 dry-run   then   .\pdc-remote.ps1 reset'
}

function Invoke-DryRun {
    Write-Banner 'Dry run - asking the VM what WOULD be deleted'
    if (-not (Assert-VmUser)) { return }
    Write-Info 'read-only: this lists, it does not remove'
    Write-Line ''
    Write-Line '  containers that would be force-removed'
    $c = Invoke-Remote -Command ('docker ps -a --format "  {{.Names}}  {{.Status}}" | grep "' + $script:Cfg.CONTAINER_PREFIX + '" || echo "  (none)"')
    foreach ($l in $c) { Write-Line $l }
    Write-Line ''
    Write-Line '  volumes that would be deleted'
    if ($script:Cfg.RESET_FLAGS -eq '--keep-opensearch') {
        $v = Invoke-Remote -Command ('docker volume ls -q | grep "^' + $script:Cfg.VOLUME_PREFIX + '" | grep -v opensearch || echo "(none)"')
    } else {
        $v = Invoke-Remote -Command ('docker volume ls -q | grep "^' + $script:Cfg.VOLUME_PREFIX + '" || echo "(none)"')
    }
    foreach ($l in $v) { Write-Line ('    - ' + $l) }
    if ($script:Cfg.RESET_FLAGS -eq '--keep-opensearch') { Write-Line '    (opensearch volumes preserved)' }
    Write-Line ''
    Write-Line '  disk that would be reclaimed'
    foreach ($l in (Invoke-Remote -Command 'docker system df')) { Write-Line ('    ' + $l) }
    Write-Line ''
}

function Invoke-Backup {
    Write-Banner 'Snapshot before the wipe'
    if (-not (Assert-VmUser)) { return }
    $b = Join-Path $script:Here ('logs\backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    New-Item -ItemType Directory -Path $b -Force | Out-Null
    Write-Info 'pulling conf/.env (it survives the wipe, but a copy costs nothing)'
    (Invoke-Remote -Command ('cat "' + $script:Cfg.PDC_DIR + '/conf/.env" 2>/dev/null || sudo -n cat "' + $script:Cfg.PDC_DIR + '/conf/.env" 2>/dev/null || echo "(unreadable without sudo - not fatal)"')) |
        Set-Content -Path (Join-Path $b 'conf.env') -Encoding utf8
    Write-Info 'inventorying containers, volumes, images and disk'
    # \t not a PowerShell backtick-t: in a single-quoted string the backtick is
    # literal, and bash would read `t{{.Image}}` as a command substitution.
    # docker's --format expands the backslash escape itself.
    (Invoke-Remote -Command 'docker ps -a --format "{{.Names}}\t{{.Image}}\t{{.Status}}"') | Set-Content (Join-Path $b 'containers.tsv') -Encoding utf8
    (Invoke-Remote -Command 'docker volume ls')    | Set-Content (Join-Path $b 'volumes.txt') -Encoding utf8
    (Invoke-Remote -Command 'docker system df -v') | Set-Content (Join-Path $b 'disk.txt') -Encoding utf8
    (Invoke-Remote -Command ('cd "' + $script:Cfg.PDC_DIR + '" && ./pdc.sh ps') -Merge) | Set-Content (Join-Path $b 'pdc-ps.txt') -Encoding utf8
    Write-Ok "saved to $b"
    foreach ($f in (Get-ChildItem $b)) { Write-Plain ("{0,10}  {1}" -f $f.Length, $f.Name) }
    Write-Line ''
    Write-Note 'this is a RECORD, not a restore point - volumes are not backed up.'
    Write-Note 'a reset really does destroy the catalog, glossaries and users.'
}

function Invoke-Upload {
    Write-Banner 'Uploading pdc-reset.sh'
    if (-not (Assert-VmUser)) { return $false }
    if (-not (Test-Path $script:Cfg.RESET_SCRIPT)) {
        Write-Bad "not found: $($script:Cfg.RESET_SCRIPT)"
        return $false
    }
    $lines = (Get-Content $script:Cfg.RESET_SCRIPT).Count
    Write-Info "source: $($script:Cfg.RESET_SCRIPT) ($lines lines)"
    # bash refuses to run a CRLF script. Write LF-only bytes to a temp file.
    $text = (Get-Content $script:Cfg.RESET_SCRIPT -Raw) -replace "`r`n", "`n"
    $tmp = Join-Path $env:TEMP ('pdc-reset-' + [Guid]::NewGuid().ToString('N') + '.sh')
    [IO.File]::WriteAllText($tmp, $text, (New-Object Text.UTF8Encoding($false)))
    Write-Info 'stripped CRLF to LF - bash refuses to run a CRLF script'
    $okCopy = Copy-ToRemote -LocalPath $tmp -RemotePath $script:Cfg.REMOTE_SCRIPT
    Remove-Item $tmp -Force
    if (-not $okCopy) { Write-Bad 'scp failed'; return $false }
    $out = Invoke-Remote -Command ('chmod 755 "' + $script:Cfg.REMOTE_SCRIPT + '" && bash -n "' + $script:Cfg.REMOTE_SCRIPT + '" && echo SYNTAX_OK') -Merge
    foreach ($l in $out) { Write-Plain $l }
    if ($script:LastRemoteExit -ne 0) { Write-Bad 'remote syntax check failed'; return $false }
    Write-Ok "uploaded to $($script:Cfg.REMOTE_SCRIPT) and syntax-checked on the VM"
    Set-CkPass 'up' $script:Cfg.REMOTE_SCRIPT
    return $true
}

function Invoke-Reset {
    Start-Log 'reset'
    Start-Timer
    Write-Banner ("PDC RESET - " + (Get-Target))

    Write-Step 1 10 'Preflight'
    if (-not (Assert-VmUser)) { return }
    if (-not (Test-Remote 'true')) {
        Set-CkFail 'ssh'
        Write-Bad ("cannot reach " + (Get-Target) + " over SSH")
        Write-Hint '.\pdc-remote.ps1 doctor'
        return
    }
    Set-CkPass 'ssh' (Get-Target)
    if (-not (Test-Remote 'docker ps >/dev/null')) {
        Set-CkFail 'priv' 'docker needs sudo'
        Write-Hint '.\pdc-remote.ps1 sudo-help'
        return
    }
    Set-CkPass 'priv' 'docker ok'
    if (-not (Test-Remote ('[ -x "' + $script:Cfg.PDC_DIR + '/pdc.sh" ]'))) {
        Set-CkFail 'dir' $script:Cfg.PDC_DIR
        Write-Bad "pdc.sh not found in $($script:Cfg.PDC_DIR)"
        return
    }
    Set-CkPass 'dir' $script:Cfg.PDC_DIR
    Write-Lap

    Write-Step 2 10 'Snapshot current state'
    Invoke-Backup
    Write-Lap

    Write-Step 3 10 'Upload the current pdc-reset.sh'
    if (-not (Invoke-Upload)) { return }
    Write-Lap

    Write-Step 4 10 'Confirm'
    Invoke-Plan
    Write-Line ''
    Write-Line '  This PERMANENTLY DELETES the catalog, glossaries, users and licence.' 'Red'
    if (-not (Confirm-Typed 'reset')) { return }
    Set-Ck 'run' 'running' ''

    Write-Step 5 10 'Running the reset on the VM - streamed live, 8 to 20 minutes'
    Write-Note "the remote script's own [reset]/[ ok ]/[warn] lines appear below"
    Write-Rule
    $rc = Invoke-RemoteStreaming -Command ("bash '" + $script:Cfg.REMOTE_SCRIPT + "' -y " + $script:Cfg.RESET_FLAGS)
    Write-Rule
    if ($rc -eq 0) {
        Set-CkPass 'run' 'exit 0'
    } else {
        Set-CkFail 'run' "exit $rc"
        Write-Warn "the script exited $rc - continuing to verification anyway, because a"
        Write-Warn 'late failure often still leaves a recoverable stack (see: unstick)'
    }
    Write-Lap

    Invoke-Verify

    Write-Step 10 10 'Summary'
    Show-Ck
    Write-Line ''
    if ((Get-FirstIncomplete) -eq '') {
        Write-Ok ("Reset complete and verified in " + (Get-Elapsed) + ".")
    } else {
        Write-Warn ("Finished in " + (Get-Elapsed) + " with open checkpoints - see above.")
        Write-Hint 'most common fix: .\pdc-remote.ps1 unstick'
        Write-Hint 'then re-verify:  .\pdc-remote.ps1 verify'
    }
    Write-Line ''
    Invoke-Render 'post-reset' @{ PDC_HOST = $script:Cfg.PDC_HOST; SWAGGER_PATH = $script:Cfg.SWAGGER_PATH }
    Write-Line ''
    Write-LogWhere
}

function Invoke-Verify {
    Write-Banner 'Independent verification'
    if (-not (Assert-VmUser)) { return }
    Write-Info "not trusting the script's exit code - re-checking the four things that matter"

    Write-Step 6 10 'OpenSearch security index'
    $node = ((Invoke-Remote -Command 'docker ps --format "{{.Names}}" | grep opensearch | grep -vE "init|volume" | head -1') -join '').Trim()
    if (-not $node) {
        Set-CkFail 'os' 'no opensearch node container'
        Write-Hint '.\pdc-remote.ps1 logs SVC=opensearch'
    } else {
        Write-Info "node: $node"
        $cmd = 'docker exec ' + $node + ' curl -sk -u $(docker exec ' + $node + ' printenv OPENSEARCH_USERNAME):$(docker exec ' + $node + ' printenv OPENSEARCH_PASSWORD) https://localhost:9200/_cat/indices/.opendistro_security'
        $idx = (Invoke-Remote -Command $cmd) -join ''
        if ($idx -match 'opendistro_security') {
            Set-CkPass 'os' '.opendistro_security present'
        } else {
            Set-CkFail 'os' 'security index missing'
            Write-Hint 'see docs/PDC-VM-TROUBLESHOOTING.md, the opensearch-cluster-init checklist'
        }
    }

    Write-Step 7 10 "App tier - waiting for fe and public-api, up to $($script:Cfg.WAIT_TIMEOUT)s"
    $deadline = (Get-Date).AddSeconds([int]$script:Cfg.WAIT_TIMEOUT)
    $upFe = 0; $upApi = 0
    while ((Get-Date) -lt $deadline) {
        $s = (Invoke-Remote -Command ('docker ps --format "{{.Names}} {{.Status}}" | grep -E "^' + $script:Cfg.CONTAINER_PREFIX + '(fe|public-api)-[0-9]"')) -join "`n"
        $upFe  = ([regex]::Matches($s, $script:Cfg.CONTAINER_PREFIX + 'fe-.*Up')).Count
        $upApi = ([regex]::Matches($s, $script:Cfg.CONTAINER_PREFIX + 'public-api-.*Up')).Count
        if ($upFe -ge 1 -and $upApi -ge 1) { break }
        Write-Host '.' -NoNewline
        Start-Sleep -Seconds 10
    }
    Write-Host ''
    if ($upFe -ge 1 -and $upApi -ge 1) {
        Set-CkPass 'app' 'fe + public-api Up'
    } else {
        Set-CkFail 'app' "fe=$upFe public-api=$upApi"
        Write-Hint 'services stranded in Created -> .\pdc-remote.ps1 unstick'
    }
    $stuck = [int](((Invoke-Remote -Command ('docker ps -a --format "{{.Names}} {{.Status}}" | grep "^' + $script:Cfg.CONTAINER_PREFIX + '" | grep -cE "Created|Exited \([1-9]"')) -join '') -replace '\D', '')
    if ($stuck -gt 0) { Write-Warn "$stuck container(s) are Created or exited non-zero" }

    Write-Step 8 10 'HTTPS front door'
    $code = Invoke-PdcHttp -Url ($script:Cfg.PDC_HOST + '/')
    if ($code -match '^(200|301|302|303|307)$') { Set-CkPass 'http' "HTTP $code" }
    elseif ($code -eq '404') { Set-CkFail 'http' '404 - Traefik up, no backends'; Write-Hint '.\pdc-remote.ps1 unstick' }
    elseif ($code -eq '000') { Set-CkFail 'http' 'no response'; Write-Hint '.\pdc-remote.ps1 status' }
    else { Set-Ck 'http' 'warn' "HTTP $code"; Write-Warn "unexpected HTTP $code" }

    Write-Step 9 10 "Keycloak realm $($script:Cfg.KC_REALM)"
    $kc = Invoke-PdcHttp -Url ($script:Cfg.PDC_HOST + '/keycloak/realms/' + $script:Cfg.KC_REALM + '/.well-known/openid-configuration')
    if ($kc -eq '200') { Set-CkPass 'kc' 'realm responds' }
    elseif ($kc -eq '404') { Set-CkFail 'kc' "realm $($script:Cfg.KC_REALM) not found"; Write-Hint 'the realm import may still be running - retry: verify' }
    else { Set-Ck 'kc' 'warn' "HTTP $kc"; Write-Warn "Keycloak returned $kc" }
    Write-Line ''
}

function Invoke-Resume {
    Write-Banner 'Resume'
    Show-Ck
    $next = Get-FirstIncomplete
    Write-Line ''
    switch ($next) {
        ''      { Write-Ok 'nothing outstanding - the last reset verified clean' }
        'cfg'   { Write-Info 'start at: .\pdc-remote.ps1 config' }
        'ssh'   { Write-Info 'start at: .\pdc-remote.ps1 enroll, then ssh-test' }
        'priv'  { Write-Info 'start at: .\pdc-remote.ps1 priv-test (see also: sudo-help)' }
        'dir'   { Write-Info 'start at: .\pdc-remote.ps1 doctor' }
        'up'    { Write-Info 'start at: .\pdc-remote.ps1 upload' }
        'run'   { Write-Warn 'the reset itself never completed'; Write-Info 're-run: .\pdc-remote.ps1 reset' }
        'os'    { Write-Warn 'OpenSearch security never initialised'; Write-Info 'safest path is a fresh: .\pdc-remote.ps1 reset' }
        'app'   { Write-Info 'app tier never came up - try: .\pdc-remote.ps1 unstick' }
        'http'  { Write-Info 'front door still 404 - try: .\pdc-remote.ps1 unstick' }
        'kc'    { Write-Info 'Keycloak realm not answering yet - try: .\pdc-remote.ps1 verify' }
    }
    Write-Line ''
}

# ===========================================================================
#  TOKEN AND LICENCE
# ===========================================================================
function Get-PdcToken {
    param([string] $User, [string] $Password)
    $url = $script:Cfg.PDC_HOST + '/keycloak/realms/' + $script:Cfg.KC_REALM + '/protocol/openid-connect/token'
    $resp = & curl.exe -sk --max-time 20 --resolve "$($script:Cfg.PDC_FQDN):443:$($script:Cfg.VM_HOST)" `
        -X POST $url `
        -d "client_id=$($script:Cfg.KC_CLIENT)" -d 'grant_type=password' -d "username=$User" `
        --data-urlencode "password=$Password"
    return ($resp -join '')
}

function Invoke-Token {
    Write-Banner ("Get a JWT for " + $script:Cfg.PDC_HOST + $script:Cfg.SWAGGER_PATH)
    Invoke-Render 'token-intro' @{ KC_REALM = $script:Cfg.KC_REALM; KC_CLIENT = $script:Cfg.KC_CLIENT }
    Write-Line ''
    $u = Read-Answer 'PDC username (NOT an email address)' $script:Cfg.PDC_ADMIN_USER
    $pw = Read-Secret "password for $u"
    if (-not $pw) { Write-Bad 'empty password - aborted'; return }
    Write-Line ''
    Write-Info ("POST " + $script:Cfg.PDC_HOST + '/keycloak/realms/' + $script:Cfg.KC_REALM + '/protocol/openid-connect/token')
    $resp = Get-PdcToken -User $u -Password $pw
    $pw = $null
    $tok = ''
    if ($resp -match '"access_token"\s*:\s*"([^"]+)"') { $tok = $Matches[1] }
    if (-not $tok) {
        Write-Bad 'no access_token returned'
        Write-Plain ($resp.Substring(0, [Math]::Min(600, $resp.Length)))
        Write-Line ''
        if ($resp -match 'invalid_grant')       { Write-Hint 'wrong username or password, or the account is disabled' }
        elseif ($resp -match 'unauthorized_client') { Write-Hint "client '$($script:Cfg.KC_CLIENT)' does not allow the direct-access-grant flow" }
        elseif ($resp -match 'invalid_client')  { Write-Hint "client '$($script:Cfg.KC_CLIENT)' is wrong for this build - check the Keycloak admin console" }
        elseif (-not $resp)                     { Write-Hint 'no response at all - is PDC up? .\pdc-remote.ps1 status' }
        else { Write-Hint "realm '$($script:Cfg.KC_REALM)' may be wrong - check: .\pdc-remote.ps1 health" }
        return
    }
    Write-Ok 'token acquired'

    # Decode the payload for subject and expiry. base64url -> base64, then pad.
    $payload = $tok.Split('.')[1].Replace('-', '+').Replace('_', '/')
    switch ($payload.Length % 4) { 2 { $payload += '==' } 3 { $payload += '=' } }
    $json = ''
    try { $json = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($payload)) } catch { }
    if ($json -match '"preferred_username"\s*:\s*"([^"]+)"') { Write-Kv 'subject' $Matches[1] }
    if ($json -match '"exp"\s*:\s*(\d+)') {
        $exp = [datetimeoffset]::FromUnixTimeSeconds([int64]$Matches[1]).LocalDateTime
        $mins = [int]($exp - (Get-Date)).TotalMinutes
        Write-Kv 'expires' ($exp.ToString('HH:mm:ss') + " - in $mins minutes")
    }
    Write-Kv 'length' ("$($tok.Length) characters")

    $jwtPath = Join-Path $script:Here '.state\token.jwt'
    Set-Content -Path $jwtPath -Value $tok -Encoding ascii -NoNewline
    & icacls.exe $jwtPath /inheritance:r | Out-Null
    & icacls.exe $jwtPath /grant:r ("$env:USERNAME" + ':R') | Out-Null
    if (Set-Clip ("Bearer " + $tok)) { Write-Ok "'Bearer <token>' copied to the Windows clipboard" }
    Write-Line ''
    Invoke-Render 'token-swagger' @{
        PDC_HOST     = $script:Cfg.PDC_HOST
        DEVICE_ID    = $script:Cfg.DEVICE_ID
        STATE_DIR    = (Join-Path $script:Here '.state')
        KC_REALM     = $script:Cfg.KC_REALM
        KC_CLIENT    = $script:Cfg.KC_CLIENT
        SWAGGER_PATH = $script:Cfg.SWAGGER_PATH
        LICENSE_PATH = $script:Cfg.LICENSE_PATH
    }
}

function Invoke-License {
    Write-Banner 'Offline licence upload from a file on the VM'
    if (-not (Assert-VmUser)) { return }
    if (-not $script:Cfg.LICENSE_BIN) {
        Write-Bad 'LICENSE_BIN is not set'
        Write-Hint 'set it in pdc-remote.env to a path ON THE VM, or use Swagger: .\pdc-remote.ps1 token'
        return
    }
    if (-not (Test-Remote ('[ -f "' + $script:Cfg.LICENSE_BIN + '" ]'))) {
        Write-Bad "$($script:Cfg.LICENSE_BIN) not found on the VM"
        return
    }
    Write-Kv 'licence' ($script:Cfg.LICENSE_BIN + '  (on the VM)')
    Write-Kv 'device'  $script:Cfg.DEVICE_ID
    Write-Kv 'user'    ("$($script:Cfg.PDC_ADMIN_USER) @ realm $($script:Cfg.KC_REALM)")
    Write-Note 'the password is read with echo off and never stored'
    $pw = Read-Secret 'PDC admin password'
    if (-not $pw) { Write-Bad 'empty password - aborted'; return }
    Write-Line ''
    Write-Info 'requesting a token...'
    $resp = Get-PdcToken -User $script:Cfg.PDC_ADMIN_USER -Password $pw
    $pw = $null
    $tok = ''
    if ($resp -match '"access_token"\s*:\s*"([^"]+)"') { $tok = $Matches[1] }
    if (-not $tok) {
        Write-Bad 'token request failed'
        Write-Hint 'wrong password, or the realm is not up yet - try: .\pdc-remote.ps1 health'
        return
    }
    Write-Ok 'token acquired'
    Write-Info 'uploading...'
    $cmd = "curl -sk -X POST '" + $script:Cfg.PDC_HOST + $script:Cfg.LICENSE_PATH + "' -H 'Authorization: Bearer $tok' -F 'deviceId=$($script:Cfg.DEVICE_ID)' -F 'fileData=@$($script:Cfg.LICENSE_BIN);type=application/octet-stream'"
    foreach ($l in (Invoke-Remote -Command $cmd -Merge)) { Write-Line ('  ' + $l) }
    Write-Line ''
    Write-Ok 'upload request sent - confirm it in the PDC UI under Administration'
}

# ===========================================================================
#  STATE
# ===========================================================================
function Invoke-Checkpoints {
    Write-Banner 'Checkpoints'
    Show-Ck
    $n = Get-FirstIncomplete
    Write-Line ''
    if (-not $n) { Write-Ok 'all clear' }
    else { Write-Info ("first incomplete: $n - " + $script:CkDesc[$n] + ".  See: .\pdc-remote.ps1 resume") }
    Write-Line ''
}

function Invoke-Clean {
    Clear-Ck
    Write-Ok 'checkpoints cleared (config and logs kept)'
}
function Invoke-CleanLogs {
    $d = Join-Path $script:Here 'logs'
    if (Test-Path $d) { Remove-Item $d -Recurse -Force }
    Write-Ok 'logs deleted'
}
function Invoke-DistClean {
    Invoke-Clean
    Invoke-CleanLogs
    if (Test-Path $script:ConfigFile) { Remove-Item $script:ConfigFile -Force }
    $s = Join-Path $script:Here '.state'
    if (Test-Path $s) { Remove-Item $s -Recurse -Force }
    Write-Ok 'config and state removed - next run starts from: .\pdc-remote.ps1 config'
}

# ===========================================================================
#  DISPATCH
# ===========================================================================
switch ($Command.ToLower()) {
    'help'          { Invoke-Help }
    'usage'         { Invoke-Help }
    'version'       { Invoke-Version }
    'config'        { Invoke-Config }
    'show-config'   { Invoke-ShowConfig }
    'probe'         { Invoke-Probe }
    'enable-ssh'    { Invoke-EnableSsh }
    'wait-ssh'      { Invoke-WaitSsh }
    'keygen'        { Invoke-Keygen }
    'import-wsl-key'{ Invoke-ImportWslKey }
    'enroll'        { Invoke-Enroll }
    'enroll-http'   { Invoke-EnrollHttp }
    'ssh-test'      { Invoke-SshTest }
    'priv-test'     { Invoke-PrivTest }
    'shell'         { Invoke-Shell }
    'doctor'        { Invoke-Doctor }
    'sudo-help'     { Invoke-SudoHelp }
    'env-check'     { Invoke-EnvCheck }
    'env-fix'       { Invoke-EnvFix }
    'status'        { Invoke-Status }
    'ps'            { Invoke-Status }
    'health'        { Invoke-Health }
    'logs'          { Invoke-Logs }
    'unstick'       { Invoke-Unstick }
    'plan'          { Invoke-Plan }
    'dry-run'       { Invoke-DryRun }
    'backup'        { Invoke-Backup }
    'upload'        { Invoke-Upload | Out-Null }
    'reset'         { Invoke-Reset }
    'reset-keep-opensearch' { $script:Cfg.RESET_FLAGS = '--keep-opensearch'; Invoke-Reset }
    'verify'        { Invoke-Verify }
    'resume'        { Invoke-Resume }
    'token'         { Invoke-Token }
    'license'       { Invoke-License }
    'licence'       { Invoke-License }
    'checkpoints'   { Invoke-Checkpoints }
    'clean'         { Invoke-Clean }
    'clean-logs'    { Invoke-CleanLogs }
    'distclean'     { Invoke-DistClean }
    default {
        Write-Bad "unknown command: $Command"
        Write-Hint 'run: .\pdc-remote.ps1 help'
        exit 1
    }
}
