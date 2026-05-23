@echo off
REM ─── Deploy forex-trading to Oracle Cloud ─────────────────────────────────
REM Run this from C:\Users\Hp\Desktop\forex-trading\
REM Requires: ssh key at gold-trading\ssh-key-2026-05-07.key

SET KEY=..\gold-trading\ssh-key-2026-05-07.key
SET HOST=ubuntu@40.233.83.223
SET REMOTE_DIR=/home/ubuntu/forex-trading

echo [1/4] Creating remote directory...
ssh -i %KEY% %HOST% "mkdir -p %REMOTE_DIR%"

echo [2/4] Copying files...
scp -i %KEY% ^
  config.py ^
  notifier.py ^
  forex_utils.py ^
  forex_exposure_manager.py ^
  eur_usd_dashboard.py ^
  gbp_usd_dashboard.py ^
  aud_usd_dashboard.py ^
  forex_outcome_tracker.py ^
  forex_monitor.py ^
  %HOST%:%REMOTE_DIR%/

echo [3/4] Installing service...
scp -i %KEY% forex-monitor.service %HOST%:/tmp/forex-monitor.service
ssh -i %KEY% %HOST% "sudo mv /tmp/forex-monitor.service /etc/systemd/system/forex-monitor.service && sudo systemctl daemon-reload && sudo systemctl enable forex-monitor && sudo systemctl restart forex-monitor"

echo [4/4] Checking service status...
ssh -i %KEY% %HOST% "sudo systemctl status forex-monitor --no-pager -l"

echo Done. Check your phone for the startup push notification.
pause
