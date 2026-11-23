#!/usr/bin/env bash
# デスクトップにログインしたとき、ダッシュボードを Chromium の全画面表示（キオスク表示）で開く。
# deploy/install.sh が ~/.config/autostart/env-kiosk.desktop から呼ぶように設定する。
set -u

URL="${KIOSK_URL:-http://127.0.0.1:8080/}"

# env-dashboard が起動するまで待つ（最大 2 分）
for _ in $(seq 1 120); do
  curl -fs -o /dev/null "$URL" && break
  sleep 1
done

# Raspberry Pi OS のバージョンで名前が違う
BROWSER="$(command -v chromium || command -v chromium-browser || true)"
if [ -z "$BROWSER" ]; then
  echo "Chromium が見つからない" >&2
  exit 1
fi

# 停電などで落ちたあとに「ページを復元しますか」を出さない
PREFS="$HOME/.config/chromium/Default/Preferences"
if [ -f "$PREFS" ]; then
  sed -i 's/"exited_cleanly":false/"exited_cleanly":true/; s/"exit_type":"[^"]*"/"exit_type":"Normal"/' "$PREFS"
fi

exec "$BROWSER" \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --no-first-run \
  --password-store=basic \
  --check-for-update-interval=31536000 \
  "$URL"
