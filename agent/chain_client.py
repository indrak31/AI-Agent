from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from eth_account import Account
from web3 import HTTPProvider, Web3
from web3.contract import Contract

try:
    from .config import action_to_int, env, env_bool, env_int, env_decimal, load_contract_abi
    from .swap_executor import DexSwapExecutor, PreparedSwap, describe_assumption
except ImportError:  # pragma: no cover
    from config import action_to_int, env, env_bool, env_int, env_decimal, load_contract_abi
    from swap_executor import DexSwapExecutor, PreparedSwap, describe_assumption


LOGGER = logging.getLogger("agent.chain_client")


@dataclass(slots=True)
class TradeExecutionResult:
    status: str
    action: str
    size: float
    tx_hash: str | None
    receipt_status: int | None
    verification: dict[str, Any] | None
    message: str


class KillSwitchClient:
    def __init__(self) -> None:
        self.web3 = Web3(HTTPProvider(env("MONAD_TESTNET_RPC_URL", required=True), request_kwargs={"timeout": 20}))
        self.chain_id = env_int("MONAD_TESTNET_CHAIN_ID", 10143)
        self.account = Account.from_key(env("DEPLOYER_PRIVATE_KEY", required=True))
        self.owner_address = Web3.to_checksum_address(self.account.address)
        self.contract: Contract = self.web3.eth.contract(
            address=Web3.to_checksum_address(env("KILLSWITCH_ADDRESS", required=True)),
            abi=load_contract_abi("KillSwitch")
        )
        self.swap_executor = DexSwapExecutor()
        self.live_swaps_enabled = env_bool("ENABLE_LIVE_SWAPS", False)
        self.latest_reference_price: Decimal | None = None
        self._error_selectors = {
            Web3.keccak(text="DailyCapExceeded(uint256,uint256)")[:4].hex(): "daily cap exceeded",
            Web3.keccak(text="PerTradeLimitExceeded(uint256,uint256)")[:4].hex(): "per-trade limit exceeded",
            Web3.keccak(text="CooldownActive(uint256)")[:4].hex(): "cooldown not elapsed",
            Web3.keccak(text="ContractPaused()")[:4].hex(): "kill-switch is paused"
        }

    def set_reference_price(self, price: Decimal) -> None:
        self.latest_reference_price = price

    def get_status(self) -> dict[str, Any]:
        paused = self.contract.functions.paused().call()
        daily_cap = self.contract.functions.dailyCap().call()
        traded_today = self.contract.functions.tradedToday().call()
        cooldown_seconds = self.contract.functions.cooldownSeconds().call()
        last_trade_timestamp = self.contract.functions.lastTradeTimestamp().call()
        remaining_cap = self.contract.functions.remainingDailyCapacity().call()

        next_trade_at = None
        if cooldown_seconds and last_trade_timestamp:
            next_trade_at = last_trade_timestamp + cooldown_seconds

        remaining_cap_human = Web3.from_wei(remaining_cap, "ether")
        status = "paused" if paused else "active"
        if not paused and remaining_cap == 0:
            status = "cap_hit"

        return {
            "status": status,
            "paused": paused,
            "daily_cap": float(Web3.from_wei(daily_cap, "ether")),
            "traded_today": float(Web3.from_wei(traded_today, "ether")),
            "remaining_cap": float(remaining_cap_human),
            "cooldown_seconds": int(cooldown_seconds),
            "next_trade_at": next_trade_at
        }

    def execute_trade(self, action: str, size: float | Decimal) -> TradeExecutionResult:
        normalized_action = action.lower()
        if normalized_action == "hold":
            return TradeExecutionResult(
                status="skipped",
                action="hold",
                size=float(size),
                tx_hash=None,
                receipt_status=None,
                verification=None,
                message="Hold decision. No transaction submitted."
            )

        if self.latest_reference_price is None:
            raise RuntimeError("Reference price not set. Call set_reference_price() before execute_trade().")

        size_decimal = Decimal(str(size))
        prepared = self.swap_executor.prepare_swap(normalized_action, size_decimal, self.latest_reference_price)
        size_for_contract = Web3.to_wei(size_decimal, "ether")

        if not self.live_swaps_enabled:
            LOGGER.info("Dry-run trade prepared. %s", describe_assumption())
            return TradeExecutionResult(
                status="dry_run",
                action=normalized_action,
                size=float(size_decimal),
                tx_hash=None,
                receipt_status=None,
                verification={
                    "target": prepared.target,
                    "calldata": prepared.calldata,
                    "amount_in_human": float(prepared.amount_in_human),
                    "min_amount_out_human": float(prepared.min_amount_out_human)
                },
                message="ENABLE_LIVE_SWAPS=false. Transaction prepared but not broadcast."
            )

        function = self.contract.functions.executeTrade(
            action_to_int(normalized_action),
            size_for_contract,
            prepared.target,
            prepared.calldata
        )
        nonce = self.web3.eth.get_transaction_count(self.owner_address)
        tx = function.build_transaction(
            {
                "from": self.owner_address,
                "nonce": nonce,
                "chainId": self.chain_id,
                "value": prepared.value_wei
            }
        )
        tx["gas"] = self.web3.eth.estimate_gas(tx)
        tx["maxFeePerGas"] = self.web3.eth.gas_price
        tx["maxPriorityFeePerGas"] = self.web3.eth.max_priority_fee

        self._preflight_or_raise(tx)

        signed = self.web3.eth.account.sign_transaction(tx, private_key=self.account.key)
        tx_hash = self.web3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt["status"] != 1:
            raise RuntimeError(f"Trade transaction reverted on chain: {tx_hash.hex()}")

        verification = self.swap_executor.verify_execution(self.owner_address, prepared)
        return TradeExecutionResult(
            status="submitted",
            action=normalized_action,
            size=float(size_decimal),
            tx_hash=tx_hash.hex(),
            receipt_status=int(receipt["status"]),
            verification=verification,
            message="Trade executed through KillSwitch."
        )

    def _preflight_or_raise(self, tx: dict[str, Any]) -> None:
        try:
            self.web3.eth.call(tx)
        except Exception as exc:  # noqa: BLE001
            message = self._decode_revert(exc)
            raise RuntimeError(f"KillSwitch preflight failed: {message}") from exc

    def _decode_revert(self, exc: Exception) -> str:
        text = str(exc)
        for selector, meaning in self._error_selectors.items():
            if selector in text:
                return meaning
        lowered = text.lower()
        if "paused" in lowered:
            return "kill-switch is paused"
        if "cooldown" in lowered:
            return "cooldown not elapsed"
        if "dailycapexceeded" in lowered:
            return "daily cap exceeded"
        if "pertradelimitexceeded" in lowered:
            return "per-trade limit exceeded"
        return text

