#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/opt/starzygiftwatch
REPO_URL=https://github.com/rezajavadi995/StarzYGiftWatch.git
SERVICE_USER=starzygiftwatch

is_empty_dir() {
  [[ -d "$1" ]] && [[ -z "$(find "$1" -mindepth 1 -maxdepth 1 -print -quit)" ]]
}

is_empty_interrupted_scaffold() {
  [[ -d "$APP_DIR" && ! -e "$APP_DIR/.git" && -d "$APP_DIR/data" ]] || return 1
  is_empty_dir "$APP_DIR/data" || return 1
  local entry
  while IFS= read -r entry; do
    [[ "${entry##*/}" == "data" ]] || return 1
  done < <(find "$APP_DIR" -mindepth 1 -maxdepth 1 -print)
}

acquire_repo() {
  if [[ -d "$APP_DIR/.git" ]]; then
    git -C "$APP_DIR" pull --ff-only
  elif [[ ! -e "$APP_DIR" ]] || is_empty_dir "$APP_DIR"; then
    git clone "$REPO_URL" "$APP_DIR"
  elif is_empty_interrupted_scaffold; then
    rmdir "$APP_DIR/data"
    git clone "$REPO_URL" "$APP_DIR"
  else
    echo "$APP_DIR exists but is not a StarzYGiftWatch Git checkout; inspect it manually before installing." >&2
    exit 1
  fi
}

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then exec sudo bash "$0" "$@"; fi
if ! command -v apt-get >/dev/null; then echo "Ubuntu/Debian with apt-get required" >&2; exit 1; fi
apt-get update
apt-get install -y python3.12 python3.12-venv git ca-certificates
id -u "$SERVICE_USER" >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
acquire_repo
mkdir -p "$APP_DIR/data"
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"
python3.12 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
if [[ ! -f /etc/starzygiftwatch.env ]]; then
  install -m 600 -o root -g "$SERVICE_USER" /dev/null /etc/starzygiftwatch.env
  cat > /etc/starzygiftwatch.env <<'ENV'
BOT_TOKEN=
ADMIN_ID=
DATABASE_PATH=/opt/starzygiftwatch/data/watch.db
LOG_LEVEL=INFO
ENV
fi
chown root:"$SERVICE_USER" /etc/starzygiftwatch.env
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
cd /opt/starzygiftwatch
exec /opt/starzygiftwatch/.venv/bin/python -m starzygiftwatch.cli
WRAP
chmod +x /usr/local/bin/watch
bash -n "$APP_DIR/install.sh"
"$APP_DIR/.venv/bin/python" -m compileall -q "$APP_DIR/starzygiftwatch"
systemctl daemon-reload
echo "StarzYGiftWatch installed. Configure it by running: watch"
