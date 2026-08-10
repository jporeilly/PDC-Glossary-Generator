# Copies the freshly built NSIS installer from Tauri's deeply nested output
# (desktop\src-tauri\target\release\bundle\nsis\) to the repo root's dist\
# folder - ONE short, memorable path for every build artifact, matching the
# Lab repo's convention (its tarballs land in dist\ too). Run after
# tauri:build; wired into the "dist" npm script.
$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$nsis = Join-Path $here "..\src-tauri\target\release\bundle\nsis"
$dist = Join-Path $here "..\..\dist"

$exe = Get-ChildItem -Path $nsis -Filter "*-setup.exe" -ErrorAction Stop |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $exe) {
    Write-Error "no *-setup.exe found in $nsis - run 'npm run tauri:build' first"
}

New-Item -ItemType Directory -Force -Path $dist | Out-Null
Copy-Item -Path $exe.FullName -Destination $dist -Force
$final = Join-Path (Resolve-Path $dist).Path $exe.Name
$hash = (Get-FileHash -Path $final -Algorithm SHA256).Hash
Write-Output "installer -> $final"
Write-Output "sha256    -> $hash"
