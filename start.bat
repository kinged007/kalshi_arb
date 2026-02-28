@echo off
echo Starting Kalshi Arbitrage Monitor Phase 1...
echo Checking dependencies and launching script via uv...

REM Run the main Python script with the configured arguments
uv run python kalshi_arb.py watch --max-hours 0.5 --reset-int 0.25 --stake 1 --trade

REM Pause so the terminal doesn't close immediately if it crashes or exits
pause
