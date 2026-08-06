"""State-location rules.

The app used to keep every persisted file beside api.py. That breaks the moment
it is installed somewhere read-only (C:\\Program Files), so paths.py decides the
directory instead. These tests pin the decision order, because getting it wrong
does not raise - it silently writes the user's glossary somewhere they will
never look for it.
"""
import os
import sys

import pytest

from core import paths


@pytest.fixture
def clean_env(monkeypatch):
    """paths caches its answer for the process; each test needs a fresh one."""
    monkeypatch.delenv("GLOSSARY_STATE_DIR", raising=False)
    paths.reset_cache()
    yield monkeypatch
    paths.reset_cache()


def test_explicit_state_dir_wins(clean_env, tmp_path):
    target = tmp_path / "explicit"
    clean_env.setenv("GLOSSARY_STATE_DIR", str(target))
    assert paths.state_dir() == str(target)
    assert paths.state_source() == "GLOSSARY_STATE_DIR"
    assert target.is_dir(), "the state dir must be created, not merely named"


def test_writable_app_dir_keeps_state_in_place(clean_env):
    """A source checkout, run.ps1/run.sh and the lab VM must not move: their
       state stays beside the code exactly as it did before paths.py existed."""
    clean_env.setattr(paths, "_is_writable", lambda p: True)
    assert paths.state_dir() == paths.APP_DIR
    assert "app directory" in paths.state_source()


def test_read_only_app_dir_falls_back_to_user_dir(clean_env):
    """The packaged case. Program Files is not writable, so state has to leave
       the install tree - otherwise the first save fails and the app merely
       looks broken."""
    clean_env.setattr(paths, "_is_writable", lambda p: False)
    resolved = paths.state_dir()
    assert resolved != paths.APP_DIR
    assert resolved == paths._user_data_dir()
    assert "read-only" in paths.state_source()


def test_per_file_override_beats_the_state_dir(clean_env, tmp_path):
    """Existing deployments (and this suite) point individual files at their own
       paths. That must keep working, or upgrading silently orphans their data."""
    clean_env.setenv("GLOSSARY_STATE_DIR", str(tmp_path / "state"))
    clean_env.setenv("GLOSSARY_GLOSSARIES", str(tmp_path / "elsewhere" / "g.json"))
    assert paths.state_path("glossaries.json", "GLOSSARY_GLOSSARIES") == \
        str(tmp_path / "elsewhere" / "g.json")


def test_state_path_without_override_lands_in_the_state_dir(clean_env, tmp_path):
    clean_env.setenv("GLOSSARY_STATE_DIR", str(tmp_path))
    clean_env.delenv("GLOSSARY_GLOSSARIES", raising=False)
    assert paths.state_path("glossaries.json", "GLOSSARY_GLOSSARIES") == \
        os.path.join(str(tmp_path), "glossaries.json")


def test_empty_override_is_ignored(clean_env, tmp_path):
    """An env var set to "" is the shape a shell script produces when a variable
       is unset - treat it as absent, not as the current directory."""
    clean_env.setenv("GLOSSARY_STATE_DIR", str(tmp_path))
    clean_env.setenv("GLOSSARY_GLOSSARIES", "")
    assert paths.state_path("glossaries.json", "GLOSSARY_GLOSSARIES") == \
        os.path.join(str(tmp_path), "glossaries.json")


def test_assets_never_move_to_the_state_dir(clean_env, tmp_path):
    """templates/, VERSION and the domain pack ship WITH the install and are
       replaced by an upgrade. Resolving them against the state dir would mean a
       packaged app looking for its own templates in %APPDATA%."""
    clean_env.setenv("GLOSSARY_STATE_DIR", str(tmp_path))
    assert paths.asset_path("VERSION") == os.path.join(paths.APP_DIR, "VERSION")
    assert os.path.isfile(paths.asset_path("VERSION"))


def test_domain_pack_prefers_the_env_var_then_the_install(clean_env, tmp_path):
    clean_env.setenv("GLOSSARY_DOMAIN_PACK", str(tmp_path / "pack.json"))
    assert paths.domain_pack_path() == str(tmp_path / "pack.json")
    clean_env.delenv("GLOSSARY_DOMAIN_PACK", raising=False)
    clean_env.setenv("GLOSSARY_STATE_DIR", str(tmp_path / "state"))
    assert paths.domain_pack_path() == paths.asset_path("domain_pack.json")


def test_a_pack_in_the_state_dir_beats_the_shipped_one(clean_env, tmp_path):
    """The user drops a pack in, or the app rewrites one. Either must win over
       the starter that shipped with the install, or refreshing the pack would
       appear to do nothing."""
    clean_env.delenv("GLOSSARY_DOMAIN_PACK", raising=False)
    state = tmp_path / "state"
    state.mkdir()
    clean_env.setenv("GLOSSARY_STATE_DIR", str(state))
    assert paths.domain_pack_path() == paths.asset_path("domain_pack.json")

    (state / "domain_pack.json").write_text("{}", encoding="utf-8")
    assert paths.domain_pack_path() == str(state / "domain_pack.json")


def test_pack_writes_never_target_the_install_dir(clean_env, tmp_path):
    """The read path can be the shipped starter, which under a packaged install
       is in Program Files. Writing there fails, and "Draft pack -> apply" would
       report success on a file it never replaced."""
    clean_env.delenv("GLOSSARY_DOMAIN_PACK", raising=False)
    clean_env.setenv("GLOSSARY_STATE_DIR", str(tmp_path))
    assert paths.domain_pack_write_path() == os.path.join(str(tmp_path), "domain_pack.json")
    assert paths.domain_pack_write_path() != paths.asset_path("domain_pack.json")

    # An explicit override still wins - the operator chose that file.
    clean_env.setenv("GLOSSARY_DOMAIN_PACK", str(tmp_path / "chosen.json"))
    assert paths.domain_pack_write_path() == str(tmp_path / "chosen.json")


def test_writability_is_probed_not_asked(tmp_path):
    """os.access(W_OK) reports the read-only ATTRIBUTE on Windows and ignores
       ACLs, so it says yes for directories that then refuse the write. The
       probe has to be a real file operation."""
    assert paths._is_writable(str(tmp_path)) is True
    missing = tmp_path / "does" / "not" / "exist"
    assert paths._is_writable(str(missing)) is True, "a creatable path is writable"
    assert missing.is_dir()


def test_probe_leaves_nothing_behind(tmp_path):
    before = set(os.listdir(tmp_path))
    paths._is_writable(str(tmp_path))
    assert set(os.listdir(tmp_path)) == before


def test_unwritable_path_reports_false(tmp_path):
    """A file where a directory is expected: makedirs fails, so does the probe."""
    blocker = tmp_path / "iam-a-file"
    blocker.write_text("x", encoding="utf-8")
    assert paths._is_writable(str(blocker)) is False


@pytest.mark.skipif(sys.platform != "win32", reason="Windows layout")
def test_windows_user_dir_is_under_appdata(clean_env, tmp_path):
    clean_env.setenv("APPDATA", str(tmp_path))
    assert paths._user_data_dir() == os.path.join(str(tmp_path), "PDC-Glossary")


def test_app_modules_agree_on_the_state_dir():
    """api, audit and tagdict must resolve through the SAME module. Three copies
       of the rule is how the State snapshot ended up ignoring the registry
       override it documented."""
    from core import audit
    from engine import tagdict
    for mod in (audit, tagdict):
        assert mod.paths is paths
