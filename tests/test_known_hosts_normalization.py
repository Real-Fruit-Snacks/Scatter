from pathlib import Path

from scatter.config import load_inventory


def test_known_hosts_boolean_false_is_off(tmp_path: Path) -> None:
    invp = tmp_path / "inv.yaml"
    invp.write_text(
        """
        defaults:
          known_hosts: false
        hosts:
          - host: h
            command: echo x
        """,
        encoding="utf-8",
    )
    inv = load_inventory(invp)
    assert inv.defaults.known_hosts == "off"


def test_known_hosts_string_variants(tmp_path: Path) -> None:
    invp = tmp_path / "inv.yaml"
    invp.write_text(
        """
        defaults:
          known_hosts: On
        hosts:
          - host: h
            command: echo x
        """,
        encoding="utf-8",
    )
    inv = load_inventory(invp)
    assert inv.defaults.known_hosts == "strict"
