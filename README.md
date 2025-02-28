# 🚀 Solana Automated Trading Bot

This **Solana Automated Trading Bot** monitors new token listings, analyzes market trends, and executes buy/sell trades based on configurable parameters. It leverages **asyncio**, **aiohttp**, and **Solana SDK** for high-performance trading.

## 🛠 Features
- **Async-based Trading Engine:** Efficient non-blocking execution.
- **Dynamic RugCheck Validation:** Automatically verifies token legitimacy.
- **Customizable Trading Strategy:** Adjust profit targets, volume thresholds, slippage, and more.
- **Database Persistence:** Saves token data using SQLite for tracking trades.
- **Robust Error Handling:** Includes retry mechanisms and structured logging.
- **Graceful Shutdown Handling:** Ensures proper cleanup and state preservation.

---

## 📌 **Prerequisites**
Before running the bot, ensure you have:

- **Python 3.9+**
- **Docker & Docker Compose** (if running with containers)
- A **Solana Wallet Private Key** (Base58 format)
- An **RPC Endpoint** from a provider like [Alchemy](https://www.alchemy.com/) or [QuickNode](https://www.quicknode.com/)
- API Access to [GMGN](https://gmgn.ai) and [RugCheck](https://rugcheck.xyz)

---

## 🚀 **Installation & Setup**

### 1️⃣ **Clone the Repository**
```bash
git clone https://github.com/yourusername/solana-trading-bot.git
cd solana-trading-bot
```

### 2️⃣ **Create a Virtual Environment (Optional)**
```bash
python3 -m venv venv
source venv/bin/activate   # On Mac/Linux
venv\Scripts\activate      # On Windows
```

### 3️⃣ **Install Dependencies**
```bash
pip install -r requirements.txt
```

### 4️⃣ **Configuration**
The bot uses **environment variables** for configuration. Create a `.env` file in the project root and add:

```ini
# SOLANA Wallet Private Key (Base58 Encoded)
WALLET_PRIVATE_KEY=your_private_key_here

# Solana RPC URL (Mainnet)
SOLANA_RPC=https://api.mainnet-beta.solana.com

# API Hosts
GMGN_API_HOST=https://gmgn.ai
RUGCHECK_API_ENDPOINT=https://api.rugcheck.xyz/v1/tokens/{token_address}

# Trading Parameters
CHECK_INTERVAL=60
VOLUME_THRESHOLD=1000
LIQUIDITY_THRESHOLD=500
TX_COUNT_THRESHOLD=100
TREND_SCORE_MIN=0.5
SCAM_RISK_MAX=0.5
PROFIT_MULTIPLIER_MIN=2.0
PROFIT_MULTIPLIER_MAX=3.0
SELL_PERCENTAGE=0.5
BUY_AMOUNT_SOL=1
CACHE_EXPIRY=300
SLIPPAGE=0.5

# RugCheck API Key (If pre-obtained)
API_KEY_RUGCHECK=
```

> **⚠️ IMPORTANT:** Never hardcode private keys directly in your scripts. Always use a `.env` file or a secure secrets manager.

---

## ▶ **Running the Bot**
### 🔧 **Method 1: Running Directly**
```bash
python bot.py
```

### 🐳 **Method 2: Running with Docker**
#### 1️⃣ **Build the Docker Image**
```bash
docker build -t solana-trading-bot .
```

#### 2️⃣ **Run the Container**
```bash
docker run --env-file .env --name solana-trader -d solana-trading-bot
```

#### 3️⃣ **Check Logs**
```bash
docker logs -f solana-trader
```

---

## 🛠 **Docker Compose (Recommended for Production)**
To manage the bot easily, use **Docker Compose**. Create a `docker-compose.yml` file:

```yaml
version: "3.8"
services:
  solana-trading-bot:
    container_name: solana-trader
    build: .
    env_file:
      - .env
    restart: always
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### **Running with Docker Compose**
```bash
docker-compose up --build -d
```

### **Stopping the Bot**
```bash
docker-compose down
```

---

## 🔍 **Bot Logic & Trading Strategy**
### 📊 **How it Works**
1. The bot **fetches new tokens** from **GMGN API**.
2. It **retrieves market analytics** (volume, liquidity, transactions).
3. It checks for **trending tokens** and verifies **scam risk**.
4. If the token meets buying criteria:
   - It **buys the token** using a swap route.
   - **Stores the purchase details** in the SQLite database.
5. The bot continuously **monitors price changes**.
6. If a token reaches a profitable threshold:
   - It **sells automatically** based on **predefined profit targets**.

### 🏆 **Trading Criteria**
| Parameter              | Condition                        |
|------------------------|--------------------------------|
| Volume                | ≥ `VOLUME_THRESHOLD`            |
| Liquidity             | ≥ `LIQUIDITY_THRESHOLD`         |
| Transaction Count     | ≥ `TX_COUNT_THRESHOLD`          |
| Trend Score          | ≥ `TREND_SCORE_MIN`             |
| Scam Risk            | ≤ `SCAM_RISK_MAX`               |
| Profit to Sell (Max) | ≥ `PROFIT_MULTIPLIER_MAX` (3x)  |
| Profit to Partial Sell | ≥ `PROFIT_MULTIPLIER_MIN` (2x) |

---

## 📂 **File Structure**
```
/solana-trading-bot
│── bot.py                 # Main trading bot script
│── requirements.txt        # Dependencies
│── .env                    # Configuration (ignored by Git)
│── docker-compose.yml       # Docker Compose setup
│── Dockerfile               # Docker build instructions
│── README.md                # Documentation (You are here)
│── trading_bot.log          # Logs (if running)
```

---

## 🛑 **Troubleshooting**
### ❌ `Error: Invalid private key format`
- Ensure `WALLET_PRIVATE_KEY` is **Base58 encoded** (not raw bytes or JSON).

### ❌ `Transaction failed`
- Check RPC endpoint **rate limits** and **wallet balance**.

### ❌ `Bot exits unexpectedly`
- Run with `docker logs -f solana-trader` to diagnose.

---

## 📜 **Legal Disclaimer**
This bot is for **educational purposes only**. Cryptocurrency trading is risky, and **no guarantees** of profit are made. Use at **your own risk**.

---

## 💬 **Support & Contributions**
- Issues? Open an [issue](https://github.com/yourusername/solana-trading-bot/issues).
- Contributions? Fork and submit a PR!

## ✅ **Testing the Solana Trading Bot**
To ensure the bot functions correctly before deploying it with real funds, follow these **testing procedures**.

---

## 🛠 **1. Prepare a Safe Test Environment**
Before running the bot in a **live trading** environment, test it using a **sandbox** or **simulated trades**.

### **Option 1: Use a Testnet (Recommended)**
You can switch the bot to use **Solana Testnet** instead of the **Mainnet** by updating the `.env` file:

```ini
SOLANA_RPC=https://api.testnet.solana.com
```

This allows you to simulate trades **without risking real money**. However, not all token APIs provide data for testnet.

### **Option 2: Use a Separate Wallet**
- Generate a **new Solana wallet** and fund it with a small amount of **SOL** for testing:
```bash
solana-keygen new --outfile test-wallet.json
solana airdrop 2 $(solana address) --url https://api.testnet.solana.com
```
- Update the `.env` file with the **private key** from `test-wallet.json`.

### **Option 3: Enable Dry-Run Mode (No Real Transactions)**
Modify the bot to **simulate trades** by logging transactions instead of executing them. In `bot.py`, modify the trading functions:

```python
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

async def execute_buy(self, token_state: TokenState, amount_in_sol: float = settings.BUY_AMOUNT_SOL) -> bool:
    if DRY_RUN:
        logging.info(f"[SIMULATED] Buying {token_state.name} ({token_state.token_address}) for {amount_in_sol} SOL")
        return True  # Simulated success
    # Proceed with actual buy logic...
```

Set **DRY_RUN=true** in your `.env` file.

---

## 🔍 **2. Run the Bot in Test Mode**
After setting up the test environment, run the bot:

```bash
python bot.py
```
or, if using Docker:

```bash
docker-compose up --build
```

---

## 📜 **3. Check Logs for Potential Wins & Losses**
The bot logs trades to `trading_bot.log`. Open it to see **potential wins and losses**:

```bash
tail -f trading_bot.log
```

Example log entries:

```
2025-03-01 10:45:23 - INFO - [SIMULATED] Buying TEST_TOKEN (6h32K...1fgB) for 1 SOL
2025-03-01 10:50:34 - INFO - Potential Profit Detected: TEST_TOKEN increased 2.1x
2025-03-01 10:55:12 - INFO - Selling 50% of TEST_TOKEN at 2.2x profit
2025-03-01 11:05:45 - WARNING - TEST_TOKEN dropped below initial price. Loss: -0.2 SOL
```

**Interpretation:**
- If a token **rises above the PROFIT_MULTIPLIER_MIN**, the bot **logs potential profit**.
- If a token **falls below buy price**, it logs a **potential loss**.

---

## 📊 **4. Analyze Trade Outcomes**
After running for a while, review **win/loss potential**:

```bash
grep "Potential Profit" trading_bot.log
grep "Loss" trading_bot.log
```

Example:
```
Potential Profit Detected: TEST_TOKEN increased 2.1x
Potential Profit Detected: MEMECOIN up 3.5x 🚀
Loss: -0.2 SOL on RUGPULL_TOKEN
```

This helps you adjust **trading parameters** before going live.

---

## 🛠 **5. Debug and Improve**
If something isn't working:
- Check `trading_bot.log` for **errors**.
- Manually **verify token prices** on [Solana Explorer](https://explorer.solana.com/).
- **Run in debug mode** for detailed logs:
```bash
LOG_LEVEL=DEBUG python bot.py
```

---

## 🎯 **Final Steps Before Live Trading**
Once testing is successful:
- Remove **DRY_RUN=true** from `.env`
- Switch back to **Mainnet RPC**:
```ini
SOLANA_RPC=https://api.mainnet-beta.solana.com
```
- Fund your **real wallet** and **start trading!**

---

## 🚀 **Next Steps**
✅ Use **Telegram or Webhook Alerts** for notifications.  
✅ Add a **Dashboard** to track performance.  
✅ Improve **risk management strategies**.

---

🎉 **Congratulations!** You now have a fully tested **Solana Trading Bot** ready for real profits! 🚀

🚀 **Happy Trading!**
