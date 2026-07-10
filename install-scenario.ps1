# ============================================================
#  PDC Glossary Generator — scenario installer (Windows)
#
#  Lists the scenarios under data_sources\ (anything with a
#  scenario.json), lets you pick one (or pass -Scenario), then
#  installs that scenario's files into the app's RUNTIME config.
#  The app itself (code, git tree) is never touched — these are
#  all git-ignored runtime files:
#
#    - domain_pack.json   <- the scenario vocabulary
#    - people.json        <- the steward roster seed
#    - .env               <- GLOSSARY_COMPANY set
#    - tag_dictionary.json backed up + removed (forces reseed)
#    - datasources.csv    <- the scenario's PDC bulk-load connections
#
#  Usage:   .\install-scenario.ps1              # interactive menu
#           .\install-scenario.ps1 -Scenario CSCU   (or RETAIL)
# ============================================================
param([string]$Scenario)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$App = "glossary_generator"
$DS  = "data_sources"

# ---- discover scenarios -----------------------------------------------------
$manifests = Get-ChildItem -Path $DS -Directory | ForEach-Object {
    $m = Join-Path $_.FullName "scenario.json"
    if (Test-Path $m) { Get-Content $m -Raw -Encoding UTF8 | ConvertFrom-Json }
}
if (-not $manifests) { Write-Error "No scenarios found under $DS\"; exit 1 }

# ---- pick one ---------------------------------------------------------------
if (-not $Scenario) {
    Write-Host ""
    Write-Host "  PDC Glossary Generator - available scenarios" -ForegroundColor Cyan
    Write-Host ""
    for ($i = 0; $i -lt $manifests.Count; $i++) {
        $s = $manifests[$i]
        Write-Host ("  {0}) {1,-6} {2} - {3}" -f ($i + 1), $s.id, $s.name, $s.industry)
        Write-Host ("     {0}" -f $s.description) -ForegroundColor DarkGray
    }
    Write-Host ""
    $n = Read-Host ("  Select a scenario [1-{0}]" -f $manifests.Count)
    if ($n -notmatch '^\d+$' -or [int]$n -lt 1 -or [int]$n -gt $manifests.Count) {
        Write-Error "Invalid selection."; exit 1
    }
    $sel = $manifests[[int]$n - 1]
} else {
    $sel = $manifests | Where-Object { $_.id -eq $Scenario }
    if (-not $sel) { Write-Error "Unknown scenario '$Scenario'"; exit 1 }
}

$packSrc   = Join-Path $DS (Join-Path $sel.id $sel.pack)
$peopleSrc = Join-Path $DS (Join-Path $sel.id $sel.people)
if (-not (Test-Path $packSrc))   { Write-Error "Pack not found: $packSrc"; exit 1 }
if (-not (Test-Path $peopleSrc)) { Write-Error "Roster not found: $peopleSrc"; exit 1 }

Write-Host ""
Write-Host ("Installing scenario: {0}" -f $sel.name) -ForegroundColor Cyan
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

# ---- 1. domain pack ---------------------------------------------------------
$packDst = Join-Path $App "domain_pack.json"
if (Test-Path $packDst) { Copy-Item $packDst "$packDst.backup-$stamp" }
Copy-Item $packSrc $packDst
Write-Host "  + $packDst"

# ---- 2. steward roster (backs up an existing one) ---------------------------
$peopleDst = Join-Path $App "people.json"
if (Test-Path $peopleDst) {
    Copy-Item $peopleDst "$peopleDst.backup-$stamp"
    Write-Host "  ~ existing people.json backed up (people.json.backup-$stamp)"
}
Copy-Item $peopleSrc $peopleDst
Write-Host "  + $peopleDst"

# ---- 3. force a dictionary reseed from the new pack -------------------------
$dict = Join-Path $App "tag_dictionary.json"
if (Test-Path $dict) {
    Move-Item $dict "$dict.backup-$stamp"
    Write-Host "  ~ tag_dictionary.json backed up + removed (reseeds on next start)"
}

# ---- 4. GLOSSARY_COMPANY in .env ---------------------------------------------
$envFile = Join-Path $App ".env"
if (-not (Test-Path $envFile)) {
    $example = Join-Path $App ".env.example"
    if (Test-Path $example) { Copy-Item $example $envFile } else { New-Item -ItemType File $envFile | Out-Null }
}
$content = Get-Content $envFile -Raw -Encoding UTF8
$line = 'GLOSSARY_COMPANY="{0}"' -f $sel.company
if ($content -match '(?m)^[#\s]*GLOSSARY_COMPANY=') {
    $content = [regex]::Replace($content, '(?m)^[#\s]*GLOSSARY_COMPANY=.*$', $line, 1)
} else {
    $content = $content.TrimEnd() + "`n`n$line`n"
}
[IO.File]::WriteAllText((Resolve-Path $envFile), $content, (New-Object Text.UTF8Encoding $false))
Write-Host ("  + GLOSSARY_COMPANY=""{0}""  ({1})" -f $sel.company, $envFile)

# ---- 4b. retarget env-pinned pack/roster paths, if the user set them --------
# GLOSSARY_DOMAIN_PACK / GLOSSARY_PEOPLE_SEED in .env OVERRIDE the copied
# runtime files, so if they are set (uncommented) point them at the selected
# scenario instead of leaving them pinned to an old one.
$content = Get-Content $envFile -Raw -Encoding UTF8
$retarget = @{
    "GLOSSARY_DOMAIN_PACK" = ("../data_sources/{0}/{1}" -f $sel.id, $sel.pack)
    "GLOSSARY_PEOPLE_SEED" = ("../data_sources/{0}/{1}" -f $sel.id, $sel.people)
}
$dirty = $false
foreach ($k in $retarget.Keys) {
    if ($content -match ("(?m)^{0}=" -f $k)) {
        $content = [regex]::Replace($content, ("(?m)^{0}=.*$" -f $k), ("{0}={1}" -f $k, $retarget[$k]), 1)
        Write-Host ("  ~ {0} -> {1}  (env override retargeted)" -f $k, $retarget[$k])
        $dirty = $true
    }
}
if ($dirty) {
    [IO.File]::WriteAllText((Resolve-Path $envFile), $content, (New-Object Text.UTF8Encoding $false))
}

# ---- 5. bulk-load datasources CSV -------------------------------------------
$dsCsvSrc = Join-Path $DS (Join-Path $sel.id $sel.datasources_csv)
$dsCsvDst = Join-Path $App "datasources.csv"
if (Test-Path $dsCsvSrc) {
    if (Test-Path $dsCsvDst) { Copy-Item $dsCsvDst "$dsCsvDst.backup-$stamp" }
    Copy-Item $dsCsvSrc $dsCsvDst
    Write-Host "  + $dsCsvDst  (the scenario's PDC bulk-load connections)"
} else {
    Write-Host "  ~ no datasources CSV in this scenario (skipped)"
}

Write-Host ""
Write-Host "Done. Next steps:" -ForegroundColor Green
Write-Host ("  1. Stand up the lab:      cd {0}\lab; make up; make load SCENARIO={1}  (on the Docker host)" -f $DS, $sel.id)
Write-Host ("  2. Start the app:         cd {0}; .\run.ps1" -f $App)
Write-Host  "  3. In the app:            Dictionary page -> confirm the vocabulary reseeded"
Write-Host ("  4. Register PDC sources:  Connections -> Bulk-load panel -> choose {0}" -f $dsCsvDst)
Write-Host ("  5. Courseware:            {0}\" -f $sel.courseware)
Write-Host ""
Write-Host "One scenario at a time - rerun this script to switch (it backs everything up)."
