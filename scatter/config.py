"""Inventory and configuration loading for Scatter.

Supports loading a YAML inventory with global defaults and per-host overrides.

Highlights
- ``env:VAR`` resolution for sensitive fields like ``identity`` and ``password``.
- Flexible ``known_hosts`` normalization accepting booleans and string variants
  (e.g., ``false``, ``no``, ``0`` → ``off``; ``true``, ``on``, ``1`` → ``strict``).
- Validation: raises ``FileNotFoundError`` for missing files and ``ValueError``
  when the inventory contains no hosts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class InventoryDefaults:
    """Global defaults applied to hosts unless overridden per-host."""
    username: Optional[str] = None
    port: int = 22
    connect_timeout: float = 10.0
    known_hosts: str = "strict"  # "strict" | "off"
    pty: bool = False
    identity: Optional[str] = None
    password: Optional[str] = None


@dataclass
class HostEntry:
    """A single host specification from the inventory."""
    host: str
    username: Optional[str] = None
    port: Optional[int] = None
    tags: List[str] = field(default_factory=list)
    identity: Optional[str] = None
    password: Optional[str] = None
    command: Optional[str] = None

    def effective_username(self, defaults: InventoryDefaults, override: Optional[str]) -> Optional[str]:
        if override:
            return override
        if self.username:
            return self.username
        return defaults.username

    def effective_port(self, defaults: InventoryDefaults, override: Optional[int]) -> int:
        if override:
            return override
        if self.port:
            return int(self.port)
        return int(defaults.port)


@dataclass
class Inventory:
    """Parsed inventory contents with defaults and host list."""
    defaults: InventoryDefaults
    hosts: List[HostEntry]


def load_inventory(path: Path | str) -> Inventory:
    """Load and parse an inventory YAML file into an ``Inventory``.

    Expands ``env:VAR`` references for supported fields, normalizes known-hosts,
    and validates that at least one host is present.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Inventory file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    def _resolve_env(value: Optional[str]) -> Optional[str]:
        if not isinstance(value, str):
            return value
        value = value.strip()
        if value.startswith("env:"):
            env_key = value[4:].strip()
            return os.environ.get(env_key)
        return value

    raw_defaults: Dict[str, Any] = data.get("defaults", {}) or {}

    def _normalize_known_hosts(value: Any) -> str:
        # Accept YAML booleans (off -> False) and strings
        if isinstance(value, bool):
            return "off" if value is False else "strict"
        val = str(value).strip().lower()
        if val in {"off", "no", "false", "0"}:
            return "off"
        if val in {"strict", "on", "true", "1"}:
            return "strict"
        # Default to strict if unknown
        return "strict"
    defaults = InventoryDefaults(
        username=raw_defaults.get("username"),
        port=int(raw_defaults.get("port", 22)),
        connect_timeout=float(raw_defaults.get("connect_timeout", 10.0)),
        known_hosts=_normalize_known_hosts(raw_defaults.get("known_hosts", "strict")),
        pty=bool(raw_defaults.get("pty", False)),
        identity=_resolve_env(raw_defaults.get("identity")),
        password=_resolve_env(raw_defaults.get("password")),
    )

    raw_hosts: List[Dict[str, Any]] = data.get("hosts", []) or []
    hosts: List[HostEntry] = []
    for item in raw_hosts:
        hosts.append(
            HostEntry(
                host=str(item["host"]),
                username=item.get("username"),
                port=item.get("port"),
                tags=list(item.get("tags", []) or []),
                identity=_resolve_env(item.get("identity")),
                password=_resolve_env(item.get("password")),
                command=item.get("command"),
            )
        )

    if not hosts:
        raise ValueError("Inventory contains no hosts.")

    return Inventory(defaults=defaults, hosts=hosts)


