#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL=${STARZYGIFTWATCH_REPO_URL:-https://github.com/rezajavadi995/StarzYGiftWatch.git}
APP_DIR=${STARZYGIFTWATCH_APP_DIR:-/opt/starzygiftwatch}
ENV_FILE=${STARZYGIFTWATCH_ENV_FILE:-/etc/starzygiftwatch.env}
SERVICE_FILE=${STARZYGIFTWATCH_SERVICE_FILE:-/etc/systemd/system/starzygiftwatch.service}
WATCH_WRAPPER=${STARZYGIFTWATCH_WATCH_WRAPPER:-/usr/local/bin/watch}
SYSTEM_WATCH=${STARZYGIFTWATCH_SYSTEM_WATCH:-/usr/bin/watch}
SERVICE_USER=${STARZYGIFTWATCH_SERVICE_USER:-starzygiftwatch}
PYTHON_BIN=${STARZYGIFTWATCH_PYTHON:-python3.12}
SKIP_APT=${STARZYGIFTWATCH_SKIP_APT:-0}
SKIP_USER=${STARZYGIFTWATCH_SKIP_USER:-0}
SKIP_SYSTEMD=${STARZYGIFTWATCH_SKIP_SYSTEMD:-0}
SKIP_PIP=${STARZYGIFTWATCH_SKIP_PIP:-0}
VENV_ARGS=${STARZYGIFTWATCH_VENV_ARGS:-}

stage="initialization"
trap 'echo "ERROR: install failed during ${stage}" >&2' ERR

