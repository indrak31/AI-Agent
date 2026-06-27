# Edge Case Checklist

## Kill-switch trigger scenarios

### Per-trade limit exceeded

- How to trigger:
  - Deploy `KillSwitch.sol` with `KILLSWITCH_PER_TRADE_LIMIT=100`.
  - In `.env`, set `BASE_ORDER_SIZE=150` and `ENABLE_LIVE_SWAPS=true`.
  - Run `python -m agent.agent_loop`.
- Expected behavior:
  - `agent/chain_client.py` preflights the call with `eth_call`.
  - The client decodes `PerTradeLimitExceeded` and logs a plain-English failure.
  - `agent_loop.py` writes the failure into shared state and stops acting for that cycle instead of retrying.
- Handling code:
  - `agent/chain_client.py`, `KillSwitchClient._preflight_or_raise`
  - `contracts/KillSwitch.sol`, `executeTrade`

### Cooldown active

- How to trigger:
  - Deploy with `KILLSWITCH_COOLDOWN_SECONDS=300`.
  - Submit one successful trade, then force another `buy` or `sell` decision inside five minutes.
  - For local testing, `npm test` already covers this path in `test/KillSwitch.test.js`.
- Expected behavior:
  - The second attempt decodes as "cooldown not elapsed".
  - Shared state and the dashboard show the error and the next eligible timestamp.
- Handling code:
  - `contracts/KillSwitch.sol`, `CooldownActive`
  - `agent/chain_client.py`, `KillSwitchClient.get_status`
  - `agent/dashboard.py`, `build_status_panel`

### Paused

- How to trigger:
  - Call `pause()` from the owner account after deployment.
  - Start or continue `python -m agent.agent_loop`.
- Expected behavior:
  - Preflight fails with "kill-switch is paused".
  - The dashboard moves the status panel to red and the agent holds.
- Handling code:
  - `contracts/KillSwitch.sol`, `pause`, `unpause`, `whenNotPaused`
  - `agent/chain_client.py`, `_decode_revert`

## Daily cap exhaustion mid-session

- How to trigger:
  - Deploy with a small `KILLSWITCH_DAILY_CAP`, such as `50`.
  - Use `BASE_ORDER_SIZE=25`, allow two successful trades, then force a third.
- Expected behavior:
  - The third trade is blocked with `DailyCapExceeded`.
  - `agent_loop.py` records the failure and the dashboard status becomes `CAP_HIT`.
- Handling code:
  - `contracts/KillSwitch.sol`, `remainingDailyCapacity`, `executeTrade`
  - `agent/chain_client.py`, `get_status`

## DEX unavailable or high slippage

### Router unavailable

- How to trigger:
  - Put a bad `DEX_ROUTER_ADDRESS` in `.env`, or point at a contract that does not expose `getAmountsOut`.
- Expected behavior:
  - `agent/swap_executor.py` logs the quote failure and falls back to reference-price math for preparation.
  - If the live trade path is enabled, the on-chain forward call still fails loudly and the receipt error is surfaced.
- Handling code:
  - `agent/swap_executor.py`, `DexSwapExecutor.prepare_swap`
  - `agent/chain_client.py`, `execute_trade`

### High slippage

- How to trigger:
  - Set `SLIPPAGE_BPS=5` against a volatile or thin pool and enable live swaps.
- Expected behavior:
  - The DEX call reverts or returns a poor quote.
  - The trade is not retried blindly; the agent logs the failure and waits for the next cycle.
- Handling code:
  - `agent/swap_executor.py`, `prepare_swap`
  - `agent/chain_client.py`, `execute_trade`

## Stale or missing Pyth feed

### Stale feed

- How to trigger:
  - Set `PYTH_MAX_STALENESS_SECONDS=1` and wait more than one second between updates, or use an inactive feed ID.
- Expected behavior:
  - `agent/price_feed.py` raises `StalePriceError`.
  - The poller logs the issue and backs off instead of crashing.
  - `agent_loop.py` records the failure for the dashboard.
- Handling code:
  - `agent/price_feed.py`, `_read_single_feed`, `poll_forever`
  - `agent/agent_loop.py`, `run_forever`

### Missing feed

- How to trigger:
  - Replace `PYTH_ETH_USD_FEED_ID` or `PYTH_USDC_USD_FEED_ID` with garbage.
- Expected behavior:
  - `PriceFeedError` is raised with a clear message.
  - Trading stops for that cycle; no transaction is sent.
- Handling code:
  - `agent/price_feed.py`, `_normalize_feed_id`, `_read_single_feed`

## LLM timeout or malformed response

### Malformed JSON

- How to trigger:
  - Temporarily change `SYSTEM_PROMPT` in `agent/agent_loop.py` to allow prose output, or use a deliberately poor model.
- Expected behavior:
  - The agent retries the LLM call once.
  - If parsing fails twice, the decision falls back to `hold`.
- Handling code:
  - `agent/agent_loop.py`, `_decide`, `_parse_llm_output`

### Timeout or API failure

- How to trigger:
  - Remove network access, set an invalid `ANTHROPIC_API_KEY`, or point `ANTHROPIC_MODEL` to an unavailable model.
- Expected behavior:
  - The cycle fails loudly, logs the error, writes it to shared state, and does not send a trade.
- Handling code:
  - `agent/agent_loop.py`, `run_forever`, `_invoke_llm`
  - `agent/shared_state.py`, `append_error`

## Wallet nonce conflicts

- How to trigger:
  - Submit overlapping live transactions from the same `DEPLOYER_PRIVATE_KEY` outside this agent while the agent is running.
- Expected behavior:
  - The broadcast path fails from `web3.py`.
  - The error is surfaced in the dashboard and the agent waits for the next loop.
- Handling code:
  - `agent/chain_client.py`, `execute_trade`
  - `agent/agent_loop.py`, `run_forever`

