#!/usr/bin/env bash
# Pi で計測・ダッシュボード・キオスク表示（と、あれば災危通報の受信）を起動時に自動で動かす。
#
#   deploy/install.sh               # env-station・env-dashboard・キオスク表示
#   deploy/install.sh --with-gnss   # 上に加えて gnss-relay・qzss-dcr（MAX-M10S をつないでから）
#
# 何度実行してもよい。ユニットファイルを直したら、もう一度実行すると反映される。
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
EXPECTED="$HOME/raspberrypi-env-station"
UNIT_DIR="$HOME/.config/systemd/user"
AUTOSTART="$HOME/.config/autostart/env-kiosk.desktop"
WITH_GNSS=false
[ "${1:-}" = "--with-gnss" ] && WITH_GNSS=true

fail() {
  echo "中止: $1" >&2
  exit 1
}

# --- 前提の確認（足りなければ何も変えずに止める）---
[ "$REPO" = "$EXPECTED" ] || fail "リポジトリは $EXPECTED に置く（今は $REPO）。ユニットファイルがこの場所を前提にしている"
[ -f "$REPO/config.toml" ] || fail "config.toml がない。cp config.example.toml config.toml して設置場所を書く"
[ -x "$REPO/.venv/bin/env-station" ] || fail ".venv がない。uv sync --extra pi を実行する"
[ -f "$REPO/web/build/index.html" ] || fail "web/build がない。README の「ダッシュボード」の手順でビルドする"
id -nG | grep -qw i2c || fail "$USER が i2c グループに入っていない。sudo usermod -aG i2c $USER のあと再ログイン"
if $WITH_GNSS; then
  [ -x "$HOME/qzss_dcr/.venv/bin/python" ] || fail "$HOME/qzss_dcr/.venv がない。README の「災危通報の受信」の手順で用意する"
fi

SERVICES=(env-station env-dashboard)
$WITH_GNSS && SERVICES+=(gnss-relay qzss-dcr)

# 手で動かしているものがあると、I2C やポートを取り合う（サービスとして動いているものは除く）
declare -A PATTERNS=(
  [env-station]="/bin/env-station"
  [env-dashboard]="/bin/env-dashboard"
  [gnss-relay]="/bin/gnss-relay"
  [qzss-dcr]="qzss_dcr.py"
)
for name in "${!PATTERNS[@]}"; do
  if pgrep -u "$USER" -f "${PATTERNS[$name]}" >/dev/null \
    && ! systemctl --user is-active -q "$name" 2>/dev/null; then
    echo "注意: 手で起動した $name が動いている。止めてから使う（Ctrl+C）"
  fi
done

# --- systemd のユーザーサービス ---
mkdir -p "$UNIT_DIR" "$REPO/data/qzss_dcr"
for name in "${SERVICES[@]}"; do
  cp "$REPO/deploy/systemd/$name.service" "$UNIT_DIR/"
done
systemctl --user daemon-reload
systemctl --user enable --now "${SERVICES[@]/%/.service}"
systemctl --user restart "${SERVICES[@]/%/.service}"  # 2 回目以降はユニットの変更を反映する

# ログインしていなくても、起動時にユーザーサービスを動かす
if [ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" != "yes" ]; then
  sudo loginctl enable-linger "$USER"
fi

# --- キオスク表示（デスクトップにログインしたとき）---
mkdir -p "$(dirname "$AUTOSTART")"
cat >"$AUTOSTART" <<EOF
[Desktop Entry]
Type=Application
Name=env-station kiosk
Comment=ダッシュボードを全画面で開く
Exec=$REPO/deploy/kiosk/start-kiosk.sh
X-GNOME-Autostart-enabled=true
EOF
chmod +x "$REPO/deploy/kiosk/start-kiosk.sh"

echo
systemctl --user --no-pager --lines=0 status "${SERVICES[@]/%/.service}" || true
echo
echo "完了。次に再起動すると、計測とダッシュボードが動き、デスクトップに全画面で表示される。"
echo "ログ: journalctl --user -u env-station -f"
echo "キオスク表示を抜けるには Alt+F4（キーボードをつないでいるとき）"
