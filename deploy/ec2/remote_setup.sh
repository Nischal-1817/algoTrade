#!/bin/bash
set -euo pipefail
cd /home/ec2-user/algoTrade
tar -xzf /home/ec2-user/algoTrade_deploy.tar.gz
rm -f /home/ec2-user/algoTrade_deploy.tar.gz
source .venv/bin/activate
pip install -q -r requirements.txt
mkdir -p logs data reports
touch logs/live_service.log
append_env() {
  local key="$1"
  local val="$2"
  if ! grep -q "^${key}=" .env 2>/dev/null; then
    echo "" >> .env
    echo "${key}=${val}" >> .env
  fi
}
append_env ENABLE_LIVE_TRADING 1
append_env LIVE_TRADING_CONFIRM I_UNDERSTAND_REAL_MONEY
append_env ALGO_MODE dynamic
append_env ALGO_MAX_SLOTS 4
append_env ALGO_CAPITAL 20000
if [ ! -s data/watchlist.json ]; then
  echo "Building watchlist (Nifty 100 -> top 50, ~5-10 min)..."
  python scripts/build_watchlist.py --universe nifty100 --top 50 --start 2018-01-01
else
  echo "Using existing data/watchlist.json (re-run build_watchlist.py to refresh ranks)"
fi
python scripts/validate_angel_setup.py
python scripts/export_dashboard_snapshot.py
sudo cp deploy/ec2/algo-dashboard.service /etc/systemd/system/algo-dashboard.service
sudo systemctl daemon-reload
sudo systemctl enable algo-dashboard.service
sudo systemctl restart algo-dashboard.service
sudo systemctl restart algo-live.service
sudo systemctl status algo-live.service --no-pager || true
sudo systemctl status algo-dashboard.service --no-pager || true
