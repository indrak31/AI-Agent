from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import Decimal


@dataclass(slots=True)
class StrategySignal:
    signal: str
    ema_short: Decimal
    ema_long: Decimal
    separation_bps: Decimal
    sample_count: int


class IncrementalEmaStrategy:
    def __init__(
        self,
        short_period: int = 5,
        long_period: int = 20,
        min_separation_bps: int = 10
    ) -> None:
        if short_period >= long_period:
            raise ValueError("short_period must be less than long_period")

        self.short_period = short_period
        self.long_period = long_period
        self.min_separation_bps = Decimal(min_separation_bps)
        self.short_alpha = Decimal(2) / Decimal(short_period + 1)
        self.long_alpha = Decimal(2) / Decimal(long_period + 1)
        self.prices: deque[Decimal] = deque(maxlen=long_period)
        self.ema_short: Decimal | None = None
        self.ema_long: Decimal | None = None

    def update(self, price: Decimal) -> StrategySignal:
        if price <= 0:
            raise ValueError("EMA strategy requires positive prices")

        self.prices.append(price)
        if self.ema_short is None:
            self.ema_short = price
        else:
            self.ema_short = self._next_ema(price, self.ema_short, self.short_alpha)

        if self.ema_long is None:
            self.ema_long = price
        else:
            self.ema_long = self._next_ema(price, self.ema_long, self.long_alpha)

        if len(self.prices) < self.long_period:
            return StrategySignal(
                signal="AMBIGUOUS",
                ema_short=self.ema_short,
                ema_long=self.ema_long,
                separation_bps=Decimal(0),
                sample_count=len(self.prices)
            )

        separation_bps = (abs(self.ema_short - self.ema_long) / self.ema_long) * Decimal(10_000)

        if separation_bps < self.min_separation_bps:
            signal = "AMBIGUOUS"
        elif self.ema_short > self.ema_long:
            signal = "BUY"
        elif self.ema_short < self.ema_long:
            signal = "SELL"
        else:
            signal = "AMBIGUOUS"

        return StrategySignal(
            signal=signal,
            ema_short=self.ema_short,
            ema_long=self.ema_long,
            separation_bps=separation_bps,
            sample_count=len(self.prices)
        )

    @staticmethod
    def _next_ema(price: Decimal, previous_ema: Decimal, alpha: Decimal) -> Decimal:
        return (price * alpha) + (previous_ema * (Decimal(1) - alpha))

