#!/usr/bin/env bash
set -Eeuo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

source_repo="$tmp/source"
mkdir -p "$source_repo"
tar -C "$repo_root" --exclude='.git' --exclude='.venv' --exclude='.pytest_cache' -cf - . | tar -C "$source_repo" -xf -
git -C "$source_repo" init -q
git -C "$source_repo" config user.email test@example.invalid
git -C "$source_repo" config user.name 'Installer Test'
git -C "$source_repo" add .
git -C "$source_repo" commit -qm 'source snapshot'

run_installer() {
  local app_dir=$1 env_file=$2 service_file=$3 wrapper=$4 system_watch=$5
  STARZYGIFTWATCH_REPO_URL="$source_repo" \
  STARZYGIFTWATCH_APP_DIR="$app_dir" \
  STARZYGIFTWATCH_ENV_FILE="$env_file" \
  STARZYGIFTWATCH_SERVICE_FILE="$service_file" \
  STARZYGIFTWATCH_WATCH_WRAPPER="$wrapper" \
  STARZYGIFTWATCH_SYSTEM_WATCH="$system_watch" \
  STARZYGIFTWATCH_SERVICE_USER="$(id -gn)" \
  STARZYGIFTWATCH_SKIP_APT=1 \
  STARZYGIFTWATCH_SKIP_USER=1 \
  STARZYGIFTWATCH_SKIP_SYSTEMD=1 \
  STARZYGIFTWATCH_SKIP_PIP=1 \
  STARZYGIFTWATCH_VENV_ARGS='--system-site-packages' \
  bash "$repo_root/install.sh"
}

system_watch="$tmp/system-watch"
cat > "$system_watch" <<'WATCH'
#!/usr/bin/env bash
printf 'system-watch:%s\n' "$*"
WATCH
chmod +x "$system_watch"

app="$tmp/opt/starzygiftwatch"
env_file="$tmp/etc/starzygiftwatch.env"
service_file="$tmp/systemd/starzygiftwatch.service"
wrapper="$tmp/bin/watch"
mkdir -p "$(dirname "$env_file")" "$(dirname "$service_file")" "$(dirname "$wrapper")"

run_installer "$app" "$env_file" "$service_file" "$wrapper" "$system_watch"
test -d "$app/.git"
test -d "$app/data"
test -x "$app/.venv/bin/python"
test -f "$env_file"
test -f "$service_file"
if git -C "$app" status --porcelain | grep -q .; then
  echo "installer left cloned repository dirty" >&2
  git -C "$app" status --porcelain >&2
  exit 1
fi

cat > "$env_file" <<ENV
BOT_TOKEN=preserved-secret
ADMIN_ID=123456
DATABASE_PATH=$app/data/custom.db
LOG_LEVEL=DEBUG
ENV
printf 'database' > "$app/data/watch.db"
run_installer "$app" "$env_file" "$service_file" "$wrapper" "$system_watch"
grep -q 'BOT_TOKEN=preserved-secret' "$env_file"
grep -q "DATABASE_PATH=$app/data/custom.db" "$env_file"
grep -q 'database' "$app/data/watch.db"
[[ "$($wrapper -n 1 echo hi)" == 'system-watch:-n 1 echo hi' ]]

interrupted="$tmp/interrupted/starzygiftwatch"
interrupted_env="$tmp/interrupted/etc/starzygiftwatch.env"
interrupted_service="$tmp/interrupted/systemd/starzygiftwatch.service"
interrupted_wrapper="$tmp/interrupted/bin/watch"
mkdir -p "$interrupted/data" "$(dirname "$interrupted_env")" "$(dirname "$interrupted_service")" "$(dirname "$interrupted_wrapper")"
run_installer "$interrupted" "$interrupted_env" "$interrupted_service" "$interrupted_wrapper" "$system_watch"
test -d "$interrupted/.git"
test -d "$interrupted/data"

unexpected="$tmp/unexpected/starzygiftwatch"
unexpected_env="$tmp/unexpected/etc/starzygiftwatch.env"
unexpected_service="$tmp/unexpected/systemd/starzygiftwatch.service"
unexpected_wrapper="$tmp/unexpected/bin/watch"
mkdir -p "$unexpected/data" "$(dirname "$unexpected_env")" "$(dirname "$unexpected_service")" "$(dirname "$unexpected_wrapper")"
printf 'keep me' > "$unexpected/data/watch.db"
if run_installer "$unexpected" "$unexpected_env" "$unexpected_service" "$unexpected_wrapper" "$system_watch" >"$tmp/unexpected.log" 2>&1; then
  echo "installer unexpectedly accepted non-git directory with existing data" >&2
  exit 1
fi
grep -q 'exists but is not a valid StarzYGiftWatch Git repository' "$tmp/unexpected.log"
grep -q 'keep me' "$unexpected/data/watch.db"
