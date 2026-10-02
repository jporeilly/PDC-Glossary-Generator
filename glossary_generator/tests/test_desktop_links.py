"""New tabs in the desktop window - the two ways they silently die.

The desktop shell shows the app in a webview pointed at
http://127.0.0.1:<port>. Two things about that window are invisible from a
browser:

1. The shell's opener plugin cancels every click on a link that opens a new
   tab and asks the shell to open it in the system browser. Capabilities
   cover only the shell's own start-up page unless one names the served
   pages, so the request was refused - after the click was already gone.
   Every such link was dead in the installed app.
2. `window.open()` returns null there: the window has no second window to
   give, so a button built on it does nothing.

None of this can be exercised without the shell, so these hold the pieces in
place: the grant, its narrowness, and where `window.open()` may appear.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CAPS = os.path.join(ROOT, "desktop", "src-tauri", "capabilities")
UI_SRC = os.path.join(ROOT, "frontend", "src")


def _capability(name):
    with open(os.path.join(CAPS, name), encoding="utf-8") as f:
        return json.load(f)


def test_the_apps_pages_may_open_links_and_nothing_else():
    cap = _capability("served-app.json")
    assert cap["windows"] == ["main"]
    # the served pages only: the splash already has its own, wider, grant
    assert cap.get("local") is False
    # the port is a wildcard because the shell picks a free one at launch; an
    # omitted port would mean port 80 only and match nothing
    assert cap["remote"]["urls"] == ["http://127.0.0.1:*"]
    assert sorted(cap["permissions"]) == ["opener:allow-default-urls", "opener:allow-open-url"]


def test_only_the_splash_reaches_the_shell():
    """The shell's commands and the file opener are default.json's; a `remote`
    key there, or in any other capability, would hand them to the served pages."""
    for name in sorted(os.listdir(CAPS)):
        if not name.endswith(".json") or name == "served-app.json":
            continue
        assert "remote" not in _capability(name), f"{name} grants remote pages access"


def _window_open_users():
    found = {}
    for base, _dirs, files in os.walk(UI_SRC):
        for name in files:
            if not name.endswith((".js", ".jsx", ".ts", ".tsx")):
                continue
            path = os.path.join(base, name)
            with open(path, encoding="utf-8") as f:
                text = f.read()
            if "window.open(" in text:
                found[os.path.relpath(path, UI_SRC).replace(os.sep, "/")] = text
    return found


def test_the_one_window_open_is_hidden_in_the_desktop_window():
    """The Files page opens a blob: preview in a new tab. Neither a second
    window nor the system browser can show that from the desktop app, so the
    button is offered in a browser only. Anything else should be a link."""
    users = _window_open_users()
    assert list(users) == ["pages/FilesPage.jsx"], sorted(users)
    text = users["pages/FilesPage.jsx"]
    assert text.count("window.open(") == 1
    assert "'__TAURI_INTERNALS__' in window" in text
    gate = text.index("blobUrl && !IN_DESKTOP_WINDOW && (")
    call = text.index("window.open(")
    assert 0 < call - gate < 200, "the Open in new tab button is no longer gated"
