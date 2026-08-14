<#
.SYNOPSIS
    One-shot from Windows: reseed (or verify) PDC's email-domain safe list.

.DESCRIPTION
    Ships remote/reseed-provider.sh to the VM over the pdc-remote SSH channel
    and runs it there. The domains live at provider_conf.emailDomains on the
    css-auth-proxy provider record; the working write path on PDC 11 is the
    init's own DELETE+POST with the full templated config, driven by
    EMAIL_DOMAINS in vendor/.env.default. Edit THAT list first if you are
    adding a new domain - this script applies whatever the .env seeds.

    Reads the connection from pdc-remote.env (same folder). No passwords
    cross the wire: the VM-side script uses the deployment's own stored
    credentials, on the VM.

.EXAMPLE
    .\reseed-domains.ps1 -VerifyOnly     # read-only: is azwater.gov live?
    .\reseed-domains.ps1                 # reseed from vendor/.env.default
#>
[CmdletBinding()]
param(
    [switch] $VerifyOnly
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

# minimal pdc-remote.env reader: KEY=VALUE lines, %VAR% expansion
$envPath = Join-Path $here 'pdc-remote.env'
if (-not (Test-Path $envPath)) {
    Write-Host "  [x]  $envPath not found - run .\pdc-remote.ps1 config first"
    exit 1
}
$cfg = @{}
foreach ($line in Get-Content $envPath) {
    if ($line -match '^\s*([A-Z_]+)\s*=\s*(.+?)\s*$') {
        $cfg[$Matches[1]] = [Environment]::ExpandEnvironmentVariables($Matches[2])
    }
}
foreach ($k in @('VM_HOST', 'VM_USER', 'SSH_KEY')) {
    if (-not $cfg[$k]) { Write-Host "  [x]  $k missing from pdc-remote.env"; exit 1 }
}

$script = Join-Path $here 'reseed-provider.sh'
if (-not (Test-Path $script)) { Write-Host "  [x]  $script not found"; exit 1 }

$target = "$($cfg.VM_USER)@$($cfg.VM_HOST)"
$sshArgs = @('-i', $cfg.SSH_KEY, '-o', 'StrictHostKeyChecking=accept-new', '-o', 'ConnectTimeout=8')

Write-Host "  [..] shipping reseed-provider.sh to $target"
& scp.exe @sshArgs $script "${target}:/tmp/reseed-provider.sh"
if ($LASTEXITCODE -ne 0) { Write-Host '  [x]  scp failed'; exit 1 }

$mode = ''
if ($VerifyOnly) { $mode = 'verify' }
& ssh.exe @sshArgs $target "bash /tmp/reseed-provider.sh $mode; rc=`$?; rm -f /tmp/reseed-provider.sh; exit `$rc"
exit $LASTEXITCODE
