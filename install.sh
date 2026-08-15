#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then exec sudo bash "$0" "$@"; fi
if ! command -v apt-get >/dev/null; then echo "Ubuntu/Debian with apt-get required" >&2; exit 1; fi
apt-get update
apt-get install -y python3.12 python3.12-venv git ca-certificates
id -u starzygiftwatch >/dev/null 2>&1 || useradd --system --home /opt/starzygiftwatch --shell /usr/sbin/nologin starzygiftwatch
mkdir -p /opt/starzygiftwatch/data
if [[ ! -d /opt/starzygiftwatch/.git ]]; then
  git clone https://github.com/rezajavadi995/StarzYGiftWatch.git /opt/starzygiftwatch
else
  git -C /opt/starzygiftwatch pull --ff-only
fi
chown -R starzygiftwatch:starzygiftwatch /opt/starzygiftwatch
python3.12 -m venv /opt/starzygiftwatch/.venv
/opt/starzygiftwatch/.venv/bin/pip install -r /opt/starzygiftwatch/requirements.txt
if [[ ! -f /etc/starzygiftwatch.env ]]; then
  install -m 600 -o root -g starzygiftwatch /dev/null /etc/starzygiftwatch.env
  cat > /etc/starzygiftwatch.env <<'ENV'
BOT_TOKEN=
ADMIN_ID=
DATABASE_PATH=/opt/starzygiftwatch/data/watch.db
LOG_LEVEL=INFO
ENV
fi
chown root:starzygiftwatch /etc/starzygiftwatch.env
chmod 600 /etc/starzygiftwatch.env
cat > /etc/systemd/system/starzygiftwatch.service <<'UNIT'
[Unit]
Description=StarzYGiftWatch Telegram Gift watcher
After=network-online.target
Wants=network-online.target
ConditionPathExists=/etc/starzygiftwatch.env

[Service]
Type=simple
User=starzygiftwatch
Group=starzygiftwatch
WorkingDirectory=/opt/starzygiftwatch
EnvironmentFile=/etc/starzygiftwatch.env
ExecStart=/opt/starzygiftwatch/.venv/bin/python -m starzygiftwatch.main
Restart=on-failure
RestartSec=10
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=/opt/starzygiftwatch /etc/starzygiftwatch.env

[Install]
WantedBy=multi-user.target
UNIT
cat > /usr/local/bin/watch <<'WRAP'
#!/usr/bin/env bash
if [[ $# -gt 0 ]]; then exec /usr/bin/watch "$@"; fi
exec /opt/starzygiftwatch/.venv/bin/python -m starzygiftwatch.cli
WRAP
chmod +x /usr/local/bin/watch
bash -n /opt/starzygiftwatch/install.sh
/opt/starzygiftwatch/.venv/bin/python -m compileall -q /opt/starzygiftwatch/starzygiftwatch
systemctl daemon-reload || true
echo "StarzYGiftWatch installed. Configure it by running: watch"
