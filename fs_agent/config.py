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
        self.model_extra_body: dict[str, Any] = {}
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

        self.model_extra_body = config.get("model_extra_body", {}) or {}

        if not isinstance(self.model_extra_body, dict):
            raise ValueError("Invalid config: 'model_extra_body' must be a dict")

        self.debug = config.get("debug", False)

    def build_model(self, role: str):
        """Build the chat model for an agent role from config.

        The model id is the ``"<provider>:<model>"`` string under ``models``.
        ``model_extra_body`` (if non-empty) is forwarded to ``init_chat_model``
        as ``extra_body``, so provider-specific options live in config instead
        of code — e.g. Qwen's ``{"enable_thinking": false}`` or DeepSeek's
        ``{"thinking": {"type": "disabled"}}``. Leaving it empty keeps the call
        provider-agnostic, compatible with both DeepSeek and Qwen.
        """
        from langchain.chat_models import init_chat_model

        model_name = self.models.get(role)
        if not model_name:
            raise ValueError(f"No model configured for role '{role}'")

        kwargs: dict[str, Any] = {"model": model_name}
        if self.model_extra_body:
            kwargs["extra_body"] = self.model_extra_body
        return init_chat_model(**kwargs)