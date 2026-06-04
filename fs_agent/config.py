import yaml
from threading import Lock
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"

class SingletonMeta(type):
    """Thread-safe Singleton metaclass."""
    _instances = {}
    _lock = Lock()

    def __call__(cls, *args, **kwargs):
        # Double-checked locking to ensure thread safety
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    instance = super().__call__(*args, **kwargs)
                    cls._instances[cls] = instance
        return cls._instances[cls]


class Config(metaclass=SingletonMeta):
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
        self.models: dict[str, str] = {}
        self.debug: bool = False

        self.load_config(self.path)

    def load_config(self, path: str | Path) -> None:
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with path.open("r", encoding="utf-8") as stream:
            config: dict[str, Any] = yaml.safe_load(stream) or {}

        self.models = config.get("models", {})

        if not isinstance(self.models, dict):
            raise ValueError("Invalid config: 'models' must be a dict")

        self.debug = config.get("debug", False)