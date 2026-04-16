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

    # Validate Feishu sending config: App API mode or webhook fallback
    has_app_api = (
        config.feishu_app
        and config.feishu_app.enabled
        and os.environ.get(config.feishu_app.app_id_env)
        and os.environ.get(config.feishu_app.app_secret_env)
    )
    feishu_webhook = os.environ.get(config.notification.feishu_webhook_env)
    if not has_app_api and not feishu_webhook:
        raise ValueError(
            "No Feishu sending method configured. Either:\n"
            "  1. Enable feishu_app in config.yaml and set FEISHU_APP_ID + FEISHU_APP_SECRET\n"
            "  2. Or set FEISHU_WEBHOOK_URL for webhook fallback"
        )

    # Validate Zotero credentials (optional -- only when zotero block exists and enabled)
    if config.zotero and config.zotero.enabled:
        zotero_user_id = os.environ.get(config.zotero.user_id_env)
        zotero_api_key = os.environ.get(config.zotero.api_key_env)
        if not zotero_user_id or not zotero_api_key:
            raise ValueError(
                f"Zotero enabled but missing credentials: set {config.zotero.user_id_env} and {config.zotero.api_key_env}"
            )

    # Validate Obsidian credentials (optional -- only when obsidian block exists and enabled)
    if config.obsidian and config.obsidian.enabled:
        if not config.obsidian.vault_repo_url:
            raise ValueError(
                "Obsidian enabled but vault_repo_url is empty. Set obsidian.vault_repo_url in config."
            )
        obsidian_pat = os.environ.get(config.obsidian.vault_pat_env)
        if not obsidian_pat:
            raise ValueError(
                f"Obsidian enabled but missing credentials: set {config.obsidian.vault_pat_env}"
            )

    return config
