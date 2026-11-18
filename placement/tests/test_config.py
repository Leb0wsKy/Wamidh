from pathlib import Path

import pytest

from placement.config import load_config

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("cwd", [REPO_ROOT, REPO_ROOT / "placement"])
def test_config_path_relative_to_placement_works_from_repo_root_or_package(
    cwd: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(cwd)

    cfg = load_config("config/pilot_kroumirie.yaml")

    assert cfg["root"] == REPO_ROOT
    assert cfg["paths"]["raw"] == REPO_ROOT / "data" / "raw"
