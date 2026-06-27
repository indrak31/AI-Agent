from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from web3 import HTTPProvider, Web3
from web3.contract import Contract
from web3.exceptions import ContractLogicError

try:
    from .config import env, env_bool, env_int
except ImportError:  # pragma: no cover
    from config import env, env_bool, env_int


LOGGER = logging.getLogger("agent.price_feed")

PYTH_ABI = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "id", "type": "bytes32"},
            {"internalType": "uint256", "name": "age", "type": "uint256"}
        ],
        "name": "getPriceNoOlderThan",
        "outputs": [
            {
                "components": [
                    {"internalType": "int64", "name": "price", "type": "int64"},
                    {"internalType": "uint64", "name": "conf", "type": "uint64"},
                    {"internalType": "int32", "name": "expo", "type": "int32"},
                    {"internalType": "uint256", "name": "publishTime", "type": "uint256"}
                ],
                "internalType": "struct PythStructs.Price",
                "name": "",
                "type": "tuple"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "id", "type": "bytes32"}],
        "name": "getPriceUnsafe",
        "outputs": [
            {
                "components": [
                    {"internalType": "int64", "name": "price", "type": "int64"},
                    {"internalType": "uint64", "name": "conf", "type": "uint64"},
                    {"internalType": "int32", "name": "expo", "type": "int32"},
                    {"internalType": "uint256", "name": "publishTime", "type": "uint256"}
                ],
                "internalType": "struct PythStructs.Price",
                "name": "",
                "type": "tuple"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    }
]


class PriceFeedError(RuntimeError):
    pass


class StalePriceError(PriceFeedError):
    pass


@dataclass(slots=True)
class RawPythPrice:
    price: Decimal
    confidence: Decimal
    exponent: int
    publish_time: int
    feed_id: str


@dataclass(slots=True)
class PricePoint:
    symbol: str
    price: Decimal
    confidence: Decimal
    publish_time: int
    observed_at: str
    contract_address: str
    feed_ids: list[str]
    age: int = 0
    is_stale: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "price": float(self.price),
            "confidence": float(self.confidence),
            "publish_time": self.publish_time,
            "observed_at": self.observed_at,
            "contract_address": self.contract_address,
            "feed_ids": self.feed_ids,
            "age": self.age,
            "is_stale": self.is_stale
        }


