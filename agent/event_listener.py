from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from web3 import HTTPProvider, Web3
from web3.contract import Contract

try:
    from .config import env, env_int, int_to_action, load_contract_abi
except ImportError:  # pragma: no cover
    from config import env, env_int, int_to_action, load_contract_abi


LOGGER = logging.getLogger("agent.event_listener")


@dataclass(slots=True)
class TradeRecord:
    action: str
    size: float
    timestamp: int
    iso_time: str
    tx_hash: str
    target: str
    value: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "size": self.size,
            "timestamp": self.timestamp,
            "iso_time": self.iso_time,
            "tx_hash": self.tx_hash,
            "target": self.target,
            "value": self.value
        }


class TradeEventListener:
    def __init__(
        self,
        rpc_url: str,
        kill_switch_address: str,
        history_limit: int = 25,
        lookback_blocks: int = 500
    ) -> None:
        self.web3 = Web3(HTTPProvider(rpc_url, request_kwargs={"timeout": 15}))
        self.contract: Contract = self.web3.eth.contract(
            address=Web3.to_checksum_address(kill_switch_address),
            abi=load_contract_abi("KillSwitch")
        )
        self.history: deque[TradeRecord] = deque(maxlen=history_limit)
        latest_block = self.web3.eth.block_number if self.web3.is_connected() else 0
        self.next_from_block = max(latest_block - lookback_blocks, 0)

    def poll_once(self) -> list[TradeRecord]:
        if not self.web3.is_connected():
            raise RuntimeError("RPC connection failed while polling KillSwitch events.")

        latest_block = self.web3.eth.block_number
        if latest_block < self.next_from_block:
            self.next_from_block = latest_block

        if latest_block == self.next_from_block:
            return []

        event = self.contract.events.TradePlaced()
        logs = event.get_logs(fromBlock=self.next_from_block + 1, toBlock=latest_block)
        parsed = [self._parse(log) for log in logs]
        for trade in parsed:
            self.history.append(trade)
        self.next_from_block = latest_block
        return parsed

    def poll_forever(self, interval_seconds: int = 10) -> None:
        LOGGER.info("Polling KillSwitch TradePlaced events over HTTP logs for Monad testnet compatibility.")
        while True:
            try:
                for trade in self.poll_once():
                    LOGGER.info("trade event: %s %s tx=%s", trade.action, trade.size, trade.tx_hash)
            except Exception as exc:  # noqa: BLE001
                LOGGER.error("event polling error: %s", exc)
            time.sleep(interval_seconds)

    def get_recent_trades(self) -> list[dict[str, Any]]:
        return [trade.as_dict() for trade in self.history]

    def _parse(self, log: Any) -> TradeRecord:
        args = log["args"]
        timestamp = int(args["timestamp"])
        return TradeRecord(
            action=int_to_action(int(args["action"])),
            size=float(Web3.from_wei(int(args["size"]), "ether")),
            timestamp=timestamp,
            iso_time=datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(),
            tx_hash=log["transactionHash"].hex(),
            target=args["target"],
            value=str(args["value"])
        )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    listener = TradeEventListener(
        rpc_url=env("MONAD_TESTNET_RPC_URL", required=True),
        kill_switch_address=env("KILLSWITCH_ADDRESS", required=True),
        history_limit=env_int("EVENT_HISTORY_LIMIT", 25),
        lookback_blocks=env_int("EVENT_LOOKBACK_BLOCKS", 500)
    )
    listener.poll_forever(interval_seconds=10)


if __name__ == "__main__":
    main()

