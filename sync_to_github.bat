@echo off
REM ─── Push forex-trading to GitHub ─────────────────────────────────────────
REM One-time setup: create a repo called "forex-trading" on github.com
REM Then run this script once to connect and push.
REM After that: just double-click to sync changes.

cd /d C:\Users\Hp\Desktop\forex-trading

REM Initialise if not already a git repo
if not exist .git (
    git init
    git branch -M main
    echo Enter your GitHub repo URL (e.g. https://github.com/shaheryarskhan7-glitch/forex-trading.git):
    set /p REMOTE_URL=
    git remote add origin %REMOTE_URL%
)

git add config.py notifier.py forex_utils.py forex_exposure_manager.py
git add eur_usd_dashboard.py gbp_usd_dashboard.py aud_usd_dashboard.py
git add forex_outcome_tracker.py forex_monitor.py forex-monitor.service
git add .gitignore deploy_to_oracle.bat sync_to_github.bat
git add strategies\ backtests\ 2>nul

git commit -m "Forex monitor: EUR/USD GBP/USD AUD/USD — S1+S2+S3"
git push -u origin main

echo Done. Check GitHub.
pause
