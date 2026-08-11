"""Entry point for the desktop shell's backend.

Why this exists rather than `python -m uvicorn api:app`:

The vendored runtime is Python's Windows "embeddable package", whose `._pth`
file REPLACES sys.path outright. The current directory is not on it, and
PYTHONPATH is ignored while a `._pth` is present - so `api:app` is simply not
importable, no matter what working directory the process is given. The failure
is a bare ModuleNotFoundError with nothing pointing at the cause.

Putting the app directory on sys.path explicitly fixes that, and gives the
packaged and development launches ONE code path instead of two that can drift.

    python boot.py --port 5599 [--app-dir <dir>]

--app-dir defaults to glossary_generator/ beside this file, which is the shape
stage-app.ps1 produces:

    app/boot.py
    app/glossary_generator/api.py
    app/frontend/dist/index.html
"""
import argparse
import os
import sys


def _plain(path):
    r"""Drop Windows' verbatim \\?\ prefix from a drive path.

    os.chdir() cannot use one: SetCurrentDirectory rejects the verbatim form,
    so an install under C:\Program Files failed here with every file present
    and every path check passing. The shell strips it too - this is the second
    line of defence, because the cost of getting it wrong is a server that
    dies before it can say why.

    Genuine UNC paths (\\?\UNC\...) and paths over the legacy limit still need
    the prefix, so only ordinary drive paths are unwrapped.
    """
    p = str(path)
    if p.startswith("\\\\?\\"):
        rest = p[4:]
        if len(rest) > 2 and rest[1] == ":" and rest[0].isalpha() and len(rest) < 250:
            return rest
    return p


def main():
    ap = argparse.ArgumentParser(description="Start the Glossary Generator backend.")
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--app-dir", default=None)
    args = ap.parse_args()

    here = _plain(os.path.dirname(os.path.abspath(__file__)))
    app_dir = _plain(os.path.abspath(args.app_dir or os.path.join(here, "glossary_generator")))

    api_py = os.path.join(app_dir, "api.py")
    if not os.path.isfile(api_py):
        # Explicit beats a ModuleNotFoundError three frames deep: this is the
        # message that tells whoever is reading the log that the INSTALL is
        # wrong, not the app.
        sys.exit("boot: api.py not found at {} - the install is incomplete".format(api_py))

    # Both directories, in this order:
    #   app_dir  - api.py and its siblings
    #   here     - pdc_client/, the shared PDC API client that lives at the REPO
    #              ROOT, one level up from glossary_generator. In development it
    #              is pip-installed into the venv, so nothing points at it; in
    #              the packaged tree it is just a directory, and without this the
    #              import fails deep inside api.py's module-level code.
    sys.path.insert(0, here)
    sys.path.insert(0, app_dir)
    os.chdir(app_dir)

    # Belt and braces with the shell's PYTHONDONTWRITEBYTECODE: never compile
    # bytecode into a read-only install tree - a .pyc the installer never
    # shipped is a file the uninstaller leaves behind.
    sys.dont_write_bytecode = True

    import uvicorn
    uvicorn.run("api:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
