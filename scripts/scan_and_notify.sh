#!/bin/bash
# Daily opportunity scanner + price alerts with Telegram notification
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Credentials come from .env, which is gitignored. Expected keys:
#   TELEGRAM_BOT_TOKEN=<token from BotFather>
#   TELEGRAM_CHAT_ID=<destination chat id>
if [ -f .env ]; then
    set -a
    . ./.env
    set +a
fi

BOT_TOKEN="${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN is not set (add it to .env)}"
CHAT_ID="${TELEGRAM_CHAT_ID:?TELEGRAM_CHAT_ID is not set (add it to .env)}"

send_telegram() {
    local MSG="${1:0:4000}"
    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d chat_id="$CHAT_ID" \
        -d parse_mode="Markdown" \
        --data-urlencode text="$MSG" > /dev/null
}

# Run full opportunity scan (records to DB), capture notification output
OUTPUT=$(.venv/bin/python scripts/run_opportunity_scan.py --quiet 2>/dev/null)
if [ -n "$OUTPUT" ]; then
    send_telegram "$OUTPUT"
fi

# Run price target alerts
ALERTS=$(.venv/bin/python scripts/price_alerts.py --quiet 2>/dev/null)
if [ -n "$ALERTS" ]; then
    send_telegram "$ALERTS"
fi
