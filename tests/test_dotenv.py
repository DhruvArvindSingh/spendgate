"""The .env loader (src/spendgate/dotenv.py)."""

from __future__ import annotations

import os

from spendgate.dotenv import find_and_load, load


def test_loads_keys_and_returns_names_not_values(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('FOO=bar\nexport BAZ="qux"\n# comment\n\nEMPTY=\n')
    monkeypatch.delenv("FOO", raising=False)
    monkeypatch.delenv("BAZ", raising=False)

    names = load(env)
    assert set(names) == {"FOO", "BAZ"}
    assert os.environ["FOO"] == "bar"
    assert os.environ["BAZ"] == "qux", "quotes are stripped"
    assert "EMPTY" not in os.environ, "blank values are skipped, not set empty"
    assert "bar" not in names, "the loader must never hand back values"


def test_existing_environment_wins(tmp_path, monkeypatch):
    """So `OPENROUTER_MODEL=x python -m ...` overrides the file, as expected."""
    env = tmp_path / ".env"
    env.write_text("SPENDGATE_TEST_VAR=from_file\n")
    monkeypatch.setenv("SPENDGATE_TEST_VAR", "from_shell")
    load(env)
    assert os.environ["SPENDGATE_TEST_VAR"] == "from_shell"
    load(env, override=True)
    assert os.environ["SPENDGATE_TEST_VAR"] == "from_file"


def test_missing_file_is_not_an_error(tmp_path):
    assert load(tmp_path / "nope.env") == []


def test_walks_upward_to_find_the_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("SPENDGATE_WALK=1\n")
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    monkeypatch.delenv("SPENDGATE_WALK", raising=False)
    assert find_and_load(deep) == ["SPENDGATE_WALK"]
    assert os.environ["SPENDGATE_WALK"] == "1"


def test_env_is_gitignored():
    """A committed .env is the one mistake this project cannot take back."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    ignore = (root / ".gitignore").read_text().splitlines()
    assert ".env" in [line.strip() for line in ignore]


def test_opt_out_disables_loading(tmp_path, monkeypatch):
    """Without this, any test that strips a key from the environment silently
    gets it back from disk — and for the LLM runner that means a real, paid run."""
    (tmp_path / ".env").write_text("SPENDGATE_OPTOUT_CHECK=loaded\n")
    monkeypatch.delenv("SPENDGATE_OPTOUT_CHECK", raising=False)
    monkeypatch.setenv("SPENDGATE_NO_DOTENV", "1")
    assert load(tmp_path / ".env") == []
    assert find_and_load(tmp_path) == []
    assert "SPENDGATE_OPTOUT_CHECK" not in os.environ
