#!/bin/bash
# Sends Slack Attendance Bot result directly to Telegram after each run.

TIMESTAMP=$(date "+%d.%m.%Y %H:%M %Z")

# Load credentials from .env (never commit these)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/.env" ]; then
  # shellcheck disable=SC1091
  set -a; source "${SCRIPT_DIR}/.env"; set +a
fi
BOT_TOKEN="${TELEGRAM_BOT_TOKEN}"
CHAT_ID="${TELEGRAM_CHAT_ID}"

# Extract final state from today's journald logs
LOGS=$(sudo journalctl -u slack-attendance-bot-docker.service --since "today" --no-pager -q 2>/dev/null)

STATE=$(echo "$LOGS" \
  | grep "STATE=RUN_COMPLETED\|STATE=RUN_FAILED" \
  | tail -1 \
  | grep -oP 'STATE=RUN_\K\w+')

# Check if re-authentication happened this run
REAUTH=$(echo "$LOGS" | grep -c "STATE=SESSION_SAVED" || true)

case "$STATE" in
  COMPLETED*)
    RESULT=$(echo "$LOGS" | grep "STATE=RUN_COMPLETED" | tail -1 | grep -oP 'RUN_COMPLETED \| \K\w+')
    # Extract what Mia actually said (if bot logged a rejection)
    MIA_TEXT=$(echo "$LOGS" | grep "STATE=MIA_REJECTION" | tail -1 | grep -oP 'MIA_REJECTION \| \K.+' | head -c 120)
    REAUTH_SUFFIX=""
    [ "$REAUTH" -gt 0 ] && REAUTH_SUFFIX=$'\n'"⚠️ Hinweis: Slack-Session wurde neu authentifiziert."
    if [ "$RESULT" = "SURVEY_CLOSED" ]; then
      MIA_DETAIL=""
      [ -n "$MIA_TEXT" ] && MIA_DETAIL=$'\n'"💬 Mia: ${MIA_TEXT}"
      MESSAGE="⚠️ Slack Attendance: Zeitfenster geschlossen ($TIMESTAMP)${MIA_DETAIL}${REAUTH_SUFFIX}"
    else
      MESSAGE="✅ Slack Attendance: ${RESULT:-PRESENT_RECORDED} ($TIMESTAMP)${REAUTH_SUFFIX}"
    fi
    ;;
  FAILED*)
    REASON=$(echo "$LOGS" | grep "STATE=RUN_FAILED" | tail -1 | grep -oP 'RUN_FAILED \| \K\w+')
    if [ "$REAUTH" -gt 0 ]; then
      MESSAGE="❌ Slack Attendance FAILED: ${REASON:-UNKNOWN} ($TIMESTAMP)
⚠️ Hinweis: Slack-Session wurde neu authentifiziert."
    else
      MESSAGE="❌ Slack Attendance FAILED: ${REASON:-UNKNOWN} ($TIMESTAMP)"
    fi
    ;;
  *)
    MESSAGE="⚠️ Slack Attendance: Status unbekannt ($TIMESTAMP)"
    ;;
esac

curl -s "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
  -d "chat_id=${CHAT_ID}" \
  --data-urlencode "text=${MESSAGE}" \
  > /dev/null
