#!/usr/bin/env bash
# Claude Code statusLine wrapper:
#   1. 保留原 claude-hud 状态行显示(透传 stdin,输出其 stdout)
#   2. 把 statusLine JSON(含 context_window / rate_limits)后台推给 Indicator bridge
# 配置: settings.json 的 statusLine.command 指向本脚本。
input=$(cat)

# 后台推送会话指标给 bridge(发了就走,绝不拖慢状态行)
PORT="${INDICATOR_BRIDGE_PORT:-9527}"
F="$(mktemp -t indmetric)"
printf '%s' "$input" > "$F"
( curl -s -m1 -X POST "http://127.0.0.1:${PORT}/metrics" \
    -H 'Content-Type: application/json' --data-binary @"$F" >/dev/null 2>&1; rm -f "$F" ) &

# 前台:原 claude-hud statusline(动态定位最新插件版本)
plugin_dir=$(ls -d "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/plugins/cache/claude-hud/claude-hud/*/ 2>/dev/null \
  | awk -F/ '{ print $(NF-1) "\t" $(0) }' | sort -t. -k1,1n -k2,2n -k3,3n -k4,4n | tail -1 | cut -f2-)
BUN="$(command -v bun || echo "$HOME/.bun/bin/bun")"
printf '%s' "$input" | exec "$BUN" --env-file /dev/null "${plugin_dir}src/index.ts"
