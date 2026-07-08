# ============================================================
#  PDC Glossary Generator — scenario remover / app reset (Windows)
#
#  Undoes install-scenario.ps1: removes the installed scenario's
#  runtime files so the app is back to its clean, generic state.
#  Everything removed is first backed up beside itself with a
#  .backup-<timestamp> suffix (all git-ignored).
#
#  Default: removes the scenario config
#    - domain_pack.json      (the installed vocabulary)
#    - people.json           (the steward roster)
#    - tag_dictionary.json   (the persisted, seeded dictionary)
#    - GLOSSARY_COMPANY in .env  (commented back out)
#
#  -All: ALSO removes the rest of the app's runtime state
#    - connections.json  settings.json  glossaries.json
#    - audit_log.json    registries/
#
#  Usage:   .\reset-scenario.ps1          # scenario files only
#           .\reset-scenario.ps1 -All     # full runtime reset
# ============================================================
param([switch]$All)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$App = "glossary_generator"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

function Backup-Remove([string]$Path) {
    if (Test-Path $Path -PathType Leaf) {
        Move-Item $Path "$Path.backup-$stamp"
        Write-Host ("  - {0}  (backed up: {1}.backup-{2})" -f $Path, (Split-Path $Path -Leaf), $stamp)
    }
}

Write-Host ""
Write-Host "Resetting the Glossary Generator to its clean, generic state" -ForegroundColor Cyan

Backup-Remove (Join-Path $App "domain_pack.json")
Backup-Remove (Join-Path $App "people.json")
Backup-Remove (Join-Path $App "tag_dictionary.json")

# comment GLOSSARY_COMPANY back out in .env (if present)
$envFile = Join-Path $App ".env"
if (Test-Path $envFile) {
    $content = Get-Content $envFile -Raw -Encoding UTF8
    if ($content -match '(?m)^GLOSSARY_COMPANY=') {
        Copy-Item $envFile "$envFile.backup-$stamp"
        $content = [regex]::Replace($content, '(?m)^GLOSSARY_COMPANY=', '# GLOSSARY_COMPANY=')
        [IO.File]::WriteAllText((Resolve-Path $envFile), $content, (New-Object Text.UTF8Encoding $false))
        Write-Host "  ~ GLOSSARY_COMPANY commented out in $envFile"
    }
}

if ($All) {
    Write-Host ""
    Write-Host "Full runtime reset (-All):" -ForegroundColor Yellow
    Backup-Remove (Join-Path $App "connections.json")
    Backup-Remove (Join-Path $App "settings.json")
    Backup-Remove (Join-Path $App "glossaries.json")
    Backup-Remove (Join-Path $App "audit_log.json")
    $reg = Join-Path $App "registries"
    if (Test-Path $reg -PathType Container) {
        Move-Item $reg "$reg.backup-$stamp"
        Write-Host ("  - {0}\  (backed up: registries.backup-{1})" -f $reg, $stamp)
    }
}

Write-Host ""
Write-Host "Done. The app now runs generic (no scenario vocabulary, empty roster)." -ForegroundColor Green
Write-Host "Install a scenario again with:  .\install-scenario.ps1"
