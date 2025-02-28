#!/usr/bin/env python3
import asyncio
import aiohttp
import aiosqlite
import base64
import logging
import os
import signal
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from async_solana import Client as AsyncSolanaClient
from solders.keypair import Keypair as SoldersKeypair
from solders.pubkey import Pubkey
from solana.transaction import VersionedTransaction
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from spl.token.client import Token
from pydantic import BaseModel, BaseSettings, ValidationError

# --- Configuration via pydantic ---
class Settings(BaseSettings):
    SOL_ADDRESS: str = "So11111111111111111111111111111111111111112"
    GMGN_API_HOST: str = "https://gmgn.ai"
    RUGCHECK_API_ENDPOINT: str = "https://api.rugcheck.xyz/v1/tokens/{token_address}"
    SOLANA_RPC: str = "https://api.mainnet-beta.solana.com"
    CHECK_INTERVAL: int = 60
    VOLUME_THRESHOLD: float = 1000
    LIQUIDITY_THRESHOLD: float = 500
    TX_COUNT_THRESHOLD: int = 100
    TREND_SCORE_MIN: float = 0.5
    SCAM_RISK_MAX: float = 0.5
    PROFIT_MULTIPLIER_MIN: float = 2.0
    PROFIT_MULTIPLIER_MAX: float = 3.0
    SELL_PERCENTAGE: float = 0.5
    BUY_AMOUNT_SOL: float = 1
    CACHE_EXPIRY: int = 300  # in seconds
    SLIPPAGE: float = 0.5
    WALLET_PRIVATE_KEY: Optional[str]
    LOG_LEVEL: str = "INFO"
    # Optionally pre-load the RugCheck API key; if not set, the bot will attempt to fetch one.
    API_KEY_RUGCHECK: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()

# --- Validate Critical Settings ---
if not settings.WALLET_PRIVATE_KEY:
    raise ValueError("Critical environment variable missing: WALLET_PRIVATE_KEY")

# --- Logging Setup ---
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("trading_bot.log"), logging.StreamHandler()]
)

# --- Initialize Solana Client and Wallet ---
solana_client = AsyncSolanaClient(settings.SOLANA_RPC)
wallet = SoldersKeypair.from_base58(settings.WALLET_PRIVATE_KEY)

# Global RugCheck API key (can be refreshed)
API_KEY_RUGCHECK = settings.API_KEY_RUGCHECK

# --- In-Memory Cache with Async Lock ---
cache: Dict[str, Dict[str, Any]] = {}
cache_lock = asyncio.Lock()

async def get_cached_data(key: str) -> Optional[Any]:
    async with cache_lock:
        if key in cache and time.time() - cache[key]['timestamp'] < settings.CACHE_EXPIRY:
            return cache[key]['data']
    return None

async def set_cached_data(key: str, data: Any) -> None:
    async with cache_lock:
        cache[key] = {'data': data, 'timestamp': time.time()}

# --- Database Setup ---
async def setup_database() -> None:
    async with aiosqlite.connect("meme_tokens.db") as conn:
        await conn.execute('''CREATE TABLE IF NOT EXISTS tokens 
            (token_address TEXT PRIMARY KEY, name TEXT, volume REAL, liquidity REAL, tx_count INTEGER, 
             trend_score REAL, scam_risk REAL, buy_price REAL, holdings REAL, decimals INTEGER, timestamp TEXT)''')
        await conn.commit()

# --- Pydantic Models for API Response Validation ---
class TokenAnalytics(BaseModel):
    volume_24h: float
    liquidity: float
    tx_count_24h: int
    sniper_activity: float
    insider_trades: int

class TrendData(BaseModel):
    trending_tokens: List[Dict[str, Any]]

# --- API Functions with Retry Mechanism ---
@retry(retry=retry_if_exception_type(aiohttp.ClientError),
       stop=stop_after_attempt(3),
       wait=wait_exponential(multiplier=1, min=4, max=10))
