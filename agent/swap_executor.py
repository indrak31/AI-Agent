from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from web3 import HTTPProvider, Web3
from web3.contract import Contract

try:
    from .config import env, env_bool, env_int
except ImportError:  # pragma: no cover
    from config import env, env_bool, env_int


LOGGER = logging.getLogger("agent.swap_executor")
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

ROUTER_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactTokensForTokens",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"}
        ],
        "name": "getAmountsOut",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function"
    }
]

ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function"
    }
]


@dataclass(slots=True)
class PreparedSwap:
    target: str
    calldata: str
    value_wei: int
    amount_in_wei: int
    min_amount_out_wei: int
    path: list[str]
    token_in: str
    token_out: str
    amount_in_human: Decimal
    min_amount_out_human: Decimal
    balance_before: dict[str, Decimal]


class DexSwapExecutor:
    def __init__(self) -> None:
        self.web3 = Web3(HTTPProvider(env("MONAD_TESTNET_RPC_URL", required=True), request_kwargs={"timeout": 15}))
        self.router_address = Web3.to_checksum_address(env("DEX_ROUTER_ADDRESS", required=True))
        self.router: Contract = self.web3.eth.contract(address=self.router_address, abi=ROUTER_ABI)
        self.base_token = self._normalize_token(env("DEX_BASE_TOKEN_ADDRESS", required=True))
        self.quote_token = self._normalize_token(env("DEX_QUOTE_TOKEN_ADDRESS", required=True))
        self.base_decimals = env_int("DEX_BASE_TOKEN_DECIMALS", 18)
        self.quote_decimals = env_int("DEX_QUOTE_TOKEN_DECIMALS", 6)
        self.trade_recipient = Web3.to_checksum_address(env("TRADE_RECIPIENT", required=True))
        self.deadline_seconds = env_int("SWAP_DEADLINE_SECONDS", 120)
        self.slippage_bps = Decimal(env_int("SLIPPAGE_BPS", 100))

    @staticmethod
    def _normalize_token(token_address: str) -> str:
        if token_address.lower() == ZERO_ADDRESS.lower():
            return ZERO_ADDRESS
        return Web3.to_checksum_address(token_address)

    def _to_wei(self, amount: Decimal, decimals: int) -> int:
        return int((amount * (Decimal(10) ** decimals)).quantize(Decimal("1")))

    def _from_wei(self, amount: int, decimals: int) -> Decimal:
        return Decimal(amount) / (Decimal(10) ** decimals)

    def _erc20(self, token_address: str) -> Contract:
        return self.web3.eth.contract(address=Web3.to_checksum_address(token_address), abi=ERC20_ABI)

    def get_wallet_balances(self, wallet_address: str) -> dict[str, Decimal]:
        wallet = Web3.to_checksum_address(wallet_address)
        balances: dict[str, Decimal] = {}
        if self.base_token != ZERO_ADDRESS:
            raw_base = self._erc20(self.base_token).functions.balanceOf(wallet).call()
            balances["base"] = self._from_wei(raw_base, self.base_decimals)
        else:
            raw_base = self.web3.eth.get_balance(wallet)
            balances["base"] = self._from_wei(raw_base, self.base_decimals)

        if self.quote_token != ZERO_ADDRESS:
            raw_quote = self._erc20(self.quote_token).functions.balanceOf(wallet).call()
            balances["quote"] = self._from_wei(raw_quote, self.quote_decimals)
        else:
            raw_quote = self.web3.eth.get_balance(wallet)
            balances["quote"] = self._from_wei(raw_quote, self.quote_decimals)

        return balances

    def prepare_swap(self, action: str, size_quote_notional: Decimal, reference_price: Decimal) -> PreparedSwap:
        normalized_action = action.lower()
        if normalized_action not in {"buy", "sell"}:
            raise ValueError("prepare_swap only supports buy or sell")
        if size_quote_notional <= 0:
            raise ValueError("trade size must be positive")
        if reference_price <= 0:
            raise ValueError("reference price must be positive")

        if normalized_action == "buy":
            token_in = self.quote_token
            token_out = self.base_token
            input_decimals = self.quote_decimals
            output_decimals = self.base_decimals
            amount_in_human = size_quote_notional
        else:
            token_in = self.base_token
            token_out = self.quote_token
            input_decimals = self.base_decimals
            output_decimals = self.quote_decimals
            amount_in_human = size_quote_notional / reference_price

        amount_in_wei = self._to_wei(amount_in_human, input_decimals)
        path = [token_in, token_out]

        try:
            amounts_out = self.router.functions.getAmountsOut(amount_in_wei, path).call()
            expected_out_wei = int(amounts_out[-1])
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning(
                "Router quote failed; falling back to reference price only: %s. Confirm DEX router compatibility.",
                exc
            )
            if normalized_action == "buy":
                expected_out = size_quote_notional / reference_price
            else:
                expected_out = size_quote_notional
            expected_out_wei = self._to_wei(expected_out, output_decimals)

        min_out_wei = int((Decimal(expected_out_wei) * (Decimal(10_000) - self.slippage_bps) / Decimal(10_000)))
        deadline = int(time.time()) + self.deadline_seconds

        function = self.router.functions.swapExactTokensForTokens(
            amount_in_wei,
            min_out_wei,
            path,
            self.trade_recipient,
            deadline
        )
        calldata = function._encode_transaction_data()
        balances = self.get_wallet_balances(self.trade_recipient)

        return PreparedSwap(
            target=self.router_address,
            calldata=calldata,
            value_wei=0,
            amount_in_wei=amount_in_wei,
            min_amount_out_wei=min_out_wei,
            path=path,
            token_in=token_in,
            token_out=token_out,
            amount_in_human=amount_in_human,
            min_amount_out_human=self._from_wei(min_out_wei, output_decimals),
            balance_before=balances
        )

    def verify_execution(self, wallet_address: str, prepared: PreparedSwap) -> dict[str, Any]:
        balances_after = self.get_wallet_balances(wallet_address)
        return {
            "before": {k: float(v) for k, v in prepared.balance_before.items()},
            "after": {k: float(v) for k, v in balances_after.items()},
            "path": prepared.path,
            "amount_in_human": float(prepared.amount_in_human),
            "min_amount_out_human": float(prepared.min_amount_out_human)
        }


def describe_assumption() -> str:
    return (
        "This module assumes a PancakeSwap V2-compatible router on Monad testnet. "
        "Verify the router address, token addresses, and approval flow in the DEX's official docs before enabling live swaps."
    )

