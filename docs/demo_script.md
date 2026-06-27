# Demo Script

## 0:00-0:30 Problem statement

Talking points:

- "Autonomous trading is interesting right up to the point where the model is wrong."
- "This project puts the LLM in the decision seat, but every trade still has to go through an on-chain kill-switch contract on Monad testnet."
- "The contract enforces a daily cap, a per-trade limit, a cooldown, and a manual pause, so the model cannot route around the guardrails."

On-screen actions:

```powershell
Get-Content .env
```

Point out:

- `MONAD_TESTNET_RPC_URL`
- `KILLSWITCH_DAILY_CAP`
- `KILLSWITCH_PER_TRADE_LIMIT`
- `ENABLE_LIVE_SWAPS`

## 0:30-1:30 Live sequence

Talking points:

- "The agent polls Pyth prices from Monad testnet, updates a 5/20 EMA strategy, and only asks Claude when the EMA signal is ambiguous."
- "Every trade decision and every recent trade gets streamed into a terminal dashboard."
- "Now I am going to force a trade that is within limits, then immediately force one that breaks the per-trade limit so you can see the contract reject it live."

On-screen actions:

1. Compile and deploy if not already deployed:

```powershell
npm run compile
npm test
npm run deploy:killswitch
```

2. Start the dashboard in one terminal:

```powershell
python -m agent.dashboard
```

3. Start the agent in another terminal:

```powershell
python -m agent.agent_loop
```

4. Trigger a normal-sized trade:

```powershell
(Get-Content .env) -replace '^BASE_ORDER_SIZE=.*$', 'BASE_ORDER_SIZE=25' | Set-Content .env
python -m agent.agent_loop
```

5. Trigger the kill-switch on the next run by exceeding the limit:

```powershell
(Get-Content .env) -replace '^BASE_ORDER_SIZE=.*$', 'BASE_ORDER_SIZE=150' | Set-Content .env
python -m agent.agent_loop
```

What to narrate while the dashboard updates:

- "Here is the latest Pyth-derived ETH/USDC price."
- "Here is the model rationale panel as the response streams in."
- "This first decision fits inside the guardrails, so the trade is prepared."
- "This second decision violates the per-trade limit, and the Python client decodes the contract error before it broadcasts."
- "The dashboard shows the kill-switch status and the error without the bot hammering the chain."

## 1:30-2:00 Closing

Talking points:

- "The point is not fully autonomous risk-taking. The point is constrained autonomy."
- "The architecture is simple: Pyth price input, EMA plus LLM reasoning, on-chain Monad guardrails, then an event-driven feedback loop back into the agent."
- "Judges should care because the safety policy is enforced on-chain, not just in Python comments."

Final on-screen action:

```powershell
python -m agent.event_listener
```

Use this to point at the `TradePlaced` events that feed back into the next decision cycle.
