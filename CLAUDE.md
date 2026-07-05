# CLAUDE.md — Indicator AI Companion

把 Seeed SenseCAP Indicator D1(ESP32-S3 + 4″ 480×480 触摸屏)做成 **Claude Code / Codex 物理状态屏(HUD)+ AI 桌面伴侣**。完整说明、上手与故障排查见 README.md。

## 架构
- `firmware/` — ESPHome + LVGL 全屏 UI。三个 API action:
  - `show_card(status,mood,title,body,footer)` — 焦点 session 的详情卡。`status` 是语言无关语义键(run/think/wait/done/ready/online),驱动配色;`mood/title/body` 是本地化文案。
  - `set_metrics(metrics)` — 右下角会话指标(context/5h limit)。
  - `set_sessions(count,focus,sN_status,sN_label,sN_provider)` — 顶部多 session 图标条(最多 4 槽)。每槽按 provider 显示图标:Claude 用 `images/claude/` 星芒, Codex 用 `images/codex/` code mark(`gen-codex.py` 生成);run/think 时呼吸+满亮、其余静止变暗;状态色体现在图标下方项目名文字上;`focus` 标记详情卡当前所示槽位(下方高亮条)。
  - `set_screensaver(active,line,hint)` — 全屏屏保层(置顶覆盖)。`line` 是俏皮话(= 伴侣卡 `body`,与待机同一条 LLM 生成路径)、`hint` 是唤醒提示。进/出走 `enter_saver`/`exit_saver` 脚本(翻转 `saver_active`、复位眼睛、显隐 saver);**已在屏保中再收 active=true 只更新 line 文案、不重置眼睛**(供屏保期间换句)。
  - **眼睛(待机 `standby_eyes` 小 + 屏保 saver 大)已用 LVGL 图元现画**,不再是 raster 帧:每只眼 = 外圈渐变虹膜 + 中/内亮圈(伪径向)+ 深瞳孔 + 白高光的同心 `obj` 圆,上下两条 bg 色矩形眼睑靠改高度眨眼。分辨率无关、任意放大都清晰、几乎零 flash(删掉 17 帧 raster 省 ~402KB)。动画由单个 `interval: 40ms` lambda 驱动:视线缓动滑移 + 微抖动(自然)、眨眼三角波;`saver_active`/`standby_active` 两个 global 各自门控大/小眼睛,`gaze` 单位 native ±7(大眼 ×20/7)。改眼睛=直接调 widget 里的几何/配色数字,不用重生成任何图。
  - 触摸:每槽是可点 `button`,点击 publish `selected_session`(值=tap_seq*4+槽位,自增以强制上报),bridge 据此切换焦点。屏保层点任意处本地隐藏并 publish `screensaver_wake`(同样自增)。**物理按钮 GPIO38(`refresh_button`)不再本地切换,只经 binary_sensor 上报;由 bridge `on_button` 智能切换屏保(待机→睡 / 屏保→醒),控制权收归 bridge 一处。**触摸只在设备↔bridge 本地闭环、不回传 agent**(要双向作答得另起自建 MCP 工具)。
- `bridge/` — Python daemon(Docker 常驻)。按 `session_id` / `thread_id` 维护多 session 注册表(`app.py` SessionState),渲染图标条 + 焦点详情卡;焦点默认跟随最近活跃、手点某槽则钉住(PIN_TTL);Claude `session-end` 即时清理,Codex 由 `push-event.sh` 盯父进程退出后补发 `session-end`,`SESSION_TTL` 兜底过期清理。仅无活跃 session 时调 OpenAI 兼容端点出伴侣卡(`companion.generate()` → 完整卡);收 statusLine/usage 指标。距最后活动超过 `SCREENSAVER_SECONDS`(默认 300s)且无 needs-you 告警时进屏保,**屏保俏皮话 = 伴侣卡 `body`(统一一条生成路径,无独立 `generate_line`)**,无卡回退 `i18n` 内置文案;按钮即时进屏保后后台 `_refresh_saver_line()` 现编一句。任何 hook 事件或点屏唤醒退出。文案语言由 `BRIDGE_LANG`(zh/en)控制,字符串表在 `indicator_bridge/i18n.py`。
- `hooks/` — `push-event.sh`(hook→bridge,fire-and-forget;包上 `cwd/source/agent_pid/payload`;Codex 无 SessionEnd 时在宿主侧 watch 父进程并补发 `session-end`)、`settings.snippet.json`(Claude)、`codex-hooks.snippet.json`(Codex)、`statusline-wrapper.sh`(Claude-only,包装 claude-hud + 推 metrics)。订阅 SessionStart/UserPromptSubmit/PreToolUse/**PostToolUse**/Notification(Claude)/PermissionRequest(Codex)/Stop/SessionEnd(Claude)。**PostToolUse(`post-tool`)是"用户确认权限/回答提问后最先触发的 hook",bridge 用它把 wait 态及时清成 think**(仅当前为 wait 才出卡,否则不抢镜),否则 wait 要拖到下个 pre-tool/stop 才更新。

## 常用命令
```bash
# 校验 + 刷固件(USB 最稳;改了 show_card 参数后必须重刷)
uv run --with esphome esphome config firmware/indicator-companion.yaml
uv run --with esphome esphome upload firmware/indicator-companion.yaml --device /dev/cu.usbserial-XXXX

# bridge(Docker)
docker compose up -d --build
docker logs indicator-bridge -f

# demo 模式:向运行中的 bridge 回放脚本化假事件流(免真实 agent,演示/录屏用)
cd bridge && uv run indicator-bridge-demo   # --speed 2 加速 / --loop 循环
```

## 注意
- 改 `show_card` / `set_sessions` 参数后,设备与 bridge 必须同步:重刷固件 + 重建容器。
- 改 Codex 图标形状/呼吸:`uv run python firmware/images/gen-codex.py` 重生成帧。Claude 图标形状:`uv run --with cairosvg --with pillow firmware/images/gen-claude.py`。
- `esphome config` 只校验 schema;lambda(配色/动画分支)正确性要 `esphome compile`(本仓库已验证可编译)。LVGL opacity 静态值要用 `%`(如 `100%`),整数 0–255 只能在 lambda 里返回。
- 真实凭据在 gitignore 的 `firmware/secrets.yaml` / `bridge/.env`,不入库;固件 `api_key` 必须 == bridge `INDICATOR_NOISE_PSK`。
