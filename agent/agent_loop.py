from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import os
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

try:
    from .chain_client import KillSwitchClient, TradeExecutionResult
    from .config import env, env_bool, env_decimal, env_int
    from .event_listener import TradeEventListener
    from .price_feed import PythPriceFeedClient, build_client_from_env, StalePriceError
    from .shared_state import SharedStateStore
    from .strategy_ema import IncrementalEmaStrategy, StrategySignal
except ImportError:  # pragma: no cover
    from chain_client import KillSwitchClient, TradeExecutionResult
    from config import env, env_bool, env_decimal, env_int
    from event_listener import TradeEventListener
    from price_feed import PythPriceFeedClient, build_client_from_env, StalePriceError
    from shared_state import SharedStateStore
    from strategy_ema import IncrementalEmaStrategy, StrategySignal


LOGGER = logging.getLogger("agent.agent_loop")

SYSTEM_PROMPT = """You are an institutional crypto trading assistant. Analyze the provided market data and return ONLY valid JSON."""


class LlmDecision(BaseModel):
    action: str = Field(pattern="^(BUY|SELL|HOLD)$")
    confidence: float
    size: float
    reason: str


@dataclass(slots=True)
class PortfolioState:
    starting_base: Decimal
    starting_quote: Decimal
    current_base: Decimal
    current_quote: Decimal
    baseline_price: Decimal | None = None

    def mark_trade(self, action: str, notional_quote: Decimal, price: Decimal) -> None:
        if price <= 0:
            return
        base_delta = notional_quote / price
        if action == "buy":
            self.current_quote -= notional_quote
            self.current_base += base_delta
        elif action == "sell":
            self.current_base -= base_delta
            self.current_quote += notional_quote

    def snapshot(self, current_price: Decimal) -> dict[str, float]:
        if self.baseline_price is None:
            self.baseline_price = current_price
        current_value = self.current_quote + (self.current_base * current_price)
        starting_value = self.starting_quote + (self.starting_base * self.baseline_price)
        pnl = current_value - starting_value
        return {
            "base_balance": float(self.current_base),
            "quote_balance": float(self.current_quote),
            "mark_to_market_quote": float(current_value),
            "pnl_quote": float(pnl)
        }


