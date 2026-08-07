<#
.SYNOPSIS
    Check the machine can run the Glossary Generator, and say what to do when
    it cannot.

.DESCRIPTION
    Written to be run AFTER install, by whoever is setting up a workshop
    machine, and to be readable by someone who did not build the app.

    It reports rather than blocks. Only two things are genuine FAILures - the
    WebView2 runtime and a usable Python - because without them the window does
    not open at all. Everything else is a WARN with a fix attached:

      - Ollama absent is not fatal: the app also drives Anthropic, OpenAI/Azure
        and Gemini, selected on the Settings page.
      - PDC unreachable is not fatal: the server is normally configured after
        install, and most of the app (scan, review, govern) works offline.

    Treating those as hard failures would teach people to ignore the output,
    which costs more than the check is worth.

.PARAMETER PdcUrl
    PDC base URL to probe. Works against ANY PDC server - there is no built-in
    default, deliberately. Resolution order: this parameter, $env:PDC_BASE_URL,
    the app's own saved connection (settings.json "pdc_base", written by the
    Connections page), glossary_generator\.env, then a prompt. If none of those
    answer, the PDC checks are skipped rather than guessing a host.

.PARAMETER NoPrompt
    Never ask for a PDC URL. For unattended/provisioning runs.

.PARAMETER Json
    Emit the results as JSON only - for piping into a provisioning log. Implies
    -NoPrompt.

.EXAMPLE
    .\check-environment.ps1

.EXAMPLE
    .\check-environment.ps1 -PdcUrl https://catalog.example.com

.EXAMPLE
    .\check-environment.ps1 -NoPrompt -Json

.NOTES
    Windows PowerShell 5.1+. ASCII-only on purpose.
#>
[CmdletBinding()]
param(
    [string]$PdcUrl,
    [switch]$NoPrompt,
    [switch]$Json
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$script:Checks   = @()
$script:Failures = 0
$script:Warnings = 0
$script:Fixes    = @()

function Say {
    param([string]$Text = "", [string]$Colour = "Gray")
    if (-not $Json) { Write-Host $Text -ForegroundColor $Colour }
}

function Report {
    param(
        [string]$Name,
        [ValidateSet("OK", "FAIL", "WARN", "SKIP")][string]$State,
        [string]$Detail = "",
        [string]$Fix = ""
    )
    $script:Checks += [ordered]@{ name = $Name; state = $State; detail = $Detail; fix = $Fix }
    if (-not $Json) {
        $colour = @{ OK = "Green"; FAIL = "Red"; WARN = "Yellow"; SKIP = "DarkGray" }[$State]
        Write-Host ("  [{0,-4}] " -f $State) -ForegroundColor $colour -NoNewline
        Write-Host ("{0,-30}" -f $Name) -NoNewline
        Write-Host $Detail -ForegroundColor DarkGray
    }
    if ($State -eq "FAIL") {
        $script:Failures++
        if ($Fix) { $script:Fixes += "  # $Name`n  $Fix" }
    } elseif ($State -eq "WARN") {
        $script:Warnings++
        if ($Fix) { $script:Fixes += "  # $Name (optional)`n  $Fix" }
    }
}

# 127.0.0.1 rather than "localhost": localhost can resolve to ::1 first, and the
# probe then reports a healthy service as down.
function Test-Port([string]$TargetHost, [int]$Port, [int]$TimeoutMs = 1500) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $iar = $c.BeginConnect($TargetHost, $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
        if ($ok) { $c.EndConnect($iar) }
        $c.Close()
        return $ok
    } catch { return $false }
}

. (Join-Path $PSScriptRoot "lib\common.ps1")

$desktopDir = Split-Path -Parent $PSScriptRoot
$repoRoot   = Split-Path -Parent $desktopDir

# Through the SHARED resolvers, which understand both layouts.
#
# This script used to carry its own copy of these rules, hardcoded to the
# checkout - $desktopDir\src-tauri\vendor\python. In an installed layout that
# path does not exist (the runtime is at $INSTDIR\python), so the check reported
# "Python 3.9+ not found" on a perfectly good installation and called it a
# blocking failure. The one script whose job is to tell you whether the install
# is sound was the one that could not find it.
$script:AppPy = Resolve-AppPy $PSScriptRoot

Say ""
Say "  PDC Glossary Generator - environment check" "Cyan"
Say "  Reports what is missing and how to fix it. Only WebView2 and Python are" "DarkGray"
Say "  hard requirements; everything else is optional and says so." "DarkGray"
Say ""

# -- the two things that stop the window opening ----------------------------
Say "  Required" "Cyan"

