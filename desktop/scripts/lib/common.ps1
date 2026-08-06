<#
    Shared helpers for the desktop scripts.

    Exists because check-environment.ps1 and seed-company.ps1 both have to answer
    the same two questions - "where does state live" and "which Python do I run"
    - and two copies of those rules is two chances to disagree with
    glossary_generator\paths.py, which is the actual authority. A check that
    probes a different directory from the one the app writes to is worse than no
    check.

    Dot-source it:  . (Join-Path $PSScriptRoot "lib\common.ps1")

    ASCII-only on purpose (PowerShell 5.1).
#>

function Get-RepoRoot {
    <# The PDC-Glossary checkout root, from a script in desktop\scripts. #>
    param([Parameter(Mandatory)][string] $ScriptRoot)
    return (Split-Path -Parent (Split-Path -Parent $ScriptRoot))
}

function Get-DesktopDir {
    param([Parameter(Mandatory)][string] $ScriptRoot)
    return (Split-Path -Parent $ScriptRoot)
}

function Resolve-StateDir {
    <#
        Mirrors glossary_generator\paths.py, in the same order:
          1. $GLOSSARY_STATE_DIR
          2. the app directory, when it is writable (a checkout)
          3. the per-user directory (a packaged install)

        Returns @{ Path; Why }.
    #>
    param([Parameter(Mandatory)][string] $ScriptRoot)

    $repoRoot = Get-RepoRoot $ScriptRoot

    if ($env:GLOSSARY_STATE_DIR) {
        return @{ Path = $env:GLOSSARY_STATE_DIR; Why = "GLOSSARY_STATE_DIR" }
    }
    # Only a CHECKOUT keeps state beside the code. An installed layout has its
    # app tree under $INSTDIR, which is read-only, so it falls through to the
    # per-user directory below - exactly as paths.py decides at runtime.
    $appDir = Join-Path $repoRoot "glossary_generator"
    if (Test-Path -LiteralPath (Join-Path $appDir "api.py")) {
        return @{ Path = $appDir; Why = "app directory (checkout)" }
    }
    # Tauri's app_data_dir is keyed on the bundle identifier.
    return @{ Path = (Join-Path $env:APPDATA "com.pentaho.pdc-glossary")
              Why  = "per-user (packaged install)" }
}

function Test-DirWritable {
    <#
        Probe by CREATING a file. os.access / ACL inspection both report the
        read-only attribute on Windows and ignore ACLs, so they happily say yes
        for a Program Files directory that then refuses the write.
    #>
    param([Parameter(Mandatory)][string] $Path)
    try {
        if (-not (Test-Path -LiteralPath $Path)) {
            New-Item -ItemType Directory -Path $Path -Force | Out-Null
        }
        $probe = Join-Path $Path (".writeprobe-" + [Guid]::NewGuid().ToString("N"))
        Set-Content -LiteralPath $probe -Value "x" -Encoding ASCII
        Remove-Item -LiteralPath $probe -Force
        return $true
    } catch {
        return $false
    }
}

function Resolve-PyExe {
    <#
        The interpreter to run. Candidates cover BOTH layouts these scripts live
        in, because the installer bundles copies of them:

          installed:  $INSTDIR\provisioning\  ->  $INSTDIR\python\python.exe
          checkout:   desktop\scripts\        ->  desktop\src-tauri\vendor\python\

        Falls back to Python 3.9+ on PATH. Returns $null when there is none.
    #>
    param([Parameter(Mandatory)][string] $ScriptRoot)

    $here = Split-Path -Parent $ScriptRoot     # provisioning\.. or scripts\..
    foreach ($rel in @("python\python.exe", "src-tauri\vendor\python\python.exe")) {
        $c = Join-Path $here $rel
        if (Test-Path -LiteralPath $c) { return $c }
    }
    foreach ($cand in @("python", "py")) {
        try {
            & $cand -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 9) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { return $cand }
        } catch {}
    }
    return $null
}

function Resolve-AppPy {
    <#
        The directory holding api.py / packinit.py / llm_detect.py.

        CHECKOUT FIRST among the dev candidates: vendor\app is a build artifact
        that goes stale the moment the source changes, and on a dev machine both
        exist - preferring it once ran a pre-1.29 packinit and warned about
        builtin keywords that no longer exist. In an installed layout only
        $INSTDIR\app is present, so it wins there by being the only one.
    #>
    param([Parameter(Mandatory)][string] $ScriptRoot)

    $here = Split-Path -Parent $ScriptRoot
    $candidates = @(
        (Join-Path $here "app\glossary_generator"),                    # installed
        (Join-Path (Get-RepoRoot $ScriptRoot) "glossary_generator"),   # checkout
        (Join-Path $here "src-tauri\vendor\app\glossary_generator")    # staged
    )
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath (Join-Path $c "packinit.py")) { return $c }
    }
    return $null
}
