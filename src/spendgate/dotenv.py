"""A twelve-line .env loader.

Not python-dotenv: this needs to read four lines out of a file, and a runtime
dependency for that is not worth it. Existing environment variables always win,
so `OPENROUTER_MODEL=x python -m ...` overrides the file as expected.
"""

from __future__ import annotations

import os
from pathlib import Path


#: Explicit opt-out. Set it to run as if no .env existed — needed in CI, and by
#: the test that asserts the LLM runner refuses to start without a key. Without
#: this, that test loads the developer's real key and starts a paid evaluation.
OPT_OUT = "SPENDGATE_NO_DOTENV"


def load(path: str | Path = ".env", *, override: bool = False) -> list[str]:
    """Load KEY=VALUE lines. Returns the names loaded — never the values."""
    if os.environ.get(OPT_OUT):
        return []
    p = Path(path)
    if not p.is_file():
        return []
    loaded: list[str] = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if not key or not value:
            continue
        if override or key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded


def find_and_load(start: str | Path = ".") -> list[str]:
    """Walk up from `start` looking for a .env, so entry points work from anywhere."""
    if os.environ.get(OPT_OUT):
        return []
    here = Path(start).resolve()
    for directory in (here, *here.parents):
        candidate = directory / ".env"
        if candidate.is_file():
            return load(candidate)
    return []