class PythPriceFeedClient:
    def __init__(
        self,
        rpc_url: str,
        contract_address: str,
        eth_usd_feed_id: str,
        usdc_usd_feed_id: str,
        max_staleness_seconds: int = 90,
        allow_stale: bool = False,
        request_timeout_seconds: int = 15
    ) -> None:
        provider = HTTPProvider(rpc_url, request_kwargs={"timeout": request_timeout_seconds})
        self.web3 = Web3(provider)
        self.contract_address = Web3.to_checksum_address(contract_address)
        self.contract: Contract = self.web3.eth.contract(address=self.contract_address, abi=PYTH_ABI)
        self.eth_usd_feed_id = self._normalize_feed_id(eth_usd_feed_id)
        self.usdc_usd_feed_id = self._normalize_feed_id(usdc_usd_feed_id)
        self.max_staleness_seconds = max_staleness_seconds
        self.allow_stale = allow_stale

    @staticmethod
    def _normalize_feed_id(feed_id: str) -> str:
        normalized = feed_id.strip().lower()
        if not normalized.startswith("0x"):
            normalized = f"0x{normalized}"
        if len(normalized) != 66:
            raise ValueError(
                "Pyth feed IDs must be 32-byte hex values. Re-check the official Pyth feed ID page."
            )
        return normalized

    @staticmethod
    def _scale(raw_price: int, exponent: int) -> Decimal:
        return Decimal(raw_price) * (Decimal(10) ** Decimal(exponent))

    def _decode(self, payload: Any, feed_id: str) -> RawPythPrice:
        price = int(payload[0])
        confidence = int(payload[1])
        exponent = int(payload[2])
        publish_time = int(payload[3])

        scaled_price = self._scale(price, exponent)
        scaled_confidence = self._scale(confidence, exponent)

        return RawPythPrice(
            price=scaled_price,
            confidence=scaled_confidence,
            exponent=exponent,
            publish_time=publish_time,
            feed_id=feed_id
        )

    def _read_single_feed(self, feed_id: str) -> RawPythPrice:
        try:
            payload = self.contract.functions.getPriceNoOlderThan(
                feed_id, self.max_staleness_seconds
            ).call()
        except ContractLogicError:
            payload = self.contract.functions.getPriceUnsafe(feed_id).call()
        except Exception as exc:  # noqa: BLE001
            raise PriceFeedError(f"Failed reading Pyth feed {feed_id}: {exc}") from exc

        price = self._decode(payload, feed_id)
        age = int(time.time()) - price.publish_time
        is_stale = age > self.max_staleness_seconds
        if is_stale:
            msg = f"Feed {feed_id} is stale by {age}s (max allowed {self.max_staleness_seconds}s). Publish time: {price.publish_time}."
            if self.allow_stale:
                LOGGER.warning(msg)
            else:
                raise StalePriceError(msg)

        return price

    def get_latest_price(self) -> PricePoint:
        if not self.web3.is_connected():
            raise PriceFeedError("RPC connection failed. Check MONAD_TESTNET_RPC_URL and network access.")

        eth_usd = self._read_single_feed(self.eth_usd_feed_id)
        usdc_usd = self._read_single_feed(self.usdc_usd_feed_id)

        try:
            cross_price = eth_usd.price / usdc_usd.price
        except (InvalidOperation, ZeroDivisionError) as exc:
            raise PriceFeedError("USDC/USD feed returned an invalid zero value; cannot derive ETH/USDC.") from exc

        relative_confidence = (
            (eth_usd.confidence / abs(eth_usd.price)) + (usdc_usd.confidence / abs(usdc_usd.price))
        )
        cross_confidence = abs(cross_price) * relative_confidence
        publish_time = min(eth_usd.publish_time, usdc_usd.publish_time)
        age = int(time.time()) - publish_time
        is_stale = age > self.max_staleness_seconds

        return PricePoint(
            symbol="ETH/USDC",
            price=cross_price,
            confidence=cross_confidence,
            publish_time=publish_time,
            observed_at=datetime.now(timezone.utc).isoformat(),
            contract_address=self.contract_address,
            feed_ids=[eth_usd.feed_id, usdc_usd.feed_id],
            age=age,
            is_stale=is_stale
        )

    def poll_forever(self, interval_seconds: int = 30, backoff_seconds: int = 10) -> None:
        while True:
            try:
                point = self.get_latest_price()
                human_time = datetime.fromtimestamp(point.publish_time, tz=timezone.utc).isoformat()
                LOGGER.info(
                    "price=%s confidence=%s publish_time=%s contract=%s age=%ss stale=%s",
                    point.price,
                    point.confidence,
                    human_time,
                    point.contract_address,
                    point.age,
                    point.is_stale
                )
                time.sleep(interval_seconds)
            except StalePriceError as exc:
                LOGGER.warning("stale price feed: %s", exc)
                time.sleep(backoff_seconds)
            except PriceFeedError as exc:
                LOGGER.error("price feed failure: %s", exc)
                time.sleep(backoff_seconds)
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("unexpected price polling error: %s", exc)
                time.sleep(backoff_seconds)


def build_client_from_env() -> PythPriceFeedClient:
    return PythPriceFeedClient(
        rpc_url=env("MONAD_TESTNET_RPC_URL", required=True),
        contract_address=env("PYTH_CONTRACT_ADDRESS", required=True),
        eth_usd_feed_id=env("PYTH_ETH_USD_FEED_ID", required=True),
        usdc_usd_feed_id=env("PYTH_USDC_USD_FEED_ID", required=True),
        max_staleness_seconds=env_int("PYTH_MAX_STALENESS_SECONDS", 90),
        allow_stale=env_bool("ALLOW_STALE_PYTH", False)
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    LOGGER.info(
        "Starting Pyth poller on Monad testnet. Verify the current contract address and feed IDs in the official docs before live use."
    )
    client = build_client_from_env()
    client.poll_forever(interval_seconds=env_int("AGENT_POLL_SECONDS", 30))


if __name__ == "__main__":
    main()

