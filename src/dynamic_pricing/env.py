"""
Lightweight helpers to load environment variables from a ``.env`` file.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_env_file(dotenv_path: str | Path = ".env") -> None:
    """
    Populate ``os.environ`` using key/value pairs from ``dotenv_path`` (if it exists).

    Existing environment variables always win so shell exports or CI secrets are never
    overwritten by accidental entries in the file.
    """

    path = Path(dotenv_path)
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if value and (value[0] == value[-1]) and value.startswith(("'", '"')):
            value = value[1:-1]
        os.environ[key] = value


__all__ = ["load_env_file"]
