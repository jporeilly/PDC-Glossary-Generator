# Copies the freshly built NSIS installer from Tauri's deeply nested output
# (desktop\src-tauri\target\release\bundle\nsis\) to the repo root's dist\
# folder - ONE short, memorable path for every build artifact, matching the
# Lab repo's convention (its tarballs land in dist\ too). Run after
# tauri:build; wired into the "dist" npm script.
$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$nsis = Join-Path $here "..\src-tauri\target\release\bundle\nsis"
$dist = Join-Path $here "..\..\dist"

$exe = Get-ChildItem -Path $nsis -Filter "*-setup.exe" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $exe) {
    Write-Error "no *-setup.exe found in $nsis - the tauri build did not produce one"
    exit 1
}

# The version the installer carries MUST be the version this checkout says.
# A failed tauri build leaves the PREVIOUS installer sitting in the bundle
# folder, and collecting it silently ships a stale artifact under a new
# version's name (field-caught: a deleted desktop\dist made the build fail,
# yet the train still reported success).
$verFile = Join-Path $here "..\..\glossary_generator\VERSION"
$want = (Get-Content $verFile -Raw).Trim()
if ($exe.Name -notmatch [regex]::Escape($want)) {
    Write-Error ("installer '{0}' is not version {1} - the build FAILED and left an " +
                 "older artifact behind; fix the build rather than shipping this" -f $exe.Name, $want)
    exit 1
}
$age = (Get-Date) - $exe.LastWriteTime
if ($age.TotalMinutes -gt 30) {
    Write-Error ("installer '{0}' was built {1:N0} minutes ago - that is not this run" -f $exe.Name, $age.TotalMinutes)
    exit 1
}

New-Item -ItemType Directory -Force -Path $dist | Out-Null
Copy-Item -Path $exe.FullName -Destination $dist -Force
$final = Join-Path (Resolve-Path $dist).Path $exe.Name
$hash = (Get-FileHash -Path $final -Algorithm SHA256).Hash
Write-Output "installer -> $final"
Write-Output "sha256    -> $hash"
