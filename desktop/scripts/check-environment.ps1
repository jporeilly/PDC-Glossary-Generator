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
      - PDC unreachable is not fatal: the vhost is normally configured after
        install, and most of the app (scan, review, govern) works offline.

    Treating those as hard failures would teach people to ignore the output,
    which costs more than the check is worth.

.PARAMETER PdcUrl
    PDC base URL to probe. Defaults to $env:PDC_BASE_URL, then to the value in
    glossary_generator\.env, then https://pentaho.io.

.PARAMETER Json
    Emit the results as JSON only - for piping into a provisioning log.

.EXAMPLE
    .\check-environment.ps1

.EXAMPLE
    .\check-environment.ps1 -PdcUrl https://pentaho.io -Json

.NOTES
    Windows PowerShell 5.1+. ASCII-only on purpose.
#>
[CmdletBinding()]
param(
    [string]$PdcUrl,
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

$desktopDir = Split-Path -Parent $PSScriptRoot
$repoRoot   = Split-Path -Parent $desktopDir

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

# Python. The packaged app carries its own, so this is only about a checkout.
$vendored = Join-Path $desktopDir "src-tauri\vendor\python\python.exe"
if (Test-Path -LiteralPath $vendored) {
    $ver = & $vendored -c "import sys;print('.'.join(map(str,sys.version_info[:3])))" 2>$null
    Report "Python (vendored)" "OK" "$ver - shipped with the app, nothing to install"

    # The imports that actually break in a packaged build. A runtime that runs
    # but cannot import oracledb is the failure this whole check exists for.
    $probe = & $vendored -c "import uvicorn,fastapi,psycopg2,oracledb,boto3;print('ok')" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Report "Vendored dependencies" "OK" "uvicorn, fastapi, psycopg2, oracledb, boto3"
    } else {
        Report "Vendored dependencies" "FAIL" "the vendored runtime cannot import its own packages" `
            "cd desktop; npm run fetch:python -- -Force"
    }
} else {
    $pyCmd = $null
    $pyVer = $null
    foreach ($cand in @("python", "py -3")) {
        try {
            $v = & ([scriptblock]::Create("$cand -c `"import sys;print('.'.join(map(str,sys.version_info[:3]))) if sys.version_info[:2]>=(3,9) else sys.exit(1)`"")) 2>$null
            if ($LASTEXITCODE -eq 0 -and $v) { $pyCmd = $cand; $pyVer = $v.Trim(); break }
        } catch {}
    }
    if ($pyCmd) {
        Report "Python 3.9+" "OK" "$pyVer via '$pyCmd'"
    } else {
        Report "Python 3.9+" "FAIL" "not found - needed to run from a checkout" `
            "winget install -e --id Python.Python.3.12"
    }
    Report "Python (vendored)" "SKIP" "not a packaged install - run.ps1 builds a venv instead"
}

# -- state -------------------------------------------------------------------
Say ""
Say "  State" "Cyan"

# Mirrors glossary_generator\paths.py: explicit env var, else the app dir when
# writable, else per-user. Kept deliberately in step with that file.
if ($env:GLOSSARY_STATE_DIR) {
    $stateDir = $env:GLOSSARY_STATE_DIR
    $stateWhy = "GLOSSARY_STATE_DIR"
} elseif (Test-Path -LiteralPath (Join-Path $repoRoot "glossary_generator\api.py")) {
    $stateDir = Join-Path $repoRoot "glossary_generator"
    $stateWhy = "app directory (checkout)"
} else {
    $stateDir = Join-Path $env:APPDATA "com.pentaho.pdc-glossary"
    $stateWhy = "per-user (packaged install)"
}

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

if ($ollamaUp) {
    $models = @()
    try {
        $tags = Invoke-RestMethod -Uri "$ollamaUrl/api/tags" -TimeoutSec 4 -ErrorAction Stop
        if ($tags -and $tags.PSObject.Properties.Name -contains "models") {
            $models = @($tags.models | ForEach-Object { $_.name })
        }
    } catch {}
    if ($models.Count -gt 0) {
        Report "Ollama" "OK" ("" + $models.Count + " model(s): " + (($models | Select-Object -First 3) -join ", "))
    } else {
        # Up but empty is the trap: the app connects, then every generate call
        # fails, which reads as "the AI is broken" rather than "no model".
        Report "Ollama" "WARN" "running on 11434 but NO model pulled" "ollama pull llama3.2:3b"
    }
} else {
    Report "Ollama" "WARN" "not running on 11434" `
        "winget install -e --id Ollama.Ollama; ollama pull llama3.2:3b"
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

# -- PDC ---------------------------------------------------------------------
Say ""
Say "  Pentaho Data Catalog (optional at install time)" "Cyan"

if (-not $PdcUrl) { $PdcUrl = $env:PDC_BASE_URL }
if (-not $PdcUrl) {
    $envFile = Join-Path $repoRoot "glossary_generator\.env"
    if (Test-Path -LiteralPath $envFile) {
        $line = Get-Content -LiteralPath $envFile |
            Where-Object { $_ -match '^\s*PDC_BASE_URL\s*=' } | Select-Object -First 1
        if ($line) { $PdcUrl = ($line -split "=", 2)[1].Trim().Trim('"').Trim("'") }
    }
}
if (-not $PdcUrl) { $PdcUrl = "https://pentaho.io" }

# PDC routes by vhost. A bare IP answers 401 on every path, which looks like bad
# credentials and sends people to reset passwords that were never wrong.
if ($PdcUrl -match '^https?://(\d{1,3}\.){3}\d{1,3}(:\d+)?/?$') {
    Report "PDC URL" "WARN" "$PdcUrl is a bare IP - PDC routes by vhost and will answer 401 everywhere" `
        "use the hostname, e.g. https://pentaho.io"
} else {
    Report "PDC URL" "OK" $PdcUrl
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
        "configure the vhost later; scan, review and govern work without PDC"
}

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
