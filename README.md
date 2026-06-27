# Monad AI Agent

This repository scaffolds the full 12-task hackathon build described in the prompt file:

- Hardhat deployment and verification on Monad testnet
- `KillSwitch.sol` guardrails contract with tests
- Python price polling, EMA strategy, LLM decision loop, swap execution helper, event listener, and Rich dashboard
- Operator docs for edge cases and the live demo

## Assumptions

- Current Monad testnet values were verified against the official Monad docs on June 25, 2026:
  - `chainId`: `10143`
  - testnet RPC: `https://testnet-rpc.monad.xyz`
  - faucet: `https://faucet.monad.xyz`
- Current Monad oracle docs list the Pyth testnet contracts below:
  - stable price feeds: `0x2880aB155794e7179c9eE2e38200202908C17B43`
  - beta price feeds: `0xad2B52D2af1a9bD5c561894Cdd84f7505e1CD0B5`
- Pyth feed IDs and the Monad testnet DEX/router address are intentionally left as `.env` values because they are the pieces most likely to drift and must be re-checked before live testing.
- This scaffold is testnet-only. Keep `ENABLE_LIVE_SWAPS=false` until every address, token decimal, approval, and feed ID has been verified.

## Install

```powershell
Copy-Item .env.example .env
npm install
python -m pip install -r requirements.txt
```

## Hardhat workflow

Generate or import a dedicated testnet wallet, then fund it from the official faucet after you verify the faucet URL in Monad's docs:

```powershell
node -e "const { Wallet } = require('ethers'); const w = Wallet.createRandom(); console.log('address=' + w.address); console.log('privateKey=' + w.privateKey);"
```

Set `DEPLOYER_PRIVATE_KEY` in `.env`, then compile, test, and deploy:

```powershell
npm run compile
npm test
npm run deploy:hello
npm run deploy:killswitch
```

Verify on Monad testnet:

```powershell
npx hardhat verify --network monadTestnet <HELLO_WORLD_ADDRESS> "<HELLO_WORLD_GREETING>"
npx hardhat verify --network monadTestnet <KILLSWITCH_ADDRESS> <DAILY_CAP_WEI_18> <PER_TRADE_LIMIT_WEI_18> <COOLDOWN_SECONDS>
```

Confirmation steps:

- Check the deployment transaction hash in the script output.
- Open the address on `https://testnet.monadvision.com` or `https://testnet.monadscan.com`.
- Monad's Hardhat verification guide notes that the command can print an error even when verification succeeds, so confirm in the explorer UI.

## Python workflow

Run the agent and dashboard as separate processes:

```powershell
python -m agent.agent_loop
python -m agent.dashboard
```

Utility entry points:

```powershell
python -m agent.price_feed
python -m agent.event_listener
```

## TODO before live testing

- Replace the placeholder Pyth feed IDs in `.env` with the current official `ETH/USD` and `USDC/USD` feed IDs from the Pyth price feed ID page.
- Confirm the DEX/router contract, token addresses, and decimals from the DEX's official Monad testnet docs.
- Seed the `KillSwitch` contract with the assets it will trade and ensure the router has the required allowance from the contract address.
- Decide whether your trade `size` should represent quote-token notional, base-token amount, or another normalized unit, then keep the agent, router amounts, and `KillSwitch` limits aligned to that convention.
