<#
.SYNOPSIS
    Seed a company's domain pack and settings into a fresh install.

.DESCRIPTION
    The app ships GENERIC: since 1.29 the engine asserts no categories at all,
    so a fresh install classifies nothing until a domain pack tells it how. This
    is the step that supplies one.

    It asks for the two things only the customer can answer - the company name
    and its glossary categories - scaffolds a THIN pack with packinit, and
    writes it where the app reads it (the state directory, NOT the install
    directory, which is read-only in a packaged build).

    The pack is deliberately thin: category keywords, governed tags and
    placeholder definitions, with table mappings and terms left EMPTY. Those get
    filled from evidence:

        seed (this script) -> scan -> review -> Export domain pack

    Re-running is safe: it refuses to overwrite an existing pack unless -Force,
    because that pack has usually been grown from a scan by then and is worth far
    more than this skeleton.

.PARAMETER Company
    Company name. Prompted for when omitted.

.PARAMETER Categories
    Comma-separated glossary categories. Prompted for when omitted; press Enter
    at the prompt to take packinit's suggested starting list.

.PARAMETER Domain
    Short pack id (e.g. water_utility). Derived from the company name if omitted.

.PARAMETER PdcUrl
    Pentaho Data Catalog server to record as the app's connection, e.g.
    https://catalog.example.com. Optional - it can be set later on the
    Connections page. Any PDC server; there is no default.

.PARAMETER Force
    Overwrite an existing domain pack. It is backed up first.

.EXAMPLE
    .\seed-company.ps1

.EXAMPLE
    .\seed-company.ps1 -Company "Northgate Water" -Categories "Customer,Billing,Usage,Water Quality"

.NOTES
    Windows PowerShell 5.1+. ASCII-only on purpose.
#>
[CmdletBinding()]
param(
    [string]$Company,
    [string]$Categories,
    [string]$Domain,
    [string]$PdcUrl,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

. (Join-Path $PSScriptRoot "lib\common.ps1")

function Ok($m)   { Write-Host "  [ok] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  [!]  $m" -ForegroundColor Yellow }
function Say($m)  { Write-Host "  $m" -ForegroundColor DarkGray }

Write-Host ""
Write-Host "  Seed a company into the Glossary Generator" -ForegroundColor Cyan
Say "The engine ships with no categories of its own. This supplies the pack"
Say "that tells it how to classify THIS company's data."
Write-Host ""

$state  = Resolve-StateDir $PSScriptRoot
$pyExe  = Resolve-PyExe    $PSScriptRoot
$appPy  = Resolve-AppPy    $PSScriptRoot

if (-not $pyExe) { throw "No Python found. Install the app, or install Python 3.9+." }
if (-not $appPy) { throw "packinit.py not found - is this a complete install?" }
if (-not (Test-DirWritable $state.Path)) {
    throw ("State directory is not writable: " + $state.Path +
           " - set GLOSSARY_STATE_DIR to a writable path.")
}
Ok ("state directory: " + $state.Path + " (" + $state.Why + ")")

# Prompt ONLY when there is a console to prompt on.
#
# The installer runs this through nsExec, which provides no interactive console,
# and PowerShell's -NonInteractive makes Read-Host throw rather than hang. The
# resulting error has nothing to do with company names and reads like a file
# access problem, which is exactly how it was first reported. So: ask when a
# person is there, and otherwise say plainly what to do instead.
if (-not $Company) {
    if ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
        try { $Company = (Read-Host "  Company name").Trim() } catch { $Company = "" }
    }
}
if (-not $Company) {
    Warn "No company name supplied and nothing to ask on - skipping."
    Say  "Run this again with -Company 'Your Company', or from a PowerShell prompt."
    exit 0            # not a failure: the app installs fine without a pack
}

if (-not $Categories) {
    Write-Host ""
    Say "Glossary categories, comma separated. These are the top-level buckets"
    Say "terms are filed under. Press Enter to take the suggested starting list."
    $Categories = (Read-Host "  Categories").Trim()
}

if (-not $Domain) {
    # Short id from the company name: "Northgate Water" -> northgate_water.
    $Domain = ($Company.ToLowerInvariant() -replace '[^a-z0-9]+', '_').Trim('_')
}

$packPath = Join-Path $state.Path "domain_pack.json"
if ((Test-Path -LiteralPath $packPath) -and (-not $Force)) {
    Warn "a domain pack already exists at $packPath"
    Say  "It has probably been grown from a scan, which is worth more than this"
    Say  "skeleton. Re-run with -Force to replace it (the old one is backed up)."
    exit 1
}
if (Test-Path -LiteralPath $packPath) {
    $backup = $packPath + ".backup-" + (Get-Date -Format "yyyyMMdd-HHmmss")
    Copy-Item -LiteralPath $packPath -Destination $backup -Force
    Ok "existing pack backed up to $(Split-Path -Leaf $backup)"
}

$args = @((Join-Path $appPy "packinit.py"), "--domain", $Domain, "--company", $Company,
          "-o", $packPath, "--force")
if ($Categories) { $args += @("--categories", $Categories) }

# packinit reports the categories it could NOT derive a keyword for, and those
# notes go to stderr. Under $ErrorActionPreference = "Stop", PowerShell 5.1
# turns any stderr line from a native command into a terminating
# NativeCommandError - so a successful run with useful notes looks like a crash.
# Relax it around the call and judge by the exit code, which is the only honest
# signal here.
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $pyExe @args 2>&1 | ForEach-Object { Write-Host ("  " + $_) -ForegroundColor DarkGray }
$code = $LASTEXITCODE
$ErrorActionPreference = $prevEap
if ($code -ne 0) { throw "packinit failed (exit $code)" }

# The company name also drives the app's own wording (settings.json "company",
# the same field the Settings page edits). Merge rather than overwrite: this can
# run against an install that already has settings.
$settingsPath = Join-Path $state.Path "settings.json"
$settings = @{}
if (Test-Path -LiteralPath $settingsPath) {
    try {
        $existing = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
        foreach ($p in $existing.PSObject.Properties) { $settings[$p.Name] = $p.Value }
    } catch {
        Warn "settings.json could not be read - writing a fresh one"
    }
}
$settings["company"] = $Company
# Recorded so the app opens pointing at the right catalog, and so the
# environment check has a server to probe instead of skipping. Credentials are
# NOT stored here - the app asks for those when it connects.
if ($PdcUrl) { $settings["pdc_base"] = $PdcUrl.TrimEnd("/") }
# NO BYTE-ORDER MARK. Set-Content -Encoding UTF8 writes one in PowerShell 5.1,
# and the app reads its state with encoding="utf-8" (not utf-8-sig) inside a
# try/except that returns the DEFAULT on failure - so a BOM does not raise, it
# silently discards the company name this script just collected. The install
# would report success and the app would show none of it.
$json = ($settings | ConvertTo-Json -Depth 10)
[IO.File]::WriteAllText($settingsPath, $json, (New-Object System.Text.UTF8Encoding($false)))
Ok "company name saved to settings.json"

Write-Host ""
Ok "seeded '$Company'"
Say "next: scan a source, review the rows, then Export domain pack - that is"
Say "what fills in table mappings, terms and abbreviations from real evidence."
Write-Host ""

exit 0
