#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

source_repo="$tmp/source"
mkdir -p "$source_repo"
tar -C "$repo_root" --exclude='.git' --exclude='.venv' --exclude='.pytest_cache' -cf - . | tar -C "$source_repo" -xf -
git -C "$source_repo" init -q
git -C "$source_repo" config user.email test@example.invalid
git -C "$source_repo" config user.name 'Wrapper Test'
git -C "$source_repo" add .
git -C "$source_repo" commit -qm 'source snapshot'

system_watch="$tmp/usr/bin/watch"
mkdir -p "$(dirname "$system_watch")"
cat > "$system_watch" <<'S'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$TMP_OUT"
S
chmod +x "$system_watch"

app="$tmp/opt/starzygiftwatch"
env_file="$tmp/etc/starzygiftwatch.env"
service_file="$tmp/systemd/starzygiftwatch.service"
wrapper="$tmp/usr/local/bin/watch"
mkdir -p "$(dirname "$env_file")" "$(dirname "$service_file")" "$(dirname "$wrapper")"

STARZYGIFTWATCH_REPO_URL="$source_repo" \
STARZYGIFTWATCH_APP_DIR="$app" \
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
bash "$repo_root/install.sh" >/dev/null

export TMP_OUT="$tmp/out"
"$wrapper" -n 1 echo hi
printf '%s\n' '-n' '1' 'echo' 'hi' | diff -u - "$TMP_OUT"
