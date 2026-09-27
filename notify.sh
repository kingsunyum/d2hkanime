#!/usr/bin/env bash
# 发送 Telegram 通知。配置见 ~/.config/anime-notify.env
# 用法: ./notify.sh "消息内容"
set -u
CONF="${ANIME_NOTIFY_CONF:-$HOME/.config/anime-notify.env}"
MSG="${1:-}"
[[ -n "$MSG" ]] || { echo "notify: 空消息" >&2; exit 0; }

if [[ ! -f "$CONF" ]]; then
  echo "notify: 未配置 $CONF，跳过" >&2; exit 2
fi
# shellcheck disable=SC1090
source "$CONF"
# 通知总开关：NOTIFY_ENABLED=0/false/no/off 时静默跳过（默认开）
: "${NOTIFY_ENABLED:=1}"
case "$(printf '%s' "$NOTIFY_ENABLED" | tr '[:upper:]' '[:lower:]')" in
  0|false|no|off) echo "notify: 通知已关闭（NOTIFY_ENABLED=$NOTIFY_ENABLED），跳过" >&2; exit 0 ;;
esac
: "${TELEGRAM_BOT_TOKEN:=}"
: "${TELEGRAM_CHAT_ID:=}"
if [[ -z "$TELEGRAM_BOT_TOKEN" || -z "$TELEGRAM_CHAT_ID" ]]; then
  echo "notify: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 未设置（见 $CONF）" >&2; exit 2
fi

extra=()
[[ -n "${TELEGRAM_PROXY:-}" ]] && extra=(-x "$TELEGRAM_PROXY")
resp=$(curl -sS -m 20 "${extra[@]}" \
  --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
  --data-urlencode "text=${MSG}" \
  --data-urlencode "disable_web_page_preview=true" \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" 2>&1)

if [[ "$resp" == *'"ok":true'* ]]; then
  echo "notify: 已发送"
else
  echo "notify: 发送失败 -> ${resp//$TELEGRAM_BOT_TOKEN/***}" >&2
  exit 1
fi
