import os
from pathlib import Path

import pytest

from scatter.config import load_inventory


def test_load_inventory_basic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inv_path = tmp_path / "inv.yaml"
    inv_path.write_text(
        """
        defaults:
          username: ubuntu
          port: 22
          connect_timeout: 5
          known_hosts: off
          pty: false
          identity: ~/.ssh/id_rsa
          password: env:GLOBAL_PW
        hosts:
          - host: h1
            username: ec2-user
            identity: ~/.ssh/h1
            command: echo ok
          - host: h2
            password: env:H2_PW
            command: echo ok2
        """,
        encoding="utf-8",
    )

    monkeypatch.setenv("GLOBAL_PW", "gpass")
    monkeypatch.setenv("H2_PW", "h2pass")

    inv = load_inventory(inv_path)

    assert inv.defaults.username == "ubuntu"
    assert inv.defaults.port == 22
    assert inv.defaults.known_hosts == "strict" or inv.defaults.known_hosts == "off"

    assert inv.hosts[0].host == "h1"
    assert inv.hosts[0].username == "ec2-user"
    assert inv.hosts[0].identity == "~/.ssh/h1"

    assert inv.hosts[1].host == "h2"
    assert inv.hosts[1].password == "h2pass"
