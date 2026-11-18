"""Load a pipeline YAML config and resolve its paths against the repository root."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PACKAGE_DIR = Path(__file__).resolve().parents[2]  # .../placement


def load_config(path: str | Path) -> dict[str, Any]:
    """Read the YAML config. Relative paths under `paths:` resolve against the repo root.

    A relative `path` is tried against the current directory first, then against the
    placement/ package directory, so commands work from the repo root or from placement/.
    The repo root is two levels above the config directory (placement/config/x.yaml).
    """
    path = Path(path)
    if not path.is_absolute() and not path.exists():
        path = PACKAGE_DIR / path
    path = path.resolve()
    with path.open(encoding="utf-8") as f:
        cfg: dict[str, Any] = yaml.safe_load(f)
    root = path.parents[2]
    cfg["root"] = root
    cfg["paths"] = {k: (root / v).resolve() for k, v in cfg["paths"].items()}
    return cfg
