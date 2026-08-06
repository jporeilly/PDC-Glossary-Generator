<#
.SYNOPSIS
    Install Ollama if missing, then pull the ONE model this machine can run.

.DESCRIPTION
    Optional by design: the app also drives Anthropic, OpenAI/Azure and Gemini
    from its Settings page, so a machine without Ollama is a configuration
    choice, not a broken install. Nothing here fails the installation.

    WHICH model is not decided here. It comes from the app's own
    llm_detect.recommend(), which sizes to the hardware - VRAM first, aggregating
    multi-GPU, then RAM, then a CPU floor. Naming a model in this script would be
    a second rule quietly disagreeing with what the app's Settings page
    recommends, and the cost of being wrong is real in both directions: a 32B
    model on a laptop is unusable, a 1B model on a workstation is needlessly bad
    at definitions.

    One model, not a set. Each is several GB, and pulling a spread "just in case"
    turns a workshop setup into a long download of things nobody will run.

.PARAMETER Model
    Pull this model instead of the detected one.

.PARAMETER SkipInstall
    Do not install Ollama; only pull, and only if it is already running.

.NOTES
    Windows PowerShell 5.1+. ASCII-only on purpose.
#>
[CmdletBinding()]
param(
    [string]$Model,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

. (Join-Path $PSScriptRoot "lib\common.ps1")

function Ok($m)   { Write-Host "  [ok] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  [!]  $m" -ForegroundColor Yellow }
function Say($m)  { Write-Host "  $m" -ForegroundColor DarkGray }

Write-Host ""
Write-Host "  Ollama (optional local AI runtime)" -ForegroundColor Cyan

function Test-OllamaUp {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $iar = $c.BeginConnect("127.0.0.1", 11434, $null, $null)
        $up = $iar.AsyncWaitHandle.WaitOne(1500, $false)
        if ($up) { $c.EndConnect($iar) }
        $c.Close()
        return $up
    } catch { return $false }
}

$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama -and -not $SkipInstall) {
    Say "not installed - trying winget"
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Warn "winget not available - install Ollama manually from https://ollama.com"
        exit 0            # optional component: never fail the install
    }
    # --silent so an unattended install does not stop on a UI prompt; the
    # accept flags are required or winget waits for agreement text.
    & winget install -e --id Ollama.Ollama --silent `
        --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        Warn "winget could not install Ollama (exit $LASTEXITCODE) - install it manually"
        exit 0
    }
    Ok "Ollama installed"
    # winget updates the machine PATH, but not this already-running process.
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
}

if (-not $ollama) {
    Warn "Ollama is not available - skipping the model pull"
    exit 0
}

if (-not (Test-OllamaUp)) {
    Say "starting the Ollama service"
    try { Start-Process -FilePath $ollama.Source -ArgumentList "serve" -WindowStyle Hidden } catch {}
    # The service needs a moment before it accepts connections; a pull issued
    # too early fails with a confusing connection error.
    foreach ($i in 1..15) {
        Start-Sleep -Milliseconds 700
        if (Test-OllamaUp) { break }
    }
}
if (-not (Test-OllamaUp)) {
    Warn "Ollama is installed but not answering on 11434 - start it, then re-run this script"
    exit 0
}

if (-not $Model) {
    $pyExe = Resolve-PyExe $PSScriptRoot
    $appPy = Resolve-AppPy $PSScriptRoot
    if ($pyExe -and $appPy) {
        # SINGLE quotes inside the Python: PowerShell strips embedded double
        # quotes when passing arguments to a native executable, so dict keys
        # written with "..." arrive as bare names and die with NameError.
        $probe = @'
import json, sys
sys.path.insert(0, sys.argv[1])
import llm_detect as d
ram = d.total_ram_gb()
name, vram, count = d.nvidia_gpu()
r = d.recommend(ram, vram, count)
print(json.dumps({'model': r.model, 'reason': r.reason}))
'@
        try {
            $out = & $pyExe -c $probe $appPy 2>$null
            if ($LASTEXITCODE -eq 0 -and $out) {
                $d = $out | ConvertFrom-Json
                $Model = $d.model
                Say $d.reason
            }
        } catch {}
    }
}

if (-not $Model) {
    Warn "could not size a model for this machine - open the app's Settings page, which recommends one"
    exit 0
}

# Already there? Pulling again is a no-op but downloads nothing only if Ollama
# says so; checking first keeps the installer log honest about what it did.
$have = @()
try {
    $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
    if ($tags -and ($tags.PSObject.Properties.Name -contains "models")) {
        $have = @($tags.models | ForEach-Object { $_.name })
    }
} catch {}

if ($have -contains $Model) {
    Ok "$Model already present - nothing to download"
    exit 0
}

Say "pulling $Model (several GB - this is the long part)"
& $ollama.Source pull $Model
if ($LASTEXITCODE -ne 0) {
    Warn "pull failed (exit $LASTEXITCODE) - run: ollama pull $Model"
    exit 0
}
Ok "$Model ready"
Write-Host ""

exit 0
