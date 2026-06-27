# 🤖 Monad AI Agent

> **Autonomous AI Trading Agent built on Monad Testnet using MiniMax AI, Pyth Network Oracle, Solidity Smart Contracts, and automated risk management.**

![Status](https://img.shields.io/badge/Status-Active-brightgreen)
![Monad](https://img.shields.io/badge/Network-Monad%20Testnet-purple)
![Python](https://img.shields.io/badge/Python-3.11-blue)
![Solidity](https://img.shields.io/badge/Solidity-0.8.28-black)
![License](https://img.shields.io/badge/License-MIT-green)

---

# 🚀 Overview

Monad AI Agent is an autonomous on-chain trading system that combines **AI reasoning**, **real-time oracle data**, and **smart contract risk management** to make explainable trading decisions.

Unlike traditional bots that execute predefined strategies, Monad AI Agent:

* Reads live market prices from **Pyth Network**
* Applies an **EMA trading strategy**
* Uses **MiniMax AI (NVIDIA NIM)** to reason about the market
* Protects funds using an on-chain **KillSwitch** smart contract
* Executes trades only when predefined safety conditions are satisfied

---

# ✨ Features

* 🤖 AI-powered market reasoning
* 📈 EMA crossover trading strategy
* 🔮 Pyth Oracle integration
* 🛡 KillSwitch smart contract protection
* ⚡ Monad Testnet deployment
* 📊 Live terminal dashboard
* 📜 Event monitoring
* 💹 Automated swap execution
* 🔒 Risk management
* 🧠 Explainable AI decisions

---

# 🏗 Architecture

```text
                 ┌─────────────────────────┐
                 │     Dashboard (UI)      │
                 └────────────┬────────────┘
                              │
                              ▼
                 ┌─────────────────────────┐
                 │      AI Agent           │
                 └────────────┬────────────┘
                              │
                              ▼
                 ┌─────────────────────────┐
                 │     MiniMax AI          │
                 │   (NVIDIA NIM API)      │
                 └────────────┬────────────┘
                              │
                              ▼
                 ┌─────────────────────────┐
                 │    EMA Strategy         │
                 └────────────┬────────────┘
                              │
                              ▼
                 ┌─────────────────────────┐
                 │     Pyth Oracle         │
                 └────────────┬────────────┘
                              │
                              ▼
                 ┌─────────────────────────┐
                 │ KillSwitch SmartContract│
                 └────────────┬────────────┘
                              │
                              ▼
                 ┌─────────────────────────┐
                 │    Monad Testnet        │
                 └─────────────────────────┘
```

---

# 🛠 Tech Stack

### Blockchain

* Monad Testnet
* Solidity
* Hardhat

### Backend

* Python
* Web3.py

### AI

* MiniMax M2.7
* NVIDIA NIM API

### Oracle

* Pyth Network

### Frontend (Current)

* Rich Terminal Dashboard

### Frontend (Planned)

* Next.js
* Tailwind CSS
* Framer Motion

---

# 📂 Project Structure

```text
agent/          AI Agent Logic
contracts/      Solidity Smart Contracts
scripts/        Deployment Scripts
test/           Contract Tests
docs/           Documentation
```

---

# ⚙ Installation

```bash
git clone https://github.com/indrak31/AI-Agent.git

cd AI-Agent

npm install

python -m pip install -r requirements.txt

cp .env.example .env
```

Configure your `.env` before running.

---

# 🚀 Deploy Contracts

```bash
npm run compile

npm test

npm run deploy:hello

npm run deploy:killswitch
```

---

# ▶ Run the AI Agent

Terminal 1

```bash
python -m agent.dashboard
```

Terminal 2

```bash
python -m agent.agent_loop
```

Utility Commands

```bash
python -m agent.price_feed

python -m agent.event_listener
```

---

# 🛡 Safety Features

* Daily trading limits
* Maximum trade size
* Cooldown timer
* Emergency pause
* Oracle validation
* AI confidence filtering

---

# 📸 Screenshots

> Add your dashboard screenshots here.

* Dashboard
* AI Reasoning
* KillSwitch
* Trade History

---

# 🎥 Demo

Coming Soon

* Live Demo
* Demo Video

---

# 🗺 Roadmap

* Web Dashboard
* TradingView Charts
* Multi-token Trading
* Portfolio Analytics
* Telegram Alerts
* Multi-Agent Coordination
* Reinforcement Learning

---

# 🤝 Team

Built for the Monad Hackathon

* **Indra Kurkute**
* **ALOK AAGE**
* **ANNANYA UKEY**

---

# 📄 License

MIT License

---

⭐ If you like this project, consider giving it a star on GitHub!
