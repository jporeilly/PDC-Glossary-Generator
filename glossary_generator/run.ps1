<#
  PDC Glossary Generator - Windows launcher (PowerShell)

  Windows equivalent of run.sh. Creates a local virtualenv (.venv), installs
  dependencies (re-installing only when requirements.txt changes), then launches
  the app with uvicorn (api:app). Nothing touches your system Python.

    .\run.ps1                    # http://127.0.0.1:5000
    .\run.ps1 -Port 8080         # choose a port
    .\run.ps1 -PyVersion 3.12    # force a Python (avoids no-wheel-yet versions)
    .\run.ps1 -BindHost 0.0.0.0  # bind all interfaces (e.g. on a lab VM)
    $env:PORT=8080; .\run.ps1    # env vars work too (HOST, PORT)

  First run only, if scripts are blocked:
    powershell -ExecutionPolicy Bypass -File .\run.ps1
  (or use run.bat, which does that for you)
#>
[CmdletBinding()]
param(
    [int]$Port,
    [string]$BindHost,     # NOTE: not -Host; $Host is reserved in PowerShell
    [string]$PyVersion     # force a specific Python, e.g. -PyVersion 3.12
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

# HOST/PORT: param > existing env > default. api.py reads these from the env.
if (-not $BindHost) { $BindHost = if ($env:HOST) { $env:HOST } else { '127.0.0.1' } }
if (-not $Port)     { $Port     = if ($env:PORT) { [int]$env:PORT } else { 5000 } }

function Ok   ($m) { Write-Host "  " -NoNewline; Write-Host "OK  " -ForegroundColor Green  -NoNewline; Write-Host $m }
function Warn ($m) { Write-Host "  " -NoNewline; Write-Host "!   " -ForegroundColor Yellow -NoNewline; Write-Host $m }
function Die  ($m) { Write-Host "  X  $m" -ForegroundColor Red; exit 1 }

Write-Host ""
$Ver = ""
try { if (Test-Path (Join-Path $PSScriptRoot "VERSION")) { $Ver = " v" + (Get-Content (Join-Path $PSScriptRoot "VERSION") -Raw).Trim() } } catch {}
Write-Host "  PDC Glossary Generator$Ver" -ForegroundColor Cyan
Write-Host "  Connect -> Review -> Dictionary -> Govern -> Resolve.  Build a Pentaho Data" -ForegroundColor DarkGray
Write-Host "  Catalog business glossary from a live data estate, then push it to PDC." -ForegroundColor DarkGray
Write-Host ""

# --- pre-flight ------------------------------------------------------------
Write-Host "  Pre-flight"

# Find a Python. Compiled deps (psycopg2-binary, mammoth) lag on wheels for the
# very newest Python, so prefer known-good 3.13/3.12/3.11 over whatever 'py -3'
# resolves to (which is the *newest*, e.g. 3.14 with no wheels yet). -PyVersion
# forces a specific one.
function Probe-Py($cand) {
    # returns the version string if $cand runs and is >= 3.9, else $null
    try {
        $v = & ([scriptblock]::Create("$cand -c `"import sys;print('.'.join(map(str,sys.version_info[:3]))) if sys.version_info[:2]>=(3,9) else sys.exit(1)`"")) 2>$null
        if ($LASTEXITCODE -eq 0 -and $v) { return $v.Trim() }
    } catch {}
    return $null
}

if ($PyVersion) {
    $candidates = @("py -$PyVersion")
} else {
    $candidates = @('py -3.13', 'py -3.12', 'py -3.11', 'py -3', 'python', 'python3')
}

$py = $null; $pyver = $null
foreach ($cand in $candidates) {
    $exe = ($cand -split ' ')[0]
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    $v = Probe-Py $cand
    if ($v) { $py = $cand; $pyver = $v; break }
}
if (-not $py) {
    if ($PyVersion) { Die "Python $PyVersion not found. Check 'py --list', or install it from python.org." }
    Die "Python 3.9+ not found on PATH. Install 3.12 from python.org (tick 'Add to PATH')."
}
Ok "Python $pyver ($py)"

if (-not (Test-Path requirements.txt)) { Die "requirements.txt not found - run this from the app folder." }
if (-not (Test-Path api.py))           { Die "api.py not found - run this from the app folder." }
Ok "App files present"

# Port availability (best-effort)
try {
    $bindIp = if ($BindHost -eq '0.0.0.0') { [System.Net.IPAddress]::Any } else { [System.Net.IPAddress]::Parse($BindHost) }
    $listener = [System.Net.Sockets.TcpListener]::new($bindIp, $Port)
    $listener.Start(); $listener.Stop()
    Ok "Port $Port is free on $BindHost"
} catch {
    Warn "Port $Port looks busy on $BindHost - start with '-Port <n>' if launch fails"
}

# Ollama (optional - only used for LLM enrichment). Use 127.0.0.1, not localhost:
# on Windows 'localhost' can resolve to IPv6 ::1 first and miss Ollama's IPv4 bind.
try {
    $tags = Invoke-RestMethod -TimeoutSec 2 -Uri 'http://127.0.0.1:11434/api/tags'
    $n = @($tags.models).Count
    $s = if ($n -ne 1) { 's' } else { '' }
    if ($n) { Ok "Ollama reachable on :11434 - $n model$s installed" }
    else    { Ok "Ollama reachable on :11434 - no models pulled yet (see suggestions below)" }
} catch {
    Warn "Ollama not detected on :11434 - start it, or leave LLM enrichment off"
}
Write-Host ""

# --- Hardware + model sizing (informational; never fatal) ------------------
# Recommends Ollama models that fit your VRAM. VRAM is read from nvidia-smi
# first (reliable), then the registry qwMemorySize QWORD (correct for >4 GB,
# unlike WMI AdapterRAM which caps at 4 GB), then CIM for names only.
function Get-Vram {
    $gpus = @()
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        try {
            $lines = & nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>$null
            foreach ($ln in $lines) {
                $p = $ln -split '\s*,\s*'
                if ($p.Count -ge 2) {
                    $mb = 0; [void][int]::TryParse(($p[1] -replace '[^\d]',''), [ref]$mb)
                    if ($mb -gt 0) { $gpus += @{ Name = $p[0].Trim(); VramGB = [math]::Round($mb/1024,0) } }
                }
            }
        } catch {}
    }
    if (-not $gpus.Count) {
        try {
            $base = 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}'
            Get-ChildItem $base -ErrorAction SilentlyContinue | ForEach-Object {
                $pr = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
                $q  = $pr.'HardwareInformation.qwMemorySize'
                if ($q) {
                    $gb = [math]::Round([int64]$q / 1GB, 0)
                    $nm = if ($pr.DriverDesc) { $pr.DriverDesc } else { 'GPU' }
                    if ($gb -gt 0) { $gpus += @{ Name = $nm; VramGB = $gb } }
                }
            }
        } catch {}
    }
    if (-not $gpus.Count) {
        try { Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue |
                ForEach-Object { $gpus += @{ Name = $_.Name; VramGB = 0 } } } catch {}
    }
    $max = 0; $tot = 0
    foreach ($g in $gpus) { if ($g.VramGB -gt $max) { $max = $g.VramGB }; $tot += $g.VramGB }
    return @{ Gpus = $gpus; MaxGB = $max; TotalGB = $tot }
}
function Recommend-Models($maxGB) {
    $t = if     ($maxGB -ge 22) { @(@('qwen2.5:32b','~20 GB'),@('qwen2.5:14b','~9 GB'),@('llama3.1:8b','~4.9 GB')) }
         elseif ($maxGB -ge 14) { @(@('qwen2.5:14b','~9 GB'),@('gemma2:9b','~5.4 GB'),@('llama3.1:8b','~4.9 GB')) }
         elseif ($maxGB -ge 10) { @(@('llama3.1:8b','~4.9 GB'),@('qwen2.5:14b','~9 GB'),@('gemma2:9b','~5.4 GB')) }
         elseif ($maxGB -ge 7)  { @(@('llama3.1:8b','~4.9 GB'),@('mistral:7b','~4.1 GB'),@('llama3.2:3b','~2 GB')) }
         elseif ($maxGB -ge 5)  { @(@('llama3.2:3b','~2 GB'),@('qwen2.5:3b','~1.9 GB'),@('phi3:mini','~2.3 GB')) }
         else                   { @(@('llama3.2:3b','~2 GB'),@('gemma2:2b','~1.6 GB'),@('qwen2.5:3b','~1.9 GB')) }
    $t | ForEach-Object { [pscustomobject]@{ Tag = $_[0]; Size = $_[1] } }
}

Write-Host "  Hardware"
try {
    $os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
    if ($os) { Ok "$($os.Caption.Trim()) - $([math]::Round($os.TotalVisibleMemorySize/1MB,0)) GB RAM" }
} catch {}
$hw = Get-Vram
if ($hw.Gpus.Count) {
    foreach ($g in $hw.Gpus) {
        if ($g.VramGB -gt 0) { Ok "GPU: $($g.Name) - $($g.VramGB) GB VRAM" } else { Ok "GPU: $($g.Name)" }
    }
    if ($hw.MaxGB -gt 0) {
        Write-Host "  Suggested models for $($hw.MaxGB) GB VRAM:" -ForegroundColor DarkGray
        foreach ($r in (Recommend-Models $hw.MaxGB)) {
            Write-Host ("      ollama pull {0,-13} # {1}" -f $r.Tag, $r.Size) -ForegroundColor DarkGray
        }
        if ($hw.Gpus.Count -ge 2) {
            Warn "$($hw.Gpus.Count) GPUs / $($hw.TotalGB) GB total - Ollama splits large models across cards (qwen2.5:32b feasible)"
        }
    } else {
        Warn "VRAM unknown - install the GPU vendor driver (ships nvidia-smi) for accurate sizing"
    }
} else {
    Warn "No discrete GPU detected - CPU inference works but is slow; stick to a 3B model (llama3.2:3b)"
}
Write-Host ""

# --- virtualenv + dependencies (reinstall only when requirements change) ---
Write-Host "  Environment"
$venvPy   = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$pyStamp  = '.venv\.pyver'
$havePyv  = if (Test-Path $pyStamp) { (Get-Content $pyStamp -Raw).Trim() } else { '' }
# Rebuild if there's no venv, its python is missing, or it was built by a
# different interpreter version (e.g. an old 3.14 attempt with no wheels).
if ((-not (Test-Path $venvPy)) -or ($havePyv -ne $pyver)) {
    if (Test-Path .venv) {
        $wasPyv = if ($havePyv) { $havePyv } else { 'incomplete' }
        Warn "Rebuilding .venv (was $wasPyv, now $pyver)"
        Remove-Item -Recurse -Force .venv
    }
    Write-Host "  creating virtualenv (.venv) on $pyver..." -ForegroundColor DarkGray
    & ([scriptblock]::Create("$py -m venv .venv"))
    if ($LASTEXITCODE -ne 0) { Die "Failed to create virtualenv." }
    Set-Content -LiteralPath $pyStamp -Value $pyver -NoNewline
}
if (-not (Test-Path $venvPy)) { Die "venv python not found at $venvPy" }

$stamp   = '.venv\.req-stamp'
$reqHash = (Get-FileHash requirements.txt -Algorithm SHA1).Hash
$have    = if (Test-Path $stamp) { Get-Content $stamp -Raw } else { '' }
if ($have.Trim() -ne $reqHash) {
    Write-Host "  installing dependencies..." -ForegroundColor DarkGray
    & $venvPy -m pip install -q --upgrade pip | Out-Null
    & $venvPy -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Die "pip install failed. Usually a missing prebuilt wheel for Python $pyver - re-run with an older Python, e.g.  .\run.ps1 -PyVersion 3.12"
    }
    Set-Content -LiteralPath $stamp -Value $reqHash -NoNewline
    Ok "Dependencies installed"
} else {
    Ok "Dependencies up to date"
}
Write-Host ""

# --- launch ----------------------------------------------------------------
$env:HOST = $BindHost
$env:PORT = "$Port"
Write-Host "  Ready"
Write-Host "  -> http://${BindHost}:${Port}" -ForegroundColor Cyan -NoNewline
Write-Host "   (Ctrl-C to stop)" -ForegroundColor DarkGray
Write-Host ""
& $venvPy -m uvicorn api:app --host $BindHost --port $Port