class AgentLoop:
    def __init__(self) -> None:
        self.store = SharedStateStore()
        self.price_feed: PythPriceFeedClient = build_client_from_env()
        self.chain_client = KillSwitchClient()
        self.event_listener = TradeEventListener(
            rpc_url=env("MONAD_TESTNET_RPC_URL", required=True),
            kill_switch_address=env("KILLSWITCH_ADDRESS", required=True),
            history_limit=env_int("EVENT_HISTORY_LIMIT", 25),
            lookback_blocks=env_int("EVENT_LOOKBACK_BLOCKS", 500)
        )
        self.strategy = IncrementalEmaStrategy(
            short_period=env_int("EMA_SHORT_PERIOD", 5),
            long_period=env_int("EMA_LONG_PERIOD", 20),
            min_separation_bps=env_int("EMA_MIN_SEPARATION_BPS", 10)
        )
        self.poll_seconds = env_int("AGENT_POLL_SECONDS", 30)
        self.base_order_size = env_decimal("BASE_ORDER_SIZE", "25")
        self.price_history: list[dict[str, Any]] = []
        self.portfolio = PortfolioState(
            starting_base=env_decimal("SIMULATED_STARTING_BASE_BALANCE", "0"),
            starting_quote=env_decimal("SIMULATED_STARTING_QUOTE_BALANCE", "1000"),
            current_base=env_decimal("SIMULATED_STARTING_BASE_BALANCE", "0"),
            current_quote=env_decimal("SIMULATED_STARTING_QUOTE_BALANCE", "1000")
        )
        self.llm_enabled = bool(env("NVIDIA_API_KEY", default="")) and not env_bool("DISABLE_LLM", False)
        self.llm = (
            OpenAI(
                api_key=env("NVIDIA_API_KEY", required=True),
                base_url=env("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
            )
            if self.llm_enabled
            else None
        )

    def run_forever(self) -> None:
        LOGGER.info("Agent loop started. Live swaps enabled=%s", self.chain_client.live_swaps_enabled)
        while True:
            cycle_started = time.time()
            try:
                self._cycle()
            except StalePriceError as exc:
                LOGGER.warning("agent cycle paused due to stale price: %s", exc)
                self.store.update(
                    {
                        "reasoning": {
                            "status": "waiting",
                            "display": str(exc)
                        }
                    }
                )
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("agent cycle failed: %s", exc)
                self.store.append_error(str(exc))
                self.store.update(
                    {
                        "reasoning": {
                            "status": "error",
                            "display": str(exc)
                        }
                    }
                )
            elapsed = time.time() - cycle_started
            time.sleep(max(self.poll_seconds - elapsed, 1))

    def _cycle(self) -> None:
        point = self.price_feed.get_latest_price()
        self.chain_client.set_reference_price(point.price)
        signal = self.strategy.update(point.price)
        self._append_price_history(point)

        recent_trades = self.event_listener.get_recent_trades()
        try:
            new_trades = self.event_listener.poll_once()
            if new_trades:
                recent_trades = self.event_listener.get_recent_trades()
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("event polling failed in-cycle: %s", exc)

        decision = self._decide(point, signal, recent_trades)
        execution = self.chain_client.execute_trade(decision.action, decision.size)
        if execution.status in {"submitted", "dry_run"} and decision.action in {"buy", "sell"}:
            self.portfolio.mark_trade(decision.action, Decimal(str(decision.size)), point.price)

        status = self.chain_client.get_status()
        market_state = point.as_dict()
        market_state["history"] = self.price_history[-20:]

        self.store.update(
            {
                "market": market_state,
                "decision": {
                    "action": decision.action,
                    "size": decision.size,
                    "source": decision.source,
                    "raw_model_output": decision.raw_model_output,
                    "rationale": decision.rationale
                },
                "reasoning": {
                    "status": "complete",
                    "display": decision.rationale,
                    "last_complete": decision.raw_model_output or decision.rationale
                },
                "portfolio": self.portfolio.snapshot(point.price),
                "kill_switch": status
            }
        )

        if execution.tx_hash:
            trade_record = {
                "action": decision.action,
                "size": decision.size,
                "timestamp": int(time.time()),
                "iso_time": datetime.now(timezone.utc).isoformat(),
                "tx_hash": execution.tx_hash,
                "target": env("DEX_ROUTER_ADDRESS", default="unknown"),
                "value": "0"
            }
            self.store.append_trade(trade_record)

        LOGGER.info(
            "decision=%s size=%s source=%s execution=%s",
            decision.action,
            decision.size,
            decision.source,
            execution.status
        )

    def _append_price_history(self, point: Any) -> None:
        self.price_history.append(
            {
                "price": float(point.price),
                "publish_time": point.publish_time,
                "observed_at": point.observed_at
            }
        )
        self.price_history = self.price_history[-50:]

    def _decide(self, point: Any, signal: StrategySignal, recent_trades: list[dict[str, Any]]) -> "Decision":
        if signal.signal in {"BUY", "SELL"}:
            action = signal.signal.lower()
            rationale = (
                f"EMA direct signal: short EMA {signal.ema_short:.4f}, "
                f"long EMA {signal.ema_long:.4f}, separation {signal.separation_bps:.2f} bps."
            )
            return Decision(
                action=action,
                size=float(self.base_order_size),
                rationale=rationale,
                source="ema",
                raw_model_output=rationale
            )

        if not self.llm_enabled or self.llm is None:
            rationale = "EMA signal was ambiguous and no NVIDIA API key is configured, so the agent held position."
            return Decision(
                action="hold",
                size=0.0,
                rationale=rationale,
                source="fallback",
                raw_model_output=rationale
            )

        for attempt in range(2):
            raw_output = self._invoke_llm(point, signal, recent_trades)
            parsed = self._parse_llm_output(raw_output)
            if parsed is not None:
                return Decision(
                    action=parsed.action.lower(),
                    size=parsed.size if parsed.action.upper() != "HOLD" else 0.0,
                    rationale=parsed.reason,
                    source="llm",
                    raw_model_output=raw_output
                )
            LOGGER.warning("Malformed LLM output on attempt %s: %s", attempt + 1, raw_output)

        rationale = "Invalid model response"
        fallback_json = json.dumps({
            "action": "HOLD",
            "confidence": 0,
            "size": 0,
            "reason": rationale
        })
        return Decision(
            action="hold",
            size=0.0,
            rationale=rationale,
            source="fallback",
            raw_model_output=fallback_json
        )

    def _invoke_llm(self, point: Any, signal: StrategySignal, recent_trades: list[dict[str, Any]]) -> str:
        self.store.update(
            {
                "reasoning": {
                    "status": "streaming",
                    "stream": "",
                    "display": "Waiting for NVIDIA NIM response..."
                }
            }
        )
        user_prompt = self._build_user_prompt(point, signal, recent_trades)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]

        response = self.llm.chat.completions.create(
            model=env("LLM_MODEL", "minimax-m2.7"),
            messages=messages,
            temperature=0.2
        )
        content = response.choices[0].message.content or ""
        
        self.store.update(
            {
                "reasoning": {
                    "status": "complete",
                    "stream": content,
                    "display": content[-env_int("REASONING_MAX_CHARS", 4000):]
                }
            }
        )
        return content

    def _build_user_prompt(self, point: Any, signal: StrategySignal, recent_trades: list[dict[str, Any]]) -> str:
        history_lines = [
            f"{entry['observed_at']}: {entry['price']:.6f}" for entry in self.price_history[-10:]
        ]
        trade_lines = [
            f"{trade['iso_time']} | {trade['action']} | size={trade['size']} | tx={trade['tx_hash']}"
            for trade in recent_trades[-10:]
        ]
        kill_switch_status = self.chain_client.get_status()

        return "\n".join(
            [
                f"Current ETH/USDC price: {point.price}",
                f"Confidence interval: {point.confidence}",
                f"Price publish time (unix): {point.publish_time}",
                f"EMA short: {signal.ema_short}",
                f"EMA long: {signal.ema_long}",
                f"EMA separation bps: {signal.separation_bps}",
                f"Proposed default trade size in quote notional: {self.base_order_size}",
                f"Kill-switch status: {json.dumps(kill_switch_status)}",
                "Recent price history:",
                *history_lines,
                "Recent trades:",
                *(trade_lines or ["none"])
            ]
        )



    @staticmethod
    def _parse_llm_output(raw_output: str) -> LlmDecision | None:
        candidate = raw_output.strip()
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            payload = json.loads(candidate[start : end + 1])
            return LlmDecision.model_validate(payload)
        except (json.JSONDecodeError, ValidationError):
            return None


@dataclass(slots=True)
class Decision:
    action: str
    size: float
    rationale: str
    source: str
    raw_model_output: str


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    AgentLoop().run_forever()


if __name__ == "__main__":
    main()