# WebView2. The installer bundles the bootstrapper, so this should already be
# satisfied on a machine that ran it; the check matters for a machine being
# prepared for the app, or one where the runtime was removed.
$wv2Keys = @(
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
    "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
    "HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
)
$wv2 = $null
foreach ($k in $wv2Keys) {
    if (Test-Path $k) {
        try {
            $v = (Get-ItemProperty -Path $k -ErrorAction Stop).pv
            if ($v) { $wv2 = $v; break }
        } catch {}
    }
}
if ($wv2) {
    Report "WebView2 runtime" "OK" $wv2
} else {
    Report "WebView2 runtime" "FAIL" "not found - the app window cannot render" `
        "winget install -e --id Microsoft.EdgeWebView2Runtime"
}

# Python. Resolve-PyExe knows both layouts: $INSTDIR\python for an install,
# desktop\src-tauri\vendor\python for a checkout, then PATH.
$script:PyExe = Resolve-PyExe $PSScriptRoot
$bundled = $script:PyExe -and (Test-Path -LiteralPath $script:PyExe) -and
           ($script:PyExe -like "*\python\python.exe")

if (-not $script:PyExe) {
    Report "Python 3.9+" "FAIL" "no interpreter found, bundled or on PATH" `
        "reinstall the app, or install Python: winget install -e --id Python.Python.3.12"
} else {
    $ver = & $script:PyExe -c "import sys;print('.'.join(map(str,sys.version_info[:3])))" 2>$null
    if ($bundled) {
        Report "Python (bundled)" "OK" ("" + $ver + " - shipped with the app, nothing to install")
    } else {
        Report "Python 3.9+" "OK" ("" + $ver + " - from PATH (running from a checkout)")
    }

    # The imports that actually break in a packaged build. A runtime that starts
    # but cannot import oracledb is the failure this whole check exists for, and
    # confirming python.exe merely EXISTS would miss it entirely.
    $probe = & $script:PyExe -c "import uvicorn,fastapi,psycopg2,oracledb,boto3;print('ok')" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Report "Python dependencies" "OK" "uvicorn, fastapi, psycopg2, oracledb, boto3"
    } elseif ($bundled) {
        Report "Python dependencies" "FAIL" "the bundled runtime cannot import its own packages" `
            "the install is incomplete - reinstall"
    } else {
        Report "Python dependencies" "WARN" "not importable from this interpreter" `
            "run.ps1 builds a venv with them; this only matters for a checkout"
    }
}

# -- state -------------------------------------------------------------------
Say ""
Say "  State" "Cyan"

# Through the shared resolver, for the same reason as the interpreter above: a
# check that probes a different directory from the one the app writes to is
# worse than no check.
$state    = Resolve-StateDir $PSScriptRoot
$stateDir = $state.Path
$stateWhy = $state.Why

$writable = $false
try {
    if (-not (Test-Path -LiteralPath $stateDir)) {
        New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
    }
    # Probe by writing. os.access / ACL inspection both lie about Program Files.
    $probeFile = Join-Path $stateDir (".writeprobe-" + [Guid]::NewGuid().ToString("N"))
    Set-Content -LiteralPath $probeFile -Value "x" -Encoding ASCII
    Remove-Item -LiteralPath $probeFile -Force
    $writable = $true
} catch {}

if ($writable) {
    Report "State directory" "OK" "$stateDir ($stateWhy)"
} else {
    Report "State directory" "FAIL" "$stateDir is not writable" `
        "set GLOSSARY_STATE_DIR to a writable path, e.g. `$env:GLOSSARY_STATE_DIR='$env:APPDATA\PDC-Glossary'"
}

$freeGb = $null
try {
    $drive = (Get-Item -LiteralPath $stateDir).PSDrive
    if ($drive -and $drive.Free) { $freeGb = [math]::Round($drive.Free / 1GB, 1) }
} catch {}
if ($null -eq $freeGb) {
    Report "Disk space" "SKIP" "could not determine free space"
} elseif ($freeGb -lt 2) {
    Report "Disk space" "WARN" "$freeGb GB free - scans and snapshots need room" "free up space on the state drive"
} else {
    Report "Disk space" "OK" "$freeGb GB free"
}

# -- LLM ---------------------------------------------------------------------
Say ""
Say "  Language model (optional - the app runs without one)" "Cyan"

$ollamaUrl = $env:OLLAMA_URL
if (-not $ollamaUrl) { $ollamaUrl = "http://127.0.0.1:11434" }
$ollamaUp = Test-Port "127.0.0.1" 11434

