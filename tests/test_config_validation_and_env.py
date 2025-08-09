from __future__ import annotations

import os
from pathlib import Path

import pytest

from scatter.config import load_inventory


def test_missing_inventory_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_inventory(Path("/nonexistent/inventory.yaml"))


def test_inventory_without_hosts_raises(tmp_path: Path) -> None:
    p = tmp_path / "inv.yaml"
    p.write_text(
        """
        defaults:
          username: u
        hosts: []
        """,
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_inventory(p)


def test_identity_env_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key_path = tmp_path / "id_key"
    key_path.write_text("x", encoding="utf-8")
    monkeypatch.setenv("ID_PATH", str(key_path))

    p = tmp_path / "inv.yaml"
    p.write_text(
        """
        defaults:
          identity: env:ID_PATH
        hosts:
          - host: h
            command: echo x
          - host: h2
            identity: env:ID_PATH
            command: echo y
        """,
        encoding="utf-8",
    )

    inv = load_inventory(p)
    assert inv.defaults.identity == str(key_path)
    assert inv.hosts[1].identity == str(key_path)


@pytest.mark.parametrize(
    "val,expected",
    [
        ("no", "off"),
        ("0", "off"),
        ("false", "off"),
        ("true", "strict"),
        ("1", "strict"),
    ],
)
def test_known_hosts_variants(tmp_path: Path, val: str, expected: str) -> None:
    p = tmp_path / "inv.yaml"
    p.write_text(
        f"""
        defaults:
          known_hosts: {val}
        hosts:
          - host: h
            command: echo x
        """,
        encoding="utf-8",
    )
    inv = load_inventory(p)
    assert inv.defaults.known_hosts == expected


