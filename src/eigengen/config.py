import argparse
import os
import json
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class EggConfig:
    model: str = "claude"
    editor: str = "nano"
    color_scheme: str = "github-dark"

    # command line arguments are carried here but not stored in config file
    args: argparse.Namespace = field(default_factory=lambda: argparse.Namespace())

    @staticmethod
    def load_config(config_path: Optional[str] = None) -> 'EggConfig':
        """
        Load configuration from a specified path or default ~/.eigengen/config.json if it exists.
        Returns an EggConfig instance with loaded or default values.
        """
        if config_path is None:
            config_path = os.path.expanduser("~/.eigengen/config.json")
        
        if not os.path.exists(config_path):
            return EggConfig()
        
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
            return EggConfig(
                model=data.get("model", "claude"),
                editor=data.get("editor", "nano"),
                color_scheme=data.get("color_scheme", "github-dark"),
                args=argparse.Namespace()
            )
        except Exception as e:
            print(f"Error loading config file '{config_path}': {e}. Using default configuration.")
            return EggConfig()

    def save_config(self, config_path: Optional[str] = None) -> None:
        """
        Save the current configuration to a specified path or ~/.eigengen/config.json.
        """
        if config_path is None:
            config_path = os.path.expanduser("~/.eigengen/config.json")
        
        try:
            with open(config_path, 'w') as f:
                json.dump({
                    "model": self.model,
                    "editor": self.editor,
                    "color_scheme": self.color_scheme
                }, f, indent=4)
            print(f"Configuration saved to {config_path}.")
        except Exception as e:
            print(f"Error saving config file '{config_path}': {e}.")