async def fetch_new_tokens(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    url = f"{settings.GMGN_API_HOST}/defi/router/v1/sol/tokens"
    async with session.get(url) as response:
        response.raise_for_status()
        tokens = await response.json()
        return tokens

@retry(retry=retry_if_exception_type(aiohttp.ClientError),
       stop=stop_after_attempt(3),
       wait=wait_exponential(multiplier=1, min=4, max=10))
async def fetch_token_analytics(session: aiohttp.ClientSession, token_address: str) -> Dict[str, Any]:
    cached = await get_cached_data(f"analytics_{token_address}")
    if cached:
        return cached
    url = f"{settings.GMGN_API_HOST}/defi/analytics/v1/sol/token/{token_address}"
    async with session.get(url) as response:
        response.raise_for_status()
        data = await response.json()
        try:
            validated = TokenAnalytics(**data).dict()
            await set_cached_data(f"analytics_{token_address}", validated)
            return validated
        except ValidationError as e:
            logging.error(f"Invalid analytics data for {token_address}: {e}")
            return {}

@retry(retry=retry_if_exception_type(aiohttp.ClientError),
       stop=stop_after_attempt(3),
       wait=wait_exponential(multiplier=1, min=4, max=10))
async def fetch_market_trends(session: aiohttp.ClientSession) -> Dict[str, float]:
    cached = await get_cached_data("trends")
    if cached:
        return cached
    url = f"{settings.GMGN_API_HOST}/defi/analytics/v1/sol/trends"
    async with session.get(url) as response:
        response.raise_for_status()
        data = await response.json()
        try:
            trends_data = TrendData(**data).dict()
            trend_scores = {token["address"]: float(token.get("trend_score", 0))
                            for token in trends_data.get("trending_tokens", [])}
            await set_cached_data("trends", trend_scores)
            return trend_scores
        except ValidationError as e:
            logging.error(f"Invalid trends data: {e}")
            return {}

@retry(retry=retry_if_exception_type(aiohttp.ClientError),
       stop=stop_after_attempt(3),
       wait=wait_exponential(multiplier=1, min=4, max=10))
async def validate_token_rugcheck(session: aiohttp.ClientSession, token_address: str) -> bool:
    global API_KEY_RUGCHECK
    if not API_KEY_RUGCHECK:
        API_KEY_RUGCHECK = await get_rugcheck_api_token(session)
        if not API_KEY_RUGCHECK:
            logging.error("Unable to obtain RugCheck API token.")
            return False
    headers = {"Authorization": f"Bearer {API_KEY_RUGCHECK}"}
    url = settings.RUGCHECK_API_ENDPOINT.format(token_address=token_address)
    async with session.get(url, headers=headers) as response:
        response.raise_for_status()
        data = await response.json()
        status = data.get("status", "UNKNOWN").upper()
        return status == "GOOD"

async def get_token_decimals(token_address: str) -> int:
    try:
        token = Token(solana_client, Pubkey.from_string(token_address),
                      program_id=Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"))
        info = await token.get_mint_info()
        return info.decimals
    except Exception as e:
        logging.error(f"Error fetching decimals for {token_address}: {e}")
        return 6  # Fallback default

@retry(retry=retry_if_exception_type(aiohttp.ClientError),
       stop=stop_after_attempt(3),
       wait=wait_exponential(multiplier=1, min=4, max=10))
async def get_swap_route(session: aiohttp.ClientSession,
                         token_in_address: str,
                         token_out_address: str,
                         amount: str,
                         slippage: float = settings.SLIPPAGE) -> Dict[str, Any]:
    url = (f"{settings.GMGN_API_HOST}/defi/router/v1/sol/tx/get_swap_route"
           f"?token_in_address={token_in_address}&token_out_address={token_out_address}"
           f"&in_amount={amount}&from_address={str(wallet.pubkey())}&slippage={slippage}")
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.json()

@retry(retry=retry_if_exception_type(aiohttp.ClientError),
       stop=stop_after_attempt(3),
       wait=wait_exponential(multiplier=1, min=4, max=10))
async def submit_transaction(session: aiohttp.ClientSession, signed_tx: str) -> Dict[str, Any]:
    payload = {"signed_tx": signed_tx}
    url = f"{settings.GMGN_API_HOST}/defi/router/v1/sol/tx/submit_signed_transaction"
    async with session.post(url, json=payload, headers={"Content-Type": "application/json"}) as response:
        response.raise_for_status()
        return await response.json()

async def confirm_transaction(tx_hash: str) -> bool:
    try:
        status = await solana_client.get_transaction(tx_hash)
        return status.get('result') is not None and \
               status.get('result', {}).get('meta', {}).get('err') is None
    except Exception as e:
        logging.error(f"Error confirming transaction {tx_hash}: {e}")
        return False

# --- Token State and Risk Analysis ---
class TokenState:
    def __init__(self, token_address: str, name: str, decimals: int):
        self.token_address = token_address
        self.name = name
        self.decimals = decimals
        self.volume = 0.0
        self.liquidity = 0.0
        self.tx_count = 0
        self.trend_score = 0.0
        self.scam_risk = 0.0
        self.buy_price = 0.0
        self.holdings = 0.0
        self.sniper_activity = 0.0
        self.insider_trades = 0

    async def update_analytics(self, analytics: Dict[str, Any]) -> None:
        self.volume = analytics.get("volume_24h", 0.0)
        self.liquidity = analytics.get("liquidity", 0.0)
        self.tx_count = analytics.get("tx_count_24h", 0)
        self.sniper_activity = analytics.get("sniper_activity", 0.0)
        self.insider_trades = analytics.get("insider_trades", 0)

    async def update_trend_score(self, trend_score: float) -> None:
        self.trend_score = trend_score

    async def update_scam_risk(self) -> None:
        # Weighted risk factors; these weights/thresholds may be tuned further.
        risk_factors = {
            'sniper_activity': (self.sniper_activity, 50, 0.3),
            'insider_trades': (self.insider_trades, 10, 0.2),
            'liquidity': (self.liquidity, settings.LIQUIDITY_THRESHOLD / 2, 0.4),
            'tx_count': (self.tx_count, settings.TX_COUNT_THRESHOLD / 2, 0.1)
        }
        risk = 0.0
        for factor, (value, threshold, weight) in risk_factors.items():
            if factor in ['sniper_activity', 'insider_trades']:
                if value > threshold:
                    risk += weight
            else:
                if value < threshold:
                    risk += weight
        self.scam_risk = risk

    async def update_holdings(self, buy_price: float, holdings: float) -> None:
        self.buy_price = buy_price
        self.holdings = holdings

# --- Trader Class for Buy/Sell Execution ---
class Trader:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def execute_buy(self, token_state: TokenState,
                          amount_in_sol: float = settings.BUY_AMOUNT_SOL) -> bool:
        try:
            amount_in_units = int(amount_in_sol * 10**9)
            route = await get_swap_route(self.session, settings.SOL_ADDRESS,
                                         token_state.token_address, str(amount_in_units))
            if not route or "data" not in route or "raw_tx" not in route["data"]:
                logging.error(f"Failed to get buy route for {token_state.name}")
                return False

            swap_tx = base64.b64decode(route["data"]["raw_tx"]["swapTransaction"])
            transaction = VersionedTransaction.from_bytes(swap_tx)
            transaction.sign([wallet])
            signed_tx = base64.b64encode(transaction.serialize()).decode("utf-8")
            result = await submit_transaction(self.session, signed_tx)
            if result and "data" in result and "hash" in result["data"]:
                tx_hash = result["data"]["hash"]
                if await confirm_transaction(tx_hash):
                    out_amount = int(route["data"].get("out_amount", 0))
                    if out_amount == 0:
                        logging.error(f"Buy route returned zero output amount for {token_state.name}")
                        return False
                    buy_price = amount_in_sol / (out_amount / (10 ** token_state.decimals))
                    holdings = out_amount / (10 ** token_state.decimals)
                    await token_state.update_holdings(buy_price, holdings)
                    await save_token_to_db(token_state)
                    logging.info(f"Bought {holdings:.4f} {token_state.name} at {buy_price:.4f} SOL/token")
                    return True
                else:
                    logging.error(f"Transaction confirmation failed for {token_state.name}")
            return False
        except Exception as e:
            logging.error(f"Error executing buy for {token_state.name}: {e}", exc_info=True)
            return False

    async def execute_sell(self, token_state: TokenState, amount_to_sell: float) -> bool:
        try:
            amount_units = int(amount_to_sell * (10 ** token_state.decimals))
            route = await get_swap_route(self.session, token_state.token_address,
                                         settings.SOL_ADDRESS, str(amount_units))
            if not route or "data" not in route or "raw_tx" not in route["data"]:
                logging.error(f"Failed to get sell route for {token_state.token_address}")
                return False

            swap_tx = base64.b64decode(route["data"]["raw_tx"]["swapTransaction"])
            transaction = VersionedTransaction.from_bytes(swap_tx)
            transaction.sign([wallet])
            signed_tx = base64.b64encode(transaction.serialize()).decode("utf-8")
            result = await submit_transaction(self.session, signed_tx)
            if result and "data" in result and "hash" in result["data"]:
                tx_hash = result["data"]["hash"]
                if await confirm_transaction(tx_hash):
                    proceeds = route["data"].get("out_amount", 0) / 10**9
                    logging.info(f"Sold {amount_to_sell:.4f} {token_state.name} for {proceeds:.4f} SOL")
                    return True
                else:
                    logging.error(f"Sell transaction confirmation failed for {token_state.token_address}")
            return False
        except Exception as e:
            logging.error(f"Error executing sell for {token_state.token_address}: {e}", exc_info=True)
            return False

# --- Token Analyzer Class ---
class TokenAnalyzer:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def analyze_token(self, token_address: str, name: str) -> Optional[TokenState]:
        analytics = await fetch_token_analytics(self.session, token_address)
        if not analytics:
            logging.warning(f"No analytics data for {token_address}")
            return None
        decimals = await get_token_decimals(token_address)
        token_state = TokenState(token_address, name, decimals)
        await token_state.update_analytics(analytics)
        await token_state.update_scam_risk()
        if await validate_token_rugcheck(self.session, token_address):
            return token_state
        logging.info(f"Token {token_address} failed RugCheck validation")
        return None

# --- Database Persistence ---
async def save_token_to_db(token_state: TokenState) -> None:
    try:
        async with aiosqlite.connect("meme_tokens.db") as conn:
            await conn.execute('''INSERT OR REPLACE INTO tokens 
                (token_address, name, volume, liquidity, tx_count, trend_score, scam_risk, buy_price, holdings, decimals, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                (token_state.token_address, token_state.name, token_state.volume, token_state.liquidity,
                 token_state.tx_count, token_state.trend_score, token_state.scam_risk, token_state.buy_price,
                 token_state.holdings, token_state.decimals, datetime.now().isoformat()))
            await conn.commit()
    except Exception as e:
        logging.error(f"Database error for token {token_state.token_address}: {e}", exc_info=True)

async def get_rugcheck_api_token(session: aiohttp.ClientSession) -> str:
    """Obtain a RugCheck API token by signing an authentication message."""
    try:
        message = "Sign-in to Rugcheck.xyz"
        message_bytes = message.encode('utf-8')
        signature = wallet.sign_message(message_bytes)
        signature_base64 = base64.b64encode(signature).decode('utf-8')
        payload = {
            "wallet": str(wallet.pubkey()),
            "message": message,
            "signature": signature_base64
        }
        async with session.post("https://api.rugcheck.xyz/v1/auth/login/solana", json=payload) as response:
            response.raise_for_status()
            data = await response.json()
            token_val = data.get("token", "")
            if token_val:
                logging.info("Obtained RugCheck API token")
            else:
                logging.error("Failed to obtain RugCheck API token from response")
            return token_val
    except Exception as e:
        logging.error(f"Error getting RugCheck API token: {e}", exc_info=True)
        return ""

# --- Main Trading Loop with Graceful Shutdown ---
async def monitor_and_trade() -> None:
    await setup_database()
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_event.set)

    async with aiohttp.ClientSession() as session:
        global API_KEY_RUGCHECK
        if not API_KEY_RUGCHECK:
            API_KEY_RUGCHECK = await get_rugcheck_api_token(session)
            if not API_KEY_RUGCHECK:
                logging.error("Exiting due to inability to obtain RugCheck API token.")
                return

        trader = Trader(session)
        analyzer = TokenAnalyzer(session)

        while not shutdown_event.is_set():
            try:
                logging.info("=== Market Check Started ===")
                tokens = await fetch_new_tokens(session)
                trends = await fetch_market_trends(session)
                # Analyze and potentially buy tokens that meet our criteria.
                for token in tokens:
                    token_address = token.get("address")
                    name = token.get("name", "Unknown")
                    token_state = await analyzer.analyze_token(token_address, name)
                    if token_state:
                        token_state.trend_score = trends.get(token_address, 0)
                        if (token_state.volume >= settings.VOLUME_THRESHOLD and
                            token_state.liquidity >= settings.LIQUIDITY_THRESHOLD and
                            token_state.tx_count >= settings.TX_COUNT_THRESHOLD and
                            token_state.trend_score >= settings.TREND_SCORE_MIN and
                            token_state.scam_risk < settings.SCAM_RISK_MAX):
                            await trader.execute_buy(token_state)
                # Check existing holdings and sell if profitable.
                async with aiosqlite.connect("meme_tokens.db") as conn:
                    cursor = await conn.execute(
                        "SELECT token_address, name, buy_price, holdings, decimals FROM tokens WHERE holdings > 0")
                    rows = await cursor.fetchall()
                    for row in rows:
                        token_address, name, buy_price, holdings, decimals = row
                        token_state = TokenState(token_address, name, decimals)
                        token_state.buy_price = buy_price
                        token_state.holdings = holdings
                        # Estimate current price with a small test swap (e.g., 0.001 tokens).
                        route = await get_swap_route(session, token_address, settings.SOL_ADDRESS,
                                                     str(int(0.001 * (10 ** decimals))))
                        if route and "data" in route:
                            sol_received = route["data"].get("out_amount", 0) / 10**9
                            if sol_received == 0:
                                continue
                            current_price = sol_received / 0.001
                            profit_multiplier = current_price / token_state.buy_price
                            if profit_multiplier >= settings.PROFIT_MULTIPLIER_MAX:
                                await trader.execute_sell(token_state, token_state.holdings)
                                await conn.execute("UPDATE tokens SET holdings = 0 WHERE token_address = ?", (token_address,))
                            elif profit_multiplier >= settings.PROFIT_MULTIPLIER_MIN:
                                amount_to_sell = token_state.holdings * settings.SELL_PERCENTAGE
                                await trader.execute_sell(token_state, amount_to_sell)
                                await conn.execute("UPDATE tokens SET holdings = ? WHERE token_address = ?",
                                                   (token_state.holdings - amount_to_sell, token_address))
                    await conn.commit()
            except Exception as e:
                logging.error(f"Error in main trading loop: {e}", exc_info=True)
            await asyncio.sleep(settings.CHECK_INTERVAL)
    logging.info("Shutting down gracefully...")

if __name__ == "__main__":
    try:
        asyncio.run(monitor_and_trade())
    except Exception as e:
        logging.critical(f"Fatal error: {e}", exc_info=True)
