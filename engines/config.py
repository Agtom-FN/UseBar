"""Cross-platform config (which service to show), stored as JSON.

  macOS   : ~/Library/Application Support/UseBar/config.json
  Windows : %APPDATA%\\UseBar\\config.json
  other   : ~/.config/usebar/config.json
"""
from __future__ import annotations
import json
import os
import sys

DEFAULTS = {"service": "claude"}
SERVICES = ["claude", "cursor"]
BETA = ["cursor"]          # experimental / endpoint not independently verified


def is_beta(service: str) -> bool:
    return service in BETA


def config_dir() -> str:
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    elif os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(base, "UseBar" if sys.platform == "darwin" or os.name == "nt" else "usebar")


def config_path() -> str:
    return os.path.join(config_dir(), "config.json")


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(config_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
    except Exception:
        pass
    if cfg.get("service") not in SERVICES:
        cfg["service"] = DEFAULTS["service"]
    return cfg


def save(cfg: dict) -> None:
    d = config_dir()
    os.makedirs(d, exist_ok=True)
    with open(config_path(), "w", encoding="utf-8") as fh:
        json.dump(cfg, fh)


def get_service() -> str:
    return load()["service"]


def set_service(service: str) -> None:
    if service not in SERVICES:
        raise ValueError(f"unknown service: {service}")
    cfg = load()
    cfg["service"] = service
    save(cfg)
