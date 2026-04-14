"""YAML + environment variable configuration loader."""

import os
from pathlib import Path

import yaml

from .models import AppConfig


def load_config(config_path: str = "config.yaml") -> AppConfig:
    """Load and validate config from YAML file + environment variables.

    Raises:
        FileNotFoundError: If config file does not exist.
        ValueError: If config is empty/invalid or required env vars are missing.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}. "
            f"Copy config.example.yaml to config.yaml and customize."
        )

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not raw or not isinstance(raw, dict):
        raise ValueError(
            f"Config file {config_path} is empty or not a valid YAML mapping."
        )

    config = AppConfig.model_validate(raw)

    # Validate API key env var exists
    api_key = os.environ.get(config.llm.api_key_env)
    if not api_key:
        raise ValueError(
            f"Missing required environment variable: {config.llm.api_key_env}. "
            f"Set it as a GitHub Secret or export it locally."
        )

    # Validate Feishu webhook env var exists
    feishu_webhook = os.environ.get(config.notification.feishu_webhook_env)
    if not feishu_webhook:
        raise ValueError(
            f"Missing required environment variable: {config.notification.feishu_webhook_env}. "
            f"Create a Feishu bot and add its webhook URL as a GitHub Secret."
        )

    return config
