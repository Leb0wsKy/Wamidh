"""Downloads for the zones pipeline: WorldPop population and OpenCelliD towers.

The OpenCelliD key is read from the OPENCELLID_API_KEY environment variable, else from the
repository's `.env` file (git-ignored). It is never printed or written anywhere else.
"""

from __future__ import annotations

import gzip
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

KEY_VAR = "OPENCELLID_API_KEY"


def _key(repo: Path) -> str | None:
    if os.environ.get(KEY_VAR):
        return os.environ[KEY_VAR].strip()
    env = repo / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip() == KEY_VAR and value.strip():
                return value.strip().strip('"').strip("'")
    return None


def _fetch(url: str, dest: Path, shown: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Wamidh zones pipeline"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:  # noqa: S310 (fixed https URLs)
            data = r.read()
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Download failed ({e.code}) for {shown}") from e
    dest.write_bytes(data)
    print(f"downloaded {shown} -> {dest} ({len(data) // 1024} KB)")


def download_worldpop(cfg: dict[str, Any], repo: Path) -> None:
    dest = repo / cfg["inputs"]["worldpop"]
    if dest.exists():
        print(f"{dest} already present")
        return
    url = cfg["downloads"]["worldpop_url"]
    _fetch(url, dest, url)


def download_towers(cfg: dict[str, Any], repo: Path) -> bool:
    """True if the towers file is present after the call."""
    dest = repo / cfg["inputs"]["towers"]
    if dest.exists():
        print(f"{dest} already present")
        return True
    key = _key(repo)
    if not key:
        print(
            f"OpenCelliD: no key. Put {KEY_VAR}=<your key> in .env (free account at "
            "opencellid.org); the zones are built without towers meanwhile."
        )
        return False
    url = cfg["downloads"]["opencellid_url"].format(key=key)
    shown = cfg["downloads"]["opencellid_url"].format(key="***")
    _fetch(url, dest, shown)
    try:  # OpenCelliD answers errors (bad key, daily limit) with a small text page, not gzip
        with gzip.open(dest, "rt", encoding="utf-8") as f:
            f.readline()
    except OSError as e:
        message = dest.read_bytes()[:300].decode("utf-8", "replace").replace(key, "***")
        dest.unlink()
        raise SystemExit(f"OpenCelliD did not return a tower file: {message!r}") from e
    return True


def download_all(cfg: dict[str, Any], repo: Path) -> None:
    download_worldpop(cfg, repo)
    download_towers(cfg, repo)
