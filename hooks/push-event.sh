#!/usr/bin/env bash
# Agent hook -> Indicator bridge 转发器。
# 用法(在 hook command 里): push-event.sh <event-name> [source]
# 同步读完 stdin 的 hook JSON,包上 cwd/source 元数据,然后把 POST 丢到后台,立即返回。
# Codex 当前没有 SessionEnd hook,所以这里在宿主侧盯住 Codex 父进程,退出时补发 session-end。
set -euo pipefail

EVENT="${1:?usage: push-event.sh <event-name>}"
SOURCE="${2:-}"
PORT="${INDICATOR_BRIDGE_PORT:-9527}"
HOST="${INDICATOR_BRIDGE_HOST:-127.0.0.1}"
AGENT_PID="${PPID:-}"

json_string() {
  # Inputs here are short metadata strings(PWD/event/source), not arbitrary JSON.
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

session_key() {
  tr '\n' ' ' < "$1" | sed -nE 's/.*"(session_id|thread_id|conversation_id|assigned_thread_id)"[[:space:]]*:[[:space:]]*"([^"]+)".*/\2/p' | head -n 1
}

safe_key() {
  printf '%s' "$1" | tr -c 'A-Za-z0-9_.-' '_'
}

start_codex_exit_watcher() {
  [ "$SOURCE" = "codex" ] || return 0
  [ -n "$AGENT_PID" ] || return 0

  local sid
  sid="$(session_key "$RAW")"
  [ -n "$sid" ] || sid="default"

  local dir
  dir="${TMPDIR:-/tmp}/indicator-codex-watch-${AGENT_PID}-$(safe_key "$sid")"
  if mkdir "$dir" 2>/dev/null; then
    cp "$BODY" "$dir/body.json"
    (
      while kill -0 "$AGENT_PID" 2>/dev/null; do
        sleep 2
      done
      curl -s -m 1 -X POST "http://${HOST}:${PORT}/hook/session-end" \
        -H 'Content-Type: application/json' --data-binary @"$dir/body.json" >/dev/null 2>&1
      rm -rf "$dir"
    ) &
  fi
}

RAW="$(mktemp -t indhook_raw)"
BODY="$(mktemp -t indhook_body)"
cat > "$RAW"

if [ ! -s "$RAW" ]; then
  printf '{}' > "$RAW"
fi

{
  printf '{"cwd":"%s","hook_event":"%s","source":"%s","agent_pid":"%s","payload":' \
    "$(json_string "${PWD:-}")" \
    "$(json_string "$EVENT")" \
    "$(json_string "$SOURCE")" \
    "$(json_string "$AGENT_PID")"
  cat "$RAW"
  printf '}\n'
} > "$BODY"

start_codex_exit_watcher

(
  curl -s -m 1 -X POST "http://${HOST}:${PORT}/hook/${EVENT}" \
    -H 'Content-Type: application/json' --data-binary @"$BODY" >/dev/null 2>&1
  rm -f "$RAW" "$BODY"
) &

exit 0
