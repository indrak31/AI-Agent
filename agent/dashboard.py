from __future__ import annotations

import time
from pathlib import Path

from rich import box
from rich.console import Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

try:
    from .shared_state import SharedStateStore
except ImportError:  # pragma: no cover
    from shared_state import SharedStateStore


def build_status_panel(kill_switch: dict) -> Panel:
    status = (kill_switch.get("status") or "unknown").upper()
    color = {"ACTIVE": "green", "PAUSED": "red", "CAP_HIT": "yellow", "UNKNOWN": "white"}.get(status, "white")
    text = Text()
    text.append(f"Status: {status}\n", style=f"bold {color}")
    text.append(f"Paused: {kill_switch.get('paused')}\n")
    text.append(f"Daily cap: {kill_switch.get('daily_cap')}\n")
    text.append(f"Traded today: {kill_switch.get('traded_today')}\n")
    text.append(f"Remaining cap: {kill_switch.get('remaining_cap')}\n")
    text.append(f"Cooldown seconds: {kill_switch.get('cooldown_seconds')}\n")
    text.append(f"Next trade at: {kill_switch.get('next_trade_at')}")
    return Panel(text, title="Kill Switch", border_style=color)


def build_market_panel(market: dict, decision: dict, portfolio: dict) -> Panel:
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Symbol", str(market.get("symbol")))
    table.add_row("Price", str(market.get("price")))
    table.add_row("Confidence", str(market.get("confidence")))
    table.add_row("Publish Time", str(market.get("publish_time")))
    if "age" in market:
        stale_str = " (STALE)" if market.get("is_stale") else " (FRESH)"
        table.add_row("Age", f"{market.get('age')}s{stale_str}")
    table.add_row("Decision", f"{decision.get('action')} ({decision.get('source')})")
    table.add_row("Decision Size", str(decision.get("size")))
    table.add_row("P&L (quote)", str(portfolio.get("pnl_quote")))
    table.add_row("MTM (quote)", str(portfolio.get("mark_to_market_quote")))
    return Panel(table, title="Market + Portfolio")


def build_reasoning_panel(reasoning: dict, decision: dict) -> Panel:
    display = reasoning.get("display") or decision.get("rationale") or "No reasoning available."
    stream = reasoning.get("stream") or ""
    if stream and display != stream:
        display = stream[-4000:]
    lines = display.splitlines()
    trimmed = "\n".join(lines[-25:])
    return Panel(trimmed, title=f"Reasoning ({reasoning.get('status', 'idle')})", border_style="cyan")


def build_trades_panel(trades: list[dict]) -> Panel:
    table = Table(box=box.SIMPLE, expand=True)
    table.add_column("Time")
    table.add_column("Action")
    table.add_column("Size", justify="right")
    table.add_column("Tx Hash")
    for trade in trades[-10:]:
        tx_hash = trade.get("tx_hash", "")
        short_hash = f"{tx_hash[:10]}...{tx_hash[-6:]}" if len(tx_hash) > 20 else tx_hash
        table.add_row(
            str(trade.get("iso_time", "")),
            str(trade.get("action", "")),
            str(trade.get("size", "")),
            short_hash
        )
    if not trades:
        table.add_row("No trades yet", "-", "-", "-")
    return Panel(table, title="Recent Trades")


def build_errors_panel(errors: list[dict]) -> Panel:
    if not errors:
        return Panel("No recent errors.", title="Errors", border_style="green")
    lines = [f"{entry.get('timestamp')} | {entry.get('message')}" for entry in errors[-5:]]
    return Panel("\n".join(lines), title="Errors", border_style="red")


def render_dashboard(state: dict) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="top", ratio=2),
        Layout(name="bottom", ratio=2)
    )
    layout["top"].split_row(Layout(name="status"), Layout(name="market"), Layout(name="reasoning"))
    layout["bottom"].split_row(Layout(name="trades", ratio=2), Layout(name="errors", ratio=1))

    layout["status"].update(build_status_panel(state.get("kill_switch", {})))
    layout["market"].update(
        build_market_panel(
            state.get("market", {}),
            state.get("decision", {}),
            state.get("portfolio", {})
        )
    )
    layout["reasoning"].update(build_reasoning_panel(state.get("reasoning", {}), state.get("decision", {})))
    layout["trades"].update(build_trades_panel(state.get("recent_trades", [])))
    layout["errors"].update(build_errors_panel(state.get("errors", [])))
    return layout


def main() -> None:
    store = SharedStateStore()
    with Live(render_dashboard(store.read()), refresh_per_second=1, screen=True) as live:
        while True:
            live.update(render_dashboard(store.read()))
            time.sleep(5)


if __name__ == "__main__":
    main()

