"""
Configuración persistente del CLI, guardada en ~/.config/ghub-cli/config.json
"""
import json
from pathlib import Path

DEFAULT_BASE_URL = "http://100.117.45.120:8000"

CONFIG_DIR = Path.home() / ".config" / "ghub-cli"
CONFIG_PATH = CONFIG_DIR / "config.json"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text())
    except (ValueError, OSError):
        return {}


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
