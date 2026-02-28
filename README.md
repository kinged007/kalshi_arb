# Kalshi Arbitrage Monitor

A command-line tool for monitoring prediction markets on Kalshi to identify real-time arbitrage and pricing inefficiency opportunities.

This tool interfaces with the Kalshi REST API to search for active markets and uses WebSockets to subscribe to orderbook deltas. It continuously watches the orderbook to detect situations where the sum of the best "Yes" and "No" asks is strictly less than 100 cents (meaning you can lock in a risk-free profit by buying both sides).

## Features
- **Search**: Query active Kalshi markets by title or ticker using the REST API.
- **Watch**: Connect via WebSockets to a specific market's orderbook and monitor for arbitrage opportunities in real-time.

## Prerequisites
- Python 3.12+
- A Kalshi account with API access
- `uv` package manager (recommended) or `pip`

## Installation

1. Clone or download the repository.
2. Install dependencies (this project uses `uv` for dependency management):
   ```bash
   uv sync
   ```
   *(Alternatively, if using pip: `pip install .` or install from `pyproject.toml`)*

3. Configure your environment variables. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
4. Edit the `.env` file to include your Kalshi API credentials:
   - `KALSHI_KEY_ID`: Your exact Key ID string from Kalshi.
   - `KALSHI_PRIVATE_KEY_PATH`: Absolute or relative path to your Kalshi RSA private key file (e.g., `kalshi_private_key.txt`).
   - `TELEGRAM_BOT_TOKEN` (optional): Bot token to receive Telegram alerts on trade execution.
   - `TELEGRAM_CHAT_ID` (optional): Chat ID for Telegram alerts.

## Usage

You can run the script via `uv run` or directly with `python` if the virtual environment is activated.

### 1. Search for Markets
Find the ticker for a market you'd like to monitor by searching through active markets:

```bash
uv run kalshi_arb.py search <query>
```
*Example:* `uv run kalshi_arb.py search Trump` or `uv run kalshi_arb.py search CPI`

### 2. Watch a Market for Arbitrage
Once you have an exact market ticker (e.g., `KXTRUMP-24DEC31`), start the monitor:

```bash
uv run kalshi_arb.py watch <ticker>
```

The script will connect via WebSockets, maintain a local orderbook, and print to the console whenever `Yes Ask + No Ask < 100c`. Press `Ctrl+C` to shut down the monitor.
