<#
.SYNOPSIS
    Stage the Python app + built React UI for bundling.

.DESCRIPTION
    Copies glossary_generator\ and frontend\dist\ into src-tauri\vendor\app,
    which tauri.conf.json's bundle.resources maps to "app" inside the install.

    The staged tree MIRRORS the repo layout:

        app\glossary_generator\api.py
        app\frontend\dist\index.html

    That is not cosmetic. api.py resolves the built UI as
    os.path.join(os.path.dirname(HERE), "frontend", "dist") - one level up from
    itself - so flattening the two into a single directory would leave the
    server running with no UI to serve.

    Deliberately EXCLUDES local state and developer debris. Shipping a
    developer's connections.json or glossaries.json into a customer install
    would leak lab hostnames and hand every attendee the same pre-populated
    glossary; .env would leak provider API keys outright.

.NOTES
    Windows PowerShell 5.1+. ASCII-only on purpose.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
# Without this an undefined variable expands to empty and robocopy just returns
# exit 16 - which is how the staging destination silently became "" once.
Set-StrictMode -Version Latest

$desktopDir = Split-Path -Parent $PSScriptRoot
$repoRoot   = Split-Path -Parent $desktopDir
$srcApp     = Join-Path $repoRoot "glossary_generator"
$srcUi      = Join-Path $repoRoot "frontend\dist"
$stageDir   = Join-Path $desktopDir "src-tauri\vendor\app"
$stageApp   = Join-Path $stageDir "glossary_generator"
$stageUi    = Join-Path $stageDir "frontend\dist"

function Ok($m)   { Write-Host "  [ok] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  [!]  $m" -ForegroundColor Yellow }

Write-Host ""
Write-Host "  Staging the app" -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath (Join-Path $srcApp "api.py"))) {
    throw "glossary_generator\api.py not found - is $repoRoot the repo root?"
}
if (-not (Test-Path -LiteralPath (Join-Path $srcUi "index.html"))) {
    throw "frontend\dist\index.html not found - run 'npm run build' in frontend\ first"
}

if (Test-Path -LiteralPath $stageDir) { Remove-Item -LiteralPath $stageDir -Recurse -Force }
New-Item -ItemType Directory -Path $stageDir -Force | Out-Null

# State files and secrets: never shipped. The installed app starts empty and
# writes to the per-user state directory (see glossary_generator\paths.py).
$excludeFiles = @(
    ".env", "glossaries.json", "glossaries.json.bak", "settings.json",
    "connections.json", "people.json", "audit_log.json", "tag_dictionary.json",
    "domain_pack.json", "datasources.csv"
)
$excludeDirs = @(".venv", "venv", "__pycache__", ".pytest_cache", "registries", "tests",
                 # 1.4 MB of documentation artwork. Referenced by docs/GUIDE.md
                 # and REFERENCE.md, so it stays in the REPO - but the app never
                 # serves it, and an installer is not where documentation images
                 # belong.
                 "diagrams")

# Developer tools, not part of the app. Since 1.33.0 they live in cli/, so the
# whole directory goes rather than a list of filenames that would drift.
#
# Nothing imports them - checked, not assumed, and it matters: seed_sample.py
# LOOKS like a dev script by its name and IS imported by api.py, so dropping it
# would break the packaged app on a customer machine and nowhere else. The
# import assertion at the end of this script exists because of that trap.
$excludeDirs  += @("cli")

# Example domain packs do NOT ship.
#
# The engine was made industry-agnostic in 1.29/1.33/1.34 - categories, tag
# dictionary and CDE patterns all had one scenario's vocabulary removed. Then
# shipping water_utility.example.json as the only example put that vocabulary
# straight back in the box, with a customer's name on some of it. Packs are
# scenario material; they belong with the scenario, and packinit writes a fresh
# one from the company name at install time.
$excludeDirs  += @("domain_packs")

