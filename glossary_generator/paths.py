"""Where the app's mutable state lives.

Every persisted file (glossaries, settings, connections, roster, dictionary,
audit log, exported registries) used to default to a path beside api.py. That
is correct for a source checkout and for the training VM, and FATAL for a
packaged install: C:\\Program Files is not writable, so the first save fails and
the app looks broken rather than mis-installed.

This module is the single place that answers "which directory". Resolution, in
order:

  1. $GLOSSARY_STATE_DIR, if set. Explicit always wins - this is what the
     Windows installer's launcher sets, so the packaged app never has to infer
     anything.
  2. The app directory, if it is writable. Unchanged behaviour for checkouts,
     run.ps1/run.sh, and the lab VM - nobody's existing state moves.
  3. The per-user data directory (%APPDATA%\\PDC-Glossary on Windows,
     $XDG_DATA_HOME or ~/.local/share/pdc-glossary elsewhere). Only reached when
     the app directory is read-only, i.e. a packaged install.

Writability is PROBED, not asked. os.access(W_OK) reports the read-only
attribute on Windows and ignores ACLs, so it happily says yes for a directory
under Program Files that will then refuse the write.

Per-file environment overrides ($GLOSSARY_GLOSSARIES and friends) still win over
all of this, unchanged - the test suite relies on exactly that, and so does any
existing deployment that set them.
"""
import os
import sys
import tempfile

APP_DIR = os.path.dirname(os.path.abspath(__file__))

_STATE_DIR = None
_STATE_SOURCE = None      # why we chose it - surfaced by /api/config


def _is_writable(path):
    """Probe by actually creating a file. See the module docstring."""
    if not os.path.isdir(path):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            return False
    try:
        fd, probe = tempfile.mkstemp(prefix=".writeprobe-", dir=path)
        os.close(fd)
        os.unlink(probe)
        return True
    except OSError:
        return False


def _user_data_dir():
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "PDC-Glossary")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/PDC-Glossary")
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "pdc-glossary")


def state_dir():
    """The directory holding mutable state. Created if missing. Cached."""
    global _STATE_DIR, _STATE_SOURCE
    if _STATE_DIR is not None:
        return _STATE_DIR

    explicit = os.environ.get("GLOSSARY_STATE_DIR")
    if explicit:
        _STATE_DIR, _STATE_SOURCE = os.path.abspath(explicit), "GLOSSARY_STATE_DIR"
    elif _is_writable(APP_DIR):
        _STATE_DIR, _STATE_SOURCE = APP_DIR, "app directory (writable)"
    else:
        _STATE_DIR, _STATE_SOURCE = _user_data_dir(), "per-user (app directory is read-only)"

    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
    except OSError:
        # Last resort: a read-only state dir is not recoverable, but failing at
        # import time would take the whole app down with a stack trace. Let the
        # individual writes fail with their own messages instead.
        pass
    return _STATE_DIR


def state_source():
    """Human-readable reason for the current state_dir(). For diagnostics."""
    state_dir()
    return _STATE_SOURCE


def state_path(name, env_var=None):
    """Resolve one piece of state.

    A per-file env override wins outright, so existing deployments and the test
    suite (which points every file at a temp dir) behave exactly as before.
    """
    if env_var:
        override = os.environ.get(env_var)
        if override:
            return override
    return os.path.join(state_dir(), name)


def asset_path(name):
    """Read-only file that ships WITH the app: templates, VERSION, the domain
       pack. Always beside the code, never in the state dir - these are part of
       the install and are replaced wholesale by an upgrade."""
    return os.path.join(APP_DIR, name)


def domain_pack_path():
    """The scenario vocabulary pack. An ASSET, not state - it ships with the
       install or is pointed at by $GLOSSARY_DOMAIN_PACK.

       Here because the same two-line rule was written out independently in
       api.py (twice), tagdict.py and suggester.py. Four copies of "where does
       the pack come from" is four chances for a packaged build to resolve it
       differently, and the engine silently falls back to generic defaults when
       the file is missing - so a wrong answer looks like a bland glossary, not
       an error."""
    return os.environ.get("GLOSSARY_DOMAIN_PACK") or asset_path("domain_pack.json")


def reset_cache():
    """Forget the resolved directory. Tests only - the environment is read once
       per process otherwise."""
    global _STATE_DIR, _STATE_SOURCE
    _STATE_DIR = _STATE_SOURCE = None