# WHICH model to pull is the app's decision, not this script's. llm_detect.py
# sizes a model to the actual hardware - VRAM first, then RAM, aggregating
# multi-GPU - and naming one here would be a second rule that quietly disagrees
# with what the app's own Settings page recommends. Recommending a 32B model to
# a laptop, or a 1B model to the 2x3060 rig, are both real costs.
$recModel  = $null
$recReason = $null
$hwDetail  = $null
if ($script:PyExe -and $script:AppPy) {
    # SINGLE quotes inside the Python. PowerShell strips embedded double quotes
    # when passing arguments to a native executable, so a dict written with "..."
    # keys arrives as bare names and dies with NameError.
    $probe = @'
import json, sys
sys.path.insert(0, sys.argv[1])
import llm_detect as d
ram = d.total_ram_gb()
name, vram, count = d.nvidia_gpu()
r = d.recommend(ram, vram, count)
print(json.dumps({'model': r.model, 'reason': r.reason, 'ram': ram,
                  'vram': vram, 'gpu': name, 'gpus': count}))
'@
    try {
        $out = & $script:PyExe -c $probe $script:AppPy 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) {
            $d = $out | ConvertFrom-Json
            $recModel  = $d.model
            $recReason = $d.reason
            if ($d.gpu) {
                $hwDetail = "" + $d.gpu + ", " + $d.vram + " GB VRAM"
            } elseif ($d.ram) {
                $hwDetail = "CPU only, " + $d.ram + " GB RAM"
            }
        }
    } catch {}
}
if ($recModel) {
    Report "Hardware / model sizing" "OK" ("$hwDetail -> $recModel")
} else {
    Report "Hardware / model sizing" "SKIP" "could not run the app's detector - see the Settings page"
}

# The fix text follows the detector. With no detector we say where to look
# rather than inventing a model name.
if ($recModel) {
    $pullFix = "ollama pull $recModel   # $recReason"
} else {
    $pullFix = "open the app's Settings page - it recommends a model for this machine"
}

if ($ollamaUp) {
    $models = @()
    try {
        $tags = Invoke-RestMethod -Uri "$ollamaUrl/api/tags" -TimeoutSec 4 -ErrorAction Stop
        if ($tags -and $tags.PSObject.Properties.Name -contains "models") {
            $models = @($tags.models | ForEach-Object { $_.name })
        }
    } catch {}
    if ($models.Count -eq 0) {
        # Up but empty is the trap: the app connects, then every generate call
        # fails, which reads as "the AI is broken" rather than "no model".
        Report "Ollama" "WARN" "running on 11434 but NO model pulled" $pullFix
    } elseif ($recModel -and ($models -notcontains $recModel)) {
        # Has models, but not the one sized to this hardware. Not a problem -
        # any of them will work - so this is information, not a warning.
        Report "Ollama" "OK" ("" + $models.Count + " model(s); recommended $recModel not among them")
    } else {
        Report "Ollama" "OK" ("" + $models.Count + " model(s): " + (($models | Select-Object -First 3) -join ", "))
    }
} else {
    Report "Ollama" "WARN" "not running on 11434" `
        ("winget install -e --id Ollama.Ollama" + [Environment]::NewLine + "  " + $pullFix)
}

# Hosted providers: presence only. Never print or log a key.
$hosted = @(
    @{ Name = "Anthropic";      Var = "ANTHROPIC_API_KEY" },
    @{ Name = "OpenAI / Azure"; Var = "OPENAI_API_KEY" },
    @{ Name = "Google Gemini";  Var = "GOOGLE_API_KEY" }
)
$anyHosted = $false
foreach ($h in $hosted) {
    if ([Environment]::GetEnvironmentVariable($h.Var)) { $anyHosted = $true }
}
if ($anyHosted) {
    $set = ($hosted | Where-Object { [Environment]::GetEnvironmentVariable($_.Var) } |
            ForEach-Object { $_.Name }) -join ", "
    Report "Hosted LLM providers" "OK" "key present for: $set"
} elseif (-not $ollamaUp) {
    Report "Hosted LLM providers" "WARN" "no provider key set and Ollama is down - AI features will be unavailable" `
        "either start Ollama, or set a provider key on the Settings page"
} else {
    Report "Hosted LLM providers" "SKIP" "not configured - using Ollama"
}

