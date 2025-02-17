import argparse
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class EggConfig:
    provider: str = "provider"
    editor: str = "nano"
    color_scheme: str = "github-dark"
    openai_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    mistral_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None

    # command line arguments are carried here but not stored in config file
    args: argparse.Namespace = field(default_factory=lambda: argparse.Namespace())

    @staticmethod
    def load_config(config_path: Optional[str] = None) -> "EggConfig":
        """
        Load configuration from a specified path or default ~/.eigengen/config.json if it exists.
        Returns an EggConfig instance with loaded or default values.
        """
        if config_path is None:
            config_path = os.path.expanduser("~/.eigengen/config.json")

        if not os.path.exists(config_path):
            return EggConfig()

        try:
            with open(config_path, "r") as f:
                data = json.load(f)
            return EggConfig(
                provider=data.get("provider", "openai-o3-mini"),
                editor=data.get("editor", "nano"),
                color_scheme=data.get("color_scheme", "github-dark"),
                openai_api_key=data.get("openai_api_key", None),
                google_api_key=data.get("google_api_key", None),
                groq_api_key=data.get("groq_api_key", None),
                anthropic_api_key=data.get("anthropic_api_key", None),
                mistral_api_key=data.get("mistral_api_key", None),
                deepseek_api_key=data.get("deepseek_api_key", None),
                args=argparse.Namespace(),
            )
        except Exception as e:
            logger.error(f"Error loading config file '{config_path}': {e}. Using default configuration.")
        return EggConfig()

    def save_config(self, config_path: Optional[str] = None) -> None:
        """
        Save the current configuration to a specified path or ~/.eigengen/config.json.
        """
        if config_path is None:
            config_path = os.path.expanduser("~/.eigengen/config.json")

        try:
            with open(config_path, "w") as f:
                json.dump(
                    {"provider": self.provider, "editor": self.editor, "color_scheme": self.color_scheme}, f, indent=4
                )
            logger.info("Configuration saved to %s.", config_path)
        except Exception as e:
            logger.error(f"Error saving config file '{config_path}': {e}.")
