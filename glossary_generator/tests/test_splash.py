"""Guards on the desktop splash page.

The splash is the only screen a user sees when the app fails to start, and its
script is one block: a syntax error anywhere stops ALL of it, so the checklist
never renders, nothing polls, and the window sits on the placeholder text
looking like a slow backend. That is precisely what happened - a `join('\\n')`
written through an inline Python heredoc lost its escape and left an
unterminated string literal.

`node --check` catches it in under a second. The page cannot be exercised any
other way here: it needs the Tauri bridge to do anything at all.
"""
import os
import re
import shutil
import subprocess
import tempfile

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPLASH = os.path.join(REPO, "desktop", "dist", "index.html")


def _script():
    with open(SPLASH, encoding="utf-8") as f:
        html = f.read()
    m = re.search(r"<script>(.*?)</script>", html, re.S)
    assert m, "no <script> block in the splash page"
    return m.group(1)


@pytest.mark.skipif(not os.path.isfile(SPLASH), reason="desktop shell not present")
def test_splash_has_a_script():
    assert len(_script()) > 500, "the splash script is suspiciously small"


@pytest.mark.skipif(not os.path.isfile(SPLASH), reason="desktop shell not present")
@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_splash_script_parses():
    """A syntax error here is invisible until the app is installed and run."""
    src = _script()
    tmp = os.path.join(tempfile.mkdtemp(), "splash.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    proc = subprocess.run(
        ["node", "--check", tmp], capture_output=True, text=True
    )
    assert proc.returncode == 0, "splash script does not parse:\n" + proc.stderr


@pytest.mark.skipif(not os.path.isfile(SPLASH), reason="desktop shell not present")
def test_the_commands_it_calls_exist_in_the_shell():
    """Every invoke() target must be a real #[tauri::command].

    A renamed command fails silently: the promise rejects, the catch re-polls,
    and the splash waits forever - the same shape as the CORS bug, and just as
    hard to read from the screen.
    """
    called = set(re.findall(r"invoke\(['\"]([a-z_]+)['\"]\)", _script()))
    assert called, "no invoke() calls found - has the splash changed shape?"

    main_rs = os.path.join(REPO, "desktop", "src-tauri", "src", "main.rs")
    with open(main_rs, encoding="utf-8") as f:
        rust = f.read()
    defined = set(re.findall(r"#\[tauri::command\]\s*(?:async\s+)?fn\s+(\w+)", rust))

    missing = sorted(called - defined)
    assert not missing, "splash calls commands the shell does not define: {}".format(missing)
