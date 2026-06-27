from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and (value is None or value == ""):
        raise RuntimeError(f"Missing required environment variable: {name}")
    if value is None:
        raise RuntimeError(f"Missing environment variable and default: {name}")
    return value


def env_int(name: str, default: int | None = None, required: bool = False) -> int:
    fallback = None if default is None else str(default)
    return int(env(name, fallback, required=required))


def env_float(name: str, default: float | None = None, required: bool = False) -> float:
    fallback = None if default is None else str(default)
    return float(env(name, fallback, required=required))


def env_decimal(name: str, default: str | None = None, required: bool = False) -> Decimal:
    return Decimal(env(name, default, required=required))


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def project_path(*parts: str) -> Path:
    return PROJECT_ROOT.joinpath(*parts)


def resolve_runtime_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def load_contract_abi(contract_name: str) -> list[dict[str, Any]]:
    artifact_path = project_path("artifacts", "contracts", f"{contract_name}.sol", f"{contract_name}.json")
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    return artifact["abi"]


def action_to_int(action: str) -> int:
    normalized = action.strip().lower()
    mapping = {"buy": 0, "sell": 1, "hold": 2}
    if normalized not in mapping:
        raise ValueError(f"Unsupported action: {action}")
    return mapping[normalized]


def int_to_action(value: int) -> str:
    mapping = {0: "buy", 1: "sell", 2: "hold"}
    return mapping.get(value, f"unknown:{value}")

