# CLAUDE.md — Indicator AI Companion

把 Seeed SenseCAP Indicator D1(ESP32-S3 + 4″ 480×480 触摸屏)做成 **Claude Code 物理状态屏(HUD)+ AI 桌面伴侣**。完整说明、上手与故障排查见 README.md。

## 架构
- `firmware/` — ESPHome + LVGL 全屏 UI。三个 API action:
  - `show_card(status,mood,title,body,footer)` — 焦点 session 的详情卡。`status` 是语言无关语义键(run/think/wait/done/ready/online),驱动配色;`mood/title/body` 是本地化文案。
  - `set_metrics(metrics)` — 右下角会话指标(context/5h limit)。
  - `set_sessions(count,focus,sN_status,sN_label)` — 顶部多 session 图标条(最多 4 槽)。每槽是 **Claude 官方星芒 mark**(`images/claude/`,取自 `claude-logo.svg`),固定品牌色 `0xD97757`;run/think 时呼吸+满亮、其余静止变暗;状态色体现在图标下方项目名文字上;`focus` 标记详情卡当前所示槽位(下方高亮条)。
  - 触摸:每槽是可点 `button`,点击 publish `selected_session`(值=tap_seq*4+槽位,自增以强制上报),bridge 据此切换焦点。**触摸只在设备↔bridge 本地闭环、不回传 Claude Code**(内置 AskUserQuestion 无法被 hook 注入答案;要双向作答得另起自建 MCP 工具)。
- `bridge/` — Python daemon(Docker 常驻)。按 `session_id` 维护多 session 注册表(`app.py` SessionState),渲染图标条 + 焦点详情卡;焦点默认跟随最近活跃、手点某槽则钉住(PIN_TTL);`session-end` / SESSION_TTL 过期清理。仅无活跃 session 时调 OpenAI 兼容端点出伴侣卡;收 statusLine 指标。文案语言由 `BRIDGE_LANG`(zh/en)控制,字符串表在 `indicator_bridge/i18n.py`。
- `hooks/` — `push-event.sh`(hook→bridge,fire-and-forget)、`statusline-wrapper.sh`(包装 claude-hud + 推 metrics)。订阅 SessionStart/UserPromptSubmit/PreToolUse/Notification/Stop/**SessionEnd**。

## 常用命令
```bash
# 校验 + 刷固件(USB 最稳;改了 show_card 参数后必须重刷)
uv run --with esphome esphome config firmware/indicator-companion.yaml
uv run --with esphome esphome upload firmware/indicator-companion.yaml --device /dev/cu.usbserial-XXXX

# bridge(Docker)
docker compose up -d --build
docker logs indicator-bridge -f
```

## 注意
- 改 `show_card` / `set_sessions` 参数后,设备与 bridge 必须同步:重刷固件 + 重建容器。
- 改图标形状/呼吸:`uv run --with cairosvg --with pillow firmware/images/gen-claude.py` 重生成帧。
- `esphome config` 只校验 schema;lambda(配色/动画分支)正确性要 `esphome compile`(本仓库已验证可编译)。LVGL opacity 静态值要用 `%`(如 `100%`),整数 0–255 只能在 lambda 里返回。
- 真实凭据在 gitignore 的 `firmware/secrets.yaml` / `bridge/.env`,不入库;固件 `api_key` 必须 == bridge `INDICATOR_NOISE_PSK`。