log() { printf '\n==> %s\n' "$*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }
run() { "$@" || fail "command failed: $*"; }

is_dir_empty() {
  [[ -d "$1" ]] || return 1
  [[ -z "$(find "$1" -mindepth 1 -maxdepth 1 -print -quit)" ]]
}

is_interrupted_empty_scaffold() {
  [[ -d "$APP_DIR" && ! -e "$APP_DIR/.git" ]] || return 1
  [[ -d "$APP_DIR/data" ]] || return 1
  is_dir_empty "$APP_DIR/data" || return 1
  local entry
  while IFS= read -r entry; do
    [[ "${entry##*/}" == "data" ]] || return 1
  done < <(find "$APP_DIR" -mindepth 1 -maxdepth 1 -print)
}

normalize_remote() {
  local remote=${1%.git}
  remote=${remote#file://}
  printf '%s' "$remote"
}

expected_repo_remote() {
  local remote expected
  remote=$(normalize_remote "$1")
  expected=$(normalize_remote "$REPO_URL")
  [[ "$remote" == "$expected" || \
     "$remote" == "https://github.com/rezajavadi995/StarzYGiftWatch" || \
     "$remote" == "git@github.com:rezajavadi995/StarzYGiftWatch" || \
     "$remote" == "ssh://git@github.com/rezajavadi995/StarzYGiftWatch" ]]
}

validate_repository() {
  [[ -d "$APP_DIR/.git" ]] || fail "$APP_DIR is not a Git repository"
  local origin
  origin=$(git -C "$APP_DIR" remote get-url origin 2>/dev/null) || fail "$APP_DIR has no origin remote"
  expected_repo_remote "$origin" || fail "$APP_DIR origin remote is not StarzYGiftWatch: $origin"
}

acquire_repository() {
  if [[ ! -e "$APP_DIR" ]]; then
    log "Cloning StarzYGiftWatch repository"
    run git clone "$REPO_URL" "$APP_DIR"
  elif is_dir_empty "$APP_DIR"; then
    log "Cloning StarzYGiftWatch repository into existing empty directory"
    run git clone "$REPO_URL" "$APP_DIR"
  elif [[ -d "$APP_DIR/.git" ]]; then
    log "Updating existing StarzYGiftWatch repository"
    validate_repository
    if [[ -n "$(git -C "$APP_DIR" status --porcelain)" ]]; then
      fail "$APP_DIR contains local Git changes; commit/stash/remove them before reinstalling"
    fi
    run git -C "$APP_DIR" fetch --prune origin
    local branch target
    branch=$(git -C "$APP_DIR" branch --show-current)
    [[ -n "$branch" ]] || fail "$APP_DIR is in detached HEAD state; manual inspection required"
    if git -C "$APP_DIR" rev-parse --verify --quiet "@{upstream}" >/dev/null; then
      target="@{upstream}"
    else
      target="origin/$branch"
      git -C "$APP_DIR" rev-parse --verify --quiet "$target" >/dev/null || target="origin/main"
    fi
    run git -C "$APP_DIR" merge --ff-only "$target"
  elif is_interrupted_empty_scaffold; then
    log "Recovering empty installer-created scaffold before cloning"
    run rmdir "$APP_DIR/data"
    run git clone "$REPO_URL" "$APP_DIR"
  else
    fail "$APP_DIR exists but is not a valid StarzYGiftWatch Git repository. Inspect it manually; it was not deleted. If it only contains empty installer scaffolding, remove that scaffolding and rerun."
  fi
  validate_repository
}

stage="privilege check"
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  exec sudo env \
    "STARZYGIFTWATCH_REPO_URL=$REPO_URL" \
    "STARZYGIFTWATCH_APP_DIR=$APP_DIR" \
    "STARZYGIFTWATCH_ENV_FILE=$ENV_FILE" \
    "STARZYGIFTWATCH_SERVICE_FILE=$SERVICE_FILE" \
    "STARZYGIFTWATCH_WATCH_WRAPPER=$WATCH_WRAPPER" \
    "STARZYGIFTWATCH_SYSTEM_WATCH=$SYSTEM_WATCH" \
    "STARZYGIFTWATCH_SERVICE_USER=$SERVICE_USER" \
    "STARZYGIFTWATCH_PYTHON=$PYTHON_BIN" \
    "STARZYGIFTWATCH_SKIP_APT=$SKIP_APT" \
    "STARZYGIFTWATCH_SKIP_USER=$SKIP_USER" \
    "STARZYGIFTWATCH_SKIP_SYSTEMD=$SKIP_SYSTEMD" \
    "STARZYGIFTWATCH_SKIP_PIP=$SKIP_PIP" \
    "STARZYGIFTWATCH_VENV_ARGS=$VENV_ARGS" \
    bash "$0" "$@"
fi

stage="platform/package checks"
if [[ "$SKIP_APT" != "1" ]] && ! command -v apt-get >/dev/null; then fail "Ubuntu/Debian with apt-get required"; fi

stage="install OS packages"
if [[ "$SKIP_APT" != "1" ]]; then
  run apt-get update
  run apt-get install -y python3.12 python3.12-venv git ca-certificates
fi
run command -v git
run command -v "$PYTHON_BIN"

stage="create service user"
if [[ "$SKIP_USER" != "1" ]] && ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
  run useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
fi

stage="acquire/update repository"
acquire_repository

stage="create runtime directories"
run mkdir -p "$APP_DIR/data"
if [[ "$SKIP_USER" != "1" ]]; then
  run chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/data"
fi

stage="create/update virtualenv"
if [[ -n "$VENV_ARGS" ]]; then
  # shellcheck disable=SC2086 # intentional operator-provided venv flags, e.g. --system-site-packages in tests
  run "$PYTHON_BIN" -m venv $VENV_ARGS "$APP_DIR/.venv"
else
  run "$PYTHON_BIN" -m venv "$APP_DIR/.venv"
fi

stage="install dependencies"
if [[ "$SKIP_PIP" != "1" ]]; then
  run "$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
  run "$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"
fi

stage="create environment file"
if [[ ! -f "$ENV_FILE" ]]; then
  run install -m 600 -o root -g "$SERVICE_USER" /dev/null "$ENV_FILE"
  cat > "$ENV_FILE" <<ENV
BOT_TOKEN=
ADMIN_ID=
DATABASE_PATH=$APP_DIR/data/watch.db
LOG_LEVEL=INFO
ENV
fi
if [[ "$SKIP_USER" != "1" ]]; then
  run chown root:"$SERVICE_USER" "$ENV_FILE"
fi
run chmod 600 "$ENV_FILE"

stage="install systemd unit"
run mkdir -p "$(dirname "$SERVICE_FILE")"
cat > "$SERVICE_FILE" <<UNIT
[Unit]
Description=StarzYGiftWatch Telegram Gift watcher
After=network-online.target
Wants=network-online.target
ConditionPathExists=$ENV_FILE

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$APP_DIR/.venv/bin/python -m starzygiftwatch.main
Restart=on-failure
RestartSec=10
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=$APP_DIR $ENV_FILE

[Install]
WantedBy=multi-user.target
UNIT

stage="install CLI wrapper"
run mkdir -p "$(dirname "$WATCH_WRAPPER")"
cat > "$WATCH_WRAPPER" <<WRAP
#!/usr/bin/env bash
if [[ \$# -gt 0 ]]; then exec "$SYSTEM_WATCH" "\$@"; fi
exec "$APP_DIR/.venv/bin/python" -m starzygiftwatch.cli
WRAP
run chmod +x "$WATCH_WRAPPER"

stage="validation checks"
validate_repository
run test -d "$APP_DIR/data"
run test -x "$APP_DIR/.venv/bin/python"
run "$APP_DIR/.venv/bin/python" --version
run "$APP_DIR/.venv/bin/python" -m compileall -q "$APP_DIR/starzygiftwatch"
run bash -n "$APP_DIR/install.sh"
run bash -n "$WATCH_WRAPPER"
run env PYTHONPATH="$APP_DIR" "$APP_DIR/.venv/bin/python" -c 'import starzygiftwatch.config, starzygiftwatch.db, starzygiftwatch.cli'
if command -v systemd-analyze >/dev/null && [[ "$SKIP_SYSTEMD" != "1" ]]; then
  run systemd-analyze verify "$SERVICE_FILE"
fi

stage="reload systemd"
if [[ "$SKIP_SYSTEMD" != "1" ]]; then
  run systemctl daemon-reload
fi

stage="complete"
echo "StarzYGiftWatch installed. Configure it by running: watch"