# -- Cloudflare Access --------------------------------------------------------
# Presence only, never the values.
#
# A service token is the only way a NON-BROWSER client gets through Access:
# authenticating in a browser sets a cookie on that browser session, and the app
# is a separate HTTP client that cannot complete an interactive login.
#
# The trap this checks for: the app is launched from the Start menu, so it
# inherits nothing from a PowerShell session. "$env:CF_ACCESS_CLIENT_ID = ..."
# in a terminal reaches only that terminal - the variables must be PERSISTENT
# (setx, or System Properties > Environment Variables) and the app restarted.
$cfId  = [Environment]::GetEnvironmentVariable("CF_ACCESS_CLIENT_ID", "User")
if (-not $cfId) { $cfId = [Environment]::GetEnvironmentVariable("CF_ACCESS_CLIENT_ID", "Machine") }
$cfSec = [Environment]::GetEnvironmentVariable("CF_ACCESS_CLIENT_SECRET", "User")
if (-not $cfSec) { $cfSec = [Environment]::GetEnvironmentVariable("CF_ACCESS_CLIENT_SECRET", "Machine") }

$sessionOnly = ($env:CF_ACCESS_CLIENT_ID -and -not $cfId)

# A Client ID always ends ".access". Checking the SHAPE catches the two ways
# this silently looks configured: the template pasted verbatim (<id>.access), and
# a truncated or half-copied value. Presence alone would report both as OK.
$looksTemplated = ($cfId -match "[<>]") -or ($cfSec -match "[<>]")
$idShapeOk      = $cfId -match "\.access$"

if ($cfId -and $cfSec -and $looksTemplated) {
    Report "Cloudflare Access token" "WARN" "still contains <placeholders> - the template was set, not the values" `
        "re-run setx with the real Client ID and Secret from Zero Trust > Access > Service Auth"
} elseif ($cfId -and $cfSec -and -not $idShapeOk) {
    Report "Cloudflare Access token" "WARN" "Client ID does not end in '.access' - check it was copied whole" `
        "Zero Trust > Access > Service Auth shows the full Client ID"
} elseif ($cfId -and $cfSec) {
    Report "Cloudflare Access token" "OK" "service token set for this user/machine"
} elseif ($sessionOnly) {
    Report "Cloudflare Access token" "WARN" "set in THIS shell only - the app will not see it" `
        "setx CF_ACCESS_CLIENT_ID `"<id>.access`"; setx CF_ACCESS_CLIENT_SECRET `"<secret>`"  (then restart the app)"
} elseif ($cfId -or $cfSec) {
    Report "Cloudflare Access token" "WARN" "only half the pair is set - both are required" `
        "set whichever of CF_ACCESS_CLIENT_ID / CF_ACCESS_CLIENT_SECRET is missing"
} else {
    Report "Cloudflare Access token" "SKIP" "not set - fine when PDC is reached directly, or via an Access Bypass policy"
}

# -- PDC ---------------------------------------------------------------------
Say ""
Say "  Pentaho Data Catalog (optional at install time)" "Cyan"

# NO default host. This check runs against whatever PDC the operator actually
# has, and guessing one would either probe a stranger's server or report a
# healthy machine as broken because someone else's host is down.
#
# Order: -PdcUrl, then the environment, then what the APP itself has saved
# (settings.json's pdc_base - the Connections page writes it), then .env, then
# ask. Reading the app's own setting is the point: whatever server you last
# connected to is the one worth checking.
$pdcWhy = $null
if ($PdcUrl) { $pdcWhy = "-PdcUrl" }

if (-not $PdcUrl -and $env:PDC_BASE_URL) {
    $PdcUrl = $env:PDC_BASE_URL
    $pdcWhy = "PDC_BASE_URL"
}
if (-not $PdcUrl) {
    $settingsFile = Join-Path $stateDir "settings.json"
    if (Test-Path -LiteralPath $settingsFile) {
        try {
            $cfg = Get-Content -LiteralPath $settingsFile -Raw | ConvertFrom-Json
            if ($cfg.PSObject.Properties.Name -contains "pdc_base" -and $cfg.pdc_base) {
                $PdcUrl = "" + $cfg.pdc_base
                $pdcWhy = "the app's saved connection"
            }
        } catch {}
    }
}
if (-not $PdcUrl) {
    $envFile = Join-Path $repoRoot "glossary_generator\.env"
    if (Test-Path -LiteralPath $envFile) {
        $line = Get-Content -LiteralPath $envFile |
            Where-Object { $_ -match '^\s*PDC_BASE_URL\s*=' } | Select-Object -First 1
        if ($line) {
            $PdcUrl = ($line -split "=", 2)[1].Trim().Trim('"').Trim("'")
            $pdcWhy = ".env"
        }
    }
}
# Ask, but only when a person is there to answer. -Json and -NoPrompt are for
# provisioning runs, where a blocked prompt would hang the whole job.
if (-not $PdcUrl -and -not $Json -and -not $NoPrompt -and [Environment]::UserInteractive) {
    Say ""
    Say "  No PDC server is configured yet." "DarkGray"
    Say "  Enter one to check it now, or press Enter to skip." "DarkGray"
    $answer = Read-Host "  PDC base URL (e.g. https://catalog.example.com)"
    if ($answer) {
        $PdcUrl = $answer.Trim()
        $pdcWhy = "entered now - not saved; set it on the app's Connections page to keep it"
    }
}

if (-not $PdcUrl) {
    Report "PDC" "SKIP" "no server configured - pass -PdcUrl, or set it on the Connections page"
} else {

# PDC routes by vhost. A bare IP answers 401 on every path, which looks like bad
# credentials and sends people to reset passwords that were never wrong.
if ($PdcUrl -match '^https?://(\d{1,3}\.){3}\d{1,3}(:\d+)?/?$') {
    Report "PDC URL" "WARN" "$PdcUrl is a bare IP - PDC routes by vhost and will answer 401 everywhere" `
        "use the server's hostname instead of its IP address"
} else {
    Report "PDC URL" "OK" ("$PdcUrl (from $pdcWhy)")
}

