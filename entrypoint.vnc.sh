#!/usr/bin/env bash
set -euo pipefail

cd /app

export DISPLAY="${DISPLAY:-:99}"
export XVFB_WHD="${XVFB_WHD:-1920x1080x24}"
export VNC_PORT="${VNC_PORT:-5900}"
export NOVNC_PORT="${NOVNC_PORT:-6080}"
export VNC_PASSWORD="${VNC_PASSWORD:-change-me}"

Xvfb "$DISPLAY" -screen 0 "$XVFB_WHD" -nolisten tcp &
fluxbox >/tmp/fluxbox.log 2>&1 &
x11vnc -display "$DISPLAY" -rfbport "$VNC_PORT" -forever -shared -passwd "$VNC_PASSWORD" >/tmp/x11vnc.log 2>&1 &
websockify --web=/usr/share/novnc/ "$NOVNC_PORT" "127.0.0.1:${VNC_PORT}" >/tmp/novnc.log 2>&1 &

echo "noVNC ready on :${NOVNC_PORT}"
exec python attendance_bot.py
