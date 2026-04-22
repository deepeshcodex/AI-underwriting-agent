"""Load YAML configs from a configurable directory."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from services.settings import settings


def config_dir() -> Path:
    return Path(settings.underwriting_config_dir)


def load_yaml(name: str) -> dict[str, Any]:
    path = config_dir() / name
    if not path.is_file():
        msg = f"Missing config file: {path}"
        raise FileNotFoundError(msg)
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        msg = f"Config {name} must be a YAML mapping at root."
        raise ValueError(msg)
    return data


@lru_cache
def load_docs() -> dict[str, Any]:
    return load_yaml("docs.yaml")


@lru_cache
def load_rules() -> dict[str, Any]:
    return load_yaml("rules.yaml")


@lru_cache
def load_prompts() -> dict[str, Any]:
    return load_yaml("prompts.yaml")


@lru_cache
def load_credit() -> dict[str, Any]:
    return load_yaml("credit.yaml")


@lru_cache
def load_ml() -> dict[str, Any]:
    return load_yaml("ml.yaml")


@lru_cache
def load_underwriting() -> dict[str, Any]:
    return load_yaml("underwriting.yaml")


@lru_cache
def load_validation() -> dict[str, Any]:
    return load_yaml("validation.yaml")


def clear_cache() -> None:
    load_docs.cache_clear()
    load_rules.cache_clear()
    load_prompts.cache_clear()
    load_credit.cache_clear()
    load_ml.cache_clear()
    load_underwriting.cache_clear()
    load_validation.cache_clear()