# robocopy: /MIR-free mirror of a clean tree, /XD and /XF do the excluding.
# Exit codes 0-7 are success (8+ is a real failure) - a quirk worth pinning,
# because treating any non-zero as failure makes every build look broken.
#
# /XD and /XF names are RELATIVE on purpose: an absolute path matches only that
# exact directory/file, so "app\__pycache__" excluded the TOP-LEVEL cache while
# every subpackage's (core/, engine/, ai/, sources/) shipped from the dev
# checkout into Program Files - where the uninstaller then left them behind
# (found on PDC-Insights 1.17.0: 24 leftover files after uninstall). A
# relative name matches at any depth.
$roboArgs = @($srcApp, $stageApp, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
foreach ($d in $excludeDirs)  { $roboArgs += @("/XD", $d) }
foreach ($f in $excludeFiles) { $roboArgs += @("/XF", $f) }
& robocopy @roboArgs | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed staging the app (exit $LASTEXITCODE)" }

# The built SPA, one level up from glossary_generator - the shape api.py
# expects (see the .DESCRIPTION note above).
New-Item -ItemType Directory -Path $stageUi -Force | Out-Null
& robocopy $srcUi $stageUi "/E" "/NFL" "/NDL" "/NJH" "/NJS" "/NP" | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed staging the UI (exit $LASTEXITCODE)" }

# boot.py puts the app dir on sys.path before importing it. The embeddable
# runtime's ._pth replaces sys.path outright, so without this the server cannot
# import api.py whatever working directory it is given. See desktop/boot.py.
Copy-Item -LiteralPath (Join-Path $desktopDir "boot.py") -Destination (Join-Path $stageDir "boot.py") -Force

# pdc_client lives at the REPO ROOT and is pip-installed into the dev venv, so
# nothing in glossary_generator/ points at it. Miss it and api.py raises
# ModuleNotFoundError at import time - after the installer has shipped.
$srcClient = Join-Path $repoRoot "pdc_client"
if (-not (Test-Path -LiteralPath (Join-Path $srcClient "__init__.py"))) {
    throw "pdc_client\__init__.py not found at $srcClient"
}
# /XD names relative here too, for the same reason as above.
& robocopy $srcClient (Join-Path $stageDir "pdc_client") "/E" "/NFL" "/NDL" "/NJH" "/NJS" "/NP" `
    "/XD" "__pycache__" ".venv" "venv" | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed staging pdc_client (exit $LASTEXITCODE)" }

# Belt and braces: prove nothing sensitive slipped through. A rename or a new
# state file would otherwise be caught only by a customer.
$leaked = Get-ChildItem -LiteralPath $stageDir -Recurse -File |
    Where-Object { $excludeFiles -contains $_.Name }
if ($leaked) {
    $leaked | ForEach-Object { Warn ("leaked: " + $_.FullName) }
    throw "state or secret files reached the staging tree - fix the exclude list"
}

# Same guard for dev virtualenvs. The staged tree runs on the VENDORED
# runtime, so a bundled venv is a second, wrong Python - PDC-Policy shipped
# one in every installer until someone listed the exe (934f61c there). The
# excludes above prevent it; this proves it, for every tree staged above.
$venvs = Get-ChildItem -LiteralPath $stageDir -Recurse -Directory |
    Where-Object { $_.Name -eq ".venv" -or $_.Name -eq "venv" }
if ($venvs) {
    $venvs | ForEach-Object { Warn ("venv: " + $_.FullName) }
    throw "a dev virtualenv reached the staging tree - fix the exclude list"
}

# The three paths the shell and the server actually depend on. Assert them here,
# where the fix is obvious, rather than at first launch on an attendee's laptop.
foreach ($must in @((Join-Path $stageApp "api.py"),
                    (Join-Path $stageUi  "index.html"),
                    (Join-Path $stageDir "boot.py"),
                    (Join-Path $stageDir "pdc_client\__init__.py"))) {
    if (-not (Test-Path -LiteralPath $must)) { throw "staging incomplete: $must is missing" }
}

# Prove the staged tree can actually be imported, using the runtime that will
# ship with it. File-existence checks cannot catch a module excluded by mistake;
# this can, and it costs about two seconds.
$vendorPy = Join-Path $desktopDir "src-tauri\vendor\python\python.exe"
if (Test-Path -LiteralPath $vendorPy) {
    $probe = "import sys; sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[2]); import api; print('import ok')"
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    # -B: do NOT write bytecode. Without it this check compiles __pycache__ into
    # the tree robocopy just finished excluding it from, and those .pyc files
    # then ship - stale caches for a Python version the user may not even be
    # running. The check has to leave the stage exactly as it found it.
    $out = & $vendorPy -B -c $probe $stageApp $stageDir 2>&1
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    if ($code -ne 0) {
        $out | ForEach-Object { Warn $_ }
        throw "the staged tree cannot import api.py - a module is missing from the stage"
    }
    # Belt and braces: -B covers this run, but anything else that touches the
    # stage (a stray manual test, a future check) would leave caches behind, and
    # a shipped .pyc is invisible until someone lists the installer.
    Get-ChildItem -LiteralPath $stageDir -Recurse -Directory -Filter "__pycache__" |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }

    Ok "staged tree imports cleanly"
} else {
    Warn "no vendored runtime yet - skipping the import check (run fetch:python first)"
}

$count = (Get-ChildItem -LiteralPath $stageDir -Recurse -File).Count
Ok "staged $count file(s) to src-tauri\vendor\app"
Write-Host ""

# robocopy returns 1 for "files were copied" and pip leaves its own code behind.
# PowerShell surfaces the LAST native exit code as the script's, so a successful
# run would look like a failure to npm and abort the tauri build.
exit 0
