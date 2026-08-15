#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d)
mkdir -p "$tmp/usr/bin" "$tmp/usr/local/bin" "$tmp/opt/starzygiftwatch/.venv/bin"
cat > "$tmp/usr/bin/watch" <<'S'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$TMP_OUT"
S
chmod +x "$tmp/usr/bin/watch"
sed "s#/usr/bin/watch#$tmp/usr/bin/watch#g; s#/opt/starzygiftwatch/.venv/bin/python#$tmp/opt/starzygiftwatch/.venv/bin/python#g" "$repo_root/install.sh" | awk '/^cat > \/usr\/local\/bin\/watch/{flag=1;next}/^WRAP/{flag=0}flag' > "$tmp/usr/local/bin/watch"
chmod +x "$tmp/usr/local/bin/watch"
export TMP_OUT="$tmp/out"
"$tmp/usr/local/bin/watch" -n 1 echo hi
printf '%s\n' '-n' '1' 'echo' 'hi' | diff -u - "$TMP_OUT"