# Any HTTP answer proves reachability; 401/403 means PDC is up and asking for
# credentials, which at install time is a perfectly good result.
function Test-Pdc([string]$Url) {
    try {
        $r = Invoke-WebRequest -Uri $Url -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        return @{ Reached = $true; Detail = "HTTP " + $r.StatusCode; Tls = $true }
    } catch {
        $resp = $null
        try { $resp = $_.Exception.Response } catch {}
        if ($resp) {
            return @{ Reached = $true
                      Detail  = "HTTP " + [int]$resp.StatusCode + " - up, credentials are entered in the app"
                      Tls     = $true }
        }
        return @{ Reached = $false; Detail = $_.Exception.Message; Tls = $true }
    }
}

$pdc = Test-Pdc $PdcUrl

# A self-signed certificate is NOT unreachability, and reporting it as such
# sends people to check firewalls and DNS for a server that is answering
# perfectly well. Retry with validation off purely to tell the two apart.
if (-not $pdc.Reached -and $pdc.Detail -match 'trust relationship|SSL|TLS|certificate') {
    $saved = [System.Net.ServicePointManager]::CertificatePolicy
    try {
        Add-Type -TypeDefinition @'
using System.Net;
using System.Security.Cryptography.X509Certificates;
public class PdcCheckCertPolicy : ICertificatePolicy {
    public bool CheckValidationResult(ServicePoint sp, X509Certificate c, WebRequest r, int p) { return true; }
}
'@ -ErrorAction SilentlyContinue
        [System.Net.ServicePointManager]::CertificatePolicy = New-Object PdcCheckCertPolicy
        $retry = Test-Pdc $PdcUrl
        if ($retry.Reached) { $pdc = @{ Reached = $true; Detail = $retry.Detail; Tls = $false } }
    } finally {
        [System.Net.ServicePointManager]::CertificatePolicy = $saved
    }
}

if ($pdc.Reached -and $pdc.Tls) {
    Report "PDC reachable" "OK" $pdc.Detail
} elseif ($pdc.Reached) {
    # Expected on a lab VM. Worth naming precisely, because the same symptom on
    # a customer machine means something quite different.
    Report "PDC reachable" "WARN" ($pdc.Detail + " - certificate is not trusted (self-signed)") `
        "expected on a lab VM; trust the cert, or keep using the app's own connection settings"
} else {
    Report "PDC reachable" "WARN" "$PdcUrl - $($pdc.Detail)" `
        "check the hostname and that the server is up; scan, review and govern work without PDC"
}

}   # end: a PDC server was configured

# -- summary -----------------------------------------------------------------
if ($Json) {
    [ordered]@{
        failures = $script:Failures
        warnings = $script:Warnings
        checks   = $script:Checks
    } | ConvertTo-Json -Depth 5
    exit ([int]($script:Failures -gt 0))
}

Say ""
if ($script:Failures -eq 0 -and $script:Warnings -eq 0) {
    Write-Host "  Everything checks out." -ForegroundColor Green
} elseif ($script:Failures -eq 0) {
    Write-Host ("  Ready to run. " + $script:Warnings + " optional item(s) not configured.") -ForegroundColor Yellow
} else {
    Write-Host ("  " + $script:Failures + " blocking problem(s), " +
                $script:Warnings + " optional.") -ForegroundColor Red
}
if ($script:Fixes.Count -gt 0) {
    Say ""
    Say "  Suggested commands:" "Cyan"
    $script:Fixes | ForEach-Object { Say $_ "DarkGray" }
}
Say ""

exit ([int]($script:Failures -gt 0))
