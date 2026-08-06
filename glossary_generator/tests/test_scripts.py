"""Guards on the shipped shell scripts.

These exist because the same fault occurred three times in one day: a Windows
path written through an inline Python heredoc, where `\\v`, `\\b` and `\\a`
silently become control characters. Each time the script parsed, committed, and
failed only when run - once mid-build, once inside an installer.

A file check catches it in a second. Reviewing harder does not.
"""
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT_DIRS = [
    os.path.join(REPO, "desktop", "scripts"),
    os.path.join(REPO, "desktop", "scripts", "lib"),
]


def _scripts():
    for d in SCRIPT_DIRS:
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.endswith(".ps1"):
                yield os.path.join(d, name)


def test_there_are_scripts_to_check():
    """A guard that silently checks nothing is worse than no guard."""
    assert list(_scripts()), "no .ps1 files found - has the layout moved?"


@pytest.mark.parametrize("path", list(_scripts()), ids=os.path.basename)
def test_no_control_characters(path):
    r"""Vertical tab, backspace, bell and friends.

    `"src-tauri\vendor\python"` written into a non-raw Python string becomes
    `src-tauri<VT>endor\python`, which PowerShell then rejects at RUNTIME with
    "Illegal characters in path" - long after review.
    """
    with open(path, "rb") as f:
        raw = f.read()
    bad = sorted({b for b in raw if b < 32 and b not in (9, 10, 13)})
    assert not bad, (
        "control characters {} in {} - almost certainly a Windows path mangled "
        "by an escape sequence".format([hex(b) for b in bad], os.path.basename(path))
    )


@pytest.mark.parametrize("path", list(_scripts()), ids=os.path.basename)
def test_ascii_only(path):
    """PowerShell 5.1 mis-parses non-ASCII in some contexts, and these scripts
    are all documented as ASCII-only. An em-dash pasted into a comment is enough
    to break a run on a machine with a different codepage."""
    with open(path, "rb") as f:
        raw = f.read()
    high = sorted({b for b in raw if b > 127})
    assert not high, "non-ASCII bytes {} in {}".format(
        [hex(b) for b in high], os.path.basename(path)
    )
