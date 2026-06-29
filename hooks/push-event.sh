#!/usr/bin/env bash
# Claude Code hook -> Indicator bridge 转发器。
# 用法(在 settings.json 的 hook command 里): push-event.sh <event-name>
# 同步读完 stdin 的 hook JSON,然后把 POST 丢到后台,立即返回——绝不阻塞 Claude Code。
set -euo pipefail

EVENT="${1:?usage: push-event.sh <event-name>}"
PORT="${INDICATOR_BRIDGE_PORT:-9527}"
HOST="${INDICATOR_BRIDGE_HOST:-127.0.0.1}"

F="$(mktemp -t indhook)"
cat > "$F"

(
  curl -s -m 1 -X POST "http://${HOST}:${PORT}/hook/${EVENT}" \
    -H 'Content-Type: application/json' --data-binary @"$F" >/dev/null 2>&1
  rm -f "$F"
) &

exit 0
