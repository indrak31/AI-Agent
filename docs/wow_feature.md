# Wow Feature

## Ranked additions

1. Live reasoning stream in the dashboard
   Judges care because it makes the LLM decision process inspectable in real time without pretending the model is infallible.
2. Autonomous pause-on-drawdown rule
   Judges care because it combines off-chain portfolio monitoring with an on-chain emergency brake.
3. Multi-oracle sanity check before each trade
   Judges care because it shows robust market-data handling instead of trusting one feed blindly.

## Top pick: live reasoning stream

This repository already implements the top pick across the agent loop and dashboard.

### Capture the reasoning

- `agent/agent_loop.py` defines a strict JSON-only system prompt with a visible `rationale` field.
- When the EMA signal is ambiguous, `_invoke_llm()` calls `ChatAnthropic.stream(...)`.
- Each streamed chunk is appended to `reasoning.stream` in shared state.
- Once the JSON is complete and validated, the final `rationale` is written to `decision.rationale` and `reasoning.last_complete`.

### Stream it into shared state

- `agent/shared_state.py` provides atomic JSON-file writes so the agent and dashboard can run in separate processes.
- The agent updates:
  - `reasoning.status`
  - `reasoning.stream`
  - `reasoning.display`
  - `decision.rationale`

### Render it without flooding the terminal

- `agent/dashboard.py` reads the current snapshot every five seconds.
- `build_reasoning_panel()` truncates the stream to the last 4,000 characters and only renders the last 25 lines.
- The current status label changes between `idle`, `streaming`, `complete`, and `error`, so the user can tell whether the panel is still live or showing the final rationale.

## Files involved

- `agent/agent_loop.py`
- `agent/shared_state.py`
- `agent/dashboard.py`
