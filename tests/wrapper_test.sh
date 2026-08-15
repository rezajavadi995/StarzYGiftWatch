#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d)
mkdir -p "$tmp/usr/bin" "$tmp/usr/local/bin" "$tmp/opt/starzygiftwatch/.venv/bin" "$tmp/outside"
cat > "$tmp/usr/bin/watch" <<'S'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$TMP_OUT"
S
chmod +x "$tmp/usr/bin/watch"
cat > "$tmp/opt/starzygiftwatch/.venv/bin/python" <<'S'
#!/usr/bin/env bash
printf 'cwd=%s\n' "$PWD" > "$TMP_OUT"
printf 'args=%s\n' "$*" >> "$TMP_OUT"
S
chmod +x "$tmp/opt/starzygiftwatch/.venv/bin/python"
sed "s#/usr/bin/watch#$tmp/usr/bin/watch#g; s#/opt/starzygiftwatch#$tmp/opt/starzygiftwatch#g" "$repo_root/install.sh" | awk '/^cat > \/usr\/local\/bin\/watch/{flag=1;next}/^WRAP/{flag=0}flag' > "$tmp/usr/local/bin/watch"
chmod +x "$tmp/usr/local/bin/watch"
export TMP_OUT="$tmp/out"
"$tmp/usr/local/bin/watch" -n 1 echo hi
printf '%s\n' '-n' '1' 'echo' 'hi' | diff -u - "$TMP_OUT"
(
  cd "$tmp/outside"
  "$tmp/usr/local/bin/watch"
)
printf 'cwd=%s/opt/starzygiftwatch\nargs=-m starzygiftwatch.cli\n' "$tmp" | diff -u - "$TMP_OUT"
