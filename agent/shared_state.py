from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

try:
    from .config import env, env_int, resolve_runtime_path
except ImportError:  # pragma: no cover
    from config import env, env_int, resolve_runtime_path


DEFAULT_STATE: dict[str, Any] = {
    "updated_at": None,
    "market": {
        "symbol": "ETH/USDC",
        "price": None,
        "confidence": None,
        "publish_time": None,
        "history": []
    },
    "decision": {
        "action": "hold",
        "size": 0.0,
        "source": "boot",
        "raw_model_output": "",
        "rationale": "Agent not started."
    },
    "reasoning": {
        "status": "idle",
        "stream": "",
        "display": "",
        "last_complete": ""
    },
    "recent_trades": [],
    "portfolio": {
        "base_balance": 0.0,
        "quote_balance": 0.0,
        "mark_to_market_quote": 0.0,
        "pnl_quote": 0.0
    },
    "kill_switch": {
        "status": "unknown",
        "paused": None,
        "remaining_cap": None,
        "daily_cap": None,
        "traded_today": None,
        "cooldown_seconds": None,
        "next_trade_at": None
    },
    "errors": []
}


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class SharedStateStore:
    def __init__(self, path: str | None = None) -> None:
        configured = path or env("SHARED_STATE_PATH", ".runtime/shared_state.json")
        self.path = resolve_runtime_path(configured)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return deepcopy(DEFAULT_STATE)

        with self.path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return _deep_merge(DEFAULT_STATE, data)

    def write(self, state: dict[str, Any]) -> dict[str, Any]:
        snapshot = _deep_merge(DEFAULT_STATE, state)
        snapshot["updated_at"] = datetime.now(timezone.utc).isoformat()

        with self._lock:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                delete=False,
                dir=str(self.path.parent),
                prefix=self.path.stem,
                suffix=".tmp"
            ) as handle:
                json.dump(snapshot, handle, indent=2)
                temp_name = handle.name
            os.replace(temp_name, self.path)

        return snapshot

    def update(self, patch: dict[str, Any]) -> dict[str, Any]:
        current = self.read()
        return self.write(_deep_merge(current, patch))

    def append_error(self, message: str, limit: int = 20) -> dict[str, Any]:
        state = self.read()
        errors = list(state.get("errors", []))
        errors.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": message
            }
        )
        state["errors"] = errors[-limit:]
        return self.write(state)

    def append_trade(self, trade: dict[str, Any], limit: int | None = None) -> dict[str, Any]:
        state = self.read()
        max_items = limit or env_int("EVENT_HISTORY_LIMIT", 25)
        trades = list(state.get("recent_trades", []))
        trades.append(trade)
        state["recent_trades"] = trades[-max_items:]
        return self.write(state)

